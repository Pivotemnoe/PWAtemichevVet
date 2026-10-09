"""Opt-in Plus subscription. Both checkout and automatic charges default to OFF."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.payments import yookassa
from app.security import utc_now

PRICE = 200
DAYS = 30
TERMS_VERSION = "plus-autorenew-20261009-v1"
CONSENT_TEXT = ("Подключаю Plus за 200 ₽ каждые 30 дней и разрешаю сохранять способ оплаты "
                "в ЮKassa для автоматического продления. Подписку можно отменить в кабинете; "
                "доступ сохранится до конца оплаченного срока.")
LIVE_STATES = ("pending", "active", "payment_failed", "needs_attention")
logger = logging.getLogger(__name__)


def enabled():
    return os.getenv("BILLING_SUBSCRIPTIONS_ENABLED", "0") == "1"


def renewals_enabled():
    return os.getenv("BILLING_AUTORENEW_ENABLED", "0") == "1"


def init_schema(path):
    with closing(db.connect(path)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS billing_agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            state TEXT NOT NULL DEFAULT 'pending',
            auto_renew INTEGER NOT NULL DEFAULT 1,
            price_rub INTEGER NOT NULL CHECK(price_rub=200),
            period_days INTEGER NOT NULL CHECK(period_days=30),
            consent_version TEXT NOT NULL,
            consent_text TEXT NOT NULL,
            consent_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payment_method_id TEXT,
            receipt_email TEXT,
            method_label TEXT,
            next_charge_at TEXT,
            canceled_at TEXT,
            reason TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS billing_one_live_agreement ON billing_agreements(user_id)
            WHERE state IN ('pending','active','payment_failed','needs_attention');
        CREATE TABLE IF NOT EXISTS billing_charges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_id INTEGER NOT NULL REFERENCES billing_agreements(id) ON DELETE CASCADE,
            original_user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            cycle_at TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            idempotence_key TEXT NOT NULL UNIQUE,
            request_payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            provider_payment_id TEXT UNIQUE,
            confirmation_url TEXT,
            created_at TEXT NOT NULL,
            first_requested_at TEXT,
            last_requested_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            applied_at TEXT,
            reason TEXT,
            UNIQUE(agreement_id,kind,cycle_at,attempt)
        );
        CREATE INDEX IF NOT EXISTS billing_charge_pending ON billing_charges(status,last_requested_at);
        CREATE TABLE IF NOT EXISTS billing_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_id INTEGER REFERENCES billing_agreements(id) ON DELETE SET NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            charge_id INTEGER REFERENCES billing_charges(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            event_key TEXT UNIQUE
        );
        """)
        c.commit()


def _event(c, agreement, kind, now, charge_id=None, key=None):
    c.execute("INSERT OR IGNORE INTO billing_events(agreement_id,user_id,charge_id,kind,created_at,event_key) "
              "VALUES(?,?,?,?,?,?)", (agreement['id'],agreement['user_id'],charge_id,kind,now,key))


