"""Isolated local QA server. Payments are fixtures; no external messages or charges."""
from pathlib import Path
import os
import sys
import uuid
import json
import sqlite3
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update({
    'APP_ENV': 'development', 'DATABASE_PATH': str(ROOT / '.mobile-tools/qa.db'),
    'APP_BASE_URL': os.environ.get('TVV_QA_ORIGIN', 'http://127.0.0.1:8096'),
    'SESSION_SECRET': 'isolated-mobile-qa-session-secret-20261013',
    'DEV_AUTH_CODE_LOG': '1', 'EMAIL_REGISTRATION_RUSSIAN_DOMAIN_ONLY': '0',
    'SMTP_HOST': '', 'SMTP_USERNAME': '', 'SMTP_PASSWORD': '', 'SMTP_FROM_EMAIL': '',
    'BOT_DATABASE_PATH': '', 'TELEGRAM_AUTH_SECRET': '', 'MAX_BOT_TOKEN': '',
    'VAPID_PUBLIC_KEY': '', 'VAPID_PRIVATE_KEY': '', 'CORE_API_SECRET': '',
    'OPENAI_API_KEY': '', 'YOOKASSA_SHOP_ID': 'qa-only', 'YOOKASSA_SECRET_KEY': 'qa-only',
    'YOOKASSA_RETURN_URL': '', 'BILLING_SUBSCRIPTIONS_ENABLED': '1', 'BILLING_AUTORENEW_ENABLED': '1',
})
from app import main
from app.payments import yookassa
from app.llm_triage import LlmTriageResult
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

def fixture_triage(**kwargs):
    if 'QA_FORCE_FAIL' in str(kwargs.get('complaint_text') or ''):
        raise RuntimeError('qa_requested_failure')
    return LlmTriageResult(text='ТЕСТОВЫЙ ОТВЕТ. Это локальная проверка сохранения истории, не медицинский разбор.\n'
        '1. Тестовая запись принята.\n2. Ответ сохранён в карточке питомца.\n'
        '3. Данные относятся только к тестовому аккаунту.\n4. Рекомендации по лечению не сформированы.\n'
        '5. Для реального обращения нужен обычный сервис.\n6. При тревожных симптомах обратитесь в клинику.', model='mobile-qa-fixture')
main.call_triage_llm = fixture_triage

fixture_path = ROOT / '.mobile-tools/qa-payments.json'
payments = json.loads(fixture_path.read_text()) if fixture_path.exists() else {}
def persist_payments():
    fixture_path.write_text(json.dumps(payments, ensure_ascii=False, indent=2) + '\n')
def fixture_item(settings, payment_id, payload):
    return_path = urlsplit(payload.get('confirmation', {}).get('return_url', '')).path
    local_return = settings.app_base_url + ('/mobile/payment-return' if return_path == '/mobile/payment-return' else '/mobile?payment=plus')
    return {'id': payment_id, 'status': 'pending', 'paid': False,
            'amount': payload['amount'], 'metadata': payload['metadata'],
            'confirmation': {'type': 'redirect', 'confirmation_url': settings.app_base_url + '/mobile/qa-checkout/' + payment_id},
            'payment_method': {'id': 'qa-method', 'saved': bool(payload.get('save_payment_method')), 'type': 'bank_card', 'card': {'last4': '4242'}},
            '_return': local_return}
def fake_provider(settings, *, method, path, payload=None, idempotence_key=None):
    if method == 'POST':
        payment_id = str(uuid.uuid4())
        item = fixture_item(settings, payment_id, payload)
        payments[payment_id] = item
        persist_payments()
        return item.copy()
    payment_id = path.rsplit('/', 1)[-1]
    if payment_id not in payments: raise yookassa.YooKassaPaymentError('fixture_payment_missing')
    return payments[payment_id].copy()
yookassa._request_json = fake_provider

# Recover only pending fixtures created by an older run of this local server.
if (ROOT / '.mobile-tools/qa.db').exists():
    with sqlite3.connect('file:' + str(ROOT / '.mobile-tools/qa.db') + '?mode=ro', uri=True) as conn:
        for payment_id, raw in conn.execute("SELECT provider_payment_id, request_payload FROM billing_charges WHERE status = 'pending' AND provider_payment_id IS NOT NULL"):
            if payment_id not in payments:
                payments[payment_id] = fixture_item(main.settings, payment_id, json.loads(raw))
    persist_payments()

@main.app.get('/mobile/qa-checkout/{payment_id}')
def checkout(payment_id: str):
    if payment_id not in payments: raise HTTPException(404)
    return HTMLResponse(f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><h1>Тестовая оплата</h1><p>Реальных списаний нет.</p><form method="post"><button name="status" value="succeeded">Подтвердить тестовый платёж</button><button name="status" value="canceled">Отменить тестовый платёж</button></form></body></html>''')

@main.app.post('/mobile/qa-checkout/{payment_id}')
async def checkout_result(payment_id: str, request: Request):
    if payment_id not in payments: raise HTTPException(404)
    from urllib.parse import parse_qs
    status = parse_qs((await request.body()).decode()).get('status', [''])[0]
    if status not in {'succeeded', 'canceled'}: raise HTTPException(400)
    payments[payment_id].update(status=status, paid=status == 'succeeded')
    persist_payments()
    return RedirectResponse(payments[payment_id]['_return'], status_code=303)

# These QA endpoints must precede the application's HTML fallback route.
qa_routes = [route for route in main.app.router.routes if getattr(route, 'path', '').startswith('/mobile/qa-checkout/')]
main.app.router.routes[:] = qa_routes + [route for route in main.app.router.routes if route not in qa_routes]

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(main.app, host='127.0.0.1', port=8096)
