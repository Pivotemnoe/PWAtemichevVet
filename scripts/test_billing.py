from __future__ import annotations
import json,os,sys,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI,HTTPException,Request
from app import billing,db,retention
from app.config import get_settings
from app.payments import yookassa
import scripts.test_retention as http_helpers

class BillingTests(unittest.TestCase):
    http=http_helpers.RetentionTests.http
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'db.sqlite'
        db.init_db(self.path);retention.init_schema(self.path);billing.init_schema(self.path)
        self.settings=replace(get_settings(),database_path=self.path,app_base_url='http://127.0.0.1:8080',
            session_secret='fixture-secret-no-live-credentials',smtp_host='',yookassa_shop_id='fixture',yookassa_secret_key='fixture')
        self.now=datetime.now(timezone.utc)
        self.clock=patch.object(billing,'utc_now',side_effect=lambda:self.now);self.clock.start();self.addCleanup(self.clock.stop)
        self.env=patch.dict(os.environ,{'BILLING_SUBSCRIPTIONS_ENABLED':'1','BILLING_AUTORENEW_ENABLED':'1','RETENTION_ENABLED':'0'})
        self.env.start();self.addCleanup(self.env.stop)
        self.user=db.get_or_create_user_by_email(self.path,'owner@mail.ru')
        self.users={self.user['id']:self.user}
        self.calls=[]
        def create(settings,*,payload,idempotence_key):
            self.calls.append((json.loads(json.dumps(payload)),idempotence_key))
            return {'id':'pay-'+idempotence_key,'status':'pending','paid':False,
                'amount':payload['amount'],'metadata':payload['metadata'],
                'confirmation':{'confirmation_url':'https://yookassa.ru/fixture'}}
        self.provider=patch.object(yookassa,'create_subscription_payment',side_effect=create)
        self.mock=self.provider.start();self.addCleanup(self.provider.stop)
        self.app=FastAPI()
        def owner(request:Request):
            try:return self.users[int(request.headers.get('x-test-user','0'))]
            except Exception:raise HTTPException(401,'authorization_required')
        def admin(request:Request):
            if request.headers.get('x-test-admin')!='yes':raise HTTPException(401,'authorization_required')
        def monitor(request:Request):
            if request.headers.get('x-test-monitor')!='yes':raise HTTPException(403,'invalid_monitoring_api_secret')
        billing.install_routes(self.app,self.settings,owner,admin,monitor,lambda s,u:SimpleNamespace(plan='free'),
                               lambda *a,**kw:None,lambda *a,**kw:None,lambda u:False)
    def rows(self,table):
        with closing(db.connect(self.path)) as c:return [dict(r) for r in c.execute('SELECT * FROM '+table)]
    def start(self):
        return billing.start(self.settings,self.user,SimpleNamespace(plan='free'),billing.TERMS_VERSION)
    def success(self,ch=None,saved=True):
        ch=ch or self.rows('billing_charges')[-1]
        payload=json.loads(ch['request_payload'])
        return {'id':ch['provider_payment_id'],'status':'succeeded','paid':True,
            'captured_at':self.now.isoformat(),'amount':{'value':'200.00','currency':'RUB'},'metadata':payload['metadata'],
            'payment_method':{'id':payload.get('payment_method_id','method-fixture'),'saved':saved,'type':'bank_card','card':{'last4':'4444'}}}
    def activate(self):
        self.start();billing.safely_apply(self.settings,self.success())
        return self.rows('billing_agreements')[0]
    def renew(self):
        a=self.activate();self.now=datetime.fromisoformat(a['next_charge_at'])+timedelta(seconds=1)
        billing.run(self.settings)
        return self.rows('billing_charges')[-1]
    def canceled_payment(self,ch,reason='insufficient_funds'):
        p=self.success(ch);p.update(status='canceled',paid=False,cancellation_details={'reason':reason});return p
    def test_explicit_unchecked_consent_and_owner_required(self):
        payload={'accepted_terms':True,'accepted_autorenew':False,'terms_version':billing.TERMS_VERSION}
        self.assertEqual(self.http('/api/billing/subscription/start','POST',payload,{'x-test-user':str(self.user['id'])})[0],422)
        payload['accepted_autorenew']=True
        self.assertEqual(self.http('/api/billing/subscription/start','POST',payload)[0],401)
        self.assertEqual(self.mock.call_count,0)
    def test_flags_disable_creation_and_worker_but_not_cancellation(self):
        self.activate()
        with patch.dict(os.environ,{'BILLING_SUBSCRIPTIONS_ENABLED':'0','BILLING_AUTORENEW_ENABLED':'0'}):
            self.assertFalse(billing.run(self.settings)['enabled'])
            with self.assertRaises(HTTPException):self.start()
            self.assertEqual(billing.cancel(self.settings,self.user)['agreement']['auto_renew'],0)
        self.assertEqual(self.mock.call_count,1)
    def test_initial_payload_price_saved_method_receipt_public_link(self):
        self.start();p,key=self.calls[0]
        self.assertEqual(p['amount'],{'value':'200.00','currency':'RUB'})
        self.assertTrue(p['save_payment_method'])
        self.assertEqual(p['confirmation']['return_url'],'https://temichevvet.ru/?payment=plus')
        self.assertEqual(p['receipt']['customer']['email'],self.user['email'])
        self.assertEqual(self.rows('billing_agreements')[0]['consent_version'],billing.TERMS_VERSION)
        self.start();self.assertEqual(self.mock.call_count,1)
    def test_paid_access_and_stale_terms_block_creation(self):
        with self.assertRaises(HTTPException) as e:billing.start(self.settings,self.user,SimpleNamespace(plan='plus'),billing.TERMS_VERSION)
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(HTTPException):billing.start(self.settings,self.user,SimpleNamespace(plan='free'),'outdated')
        self.assertEqual(self.mock.call_count,0)
    def test_max_user_receipt_email_is_required_and_reused(self):
        u=db.get_or_create_user_by_email(self.path,'placeholder@mail.ru')
        with closing(db.connect(self.path)) as c:c.execute('UPDATE users SET email=NULL WHERE id=?',(u['id'],));c.commit()
        u=db.get_user_by_id(self.path,user_id=u['id'])
        with self.assertRaises(HTTPException):billing.start(self.settings,u,SimpleNamespace(plan='free'),billing.TERMS_VERSION)
        billing.start(self.settings,u,SimpleNamespace(plan='free'),billing.TERMS_VERSION,'receipt@mail.ru')
        self.assertEqual(self.calls[0][0]['receipt']['customer']['email'],'receipt@mail.ru')
    def test_payment_applied_once_quota_and_period_survive_repeat(self):
        self.activate();end=self.rows('subscriptions')[0]['period_end']
        with closing(db.connect(self.path)) as c:c.execute('UPDATE subscriptions SET quota_used=4');c.commit()
        self.now+=timedelta(days=2);billing.safely_apply(self.settings,self.success())
        sub=self.rows('subscriptions')[0]
        self.assertEqual(sub['period_end'],end);self.assertEqual(sub['quota_used'],4)
        self.assertEqual(len([r for r in self.rows('funnel_events') if r['event_type']=='payment.succeeded']),1)
    def test_unsaved_method_grants_access_without_autorenew(self):
        self.start();billing.safely_apply(self.settings,self.success(saved=False))
        a=self.rows('billing_agreements')[0]
        self.assertEqual(a['auto_renew'],0);self.assertIsNone(a['payment_method_id'])
        self.assertEqual(self.rows('subscriptions')[0]['plan'],'plus')
    def test_due_renewal_has_one_saved_method_request_and_fresh_quota(self):
        ch=self.renew();p,key=self.calls[-1]
        self.assertNotIn('confirmation',p);self.assertNotIn('save_payment_method',p)
        self.assertEqual(p['payment_method_id'],'method-fixture')
        billing.safely_apply(self.settings,self.success(ch))
        sub=self.rows('subscriptions')[0]
        self.assertEqual(sub['quota_used'],0)
        self.assertEqual(datetime.fromisoformat(sub['period_end']),self.now+timedelta(days=30))
        billing.run(self.settings);self.assertEqual(self.mock.call_count,2)
    def test_cancellation_keeps_paid_access_and_stops_queued_charge(self):
        a=self.activate();before=self.rows('subscriptions')[0]
        self.now=datetime.fromisoformat(a['next_charge_at'])
        with closing(db.connect(self.path)) as c:
            billing._charge(c,self.settings,a,self.user,'renewal',a['next_charge_at'],self.now.isoformat());c.commit()
        billing.cancel(self.settings,self.user);billing.run(self.settings)
        self.assertEqual(self.rows('subscriptions')[0],before);self.assertEqual(self.mock.call_count,1)
        self.assertEqual(self.rows('billing_charges')[-1]['status'],'canceled')
    def test_cancellation_during_submitted_payment_preserves_paid_period_no_future_renewal(self):
        a=self.activate();self.now=datetime.fromisoformat(a['next_charge_at'])+timedelta(seconds=1)
        original=self.mock.side_effect
        def charge(s,**kw):
            p=original(s,**kw);billing.cancel(self.settings,self.user)
            p.update(status='succeeded',paid=True,captured_at=self.now.isoformat(),payment_method={'id':'method-fixture','saved':True})
            return p
        self.mock.side_effect=charge;billing.run(self.settings)
        self.assertEqual(self.rows('billing_agreements')[0]['auto_renew'],0)
        self.assertEqual(self.rows('subscriptions')[0]['plan'],'plus')
        self.now+=timedelta(days=31);billing.run(self.settings);self.assertEqual(self.mock.call_count,2)
    def test_concurrent_workers_create_one_renewal_charge(self):
        a=self.activate();self.now=datetime.fromisoformat(a['next_charge_at'])+timedelta(seconds=1)
        with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(lambda _:billing.run(self.settings),range(4)))
        self.assertEqual(self.mock.call_count,2);self.assertEqual(len(self.rows('billing_charges')),2)
    def test_unknown_retries_same_exact_payload_within_idempotence_window(self):
        original=self.mock.side_effect
        self.mock.side_effect=yookassa.YooKassaPaymentError('network')
        self.start();ch=self.rows('billing_charges')[0];self.now+=timedelta(minutes=6)
        self.mock.side_effect=original;billing.run(self.settings)
        called=self.mock.call_args.kwargs
        self.assertEqual(called['idempotence_key'],ch['idempotence_key'])
        self.assertEqual(called['payload'],json.loads(ch['request_payload']))
        self.assertEqual(len(self.rows('billing_charges')),1)
    def test_unknown_after_window_never_creates_new_charge(self):
        self.mock.side_effect=yookassa.YooKassaPaymentError('network');self.start()
        self.now+=timedelta(hours=24);billing.run(self.settings)
        self.assertEqual(self.mock.call_count,1)
        self.assertEqual(self.rows('billing_agreements')[0]['state'],'needs_attention')
    def test_cancel_unknown_blocks_new_checkout(self):
        self.mock.side_effect=yookassa.YooKassaPaymentError('network');self.start();billing.cancel(self.settings,self.user)
        with self.assertRaises(HTTPException):self.start()
        self.assertEqual(self.mock.call_count,1)
        self.assertTrue(billing.blocks_oneoff(self.settings,self.user))
        self.assertEqual(billing.stats(self.settings)['unresolved_count'],1)
        self.assertEqual(billing.stats(self.settings)['unresolved'][0]['user_id'],self.user['id'])
    def test_insufficient_funds_retries_once_after_day_then_stops(self):
        ch=self.renew();billing.safely_apply(self.settings,self.canceled_payment(ch))
        self.assertEqual(billing.public_state(self.settings,self.user)['agreement']['next_retry_at'],(self.now+timedelta(hours=24)).isoformat())
        self.now+=timedelta(hours=23);billing.run(self.settings);self.assertEqual(self.mock.call_count,2)
        self.now+=timedelta(hours=1,minutes=1);billing.run(self.settings)
        retry=self.rows('billing_charges')[-1];self.assertEqual(retry['attempt'],1)
        self.assertEqual(self.mock.call_count,3)
        billing.safely_apply(self.settings,self.canceled_payment(retry));self.now+=timedelta(days=2);billing.run(self.settings)
        self.assertEqual(self.mock.call_count,3);self.assertEqual(self.rows('billing_agreements')[0]['auto_renew'],0)
    def test_old_failed_payment_repeat_cannot_disable_successfully_renewed_subscription(self):
        ch=self.renew();old=self.canceled_payment(ch)
        billing.safely_apply(self.settings,old)
        self.now+=timedelta(hours=24,minutes=1);billing.run(self.settings)
        billing.safely_apply(self.settings,self.success())
        before=self.rows('billing_agreements')[0]
        result=billing.safely_apply(self.settings,old)
        self.assertFalse(result['changed'])
        self.assertEqual(self.rows('billing_agreements')[0],before)
    def test_invalid_amount_never_grants_access(self):
        self.start();p=self.success();p['amount']['value']='1.00'
        with self.assertRaises(yookassa.YooKassaPaymentValidationError):billing.safely_apply(self.settings,p)
        self.assertEqual(self.rows('subscriptions'),[])
        self.assertEqual(self.rows('billing_agreements')[0]['auto_renew'],0)
    def test_foreign_agreement_metadata_never_grants_access(self):
        self.start();p=self.success();p['metadata']['billing_agreement_id']='other'
        with self.assertRaises(yookassa.YooKassaPaymentValidationError):billing.safely_apply(self.settings,p)
        self.assertEqual(self.rows('subscriptions'),[])
    def test_renewal_with_wrong_saved_method_keeps_existing_period(self):
        ch=self.renew();before=self.rows('subscriptions')[0]['period_end']
        p=self.success(ch);p['payment_method']['id']='foreign-method'
        with self.assertRaises(yookassa.YooKassaPaymentValidationError):billing.safely_apply(self.settings,p)
        self.assertEqual(self.rows('subscriptions')[0]['period_end'],before)
        self.assertEqual(self.rows('billing_agreements')[0]['auto_renew'],0)
    def test_timeout_is_unknown_and_reuses_original_key(self):
        self.mock.side_effect=TimeoutError('timeout');self.start()
        self.assertEqual(self.rows('billing_charges')[0]['status'],'unknown')
        self.assertEqual(len(self.rows('billing_charges')),1)
    def test_missing_provider_configuration_creates_no_agreement(self):
        with self.assertRaises(HTTPException):
            billing.start(replace(self.settings,yookassa_secret_key=''),self.user,SimpleNamespace(plan='free'),billing.TERMS_VERSION)
        self.assertEqual(self.rows('billing_agreements'),[])
        self.assertEqual(self.mock.call_count,0)
    def test_provider_get_rejects_wrong_payment_id(self):
        with patch.object(yookassa,'_request_json',return_value={'id':'other-payment'}):
            with self.assertRaises(yookassa.YooKassaPaymentError):yookassa.get_payment(self.settings,'requested')
    def test_paid_account_merge_preserves_pending_payment_ownership_without_autorenew(self):
        self.start();p=self.success();u=db.get_or_create_user_by_email(self.path,'target@mail.ru')
        db.merge_users(self.path,source_user_id=self.user['id'],target_user_id=u['id'])
        result=billing.safely_apply(self.settings,p)
        self.assertEqual(result['user_id'],u['id'])
        self.assertEqual(self.rows('subscriptions')[0]['user_id'],u['id'])
        self.assertEqual(self.rows('billing_agreements')[0]['auto_renew'],0)
    def test_metrics_count_one_cycle_after_failed_retry_and_one_current_state(self):
        ch=self.renew();billing.safely_apply(self.settings,self.canceled_payment(ch))
        self.now+=timedelta(hours=24,minutes=1);billing.run(self.settings)
        billing.safely_apply(self.settings,self.success())
        data=billing.stats(self.settings)
        self.assertEqual(data['renewal_cycles_30d'],1)
        self.assertEqual(data['paid_renewal_cycles_30d'],1)
        self.assertEqual(data['revenue_30d_rub'],200) # First payment is now over 30 days old.
        billing.cancel(self.settings,self.user);self.start()
        self.assertEqual(sum(row['users'] for row in billing.stats(self.settings)['states']),1)
    def test_offer_matches_enabled_flow_and_documents_retry_and_cancel(self):
        old=(('Стоимость и срок',('Оплата разовая',),()),)
        new=str(billing.offer_sections(old))
        self.assertNotIn('Оплата разовая',new);self.assertIn('200 рублей',new)
        self.assertIn('24 часа',new);self.assertIn('Отменить подписку',new)
        with patch.dict(os.environ,{'BILLING_AUTORENEW_ENABLED':'0'}):self.assertEqual(billing.offer_sections(old),old)
    def test_notice_before_due_is_unique_and_cancellation_invalidates_it(self):
        a=self.activate();self.now=datetime.fromisoformat(a['next_charge_at'])-timedelta(days=1)
        billing.run(self.settings);billing.run(self.settings)
        notices=[r for r in self.rows('retention_outbox') if r['scenario']=='billing_renewal']
        self.assertEqual(len(notices),1)
        billing.cancel(self.settings,self.user)
        with closing(db.connect(self.path)) as c:
            self.assertEqual(retention._cancel_reason(c,notices[0],self.now),'subscription_changed')
        self.assertEqual(self.mock.call_count,1)
    def test_stale_failure_message_is_not_sent_after_successful_retry(self):
        ch=self.renew();billing.safely_apply(self.settings,self.canceled_payment(ch))
        notice=[r for r in self.rows('retention_outbox') if r['scenario']=='billing_failed'][0]
        self.now+=timedelta(hours=24,minutes=1);billing.run(self.settings)
        billing.safely_apply(self.settings,self.success())
        with closing(db.connect(self.path)) as c:self.assertEqual(retention._cancel_reason(c,notice,self.now),'subscription_changed')
    def test_private_method_never_in_public_or_admin_data(self):
        self.activate()
        public=json.dumps(billing.public_state(self.settings,self.user));admin=json.dumps(billing.stats(self.settings))
        self.assertNotIn('method-fixture',public+admin)
        self.assertNotIn('receipt_email',public+admin)
        self.assertIn('4444',public)
    def test_merge_cancels_mandates_and_preserves_history_and_inflight_metadata(self):
        self.activate();u=db.get_or_create_user_by_email(self.path,'other@mail.ru')
        db.merge_users(self.path,source_user_id=self.user['id'],target_user_id=u['id'])
        a=self.rows('billing_agreements')[0]
        self.assertEqual(a['user_id'],u['id']);self.assertEqual(a['auto_renew'],0)
        self.assertEqual(self.rows('billing_events')[0]['user_id'],u['id'])
        billing.safely_apply(self.settings,self.success());self.assertEqual(self.mock.call_count,1)
    def test_admin_and_internal_worker_require_correct_access(self):
        self.assertEqual(self.http('/api/admin/billing')[0],401)
        self.assertEqual(self.http('/api/internal/billing/run','POST')[0],403)
    def test_legacy_oneoff_repeat_does_not_reset_period_or_quota(self):
        p={'id':'legacy','captured_at':self.now.isoformat()}
        r=db.create_payment_record(self.path,user_id=self.user['id'],provider='yookassa',provider_payment_id='legacy',amount_rub=200,status='pending')
        self.assertTrue(billing.settle_oneoff(self.settings,r,p))
        before=self.rows('subscriptions')[0]['period_end']
        with closing(db.connect(self.path)) as c:c.execute('UPDATE subscriptions SET quota_used=5');c.commit()
        self.now+=timedelta(days=5);self.assertFalse(billing.settle_oneoff(self.settings,r,p))
        self.assertEqual(self.rows('subscriptions')[0]['period_end'],before)
        self.assertEqual(self.rows('subscriptions')[0]['quota_used'],5)

if __name__=='__main__':unittest.main(verbosity=2)