def _latest(c, uid):
    return c.execute("SELECT * FROM billing_agreements WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()


def _public(agreement):
    if not agreement:
        return None
    # Saved payment method identifiers and raw provider payloads never leave the server.
    return {k:agreement[k] for k in ('id','state','auto_renew','price_rub','period_days','method_label',
                                     'next_charge_at','canceled_at','reason')}


def public_state(settings, user):
    with closing(db.connect(settings.database_path)) as c:
        a = _latest(c,user['id'])
        item = _public(a)
        if item:
            charge = c.execute("SELECT status,provider_payment_id,confirmation_url,kind,attempt,last_requested_at FROM billing_charges WHERE agreement_id=? ORDER BY id DESC LIMIT 1",
                               (a['id'],)).fetchone()
            item['payment_in_progress'] = bool(charge and charge[0] in ('sending','unknown','pending','waiting_for_capture'))
            item['payment_status'] = charge['status'] if charge else None
            item['payment_kind'] = charge['kind'] if charge else None
            item['next_retry_at'] = ((datetime.fromisoformat(charge['last_requested_at'])+timedelta(hours=24)).isoformat()
                if charge and a['state']=='payment_failed' and charge['status']=='canceled' and charge['attempt']==0 and charge['last_requested_at'] else None)
            item['confirmation_url'] = charge['confirmation_url'] if charge and charge['kind']=='initial' and charge['status']=='pending' else None
    return {'available':enabled() and renewals_enabled(), 'renewals_enabled':renewals_enabled(),
            'price_rub':PRICE,'period_days':DAYS,'terms_version':TERMS_VERSION,
            'consent_text':CONSENT_TEXT,'agreement':item}


def _charge(c, settings, agreement, user, kind, cycle_at, now, attempt=0):
    key = str(uuid.uuid4())
    cur = c.execute("INSERT OR IGNORE INTO billing_charges(agreement_id,original_user_id,kind,cycle_at,attempt,"
                    "idempotence_key,request_payload,created_at) VALUES(?,?,?,?,?,?,'{}',?)",
                    (agreement['id'],user['id'],kind,cycle_at,attempt,key,now))
    if cur.rowcount:
        cid = cur.lastrowid
        payload = yookassa.subscription_payload(settings,user_id=user['id'],user_email=agreement['receipt_email'],
            agreement_id=agreement['id'],charge_id=cid,
            payment_method_id=agreement['payment_method_id'] if kind=='renewal' else None)
        c.execute("UPDATE billing_charges SET request_payload=? WHERE id=?",(json.dumps(payload,ensure_ascii=False),cid))
    return dict(c.execute("SELECT * FROM billing_charges WHERE agreement_id=? AND kind=? AND cycle_at=? AND attempt=?",
                         (agreement['id'],kind,cycle_at,attempt)).fetchone())


def start(settings, user, effective, consent_version, receipt_email=None):
    if not enabled() or not renewals_enabled():
        raise HTTPException(503,'subscriptions_not_enabled')
    if consent_version != TERMS_VERSION:
        raise HTTPException(409,'subscription_terms_changed')
    if effective.plan != 'free':
        raise HTTPException(409,'paid_access_already_active')
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise HTTPException(503,'yookassa_not_configured')
    receipt_email = str(user.get('email') or receipt_email or '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',receipt_email):
        raise HTTPException(422,'receipt_email_required')
    now = utc_now().isoformat()
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        a = _latest(c,user['id'])
        if a and a['state'] in LIVE_STATES:
            if a['state']!='pending':
                raise HTTPException(409,'subscription_already_exists')
            charge = c.execute("SELECT * FROM billing_charges WHERE agreement_id=? AND kind='initial'",
                               (a['id'],)).fetchone()
            c.commit()
            cid = charge['id']
        else:
            # Do not create a subscription alongside an existing one-off checkout.
            if c.execute("SELECT 1 FROM payments WHERE user_id=? AND status IN ('pending','waiting_for_capture')",
                         (user['id'],)).fetchone():
                raise HTTPException(409,'payment_already_pending')
            if c.execute("SELECT 1 FROM billing_charges ch JOIN billing_agreements a ON a.id=ch.agreement_id "
                         "WHERE a.user_id=? AND ch.status IN ('sending','unknown','needs_attention','pending','waiting_for_capture')",
                         (user['id'],)).fetchone():
                raise HTTPException(409,'payment_result_unresolved')
            cur = c.execute("INSERT INTO billing_agreements(user_id,price_rub,period_days,consent_version,"
                "consent_text,consent_at,created_at,updated_at,receipt_email) VALUES(?,?,?,?,?,?,?,?,?)",
                (user['id'],PRICE,DAYS,TERMS_VERSION,CONSENT_TEXT,now,now,now,receipt_email))
            a = dict(c.execute('SELECT * FROM billing_agreements WHERE id=?',(cur.lastrowid,)).fetchone())
            cid = _charge(c,settings,a,user,'initial',now,now)['id']
            _event(c,a,'consent',now,key=f"consent:{a['id']}")
            c.commit()
    dispatch(settings,cid)
    with closing(db.connect(settings.database_path)) as c:
        ch = dict(c.execute('SELECT * FROM billing_charges WHERE id=?',(cid,)).fetchone())
    return {'ok':bool(ch['confirmation_url']),'status':ch['status'],
            'payment_id':ch['provider_payment_id'],'confirmation_url':ch['confirmation_url'],
            'message':'Подтвердите подписку на странице ЮKassa.' if ch['confirmation_url'] else
                      'Проверяем создание платежа. Новый платёж не создаётся.'}


def cancel(settings, user):
    now = utc_now().isoformat()
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        a = _latest(c,user['id'])
        if a:
            c.execute("UPDATE billing_agreements SET state='canceled',auto_renew=0,payment_method_id=NULL,"
                      "canceled_at=COALESCE(canceled_at,?),updated_at=?,reason='user_canceled' WHERE id=?",(now,now,a['id']))
            c.execute("UPDATE billing_charges SET status='canceled',reason='user_canceled' "
                      "WHERE agreement_id=? AND status='new'",(a['id'],))
            _event(c,a,'canceled',now,key=f"cancel:{a['id']}")
            _notice(c,settings,a,'billing_canceled',f"cancel:{a['id']}",now)
        c.commit()
    return public_state(settings,user)


def _notice(c, settings, a, scenario, source, now, date=None):
    from app import retention
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='retention_outbox'").fetchone():
        return
    user = dict(c.execute('SELECT * FROM users WHERE id=?',(a['user_id'],)).fetchone())
    prefs = retention._prefs(c,user,now)
    if not prefs['service_enabled'] or prefs['channel'] not in retention._channels(c,user):
        return
    due = retention._quiet_due(datetime.fromisoformat(now),prefs['timezone'])
    if date:
        date = datetime.fromisoformat(date).astimezone(ZoneInfo(prefs['timezone'])).strftime('%d.%m.%Y')
    payload = {'action':'subscription','agreement_id':a['id'],'date':date or '', 'cycle_at':a['next_charge_at']}
    if scenario in ('billing_success','billing_failed'):
        payload['charge_id'] = int(source.split(':')[-1])
    c.execute("INSERT OR IGNORE INTO retention_outbox(user_id,campaign,dedupe_key,scenario,category,source_key,"
        "channel,payload,created_at,due_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (a['user_id'],'plus-subscription-v1',source,scenario,'billing',source,prefs['channel'],
         json.dumps(payload,ensure_ascii=False),now,due.isoformat(),(due+timedelta(days=3)).isoformat()))


