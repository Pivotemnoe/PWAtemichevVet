from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import smtplib
import urllib.error
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import db
from app.config import Settings
from app.security import utc_now

CAMPAIGN = "account-help-20261008-v1"
TITLES = {
    "first_pet": "Ваш электронный паспорт питомца",
    "first_record": "Начнём с одной записи о питомце?",
    "history": "История здоровья питомца — под рукой",
    "followup": "Как сейчас чувствует себя ваш питомец?",
    "date": "Напоминание о вашей важной дате",
    "install": "TemichevVet — на экране телефона",
    "billing_renewal": "Скоро продлится ваша подписка Plus",
    "billing_success": "Plus оплачен — доступ продлён",
    "billing_failed": "Не получилось продлить Plus",
    "billing_canceled": "Автопродление Plus отключено",
}
TEXTS = {
    "billing_renewal": ("Здравствуйте!\n\nВаша подписка Plus продлится {date}. "
        "Спишем 200 ₽ за следующие 30 дней с сохранённого способа оплаты.\n\n"
        "Если хотите остановить продление, нажмите «Отменить подписку» в кабинете. "
        "Оплаченный доступ останется до конца срока."),
    "billing_success": ("Здравствуйте!\n\nОплата Plus прошла: 200 ₽ за 30 дней. "
        "Доступ действует до {date}. История здоровья, важные даты и возможности Plus — в вашем кабинете."),
    "billing_failed": ("Здравствуйте!\n\nНе получилось продлить Plus. "
        "Откройте раздел подписки, чтобы посмотреть статус оплаты и следующие шаги. "
        "Ваши питомцы и записи сохранены."),
    "billing_canceled": ("Здравствуйте!\n\nАвтопродление Plus отключено. "
        "Новые списания для продления не будут создаваться. Оплаченный доступ останется до конца срока. "
        "История питомца сохранена в кабинете."),
    "first_pet": ("Здравствуйте!\n\nВсё важное о питомце удобно держать в одном месте: "
                  "историю здоровья, питание, вес и важные даты.\n\n"
                  "Ваш личный кабинет TemichevVet уже готов. Добавьте питомца — "
                  "так появится его электронный паспорт. Начать можно бесплатно."),
    "first_record": ("Здравствуйте!\n\nЭлектронный паспорт питомца уже есть. "
                     "Давайте сохраним в нём первую запись — например, вес, "
                     "наблюдение или важную дату.\n\nПотом её будет легко найти в истории здоровья."),
    "history": ("Здравствуйте!\n\nИстория здоровья вашего питомца сохранена в TemichevVet. "
                "Когда появятся новые наблюдения, вес или важные даты, добавьте их в электронный паспорт — "
                "всё будет рядом.\n\nОткройте свой кабинет, чтобы вернуться к записям."),
    "followup": ("Здравствуйте!\n\nНедавно вы сохранили оценку состояния питомца в TemichevVet. "
                 "Как он чувствует себя сейчас: лучше, так же или хуже?\n\n"
                 "Отметьте изменение — оно останется в истории здоровья рядом с предыдущей записью."),
    "date": ("Здравствуйте!\n\nНапоминаем о важной дате, которую вы сохранили для питомца: {date}.\n\n"
             "Откройте свою запись и отметьте выполнение, когда всё будет сделано."),
    "install": ("Здравствуйте!\n\nДобавьте TemichevVet на экран телефона — "
                "электронный паспорт и история здоровья питомца будут под рукой.\n\n"
                "iPhone: откройте сайт в Safari → «Поделиться» → «На экран Домой».\n"
                "Android в Chrome: меню ⋮ → «Установить приложение» или «Добавить на главный экран».\n\n"
                "Из MAX сначала откройте сайт во внешнем браузере. "
                "После установки уведомления можно отдельно включить в профиле."),
}
BUTTONS = {
    "billing_renewal":"Управлять подпиской", "billing_success":"Открыть Plus",
    "billing_failed":"Проверить подписку", "billing_canceled":"Открыть подписку",
    "first_pet": "Добавить питомца", "first_record": "Открыть электронный паспорт",
    "history": "Открыть историю здоровья", "followup": "Отметить самочувствие",
    "date": "Открыть важную дату", "install": "Как установить приложение",
}


def enabled() -> bool:
    return os.getenv("RETENTION_ENABLED", "0") == "1"


def series_enabled() -> bool:
    return os.getenv("RETENTION_WEEKLY_SERIES", "0") == "1"


