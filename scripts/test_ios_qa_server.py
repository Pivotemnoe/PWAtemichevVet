"""The fault switch belongs to the isolated QA process, never production."""
import os
import tempfile
import unittest
from pathlib import Path

STATE = tempfile.TemporaryDirectory(prefix='tvv-ios-qa-')
os.environ['TVV_QA_STATE_DIR'] = STATE.name
from mobile import qa_server
from fastapi.testclient import TestClient


class IOSQAServerTests(unittest.TestCase):
    def test_api_outage_keeps_shell_and_control_available_and_can_be_restored(self):
        with TestClient(qa_server.main.app) as client:
            self.assertEqual(Path(qa_server.main.settings.database_path).parent, Path(STATE.name).resolve())
            self.assertEqual(client.get('/api/me').status_code, 401)
            changed = client.post('/mobile/qa-api-state', json={'unavailable': True})
            self.assertEqual(changed.status_code, 200)
            self.assertEqual(changed.json()['ios_offline_note_count'], 0)
            self.assertEqual(client.get('/api/me').status_code, 503)
            self.assertEqual(client.get('/mobile').status_code, 200)
            self.assertEqual(client.get('/mobile/qa-api-state').status_code, 200)
            client.post('/mobile/qa-api-state', json={'unavailable': False})
            self.assertEqual(client.get('/api/me').status_code, 401)


if __name__ == '__main__': unittest.main()