def notice_cancel_reason(c, row, payload):
    a = c.execute('SELECT * FROM billing_agreements WHERE id=? AND user_id=?',
                  (payload.get('agreement_id'),row['user_id'])).fetchone()
    if not a:
        return 'subscription_changed'
    if row['scenario']=='billing_renewal' and (not a['auto_renew'] or a['state']!='active' or
                                              a['next_charge_at']!=payload.get('cycle_at')):
        return 'subscription_changed'
    if row['scenario']=='billing_failed':
        ch = c.execute('SELECT status FROM billing_charges WHERE id=? AND agreement_id=?',
                       (payload.get('charge_id'),a['id'])).fetchone()
        if not ch or ch[0]!='canceled' or a['state']=='active' or a['reason'] in ('user_canceled','account_merged'):
            return 'subscription_changed'
    return None


def dispatch(settings, cid):
    now = utc_now()
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        ch = dict(c.execute('SELECT * FROM billing_charges WHERE id=?',(cid,)).fetchone())
        a = dict(c.execute('SELECT * FROM billing_agreements WHERE id=?',(ch['agreement_id'],)).fetchone())
        if ch['status'] not in ('new','unknown'):
            c.commit();return
        if not enabled() or not renewals_enabled() or not a['auto_renew']:
            c.commit();return
        if ch['first_requested_at'] and now-datetime.fromisoformat(ch['first_requested_at'])>=timedelta(hours=23):
            c.execute("UPDATE billing_charges SET status='needs_attention',reason='idempotency_window' WHERE id=?",(cid,))
            c.execute("UPDATE billing_agreements SET state='needs_attention',auto_renew=0,reason='payment_result_unknown' WHERE id=?",(a['id'],))
            _event(c,a,'unknown',now.isoformat(),cid,key=f'unknown:{cid}')
            c.commit();return
        c.execute("UPDATE billing_charges SET status='sending',first_requested_at=COALESCE(first_requested_at,?),"
                  "last_requested_at=?,attempts=attempts+1 WHERE id=?",(now.isoformat(),now.isoformat(),cid))
        c.commit()
    # Atomic claim is the point of submission. Cancellation stops future submissions;
    # a request already in flight is reconciled, with no additional retry after cancel.
    try:
        payment = yookassa.create_subscription_payment(settings,payload=json.loads(ch['request_payload']),
                                                       idempotence_key=ch['idempotence_key'])
        pid = str(payment.get('id') or '')
        if not pid or not isinstance(payment.get('metadata'),dict):
            raise yookassa.YooKassaPaymentError('invalid_subscription_receipt')
    except (yookassa.YooKassaPaymentError,yookassa.YooKassaConfigError,TimeoutError,ConnectionError):
        with closing(db.connect(settings.database_path)) as c:
            c.execute("UPDATE billing_charges SET status='unknown',reason='provider_unconfirmed' WHERE id=?",(cid,));c.commit()
        return
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        # The request owner can move after account linking; metadata remains immutable.
        a = dict(c.execute('SELECT * FROM billing_agreements WHERE id=?',(ch['agreement_id'],)).fetchone())
        c.execute("UPDATE billing_charges SET provider_payment_id=?,confirmation_url=?,status='pending',reason=NULL WHERE id=?",
                  (pid,yookassa.confirmation_url(payment),cid))
        c.execute("INSERT OR IGNORE INTO payments(user_id,provider,provider_payment_id,plan_code,amount_rub,status,"
                  "confirmation_url,idempotence_key,created_at,updated_at,raw_payload) VALUES(?,'yookassa',?,'plus',?,'pending',?,?,?,?,?)",
                  (a['user_id'],pid,PRICE,yookassa.confirmation_url(payment),ch['idempotence_key'],now.isoformat(),now.isoformat(),json.dumps(payment,ensure_ascii=False)))
        c.commit()
    try:
        safely_apply(settings,payment)
    except yookassa.YooKassaPaymentValidationError:
        return