def init_schema(path) -> None:
    with closing(db.connect(path)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS retention_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL DEFAULT '',
            service_enabled INTEGER NOT NULL DEFAULT 1,
            weekly_enabled INTEGER NOT NULL DEFAULT 0,
            timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS retention_channels (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            available INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, channel)
        );
        CREATE TABLE IF NOT EXISTS retention_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            campaign TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            scenario TEXT NOT NULL,
            category TEXT NOT NULL,
            source_key TEXT NOT NULL,
            channel TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            reason TEXT,
            created_at TEXT NOT NULL,
            due_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempted_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT,
            provider_message_id TEXT,
            UNIQUE(user_id, dedupe_key),
            UNIQUE(user_id, category, source_key)
        );
        CREATE INDEX IF NOT EXISTS retention_outbox_due ON retention_outbox(status,due_at);
        CREATE TABLE IF NOT EXISTS retention_activity (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            last_seen_at TEXT NOT NULL,
            last_message_id INTEGER REFERENCES retention_outbox(id) ON DELETE SET NULL,
            attribution_until TEXT
        );
        CREATE TABLE IF NOT EXISTS retention_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            message_id INTEGER REFERENCES retention_outbox(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            event_key TEXT UNIQUE,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS retention_events_user ON retention_events(user_id,created_at);
        CREATE INDEX IF NOT EXISTS retention_events_message ON retention_events(message_id,kind);
        """)
        c.commit()


def _test_user(user) -> bool:
    email = (user.get("email") or "").lower()
    return email in {"review@temichevvet.ru", "chatgpt-review@temichevvet.ru"} or bool(re.search(
        r"(^qa[+_.-]|^test[+_.-]|^smoke[+_.-]|@example\.|@test\.|@review\.)", email))


def _channels(c, user) -> list[str]:
    available = []
    if c.execute("SELECT 1 FROM external_accounts WHERE user_id=? AND provider='max'",
                 (user["id"],)).fetchone():
        available.append("max")
    if user.get("email"):
        available.append("email")
    blocked = {r["channel"] for r in c.execute(
        "SELECT channel FROM retention_channels WHERE user_id=? AND available=0", (user["id"],))}
    return [v for v in available if v not in blocked]


def _prefs(c, user, now: str) -> dict:
    first = c.execute(
        "SELECT provider FROM security_audit_events WHERE user_id=? AND event_type='auth.login_success' "
        "AND status='ok' ORDER BY created_at,id LIMIT 1", (user["id"],)).fetchone()
    choices = _channels(c, user)
    suggested = first[0] if first and first[0] in choices else (choices[0] if choices else "")
    c.execute("INSERT OR IGNORE INTO retention_preferences(user_id,channel,updated_at) VALUES(?,?,?)",
              (user["id"], suggested, now))
    return dict(c.execute("SELECT * FROM retention_preferences WHERE user_id=?", (user["id"],)).fetchone())


def preferences(settings, user) -> dict:
    with closing(db.connect(settings.database_path)) as c:
        item = _prefs(c, user, utc_now().isoformat())
        item["channels"] = _channels(c, user)
        c.commit()
    return item


def _event(c, user_id, kind, now, message_id=None, key=None, metadata=None):
    c.execute("INSERT OR IGNORE INTO retention_events"
              "(user_id,message_id,kind,created_at,event_key,metadata) VALUES(?,?,?,?,?,?)",
              (user_id, message_id, kind, now, key, json.dumps(metadata or {}, ensure_ascii=False)))


def _associated_message(c, user_id, now):
    r = c.execute("SELECT last_message_id FROM retention_activity WHERE user_id=? "
                  "AND attribution_until>=?", (user_id, now)).fetchone()
    return r[0] if r else None


def activity(settings, user, *, installed=False, device="unknown"):
    if _test_user(user):
        return
    now = utc_now()
    with closing(db.connect(settings.database_path)) as c:
        c.execute("BEGIN IMMEDIATE")
        old = c.execute("SELECT * FROM retention_activity WHERE user_id=?", (user["id"],)).fetchone()
        mid = _associated_message(c, user["id"], now.isoformat())
        if not old or datetime.fromisoformat(old["last_seen_at"]) <= now - timedelta(minutes=30):
            _event(c, user["id"], "session_open", now.isoformat(), mid,
                   metadata={"device": device})
        c.execute("INSERT INTO retention_activity(user_id,last_seen_at) VALUES(?,?) "
                  "ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
                  (user["id"], now.isoformat()))
        if installed:
            _event(c, user["id"], "pwa_launch", now.isoformat(), mid,
                   key=f"pwa:{user['id']}:{device}:{now.date()}:{mid or 0}",
                   metadata={"device": device})
        c.commit()


def track_product(settings, user_id, event_type, step, metadata=None):
    if not user_id:
        return
    mapping = {
        "first_record": "record_saved", "service_activated": "record_saved",
        "service_returned": "record_saved", "check_saved": "record_saved",
        "food_saved": "record_saved", "summary_view": "summary_view",
        "summary_export": "summary_export", "payment_success": "payment",
        "subscription_open": "plus_view",
    }
    kind = mapping.get(step)
    if not kind:
        return
    with closing(db.connect(settings.database_path)) as c:
        user = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or _test_user(dict(user)):
            return
        now = utc_now().isoformat()
        mid = _associated_message(c, user_id, now)
        payment = None
        if kind == "payment":
            opened = c.execute("SELECT min(created_at) FROM retention_events WHERE message_id=? AND kind='message_open'", (mid,)).fetchone()[0]
            payment = c.execute("SELECT id,amount_rub FROM payments WHERE user_id=? AND status='succeeded' AND paid_at>=? ORDER BY paid_at DESC LIMIT 1",
                (user_id,opened or now)).fetchone()
            if not mid or not payment:
                return
        _event(c, user_id, kind, now, mid,
               key=f"outcome:{mid}:{kind}:{payment['id']}" if payment else (f"outcome:{mid}:{kind}" if mid else None),
               metadata={"payment_id":payment["id"],"amount_rub":payment["amount_rub"]} if payment else None)
        c.commit()


def track_saved(settings, user_id, kind):
    with closing(db.connect(settings.database_path)) as c:
        now = utc_now().isoformat()
        mid = _associated_message(c, user_id, now)
        _event(c, user_id, kind, now, mid, key=f"outcome:{mid}:{kind}" if mid else None)
        c.commit()


def channel_state(settings, provider_user_id, available):
    with closing(db.connect(settings.database_path)) as c:
        r = c.execute("SELECT user_id FROM external_accounts WHERE provider='max' AND provider_user_id=?",
                      (str(provider_user_id),)).fetchone()
        if r:
            c.execute("INSERT INTO retention_channels VALUES(?,?,?,?) ON CONFLICT(user_id,channel) "
                      "DO UPDATE SET available=excluded.available,updated_at=excluded.updated_at",
                      (r[0], "max", int(available), utc_now().isoformat()))
            c.commit()


def merge_identity(cur, source_id, target_id):
    if not cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retention_outbox'").fetchone():
        return
    source=cur.execute("SELECT * FROM retention_preferences WHERE user_id=?",(source_id,)).fetchone()
    target=cur.execute("SELECT * FROM retention_preferences WHERE user_id=?",(target_id,)).fetchone()
    if source and target:
        cur.execute("UPDATE retention_preferences SET service_enabled=MIN(service_enabled,?),weekly_enabled=MIN(weekly_enabled,?) WHERE user_id=?",
                    (source['service_enabled'],source['weekly_enabled'],target_id))
        cur.execute("DELETE FROM retention_preferences WHERE user_id=?",(source_id,))
    elif source:
        cur.execute("UPDATE retention_preferences SET user_id=? WHERE user_id=?",(target_id,source_id))
    for row in cur.execute("SELECT * FROM retention_outbox WHERE user_id=?",(source_id,)).fetchall():
        collision=cur.execute("SELECT 1 FROM retention_outbox WHERE user_id=? AND (dedupe_key=? OR (category=? AND source_key=?))",
                              (target_id,row['dedupe_key'],row['category'],row['source_key'])).fetchone()
        suffix=f":merged:{row['id']}" if collision else ""
        cur.execute("UPDATE retention_outbox SET user_id=?,dedupe_key=?,source_key=? WHERE id=?",
                    (target_id,row['dedupe_key']+suffix,row['source_key']+suffix,row['id']))
    cur.execute("UPDATE retention_events SET user_id=? WHERE user_id=?",(target_id,source_id))
    source=cur.execute("SELECT * FROM retention_activity WHERE user_id=?",(source_id,)).fetchone()
    target=cur.execute("SELECT * FROM retention_activity WHERE user_id=?",(target_id,)).fetchone()
    if source:
        if not target or source['last_seen_at']>target['last_seen_at']:
            cur.execute("INSERT INTO retention_activity VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_message_id=excluded.last_message_id,attribution_until=excluded.attribution_until",
                (target_id,source['last_seen_at'],source['last_message_id'],source['attribution_until']))
        cur.execute("DELETE FROM retention_activity WHERE user_id=?",(source_id,))
    for row in cur.execute("SELECT * FROM retention_channels WHERE user_id=?",(source_id,)).fetchall():
        cur.execute("INSERT INTO retention_channels VALUES(?,?,?,?) ON CONFLICT(user_id,channel) DO UPDATE SET available=MIN(available,excluded.available)",
                    (target_id,row['channel'],row['available'],row['updated_at']))
    cur.execute("DELETE FROM retention_channels WHERE user_id=?",(source_id,))
    if cur.execute("SELECT 1 FROM retention_outbox WHERE user_id=? AND campaign=? AND status='accepted'",(target_id,CAMPAIGN)).fetchone():
        cur.execute("UPDATE retention_outbox SET status='cancelled',reason='account_merged' WHERE user_id=? AND campaign=? AND status='queued' AND category='general'",
                    (target_id,CAMPAIGN))


def _quiet_due(now, tz):
    try:
        zone = ZoneInfo(tz)
    except Exception:
        zone = ZoneInfo("Europe/Moscow")
    local = now.astimezone(zone)
    if local.hour < 10:
        local = local.replace(hour=10, minute=0, second=0, microsecond=0)
    elif local.hour >= 20:
        local = (local + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def enqueue(settings, now=None) -> dict:
    now = now or utc_now()
    result = {"created": 0, "existing": 0, "excluded": 0}
    with closing(db.connect(settings.database_path)) as c:
        c.execute("BEGIN IMMEDIATE")
        users = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id")]
        for user in users:
            if _test_user(user):
                result["excluded"] += 1
                continue
            prefs = _prefs(c, user, now.isoformat())
            if not prefs["service_enabled"]:
                result["excluded"] += 1
                continue
            uid = user["id"]
            is_initial = not c.execute(
                "SELECT 1 FROM retention_outbox WHERE user_id=? AND dedupe_key=?",
                (uid, CAMPAIGN)).fetchone()
            pet = c.execute("SELECT id FROM pets WHERE owner_id=? ORDER BY id LIMIT 1", (uid,)).fetchone()
            first = c.execute("SELECT 1 FROM funnel_events WHERE user_id=? AND "
                              "event_type='service.first_record_saved' LIMIT 1", (uid,)).fetchone()
            has_history = bool(first or c.execute(
                "SELECT 1 FROM pet_history h JOIN pets p ON p.id=h.pet_id WHERE p.owner_id=? LIMIT 1",
                (uid,)).fetchone())
            followup = c.execute("""
                SELECT f.id,f.pet_id,f.created_at FROM triage_followups f
                WHERE f.user_id=? AND f.status='scheduled' AND f.scheduled_at<=?
                AND f.created_at>=? AND f.push_notified_at IS NULL
                AND NOT EXISTS(SELECT 1 FROM retention_outbox o
                    WHERE o.user_id=f.user_id AND o.category='followup' AND o.source_key='f:'||f.id)
                ORDER BY f.scheduled_at LIMIT 1
            """, (uid, now.isoformat(), (now-timedelta(hours=48)).isoformat())).fetchone()
            reminder = c.execute("""
                SELECT r.id,r.due_date,r.due_time FROM reminders r
                WHERE r.user_id=? AND r.is_active=1 AND r.due_date=?
                AND (r.due_time IS NULL OR r.due_time='' OR r.due_time<=?)
                AND NOT EXISTS(SELECT 1 FROM retention_outbox o WHERE o.user_id=r.user_id
                  AND o.category='date' AND o.source_key='r:'||r.id||':'||r.due_date)
                ORDER BY r.id LIMIT 1
            """, (uid, now.astimezone(ZoneInfo(prefs["timezone"])).date().isoformat(),
                  now.astimezone(ZoneInfo(prefs["timezone"])).strftime("%H:%M"))).fetchone()
            target = {"action": "pets"}
            category, scenario, source, due = "general", "history", CAMPAIGN, now
            if followup:
                category, scenario, source = "followup", "followup", f"f:{followup['id']}"
                target = {"action": "home", "followup_id": followup["id"]}
            elif reminder:
                category, scenario, source = "date", "date", f"r:{reminder['id']}:{reminder['due_date']}"
                target = {"action": "reminders", "reminder_id": reminder["id"], "date": reminder["due_date"]}
            elif is_initial:
                scenario = "history" if has_history else ("first_record" if pet else "first_pet")
                due = max(now, datetime.fromisoformat(user["created_at"]) + timedelta(hours=24))
            elif series_enabled() and prefs["weekly_enabled"]:
                count = c.execute("SELECT count(*) FROM retention_outbox WHERE user_id=? "
                                  "AND category='general' AND status='accepted'", (uid,)).fetchone()[0]
                if count >= 3:
                    continue
                recent = c.execute("SELECT id FROM retention_outbox WHERE user_id=? AND category='general' AND status='accepted' ORDER BY sent_at DESC LIMIT 2", (uid,)).fetchall()
                if len(recent)==2 and all(not c.execute("SELECT 1 FROM retention_events WHERE message_id=? AND kind='message_open'", (r[0],)).fetchone() for r in recent):
                    continue
                last = c.execute("SELECT max(last_seen_at) FROM retention_activity WHERE user_id=?", (uid,)).fetchone()[0]
                if last and datetime.fromisoformat(last) > now - timedelta(days=7):
                    continue
                installed = c.execute("SELECT 1 FROM retention_events WHERE user_id=? AND kind='pwa_launch'",
                                      (uid,)).fetchone()
                scenario = "install" if has_history and not installed and count == 1 else "history"
                source = f"weekly:{count}"
                target = {"action": "install" if scenario == "install" else "pets"}
            else:
                continue
            dedupe = CAMPAIGN if is_initial else source
            due = _quiet_due(due, prefs["timezone"]) if category == "general" else due
            if category == "general":
                last = c.execute("SELECT max(COALESCE(sent_at,attempted_at)) FROM retention_outbox "
                                 "WHERE user_id=? AND status IN ('accepted','sending','unknown')", (uid,)).fetchone()[0]
                if last:
                    due = _quiet_due(max(due, datetime.fromisoformat(last)+timedelta(days=7)), prefs["timezone"])
            channels = _channels(c, user)
            reason = None if prefs["channel"] in channels else "channel_unavailable"
            payload = {**target, "had_history": has_history}
            expiry = due + timedelta(days=7) if category == "general" else now + timedelta(hours=24)
            cur = c.execute("""
                INSERT OR IGNORE INTO retention_outbox(user_id,campaign,dedupe_key,scenario,category,
                source_key,channel,payload,status,reason,created_at,due_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (uid,CAMPAIGN,dedupe,scenario,category,source,prefs["channel"],
                  json.dumps(payload,ensure_ascii=False),"skipped" if reason else "queued",reason,
                  now.isoformat(),due.isoformat(),expiry.isoformat()))
            result["created" if cur.rowcount else "existing"] += 1
        c.commit()
    return result


def signature(settings, mid):
    return hmac.new(settings.session_secret.encode(), f"retention-v1:{mid}".encode(), hashlib.sha256).hexdigest()


def resolve(settings, token, user_id=None):
    try:
        mid, sig = token.split(".", 1)
        mid = int(mid)
    except Exception:
        raise HTTPException(404, "message_link_not_found") from None
    if not hmac.compare_digest(signature(settings, mid), sig):
        raise HTTPException(404, "message_link_not_found")
    with closing(db.connect(settings.database_path)) as c:
        r = c.execute("SELECT * FROM retention_outbox WHERE id=?", (mid,)).fetchone()
    if not r or (user_id is not None and r["user_id"] != user_id):
        raise HTTPException(404, "message_link_not_found")
    return dict(r)


def message_urls(settings, row):
    from app.max_auth import _app_url
    token = f"{row['id']}.{signature(settings,row['id'])}"
    base = _app_url(settings)
    return f"{base}/r/{token}", f"{base}/r/{token}/stop"


def send_email(settings, row, user):
    if not settings.smtp_host:
        raise RuntimeError("email_not_configured")
    url, stop = message_urls(settings,row)
    payload = json.loads(row["payload"])
    body = TEXTS[row["scenario"]].format(date=payload.get("date",""))
    m = EmailMessage()
    m["Subject"] = TITLES[row["scenario"]]
    m["From"] = formataddr(("TemichevVet", parseaddr(settings.smtp_from_email or settings.smtp_username)[1]))
    m["To"] = user["email"]
    m["Message-ID"] = make_msgid(domain="temichevvet.ru")
    m["List-Unsubscribe"] = f"<{stop}>"
    m["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    m.set_content(f"{body}\n\n{BUTTONS[row['scenario']]}: {url}\n\nTemichevVet\n"
                  f"Вы получили сообщение о своём кабинете. Настроить или отключить сообщения: {stop}")
    paragraphs = "".join(f"<p>{html.escape(p).replace(chr(10),'<br>')}</p>" for p in body.split("\n\n"))
    m.add_alternative(
        '<!doctype html><html lang="ru"><body style="font-family:Arial,sans-serif;line-height:1.6;'
        'max-width:600px;margin:24px auto;padding:16px;color:#183832">'
        f'<h2>TemichevVet</h2>{paragraphs}<p><a href="{html.escape(url)}" '
        'style="display:inline-block;background:#146e5b;color:white;padding:12px 18px;'
        f'border-radius:10px;text-decoration:none">{html.escape(BUTTONS[row["scenario"]])}</a></p>'
        f'<p>TemichevVet</p><p style="font-size:12px">Сообщение о вашем личном кабинете. '
        f'<a href="{html.escape(stop)}">Настроить или отключить сообщения</a></p></body></html>',
        subtype="html")
    cls = smtplib.SMTP_SSL if int(settings.smtp_port)==465 else smtplib.SMTP
    with cls(settings.smtp_host,settings.smtp_port,timeout=12) as smtp:
        if settings.smtp_use_tls and cls is smtplib.SMTP:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username,settings.smtp_password)
        refused = smtp.send_message(m)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    return m["Message-ID"]


