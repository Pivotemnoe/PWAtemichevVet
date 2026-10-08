from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI,HTTPException,Request
from app import db,retention
from app.config import get_settings


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"db.sqlite"
        db.init_db(self.path)
        retention.init_schema(self.path)
        self.settings=replace(get_settings(),database_path=self.path,app_base_url="https://example.test",
                              session_secret="test-retention-key-not-production-123456")
        self.now=datetime.now(timezone.utc).replace(hour=9,minute=0,second=0,microsecond=0)
        self.clock=patch.object(retention,"utc_now",side_effect=lambda:self.now)
        self.clock.start();self.addCleanup(self.clock.stop)
        self.env=patch.dict(os.environ,{"RETENTION_ENABLED":"1","RETENTION_WEEKLY_SERIES":"0"})
        self.env.start();self.addCleanup(self.env.stop)
        self.user=self.new_user("owner@mail.ru")
        self.app=FastAPI()
        users={self.user["id"]:self.user}
        def current(request:Request):
            try:
                return users[int(request.headers.get("x-test-user","0"))]
            except Exception:
                raise HTTPException(401,"authorization_required")
        def admin(request:Request):
            if request.headers.get("x-test-admin")!="yes":
                raise HTTPException(401,"authorization_required")
            return {}
        def monitor(request:Request):
            if request.headers.get("x-test-monitor")!="yes":
                raise HTTPException(403,"invalid_monitoring_api_secret")
        retention.install_routes(self.app,self.settings,current,admin,monitor)
        self.users=users

    def new_user(self,email):
        user=db.get_or_create_user_by_email(self.path,email)
        with closing(db.connect(self.path)) as c:
            c.execute("UPDATE users SET created_at=? WHERE id=?",
                      ((self.now-timedelta(days=14)).isoformat(),user["id"]));c.commit()
        return dict(user)

    def rows(self,table):
        with closing(db.connect(self.path)) as c:
            return [dict(r) for r in c.execute("SELECT * FROM "+table)]

    def http(self,path,method="GET",payload=None,headers=None):
        async def run():
            sent=False;messages=[]
            async def receive():
                nonlocal sent
                if not sent:
                    sent=True
                    return {"type":"http.request","body":json.dumps(payload or {}).encode(),"more_body":False}
                await asyncio.Event().wait()
            async def send(m): messages.append(m)
            u=urlsplit(path)
            scope={"type":"http","asgi":{"version":"3.0","spec_version":"2.4"},"http_version":"1.1",
                   "method":method,"scheme":"https","path":u.path,"raw_path":u.path.encode(),
                   "query_string":u.query.encode(),"root_path":"","server":("example.test",443),
                   "client":("127.0.0.1",1234),"headers":[(k.encode(),v.encode()) for k,v in
                   {"content-type":"application/json",**(headers or {})}.items()]}
            await asyncio.wait_for(self.app(scope,receive,send),5)
            status=next(m["status"] for m in messages if m["type"]=="http.response.start")
            body=b"".join(m.get("body",b"") for m in messages if m["type"]=="http.response.body")
            try: body=json.loads(body)
            except Exception: body=body.decode()
            return status,body
        return asyncio.run(run())

    def accepted(self):
        with patch.object(retention,"send_email",return_value="mail-test"):
            r=retention.run(self.settings,now=self.now)
        self.assertEqual(r["accepted"],1)
        return self.rows("retention_outbox")[0]

    def test_one_selected_channel_and_no_duplicate_send(self):
        db.link_external_account(self.path,user_id=self.user["id"],provider="max",provider_user_id="123")
        retention.preferences(self.settings,self.user)
        with closing(db.connect(self.path)) as c:
            c.execute("UPDATE retention_preferences SET channel='email'");c.commit()
        with patch.object(retention,"send_email",return_value="mail") as email,patch.object(retention,"send_max") as maxsend:
            retention.run(self.settings,now=self.now)
            retention.run(self.settings,now=self.now)
        self.assertEqual(email.call_count,1);maxsend.assert_not_called()
        self.assertEqual(len(self.rows("retention_outbox")),1)

    def test_merge_keeps_statistics_and_cancels_second_initial_message(self):
        row=self.accepted()
        other=self.new_user("second@mail.ru")
        retention.enqueue(self.settings,self.now)
        db.merge_users(self.path,source_user_id=self.user["id"],target_user_id=other["id"])
        rows=self.rows("retention_outbox")
        self.assertEqual(len(rows),2)
        self.assertEqual({r["user_id"] for r in rows},{other["id"]})
        self.assertEqual(next(r for r in rows if r["id"]!=row["id"])["status"],"cancelled")
        self.assertEqual(retention.stats(self.settings)["windows"]["30"]["accepted_users"],1)

    def test_email_contains_real_action_and_unsubscribe_links(self):
        retention.enqueue(self.settings,self.now)
        row=self.rows("retention_outbox")[0]
        settings=replace(self.settings,smtp_host="smtp.example.test",smtp_port=587,
            smtp_from_email="noreply@example.test",smtp_username="",smtp_password="")
        with patch.object(retention.smtplib,"SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            retention.send_email(settings,row,self.user)
            message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertIn("TemichevVet",message["From"])
        self.assertIn("/r/",message.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("/stop",message["List-Unsubscribe"])
        self.assertEqual(message["List-Unsubscribe-Post"],"List-Unsubscribe=One-Click")

    def test_message_links_use_public_site_with_legacy_loopback_config(self):
        for base in ("http://127.0.0.1:8080", "http://localhost:8081", "http://0.0.0.0", "http://[::1]:8080", ""):
            settings=replace(self.settings,app_base_url=base)
            action,stop=retention.message_urls(settings,{"id":123})
            self.assertTrue(action.startswith("https://temichevvet.ru/r/"),base)
            self.assertEqual(stop,action+"/stop")
        action,_=retention.message_urls(self.settings,{"id":123})
        self.assertTrue(action.startswith("https://example.test/r/"))

    def test_confirmed_payment_after_link_is_counted_once(self):
        row=self.accepted()
        token=f"{row['id']}.{retention.signature(self.settings,row['id'])}"
        self.http("/api/retention/activity","POST",{"token":token},{"x-test-user":str(self.user["id"])})
        self.now+=timedelta(minutes=1)
        with closing(db.connect(self.path)) as c:
            c.execute("INSERT INTO payments(user_id,provider,provider_payment_id,amount_rub,status,created_at,updated_at,paid_at) VALUES(?,?,?,?,?,?,?,?)",
                (self.user["id"],"mock","fixture-payment",200,"succeeded",self.now.isoformat(),self.now.isoformat(),self.now.isoformat()))
            c.commit()
        for _ in range(2):
            retention.track_product(self.settings,self.user["id"],"payment.succeeded","payment_success")
        self.assertEqual(retention.stats(self.settings)["windows"]["30"]["paid_users"],1)

    def test_quiet_hours_queue_without_sending(self):
        self.now=self.now.replace(hour=5)
        with patch.object(retention,"send_email") as send:
            result=retention.run(self.settings,now=self.now)
        send.assert_not_called()
        self.assertEqual(result["accepted"],0)
        self.assertEqual(datetime.fromisoformat(self.rows("retention_outbox")[0]["due_at"]).hour,7)

    def test_return_cancels_pending_message(self):
        retention.enqueue(self.settings,self.now)
        self.now+=timedelta(minutes=1)
        retention.activity(self.settings,self.user)
        with patch.object(retention,"send_email") as send:
            result=retention.run(self.settings,now=self.now)
        send.assert_not_called()
        self.assertEqual(result["cancelled"],1)

    def test_unknown_send_result_is_not_retried(self):
        with patch.object(retention,"send_email",side_effect=TimeoutError) as send:
            retention.run(self.settings,now=self.now)
            self.now+=timedelta(days=8)
            retention.run(self.settings,now=self.now)
        self.assertEqual(send.call_count,1)
        self.assertEqual(self.rows("retention_outbox")[0]["status"],"unknown")

    def test_two_workers_claim_only_once(self):
        with patch.object(retention,"send_email",return_value="mail") as send:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _:retention.run(self.settings,now=self.now),range(2)))
        self.assertEqual(send.call_count,1)

    def test_signed_get_does_not_count_return_or_unsubscribe(self):
        row=self.accepted()
        token=f"{row['id']}.{retention.signature(self.settings,row['id'])}"
        self.assertEqual(self.http("/r/"+token)[0],303)
        self.assertEqual(self.http("/r/"+token+"/stop")[0],200)
        self.assertEqual(len(self.rows("retention_events")),0)
        self.assertEqual(self.rows("retention_preferences")[0]["service_enabled"],1)
        self.assertEqual(self.http("/r/"+token+"/stop","POST")[0],200)
        self.assertEqual(self.rows("retention_preferences")[0]["service_enabled"],0)

    def test_account_ownership_and_statistics(self):
        row=self.accepted()
        other=self.new_user("second@mail.ru");self.users[other["id"]]=other
        token=f"{row['id']}.{retention.signature(self.settings,row['id'])}"
        self.assertEqual(self.http("/api/retention/activity","POST",{"token":token},
             {"x-test-user":str(other["id"])})[0],404)
        self.assertEqual(self.http("/api/retention/activity","POST",{"token":token})[0],401)
        for _ in range(2):
            self.assertEqual(self.http("/api/retention/activity","POST",{"token":token},
                 {"x-test-user":str(self.user["id"])})[0],200)
        retention.track_product(self.settings,self.user["id"],"weight.created","first_record")
        retention.track_product(self.settings,self.user["id"],"weight.created","first_record")
        stats=retention.stats(self.settings)["windows"]["30"]
        self.assertEqual((stats["accepted_users"],stats["returned_users"],stats["record_users"]),(1,1,1))
        self.assertEqual(self.http("/api/admin/retention")[0],401)
        self.assertEqual(self.http("/api/internal/retention/send","POST")[0],403)

    def test_unconfirmed_payment_is_not_counted(self):
        row=self.accepted()
        token=f"{row['id']}.{retention.signature(self.settings,row['id'])}"
        self.http("/api/retention/activity","POST",{"token":token},{"x-test-user":str(self.user["id"])})
        retention.track_product(self.settings,self.user["id"],"payment.succeeded","payment_success")
        self.assertEqual(retention.stats(self.settings)["windows"]["30"]["paid_users"],0)

    def test_weekly_series_stays_off_even_if_user_selected_it(self):
        self.accepted()
        with closing(db.connect(self.path)) as c:
            c.execute("UPDATE retention_preferences SET weekly_enabled=1");c.commit()
        self.now+=timedelta(days=8)
        with patch.object(retention,"send_email") as send:
            retention.run(self.settings,now=self.now)
        send.assert_not_called()
        self.assertEqual(len(self.rows("retention_outbox")),1)

    def test_old_health_task_never_becomes_current_followup(self):
        with closing(db.connect(self.path)) as c:
            old=(self.now-timedelta(days=10)).isoformat()
            triage=c.execute("INSERT INTO triage_logs(user_id,complaint_text,created_at) VALUES(?,?,?)",
                             (self.user["id"],"FICTIONAL_TEST",old)).lastrowid
            c.execute("INSERT INTO triage_followups(triage_id,user_id,urgency_level,scheduled_at,created_at,updated_at) "
                      "VALUES(?,?,?,?,?,?)",(triage,self.user["id"],"yellow",old,old,old));c.commit()
        retention.enqueue(self.settings,self.now)
        self.assertEqual(self.rows("retention_outbox")[0]["scenario"],"first_pet")

    def test_current_followup_preempts_general_message_and_answer_cancels(self):
        with closing(db.connect(self.path)) as c:
            now=self.now.isoformat()
            triage=c.execute("INSERT INTO triage_logs(user_id,complaint_text,created_at) VALUES(?,?,?)",
                             (self.user["id"],"FICTIONAL_TEST",now)).lastrowid
            fid=c.execute("INSERT INTO triage_followups(triage_id,user_id,urgency_level,scheduled_at,created_at,updated_at) "
                      "VALUES(?,?,?,?,?,?)",(triage,self.user["id"],"yellow",now,now,now)).lastrowid;c.commit()
        retention.enqueue(self.settings,self.now)
        self.assertEqual(self.rows("retention_outbox")[0]["scenario"],"followup")
        db.mark_triage_followup_answered(self.path,owner_id=self.user["id"],followup_id=fid,answer="better")
        with patch.object(retention,"send_email") as send:
            retention.run(self.settings,now=self.now)
        send.assert_not_called()

    def test_max_permanent_failure_preserves_failed_count(self):
        db.link_external_account(self.path,user_id=self.user["id"],provider="max",provider_user_id="123")
        failure=urllib.error.HTTPError("https://example.test",403,"Forbidden",None,None)
        with patch.object(retention,"send_max",side_effect=failure) as send:
            retention.run(self.settings,now=self.now)
            retention.run(self.settings,now=self.now)
        self.assertEqual(send.call_count,1)
        self.assertEqual(retention.stats(self.settings)["windows"]["30"]["failed"],1)

if __name__=="__main__":
    unittest.main(verbosity=2)