def apply_provider(settings, payment):
    """Only call with a response fetched server-to-server from YooKassa."""
    pid = str(payment.get('id') or '')
    now = utc_now()
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        r = c.execute('SELECT * FROM billing_charges WHERE provider_payment_id=?',(pid,)).fetchone()
        if not r:
            c.commit();return None
        ch = dict(r)
        a = dict(c.execute('SELECT * FROM billing_agreements WHERE id=?',(ch['agreement_id'],)).fetchone())
        if ch['applied_at']:
            c.commit();return {'status':'succeeded','user_id':a['user_id'],'changed':False}
        if ch['status']=='canceled':
            c.commit();return {'status':'canceled','user_id':a['user_id'],'changed':False}
        status = yookassa.payment_status(payment)
        metadata = payment.get('metadata') or {}
        expected = json.loads(ch['request_payload'])['metadata']
        if any(str(metadata.get(k))!=str(expected[k]) for k in expected):
            raise yookassa.YooKassaPaymentValidationError('subscription_metadata_mismatch')
        if status=='succeeded':
            yookassa.validate_plus_payment(payment,expected_user_id=ch['original_user_id'],expected_amount_rub=PRICE)
            if ch['kind']=='renewal' and str((payment.get('payment_method') or {}).get('id') or '')!=str(json.loads(ch['request_payload']).get('payment_method_id')):
                raise yookassa.YooKassaPaymentValidationError('subscription_method_mismatch')
            sub = c.execute('SELECT * FROM subscriptions WHERE user_id=?',(a['user_id'],)).fetchone()
            start = now
            if sub and sub['plan']=='plus' and sub['period_end']:
                start = max(start,datetime.fromisoformat(sub['period_end']))
            end = start+timedelta(days=DAYS)
            c.execute("INSERT INTO subscriptions(user_id,plan,quota_total,quota_used,period_start,period_end,source,updated_at) "
                "VALUES(?,'plus',10,0,?,?,'pwa',?) ON CONFLICT(user_id) DO UPDATE SET plan='plus',quota_total=10,"
                "quota_used=CASE WHEN subscriptions.period_end>? THEN subscriptions.quota_used ELSE 0 END,"
                "period_start=excluded.period_start,period_end=excluded.period_end,source='pwa',updated_at=excluded.updated_at",
                (a['user_id'],start.isoformat(),end.isoformat(),now.isoformat(),now.isoformat()))
            method = payment.get('payment_method') or {}
            saved = method.get('saved') is True and bool(method.get('id'))
            auto = bool(a['auto_renew'] and saved and a['state']!='canceled')
            label = 'Карта •••• '+str((method.get('card') or {}).get('last4') or '') if method.get('type')=='bank_card' else 'Сохранённый способ оплаты'
            c.execute("UPDATE billing_agreements SET state=?,auto_renew=?,payment_method_id=?,method_label=?,next_charge_at=?,"
                "updated_at=?,reason=? WHERE id=?",('active' if auto else 'canceled',int(auto),method.get('id') if auto else None,
                label if saved else None,end.isoformat(),now.isoformat(),None if auto else ('user_canceled' if a['canceled_at'] else 'method_not_saved'),a['id']))
            c.execute("UPDATE billing_charges SET status='succeeded',applied_at=?,reason=NULL WHERE id=?",(now.isoformat(),ch['id']))
            c.execute("UPDATE payments SET status='succeeded',paid_at=?,updated_at=?,raw_payload=? WHERE provider='yookassa' AND provider_payment_id=?",
                (str(payment.get('captured_at') or now.isoformat()),now.isoformat(),json.dumps(payment,ensure_ascii=False),pid))
            _event(c,a,'initial_paid' if ch['kind']=='initial' else 'renewal_paid',now.isoformat(),ch['id'],key=f"paid:{ch['id']}")
            c.execute("INSERT INTO funnel_events(created_at,event_type,step,status,user_id,source,path,metadata) "
                      "VALUES(?,'payment.succeeded','payment_success','ok',?,'billing','/app',?)",
                      (now.isoformat(),a['user_id'],json.dumps({'provider':'yookassa','amount_rub':PRICE,
                                                             'payment_id':pid,'billing_kind':ch['kind']})))
            _notice(c,settings,a,'billing_success',f"success:{ch['id']}",now.isoformat(),end.isoformat())
        elif status=='canceled':
            reason = str((payment.get('cancellation_details') or {}).get('reason') or 'payment_canceled')
            c.execute("UPDATE billing_charges SET status='canceled',reason=?,last_requested_at=? WHERE id=?",(reason,now.isoformat(),ch['id']))
            c.execute("UPDATE payments SET status='canceled',updated_at=?,raw_payload=? WHERE provider='yookassa' AND provider_payment_id=?",
                      (now.isoformat(),json.dumps(payment,ensure_ascii=False),pid))
            retry = ch['kind']=='renewal' and ch['attempt']==0 and reason=='insufficient_funds' and a['auto_renew']
            if a['state']!='canceled':
                c.execute("UPDATE billing_agreements SET state=?,auto_renew=?,reason=?,updated_at=? WHERE id=?",
                    ('payment_failed' if retry else 'canceled',int(retry),reason,now.isoformat(),a['id']))
            _event(c,a,'payment_failed',now.isoformat(),ch['id'],key=f"failed:{ch['id']}")
            _notice(c,settings,a,'billing_failed',f"failed:{ch['id']}",now.isoformat())
        else:
            c.execute('UPDATE billing_charges SET status=? WHERE id=?',(status,ch['id']))
            c.execute("UPDATE payments SET status=?,updated_at=?,raw_payload=? WHERE provider='yookassa' AND provider_payment_id=?",
                      (status,now.isoformat(),json.dumps(payment,ensure_ascii=False),pid))
        c.commit()
    if status=='succeeded':
        from app.retention import track_product
        try:
            track_product(settings,a['user_id'],'payment.succeeded','payment_success')
        except Exception:
            # Accounting is committed already. A metrics failure must not undo a payment.
            logger.exception('Subscription return attribution failed for charge %s',ch['id'])
    return {'status':status,'user_id':a['user_id'],'changed':status in ('succeeded','canceled')}


