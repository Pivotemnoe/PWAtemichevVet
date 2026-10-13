"""HTTP ownership / image validation and durable retry checks on an isolated DB."""
import base64
import io
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import test_api as baseline
from app import db
from fastapi.testclient import TestClient
from PIL import Image


class PetPhotoOfflineTests(unittest.TestCase):
    def setUp(self):
        baseline.disable_external_sync()
        self.user, token = baseline.login(f'photo-{id(self)}@example.ru')
        self.client = TestClient(baseline.api.app)
        self.client.cookies.set(baseline.api.USER_SESSION_COOKIE, token)
        self.pet = self.client.post('/api/pets', json={'pet_type':'кошка', 'pet_name':'Фото QA'}).json()['item']
        self.path = f'/api/pets/{self.pet["id"]}'

    def test_photo_is_private_normalized_and_persisted_then_removed(self):
        source = Image.new('RGB', (640, 320), '#b8d4ee')
        output = io.BytesIO(); source.save(output, format='PNG')
        value = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()
        response = self.client.post(self.path + '/photo', json={'data_url':value})
        self.assertEqual(response.status_code, 200, response.text)
        photo = response.json()['item']['photo_data_url']
        self.assertTrue(photo.startswith('data:image/jpeg;base64,'))
        image = Image.open(io.BytesIO(base64.b64decode(photo.split(',')[1])))
        self.assertEqual(image.size, (512, 512)); self.assertFalse(image.getexif())
        self.assertEqual(self.client.get(self.path).json()['item']['photo_data_url'], photo)
        self.assertEqual(self.client.get('/api/pets').json()['items'][0]['photo_data_url'], photo)
        anonymous = TestClient(baseline.api.app)
        self.assertEqual(anonymous.get(self.path).status_code, 401)
        stranger, stranger_token = baseline.login(f'stranger-{id(self)}@example.ru')
        anonymous.cookies.set(baseline.api.USER_SESSION_COOKIE, stranger_token)
        self.assertEqual(anonymous.post(self.path + '/photo', json={'data_url':value}).status_code, 404)
        self.assertEqual(anonymous.delete(self.path + '/photo').status_code, 404)
        self.assertEqual(self.client.get(self.path).json()['item']['photo_data_url'], photo)
        self.assertIsNone(self.client.delete(self.path + '/photo').json()['item']['photo_data_url'])

    def test_invalid_images_and_oversized_payload_are_rejected_without_replacing_photo(self):
        for value in ['data:image/jpeg;base64,' + base64.b64encode(b'not a photograph').decode(),
                      'data:image/svg+xml;base64,' + base64.b64encode(b'<svg/>').decode(),
                      'data:image/png;base64,' + 'A' * 2_800_001]:
            self.assertEqual(self.client.post(self.path + '/photo', json={'data_url':value}).status_code, 422)
        self.assertFalse(self.client.get(self.path).json()['item']['photo_data_url'])

    def test_replayed_offline_records_have_one_id_and_one_history_event(self):
        for suffix, payload, kind in [('/weights', {'weight_kg':4.8}, 'weight'),
                                      ('/observations', {'text':'Наблюдение офлайн'}, 'observation'),
                                      ('reminders', {'pet_id':self.pet['id'],'title':'Офлайн QA','due_date':'2026-10-20'}, 'reminder')]:
            path = '/api/reminders' if suffix == 'reminders' else self.path + suffix
            payload['client_request_id'] = f'photo-offline-{self.pet["id"]}-{kind}'
            first = self.client.post(path, json=payload)
            again = self.client.post(path, json=payload)
            self.assertEqual(first.status_code, 200, first.text); self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(first.json()['item']['id'], again.json()['item']['id'])
            self.assertTrue(again.json()['idempotent'])
        history = self.client.get(self.path + '/history').json()['items']
        for kind in ['weight','observation','reminder']:
            self.assertEqual(len([row for row in history if row['event_type'] == kind]), 1)

    def test_parallel_retries_do_not_create_duplicate_weight_events(self):
        def write(_):
            return db.create_measurement(baseline.api.settings.database_path, owner_id=self.user['id'],
                pet_id=self.pet['id'], weight_kg=5.0, client_request_id=f'parallel-weight-{self.pet["id"]}')
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(write, range(4)))
        self.assertEqual(len({row['id'] for row in rows}), 1)
        history = self.client.get(self.path + '/history').json()['items']
        self.assertEqual(len([row for row in history if row['event_type'] == 'weight']), 1)

    def test_reminder_retry_is_allowed_after_free_limit_is_filled(self):
        request_id = f'limit-reminder-{self.pet["id"]}'
        payload = {'pet_id':self.pet['id'], 'title':'Первая дата','due_date':'2026-10-20','client_request_id':request_id}
        first = self.client.post('/api/reminders', json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        # Fill to the actual plan limit; the existing write must still be acknowledged.
        limits = baseline.api._user_entitlements(self.user)[1]
        for index in range(int(limits['active_reminders']) - 1):
            self.client.post('/api/reminders', json={**payload, 'client_request_id':f'{request_id}-{index}'})
        repeated = self.client.post('/api/reminders', json=payload)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()['item']['id'], first.json()['item']['id'])


if __name__ == '__main__': unittest.main()