class DeliveryUncertain(Exception):
    pass


def send_max(settings, row, user):
    from app.max_auth import _max_request
    with closing(db.connect(settings.database_path)) as c:
        target = c.execute("SELECT provider_user_id FROM external_accounts WHERE user_id=? AND provider='max'",
                           (user["id"],)).fetchone()
    if not target:
        raise RuntimeError("max_account_missing")
    url, stop = message_urls(settings,row)
    payload = json.loads(row["payload"])
    body = TEXTS[row["scenario"]].format(date=payload.get("date","")).replace("Здравствуйте!\n\n","")
    try:
        result = _max_request(settings,"POST","/messages",{
            "text":body,
            "attachments":[{"type":"inline_keyboard","payload":{"buttons":[
                [{"type":"link","text":BUTTONS[row["scenario"]],"url":url}],
                [{"type":"link","text":"Настройки сообщений","url":stop}]
            ]}}],
        },query={"user_id":int(target[0])})
    except RuntimeError as exc:
        if isinstance(exc.__cause__,urllib.error.HTTPError):
            raise exc.__cause__ from None
        raise
    except json.JSONDecodeError:
        raise DeliveryUncertain("max_receipt_invalid") from None
    message = result.get("message") or result
    receipt = str((message.get("body") or {}).get("mid") or message.get("message_id") or "")
    if not receipt:
        raise DeliveryUncertain("max_receipt_missing")
    return receipt