def safely_apply(settings, payment):
    try:
        return apply_provider(settings,payment)
    except yookassa.YooKassaPaymentValidationError:
        with closing(db.connect(settings.database_path)) as c:
            c.execute("UPDATE billing_charges SET status='needs_attention',reason='verification_failed' WHERE provider_payment_id=?",
                      (payment.get('id'),))
            c.execute("UPDATE billing_agreements SET state='needs_attention',auto_renew=0,reason='verification_failed' "
                      "WHERE id IN (SELECT agreement_id FROM billing_charges WHERE provider_payment_id=?)",(payment.get('id'),))
            c.commit()
        raise


def settle_oneoff(settings, record, payment):
    """Grant old one-off payments exactly once, atomically with succeeded status."""
    now = utc_now()
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute("SELECT status FROM payments WHERE provider='yookassa' AND provider_payment_id=?",
                        (record['provider_payment_id'],)).fetchone()
        if old and old[0]=='succeeded':
            c.commit();return False
        c.execute("UPDATE payments SET status='succeeded',paid_at=?,updated_at=?,raw_payload=? WHERE provider='yookassa' AND provider_payment_id=?",
                  (str(payment.get('captured_at') or now.isoformat()),now.isoformat(),json.dumps(payment,ensure_ascii=False),record['provider_payment_id']))
        c.execute("INSERT INTO subscriptions(user_id,plan,quota_total,quota_used,period_start,period_end,source,updated_at) "
            "VALUES(?,'plus',10,0,?,?,'pwa',?) ON CONFLICT(user_id) DO UPDATE SET plan='plus',quota_total=10,quota_used=0,"
            "period_start=excluded.period_start,period_end=excluded.period_end,source='pwa',updated_at=excluded.updated_at",
            (record['user_id'],now.isoformat(),(now+timedelta(days=DAYS)).isoformat(),now.isoformat()))
        c.commit();return True


