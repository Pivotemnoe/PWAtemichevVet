"""Seed a fictional account only on the isolated loopback mobile QA server."""
import http.cookiejar
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.subscriptions import activate_paid_subscription

BASE = 'http://127.0.0.1:8096'
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def post(path, data):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with opener.open(req, timeout=15) as response:
        return json.load(response)


if __name__ == '__main__':
    # The debug code exists only because qa_server disables all real delivery.
    auth = post('/api/auth/email/start', {'email': 'ios-qa@example.ru'})
    session = post('/api/auth/email/verify', {'email': 'ios-qa@example.ru', 'code': auth['debug_code']})
    pet = post('/api/pets', {'pet_type': 'кошка', 'pet_name': 'Лео iOS', 'breed': 'домашняя',
                             'birth_year': 2022, 'weight_kg': 4.9, 'sex': 'male', 'is_main': True})
    # A synthetic Plus entitlement in the local fixture DB; no provider is called.
    state = Path(__file__).resolve().parents[1] / '.mobile-tools/qa.db'
    activate_paid_subscription(SimpleNamespace(database_path=state), user_id=session['user']['id'])
    print('Fictional iOS QA account and pet prepared')