def _cancel_reason(c, row, now):
    p = c.execute("SELECT * FROM retention_preferences WHERE user_id=?", (row["user_id"],)).fetchone()
    user = c.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
    if not user or not p or not p["service_enabled"]:
        return "disabled"
    if row["dedupe_key"] != CAMPAIGN and row["category"]=="general" and not p["weekly_enabled"]:
        return "weekly_disabled"
    if row["channel"] != p["channel"] or row["channel"] not in _channels(c,dict(user)):
        return "channel_unavailable"
    if row["expires_at"]<=now.isoformat():
        return "expired"
    payload = json.loads(row["payload"])
    if row["category"]=="followup":
        f = c.execute("SELECT * FROM triage_followups WHERE id=? AND user_id=?",
                      (payload["followup_id"],row["user_id"])).fetchone()
        if not f or f["status"]!="scheduled" or f["push_notified_at"]:
            return "followup_completed"
        if f["created_at"] < (now-timedelta(hours=48)).isoformat():
            return "followup_expired"
    elif row["category"]=="date":
        r = c.execute("SELECT * FROM reminders WHERE id=? AND user_id=?",
                      (payload["reminder_id"],row["user_id"])).fetchone()
        if not r or not r["is_active"] or r["due_date"]!=payload["date"]:
            return "date_changed"
    elif row["category"]=="billing":
        from app.billing import notice_cancel_reason
        return notice_cancel_reason(c,row,payload)
    else:
        a = c.execute("SELECT last_seen_at FROM retention_activity WHERE user_id=?", (row["user_id"],)).fetchone()
        if a and a[0] > row["created_at"]:
            return "user_returned"
        if c.execute("SELECT 1 FROM funnel_events WHERE user_id=? AND created_at>? AND status='ok' "
                     "AND step IN ('first_record','service_activated','service_returned','check_saved','food_saved','login_success')",
                     (row["user_id"],row["created_at"])).fetchone():
            return "user_returned"
        if row["scenario"] in {"first_pet","first_record"} and c.execute(
            "SELECT 1 FROM funnel_events WHERE user_id=? AND event_type='service.first_record_saved'",
            (row["user_id"],)).fetchone():
            return "first_record_saved"
        if row["scenario"]=="first_pet" and c.execute(
            "SELECT 1 FROM pets WHERE owner_id=?", (row["user_id"],)).fetchone():
            return "pet_added"
        if row["scenario"]=="install" and c.execute(
            "SELECT 1 FROM retention_events WHERE user_id=? AND kind='pwa_launch'", (row["user_id"],)).fetchone():
            return "pwa_already_launched"
        last = c.execute("SELECT max(COALESCE(sent_at,attempted_at)) FROM retention_outbox "
                         "WHERE user_id=? AND id!=? AND status IN ('accepted','sending','unknown')",
                         (row["user_id"],row["id"])).fetchone()[0]
        if last and datetime.fromisoformat(last)>now-timedelta(days=7):
            return "weekly_limit"
    return None