def run(settings, limit=5):
    if not enabled() or not renewals_enabled():
        return {'enabled':False,'checked':0}
    now = utc_now()
    candidates=[]
    with closing(db.connect(settings.database_path)) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE billing_charges SET status='unknown',reason='worker_interrupted' WHERE status='sending' AND last_requested_at<?",
                  ((now-timedelta(minutes=2)).isoformat(),))
        for a in [dict(r) for r in c.execute("SELECT * FROM billing_agreements WHERE auto_renew=1 AND state IN ('active','payment_failed')")]:
            if not a['next_charge_at'] or not a['payment_method_id']:
                continue
            due = datetime.fromisoformat(a['next_charge_at'])
            if a['state']=='active' and now < due <= now+timedelta(days=2):
                _notice(c,settings,a,'billing_renewal',f"renew:{a['id']}:{a['next_charge_at']}",now.isoformat(),due.isoformat())
            if due>now:
                continue
            user = dict(c.execute('SELECT * FROM users WHERE id=?',(a['user_id'],)).fetchone())
            attempt=0
            if a['state']=='payment_failed':
                prior = c.execute("SELECT * FROM billing_charges WHERE agreement_id=? AND kind='renewal' AND cycle_at=? ORDER BY attempt DESC LIMIT 1",
                                  (a['id'],a['next_charge_at'])).fetchone()
                if not prior or prior['status']!='canceled' or prior['attempt']!=0 or datetime.fromisoformat(prior['last_requested_at'])+timedelta(hours=24)>now:
                    continue
                attempt=1
            _charge(c,settings,a,user,'renewal',a['next_charge_at'],now.isoformat(),attempt)
        candidates=[dict(r) for r in c.execute("SELECT ch.* FROM billing_charges ch JOIN billing_agreements a ON a.id=ch.agreement_id "
            "WHERE ch.status IN ('new','unknown','pending','waiting_for_capture') "
            "AND (ch.provider_payment_id IS NOT NULL OR a.auto_renew=1) "
            "AND (ch.last_requested_at IS NULL OR ch.last_requested_at<?) ORDER BY ch.id LIMIT ?",
            ((now-timedelta(minutes=5)).isoformat(),min(max(limit,1),20)))]
        c.commit()
    checked=0
    for ch in candidates:
        if ch['provider_payment_id']:
            try:
                p=yookassa.get_payment(settings,ch['provider_payment_id'])
                safely_apply(settings,p)
            except (yookassa.YooKassaPaymentError,yookassa.YooKassaPaymentValidationError,
                    yookassa.YooKassaConfigError,TimeoutError,ConnectionError):
                continue
            with closing(db.connect(settings.database_path)) as c:
                c.execute('UPDATE billing_charges SET last_requested_at=? WHERE id=?',(now.isoformat(),ch['id']));c.commit()
        else:
            dispatch(settings,ch['id'])
        checked+=1
    with closing(db.connect(settings.database_path)) as c:
        paid_users=[r[0] for r in c.execute("SELECT DISTINCT user_id FROM billing_events WHERE kind IN ('initial_paid','renewal_paid') AND created_at>=?",
                                          (now.isoformat(),))]
    return {'enabled':True,'checked':checked,'paid_users':paid_users}


