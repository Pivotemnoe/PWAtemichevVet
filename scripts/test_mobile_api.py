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

class MobileApiTests(unittest.TestCase):
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