def run(settings, *, limit=10, dry_run=False, now=None):
    now = now or utc_now()
    if not enabled() and not dry_run:
        return {"enabled":False,"accepted":0}
    created = enqueue(settings,now)
    results = {"enabled":enabled(),"dry_run":dry_run,**created,"accepted":0,"failed":0,"unknown":0,"cancelled":0}
    if dry_run:
        return results
    with closing(db.connect(settings.database_path)) as c:
        c.execute("UPDATE retention_outbox SET status='unknown',reason='worker_interrupted' "
                  "WHERE status='sending' AND attempted_at<?", ((now-timedelta(minutes=10)).isoformat(),))
        c.commit()
    for _ in range(min(max(limit,1),50)):
        with closing(db.connect(settings.database_path)) as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("SELECT * FROM retention_outbox WHERE status='queued' AND due_at<=? "
                          "ORDER BY CASE category WHEN 'followup' THEN 0 WHEN 'date' THEN 1 WHEN 'billing' THEN 2 ELSE 3 END,due_at,id LIMIT 1",
                          (now.isoformat(),)).fetchone()
            if not r:
                c.commit()
                break
            row = dict(r)
            reason = _cancel_reason(c,row,now)
            if reason=="weekly_limit":
                c.execute("UPDATE retention_outbox SET due_at=? WHERE id=?",
                          (_quiet_due(now+timedelta(days=7),"Europe/Moscow").isoformat(),row["id"]))
                c.commit()
                continue
            if reason:
                c.execute("UPDATE retention_outbox SET status='cancelled',reason=? WHERE id=?", (reason,row["id"]))
                c.commit()
                results["cancelled"]+=1
                continue
            if row["category"]=="general":
                prefs = c.execute("SELECT timezone FROM retention_preferences WHERE user_id=?", (row["user_id"],)).fetchone()
                due = _quiet_due(now,prefs[0])
                if due>now:
                    c.execute("UPDATE retention_outbox SET due_at=? WHERE id=?", (due.isoformat(),row["id"]))
                    c.commit()
                    continue
            user = dict(c.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone())
            c.execute("UPDATE retention_outbox SET status='sending',attempts=attempts+1,attempted_at=? WHERE id=?",
                      (now.isoformat(),row["id"]))
            c.commit()
        status, reason, provider = "accepted", None, None
        try:
            provider = (send_max if row["channel"]=="max" else send_email)(settings,row,user)
        except urllib.error.HTTPError as exc:
            reason = f"http_{exc.code}"
            if exc.code==429 and row["attempts"]<2:
                status = "queued"
            elif exc.code in {400,401,403,404}:
                status = "failed"
                if exc.code in {403,404}:
                    with closing(db.connect(settings.database_path)) as c:
                        c.execute("INSERT INTO retention_channels VALUES(?,?,0,?) ON CONFLICT(user_id,channel) "
                                  "DO UPDATE SET available=0,updated_at=excluded.updated_at",
                                  (row["user_id"],row["channel"],now.isoformat()))
                        c.commit()
            else:
                status = "unknown"
        except (smtplib.SMTPRecipientsRefused,smtplib.SMTPAuthenticationError,ValueError,RuntimeError) as exc:
            status, reason = "failed", type(exc).__name__
        except Exception as exc:
            # Timeout/connection loss after send can mean accepted: do not resend blindly.
            status, reason = "unknown", type(exc).__name__
        with closing(db.connect(settings.database_path)) as c:
            c.execute("UPDATE retention_outbox SET status=?,reason=?,provider_message_id=?,sent_at=?,"
                      "due_at=CASE WHEN ?='queued' THEN ? ELSE due_at END WHERE id=?",
                      (status,reason,provider,now.isoformat() if status=="accepted" else None,status,
                       (now+timedelta(minutes=20)).isoformat(),row["id"]))
            c.commit()
        if status in results:
            results[status]+=1
    return results