def stats(settings):
    now=utc_now()
    with closing(db.connect(settings.database_path)) as c:
        states=[dict(r) for r in c.execute('SELECT state,count(*) users FROM billing_agreements a WHERE id=(SELECT max(id) FROM billing_agreements WHERE user_id=a.user_id) GROUP BY state')]
        events=[dict(r) for r in c.execute('SELECT kind,count(*) events,count(DISTINCT user_id) users FROM billing_events WHERE created_at>=? GROUP BY kind',((now-timedelta(days=30)).isoformat(),))]
        counts={r['kind']:r for r in events}
        initial=counts.get('initial_paid',{}).get('users',0)
        renewed=counts.get('renewal_paid',{}).get('users',0)
        revenue=c.execute("SELECT COALESCE(sum(p.amount_rub),0) FROM payments p JOIN billing_charges ch ON ch.provider_payment_id=p.provider_payment_id "
                          "WHERE p.provider='yookassa' AND p.status='succeeded' AND p.paid_at>=?",((now-timedelta(days=30)).isoformat(),)).fetchone()[0]
        cycles=c.execute("SELECT count(*),COALESCE(sum(paid),0) FROM (SELECT agreement_id,cycle_at,"
            "max(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) paid FROM billing_charges "
            "WHERE kind='renewal' AND cycle_at>=? AND cycle_at<=? GROUP BY agreement_id,cycle_at)",
            ((now-timedelta(days=30)).isoformat(),now.isoformat())).fetchone()
        recent=[dict(r) for r in c.execute("SELECT a.id,a.user_id,a.state,a.auto_renew,a.next_charge_at,a.canceled_at,a.reason,"
            "ch.status payment_status,ch.kind payment_kind,ch.attempt,ch.last_requested_at "
            "FROM billing_agreements a LEFT JOIN billing_charges ch ON ch.id="
            "(SELECT max(id) FROM billing_charges WHERE agreement_id=a.id) ORDER BY a.id DESC LIMIT 30")]
        for r in recent:
            r['next_retry_at']=((datetime.fromisoformat(r['last_requested_at'])+timedelta(hours=24)).isoformat()
                if r['state']=='payment_failed' and r['payment_status']=='canceled' and r['attempt']==0 and r['last_requested_at'] else None)
        unresolved_count=c.execute("SELECT count(*) FROM billing_charges WHERE status IN ('unknown','needs_attention')").fetchone()[0]
        unresolved=[dict(r) for r in c.execute("SELECT ch.id,ch.agreement_id,a.user_id,ch.status,ch.provider_payment_id,ch.created_at "
            "FROM billing_charges ch JOIN billing_agreements a ON a.id=ch.agreement_id "
            "WHERE ch.status IN ('unknown','needs_attention') ORDER BY ch.id LIMIT 50")]
    return {'enabled':enabled(),'renewals_enabled':renewals_enabled(),'states':states,'events_30d':events,
            'initial_payers_30d':initial,'renewed_users_30d':renewed,'revenue_30d_rub':revenue,
            'renewal_cycles_30d':cycles[0],'paid_renewal_cycles_30d':cycles[1],
            'unresolved_count':unresolved_count,'unresolved':unresolved,'recent':recent}


def blocks_oneoff(settings, user):
    with closing(db.connect(settings.database_path)) as c:
        return bool(c.execute("SELECT 1 FROM billing_agreements a WHERE a.user_id=? AND "
            "(a.state IN ('pending','active','payment_failed','needs_attention') OR EXISTS "
            "(SELECT 1 FROM billing_charges ch WHERE ch.agreement_id=a.id AND ch.status IN "
            "('sending','unknown','needs_attention','pending','waiting_for_capture'))) LIMIT 1",(user['id'],)).fetchone())


