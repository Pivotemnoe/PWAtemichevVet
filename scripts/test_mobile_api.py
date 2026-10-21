import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Reuse the suite's isolated test environment, never the local or production DB.
from scripts import test_api as baseline
from app.payments import yookassa
from app.config import get_settings
from fastapi.testclient import TestClient
from unittest.mock import patch
import unittest
from dataclasses import replace
from fastapi import FastAPI
from types import SimpleNamespace
from app import billing

class MobileApiTests(unittest.TestCase):
    def test_subscription_route_returns_android_and_ios_to_the_app(self):
        app = FastAPI()
        noop = lambda *a, **kw: None
        billing.install_routes(app, get_settings(), lambda: {'id': 10}, noop, noop,
                               lambda *a: SimpleNamespace(plan='free'), noop, noop, lambda user: False)
        with TestClient(app) as client:
            for platform in ('ios', 'android', 'browser', ''):
                with self.subTest(platform=platform), patch.object(billing, 'start', return_value={'ok': True}) as start:
                    response = client.post('/api/billing/subscription/start',
                        json={'terms_version': billing.TERMS_VERSION, 'accepted_terms': True, 'accepted_autorenew': True},
                        headers={'X-TemichevVet-Client': platform})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(start.call_args.kwargs['return_to_app'], platform in {'ios', 'android'})

    def test_legacy_payment_route_returns_android_and_ios_to_the_app(self):
        baseline.disable_external_sync()
        with TestClient(baseline.api.app) as client:
            for platform in ('ios', 'android', 'browser', ''):
                with self.subTest(platform=platform):
                    email = f'native-return-{platform or "empty"}@example.ru'
                    auth = client.post('/api/auth/email/start', json={'email': email}).json()
                    self.assertEqual(client.post('/api/auth/email/verify', json={'email': email, 'code': auth['debug_code']}).status_code, 200)
                    payment = {'id': f'fixture-{platform or "empty"}', 'status': 'pending', 'paid': False,
                               'confirmation': {'confirmation_url': 'https://yookassa.ru/fixture'}}
                    with patch.object(baseline.api, 'create_yookassa_plus_payment', return_value=payment) as provider:
                        response = client.post('/api/payments/plus/create', headers={'X-TemichevVet-Client': platform})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(provider.call_args.kwargs.get('return_to_app', False), platform in {'ios', 'android'})

    def test_production_native_payment_return_is_public_https_despite_loopback_base(self):
        for base in ['http://127.0.0.1:8080', 'http://localhost:8080', 'http://temichevvet.ru']:
            settings = replace(get_settings(), app_env='production', app_base_url=base)
            expected = 'https://temichevvet.ru/mobile/payment-return'
            with patch.object(yookassa, '_request_json', return_value={'id':'fixture-payment'}) as provider:
                yookassa.create_plus_payment(settings, user_id=10, return_to_app=True)
                self.assertEqual(provider.call_args.kwargs['payload']['confirmation']['return_url'], expected)
            payload = yookassa.subscription_payload(settings, user_id=10, user_email=None, agreement_id=1, charge_id=1, return_to_app=True)
            self.assertEqual(payload['confirmation']['return_url'], expected)

    def test_mobile_return_is_public_no_store_and_does_not_claim_payment_success(self):
        client = TestClient(baseline.api.app)
        response = client.get('/mobile/payment-return')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertIn('temichevvet://payment-return', response.text)
        self.assertNotIn('Оплата прошла', response.text)
        self.assertEqual(client.get('/mobile').status_code, 200)

    def test_native_and_browser_payments_have_separate_server_owned_return_urls(self):
        settings = get_settings()
        for native in (True, False):
            with patch.object(yookassa, '_request_json', return_value={'id': 'fixture-payment'}) as provider:
                yookassa.create_plus_payment(settings, user_id=10, user_email='fixture@example.ru', return_to_app=native)
                url = provider.call_args.kwargs['payload']['confirmation']['return_url']
                self.assertEqual(url, 'http://127.0.0.1:8080/mobile/payment-return' if native else 'http://127.0.0.1:8080/?payment=plus')
            payload = yookassa.subscription_payload(settings, user_id=10, user_email='fixture@example.ru', agreement_id=1, charge_id=1, return_to_app=native)
            self.assertEqual(payload['confirmation']['return_url'], 'http://127.0.0.1:8080/mobile/payment-return' if native else 'https://temichevvet.ru/?payment=plus')

if __name__ == '__main__': unittest.main()