class PreferenceInput(BaseModel):
    channel: str = Field(max_length=10)
    service_enabled: bool
    weekly_enabled: bool = False
    timezone: str = Field(default="Europe/Moscow",max_length=60)


class ActivityInput(BaseModel):
    installed: bool = False
    device: str = Field(default="unknown",max_length=80)
    token: str = Field(default="",max_length=90)
    kind: Literal["", "install_shown", "install_instruction", "install_accepted"] = ""


def stats(settings):
    now = utc_now()
    with closing(db.connect(settings.database_path)) as c:
        result = {"generated_at":now.isoformat(),"enabled":enabled(),"series_enabled":series_enabled(),
                  "weekly_limit":1,"windows":{},"registration":[]}
        for days in (7,30):
            since = (now-timedelta(days=days)).isoformat()
            users=[dict(r) for r in c.execute("SELECT * FROM users WHERE created_at>=?",(since,)) if not _test_user(dict(r))]
            result["registration"].append({"period":f"{days} дней","registered":len(users),
                "first_login":sum(bool(c.execute("SELECT 1 FROM sessions WHERE user_id=? LIMIT 1",(u["id"],)).fetchone()) for u in users),
                "first_record":sum(bool(c.execute("SELECT 1 FROM funnel_events WHERE user_id=? AND event_type='service.first_record_saved' LIMIT 1",(u["id"],)).fetchone()) for u in users),
                "without_pet":sum(not c.execute("SELECT 1 FROM pets WHERE owner_id=? LIMIT 1",(u["id"],)).fetchone() for u in users),
                "paid":sum(bool(c.execute("SELECT 1 FROM payments WHERE user_id=? AND status='succeeded' LIMIT 1",(u["id"],)).fetchone()) for u in users)})
            rows = [dict(r) for r in c.execute("SELECT * FROM retention_outbox WHERE created_at>=?",(since,))]
            accepted = [dict(r) for r in c.execute("SELECT * FROM retention_outbox WHERE sent_at>=? AND status='accepted'",(since,))]
            mids = {r["id"] for r in accepted}
            events = [dict(r) for r in c.execute("SELECT * FROM retention_events WHERE created_at>=?",(since,))]
            sent_dates = {r["id"]: datetime.fromisoformat(r["sent_at"]) for r in accepted}
            cohort_events = [e for e in events if e["message_id"] in mids and
                datetime.fromisoformat(e["created_at"]) <= sent_dates[e["message_id"]]+timedelta(days=7)]
            def event_users(kind):
                return len({e["user_id"] for e in cohort_events if e["kind"]==kind})
            def cut(field):
                out=[]
                for value in sorted({r[field] for r in rows+accepted}):
                    allrows=[r for r in rows if r[field]==value]
                    sent=[r for r in accepted if r[field]==value]
                    ids={r["id"] for r in sent}
                    ev=[e for e in cohort_events if e["message_id"] in ids]
                    out.append({"name":value,"eligible_users":len({r["user_id"] for r in allrows}),
                        "queued":sum(r["status"]=="queued" for r in allrows),"accepted":len(sent),
                        "failed":sum(r["status"]=="failed" for r in allrows),
                        "unknown":sum(r["status"]=="unknown" for r in allrows),
                        "returned_users":len({e["user_id"] for e in ev if e["kind"]=="message_open"}),
                    "action_users":len({e["user_id"] for e in ev if e["kind"] in {"record_saved","followup_answer","reminder_closed"}}),
                        "paid_users":len({e["user_id"] for e in ev if e["kind"]=="payment"})})
                return out
            denominator=len({r["user_id"] for r in accepted})
            result["windows"][str(days)]={
                "eligible_users":len({r["user_id"] for r in rows}), "messages":len(rows),
                "queued":sum(r["status"]=="queued" for r in rows), "accepted":len(accepted),
                "accepted_users":denominator,"failed":sum(r["status"]=="failed" for r in rows),
                "unknown":sum(r["status"]=="unknown" for r in rows),
                "cancelled":sum(r["status"]=="cancelled" for r in rows),
                "skipped":sum(r["status"]=="skipped" for r in rows),
                "returned_users":event_users("message_open"),"record_users":event_users("record_saved"),
                "answer_users":event_users("followup_answer"),"date_users":event_users("reminder_closed"),
                "pwa_users":event_users("pwa_launch"),"plus_users":event_users("plus_view"),
                "paid_users":event_users("payment"),"unsubscribed_users":event_users("unsubscribe"),
                "push_users":event_users("push_enabled"),
                "install_shown_users":len({e["user_id"] for e in events if e["kind"]=="install_shown"}),
                "install_instruction_users":len({e["user_id"] for e in events if e["kind"]=="install_instruction"}),
                "install_accepted_users":len({e["user_id"] for e in events if e["kind"]=="install_accepted"}),
                "all_pwa_users":len({e["user_id"] for e in events if e["kind"]=="pwa_launch"}),
                "all_push_users":len({e["user_id"] for e in events if e["kind"]=="push_enabled"}),
                "return_percent":round(event_users("message_open")*100/denominator,1) if denominator else None,
                "by_channel":cut("channel"),"by_scenario":cut("scenario"),
                "session_users":len({e["user_id"] for e in events if e["kind"]=="session_open"}),
            }
        result["reasons"]=[dict(r) for r in c.execute(
            "SELECT status,reason,count(*) count FROM retention_outbox WHERE reason IS NOT NULL GROUP BY status,reason")]
        result["recent"]=[dict(r) for r in c.execute(
            "SELECT id,user_id,scenario,channel,status,reason,due_at,sent_at,attempts "
            "FROM retention_outbox ORDER BY id DESC LIMIT 50")]
        result["cohorts"]=[]
        for day in (1,7,30):
            users = [dict(r) for r in c.execute("SELECT * FROM users WHERE created_at>=? AND created_at<=?",
                ((now-timedelta(days=90)).isoformat(),(now-timedelta(days=day+1)).isoformat())) if not _test_user(dict(r))]
            measured=[u for u in users if c.execute("SELECT 1 FROM retention_events WHERE user_id=? AND kind='session_open' "
                                                   "AND created_at<?",(u["id"],(datetime.fromisoformat(u["created_at"])+timedelta(days=1)).isoformat())).fetchone()]
            returned=sum(bool(c.execute("SELECT 1 FROM retention_events WHERE user_id=? AND kind='session_open' "
                  "AND created_at>=? AND created_at<? LIMIT 1",(u["id"],
                  (datetime.fromisoformat(u["created_at"])+timedelta(days=day)).isoformat(),
                  (datetime.fromisoformat(u["created_at"])+timedelta(days=day+1)).isoformat())).fetchone()) for u in measured)
            result["cohorts"].append({"day":f"D{day}","eligible":len(measured),"returned":returned,
                                      "percent":round(returned*100/len(measured),1) if measured else None})
        return result