def offer_sections(original):
    if not enabled() or not renewals_enabled():
        return original
    return tuple(section for section in original if section[0]!='Стоимость и срок') + (
        ('Стоимость и продление',(
            'Подписка Plus стоит 200 рублей за каждые 30 дней. Первый платёж пользователь подтверждает на странице ЮKassa. Следующее списание происходит после окончания оплаченного срока, затем — каждые 30 дней после успешного продления.',
            'Автоматическое продление подключается только после отдельного согласия пользователя в кабинете. ЮKassa сохраняет способ оплаты; сервис хранит его идентификатор и последние четыре цифры карты. Полный номер карты и код безопасности сервис не получает.',
            'Ранее приобретённый разовый Plus не становится подпиской. Его можно использовать до конца оплаченного срока, затем отдельно подключить подписку.',),()),
        ('Как отменить подписку',(
            'В разделе «Подписка» в кабинете нажмите «Отменить подписку». Новые запросы на списание после отмены не отправляются. Если платёж уже отправлен в ЮKassa, его результат проверяется отдельно и показывается в кабинете.',
            'Отмена продления сохраняет Plus до конца оплаченного срока. После этого остаётся Free; питомцы и записи не удаляются. Отмена не оформляет возврат за уже оплаченный период. По вопросам платежей и возврата обратитесь в поддержку.',),()),
        ('Если оплата не прошла',(
            'При недостатке средств система повторяет продление один раз через 24 часа после неудачной попытки. Если повторная оплата не прошла или причина отказа другая, автопродление отключается. При неподтверждённом ответе платёж проверяется без создания нового списания.',
            'При успешной оплате чек направляется на указанную почту. Уведомления о предстоящем продлении, результате оплаты и отмене приходят через выбранный доступный канал сервисных уведомлений — почту или MAX. Состояние подписки всегда доступно в кабинете.',),()),
    )


def merge_identity(cur, source, target):
    if not cur.execute("SELECT 1 FROM sqlite_master WHERE name='billing_agreements'").fetchone():
        return
    # Preserve history, but never silently combine two independently consented mandates.
    cur.execute("UPDATE billing_agreements SET state='canceled',auto_renew=0,payment_method_id=NULL,reason='account_merged',updated_at=? "
                "WHERE user_id IN (?,?)",(utc_now().isoformat(),source,target))
    cur.execute("UPDATE billing_charges SET status='canceled',reason='account_merged' WHERE status='new' "
                "AND agreement_id IN (SELECT id FROM billing_agreements WHERE user_id IN (?,?))",(source,target))
    cur.execute('UPDATE billing_agreements SET user_id=? WHERE user_id=?',(target,source))
    cur.execute('UPDATE billing_events SET user_id=? WHERE user_id=?',(target,source))


class StartInput(BaseModel):
    accepted_terms: Literal[True]
    accepted_autorenew: Literal[True]
    terms_version: str = Field(max_length=80)
    receipt_email: str | None = Field(default=None,max_length=254)


def install_routes(app,settings,current_user,current_admin,monitor,effective_subscription,audit,track,is_review):
    @app.get('/api/billing/subscription')
    def get_state(user:dict=Depends(current_user)):
        return public_state(settings,user)

    @app.post('/api/billing/subscription/start')
    def subscribe(payload:StartInput,request:Request,user:dict=Depends(current_user)):
        if is_review(user):
            raise HTTPException(403,'review_payment_disabled')
        result=start(settings,user,effective_subscription(settings,user),payload.terms_version,payload.receipt_email)
        audit(request,'subscription.checkout',user_id=user['id'],status='ok',actor='user',metadata={'terms_version':TERMS_VERSION})
        return result

    @app.post('/api/billing/subscription/cancel')
    def unsubscribe(request:Request,user:dict=Depends(current_user)):
        result=cancel(settings,user)
        audit(request,'subscription.canceled',user_id=user['id'],status='ok',actor='user')
        return result

    @app.get('/api/admin/billing')
    def admin_state(_:dict=Depends(current_admin)):
        return stats(settings)

    @app.post('/api/internal/billing/run')
    def worker(limit:int=5,_:None=Depends(monitor)):
        return run(settings,limit)
