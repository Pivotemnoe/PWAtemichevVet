"""Loopback-only fictional subscription preview. All payment/email/MAX providers disabled."""
import os
import sys
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
workspace = tempfile.TemporaryDirectory(prefix='tvv-subscription-preview-')
os.environ.update(
    APP_ENV='development', APP_BASE_URL='http://127.0.0.1:8097',
    DATABASE_PATH=str(Path(workspace.name)/'preview.db'), DEV_AUTH_CODE_LOG='1',
    SMTP_HOST='', MAX_BOT_TOKEN='', TELEGRAM_AUTH_SECRET='', BOT_DATABASE_PATH='',
    YOOKASSA_SHOP_ID='fictional-preview', YOOKASSA_SECRET_KEY='fictional-preview',
    OPENAI_API_KEY='', CORE_API_SECRET='', RETENTION_ENABLED='0', RETENTION_WEEKLY_SERIES='0',
    BILLING_SUBSCRIPTIONS_ENABLED='1', BILLING_AUTORENEW_ENABLED='1',
    ADMIN_USERNAME='preview', SESSION_SECRET='fictional-subscription-preview-only-123456789',
)
from app.security import make_password_hash
os.environ['ADMIN_PASSWORD_HASH'] = make_password_hash('subscription-preview-pass')
from app import main, db, billing
from app.payments import yookassa

provider_payments = {}
def fake_create(settings, *, payload, idempotence_key):
    payment = {'id':'preview-'+idempotence_key, 'status':'pending','paid':False,
               'amount':payload['amount'],'metadata':payload['metadata'],
               'confirmation':{'confirmation_url':'http://127.0.0.1:8097/qa-no-charge'}}
    provider_payments[payment['id']] = payment
    return payment

def fake_get(settings, payment_id):
    return provider_payments[payment_id]

def deny_provider(*args, **kwargs):
    raise RuntimeError('Outbound providers disabled in fictional preview')

yookassa._request_json = deny_provider
yookassa.create_subscription_payment = fake_create
yookassa.get_payment = fake_get
main.get_yookassa_payment = fake_get
main.create_yookassa_plus_payment = deny_provider

def seed_paid(user):
    result = billing.start(main.settings,user,SimpleNamespace(plan='free'),billing.TERMS_VERSION)
    p = provider_payments[result['payment_id']]
    p.update(status='succeeded',paid=True,captured_at=billing.utc_now().isoformat(),
             payment_method={'id':'fictional-method-'+str(user['id']),'saved':True,'type':'bank_card','card':{'last4':'4444'}})
    billing.safely_apply(main.settings,p)

users = {}
for kind in ('free','active','canceled','failed'):
    user = db.get_or_create_user_by_email(main.settings.database_path,kind+'-demo@mail.ru')
    users[kind] = user
    if kind == 'free':
        continue
    if kind == 'failed':
        with patch.object(billing,'utc_now',return_value=main.utc_now()-timedelta(days=30,seconds=1)):
            seed_paid(user)
    else:
        seed_paid(user)
    if kind == 'canceled':
        billing.cancel(main.settings,user)
    if kind == 'failed':
        billing.run(main.settings)
        with closing(db.connect(main.settings.database_path)) as c:
            ch=c.execute('SELECT ch.provider_payment_id FROM billing_charges ch JOIN billing_agreements a ON a.id=ch.agreement_id WHERE a.user_id=? ORDER BY ch.id DESC LIMIT 1',(user['id'],)).fetchone()
        p=provider_payments[ch[0]]
        p.update(status='canceled',paid=False,cancellation_details={'reason':'insufficient_funds'})
        billing.safely_apply(main.settings,p)

@main.app.get('/qa-subscription-login')
def local_login(view: str = 'free'):
    token = main.make_token()
    db.create_session(main.settings.database_path,user_id=users[view]['id'],
        token_hash=main.hash_value(token,main.settings.session_secret),
        expires_at=(main.utc_now()+timedelta(hours=2)).isoformat())
    response = main.RedirectResponse('/app?action=subscription',status_code=303)
    main._set_user_session_cookie(response,token)
    return response

main.app.router.routes.insert(0,main.app.router.routes.pop())
import uvicorn
try:
    uvicorn.run(main.app,host='127.0.0.1',port=8097,log_level='warning')
finally:
    workspace.cleanup()