def install_routes(app,settings,current_user,current_admin,require_monitoring):
    @app.get("/api/retention/preferences")
    def get_preferences(user:dict=Depends(current_user)):
        return preferences(settings,user)

    @app.post("/api/retention/preferences")
    def update_preferences(payload:PreferenceInput,user:dict=Depends(current_user)):
        try:
            ZoneInfo(payload.timezone)
        except Exception:
            raise HTTPException(400,"invalid_timezone") from None
        with closing(db.connect(settings.database_path)) as c:
            if payload.channel not in _channels(c,user):
                raise HTTPException(400,"channel_unavailable")
            _prefs(c,user,utc_now().isoformat())
            c.execute("UPDATE retention_preferences SET channel=?,service_enabled=?,weekly_enabled=?,timezone=?,updated_at=? WHERE user_id=?",
                (payload.channel,int(payload.service_enabled),int(payload.weekly_enabled),payload.timezone,utc_now().isoformat(),user["id"]))
            c.commit()
        return preferences(settings,user)

    @app.post("/api/retention/activity")
    def track_activity(payload:ActivityInput,user:dict=Depends(current_user)):
        target=None
        if payload.token:
            row=resolve(settings,payload.token,user["id"])
            if row["status"]!="accepted":
                raise HTTPException(404,"message_link_not_found")
            target=json.loads(row["payload"])
            now=utc_now()
            with closing(db.connect(settings.database_path)) as c:
                c.execute("BEGIN IMMEDIATE")
                old=c.execute("SELECT last_seen_at FROM retention_activity WHERE user_id=?",(user["id"],)).fetchone()
                if not old or datetime.fromisoformat(old[0])<=now-timedelta(minutes=30):
                    _event(c,user["id"],"session_open",now.isoformat(),row["id"])
                c.execute("INSERT INTO retention_activity(user_id,last_seen_at,last_message_id,attribution_until) VALUES(?,?,?,?) "
                          "ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_message_id=excluded.last_message_id,attribution_until=excluded.attribution_until",
                          (user["id"],now.isoformat(),row["id"],(datetime.fromisoformat(row["sent_at"])+timedelta(days=7)).isoformat()))
                _event(c,user["id"],"message_open",now.isoformat(),row["id"],key=f"open:{row['id']}")
                c.commit()
        activity(settings,user,installed=payload.installed,device=payload.device)
        if payload.kind:
            with closing(db.connect(settings.database_path)) as c:
                _event(c,user["id"],payload.kind,utc_now().isoformat(),
                    _associated_message(c,user["id"],utc_now().isoformat()),
                    key=f"ui:{user['id']}:{payload.device}:{payload.kind}:{utc_now().date()}")
                c.commit()
        return {"ok":True,"target":target}

    @app.get("/r/{token}")
    def open_message(token:str):
        resolve(settings,token)
        return RedirectResponse("/app?retention="+token,status_code=303,
                                headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

    @app.get("/r/{token}/stop",response_class=HTMLResponse)
    def stop_form(token:str):
        resolve(settings,token)
        return HTMLResponse('<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Сообщения TemichevVet</title><body style="font-family:Arial;max-width:560px;margin:40px auto;padding:20px">'
            '<h1>Сообщения TemichevVet</h1><p>Можно отключить сообщения на почту и в MAX. '
            'Электронный паспорт и история питомца останутся в кабинете.</p>'
            f'<form method="post"><button type="submit">Отключить сообщения</button></form>'
            '<p><a href="/app?action=notifications">Выбрать канал и настроить сообщения в кабинете</a></p></body></html>',
            headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

    @app.post("/r/{token}/stop",response_class=HTMLResponse)
    def stop_messages(token:str):
        row=resolve(settings,token)
        with closing(db.connect(settings.database_path)) as c:
            c.execute("UPDATE retention_preferences SET service_enabled=0,weekly_enabled=0,updated_at=? WHERE user_id=?",
                      (utc_now().isoformat(),row["user_id"]))
            c.execute("UPDATE retention_outbox SET status='cancelled',reason='disabled' WHERE user_id=? AND status='queued'",
                      (row["user_id"],))
            _event(c,row["user_id"],"unsubscribe",utc_now().isoformat(),row["id"],key=f"stop:{row['id']}")
            c.commit()
        return HTMLResponse('<html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<p>Сообщения отключены. Ваши записи сохранены.</p><a href="/app">Открыть TemichevVet</a></html>',
            headers={"Cache-Control":"no-store"})

    @app.get("/api/admin/retention")
    def admin_stats(_:dict=Depends(current_admin)):
        return stats(settings)

    @app.post("/api/internal/retention/send")
    def deliver(limit:int=10,dry_run:bool=False,_:None=Depends(require_monitoring)):
        return run(settings,limit=limit,dry_run=dry_run)
