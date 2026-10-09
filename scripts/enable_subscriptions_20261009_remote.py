"""Enable the deployed opt-in subscription; never create a payment or consent."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.error import HTTPError

root = Path('/opt/temichevvet/pwa')
os.chdir(root)
assert subprocess.check_output(['hostname'], text=True).strip() == 'msk-1-vm-d817'
expected = {
    'app/main.py': '4a7b5c5737193fc133e29a507368d620bc3dbaac538a4b47f7aa24fd810b95d2',
    'app/billing.py': 'b5c0f817527c7ef48fb6e18d792a701ba74ff960e0623748b6d82f627c797e44',
    'app/payments/yookassa.py': 'bc85429c7510e3f0a5c64ed3f4ed121de38165dfb29e25ec0e73f336fb668309',
    'web/app.js': 'd3d0ac91bfb0502d46ebad1cad7d51afaaf6b1975283e8583ba641d0377e55f1',
}
assert all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in expected.items()), 'production code changed'
keys = {'BILLING_SUBSCRIPTIONS_ENABLED', 'BILLING_AUTORENEW_ENABLED'}
envfile = root / '.env'
env_stat = envfile.stat()
original = envfile.read_bytes()
values = {k.strip(): v.strip().strip('"').strip("'") for line in original.decode().splitlines()
          if '=' in line and not line.lstrip().startswith('#') for k, v in [line.split('=', 1)]}
assert values.get('YOOKASSA_SHOP_ID') == '1376677'
assert values.get('YOOKASSA_SECRET_KEY')
assert all(values.get(k, '0') == '0' for k in keys), 'subscription mode already changed'
units = ['nginx', 'temichevvet_bot.service', 'temichevvet_pwa_followups.timer', 'temichevvet_pwa_monitor.timer']
def states():
    return {u: subprocess.run(['systemctl', 'is-active', u], text=True, capture_output=True).stdout.strip() for u in units}
before = states()
assert before['nginx'] == 'active'
assert subprocess.run(['systemctl', 'is-active', '--quiet', 'temichevvet_pwa.service']).returncode == 0
tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = Path('/opt/temichevvet/backups/subscription-enable-' + tag)
backup.mkdir(mode=0o700)
shutil.copy2(envfile, backup / 'env')
os.chmod(backup / 'env', 0o600)
dbpath = '/opt/temichevvet/data/pwa.db'
def snapshot(c):
    return {'billing': {t: c.execute('SELECT count(*) FROM ' + t).fetchone()[0]
                        for t in ['billing_agreements', 'billing_charges', 'billing_events']},
            'paid': {r[0]: (r[1], r[2]) for r in c.execute("SELECT id,period_end,quota_total FROM subscriptions WHERE plan!='free'")}}
with closing(sqlite3.connect('file:' + dbpath + '?mode=ro', uri=True)) as c:
    c.execute('PRAGMA query_only=ON')
    assert c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    data_before = snapshot(c)
    assert not any(data_before['billing'].values()), 'existing billing activity requires a separate review'
    with closing(sqlite3.connect(backup / 'pwa.db')) as dest:
        c.backup(dest)
os.chmod(backup / 'pwa.db', 0o600)

def restart():
    subprocess.run(['systemctl', 'restart', 'temichevvet_pwa.service'], check=True)
    for _ in range(40):
        try:
            with urlopen('http://127.0.0.1:8081/api/health', timeout=3) as r:
                health = json.load(r)
            if health.get('ok') is True or health.get('status') in {'ok', 'healthy'}:
                return health
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError('PWA did not recover')

def read_http(path):
    try:
        with urlopen('http://127.0.0.1:8081' + path, timeout=10) as r:
            return r.status, r.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()

def replace_env(content):
    temp = envfile.with_name('.env.subscription-enable')
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, env_stat.st_mode & 0o777)
    with os.fdopen(fd, 'wb') as f:
        os.fchown(f.fileno(), env_stat.st_uid, env_stat.st_gid)
        os.fchmod(f.fileno(), env_stat.st_mode & 0o777)
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, envfile)

changed = False
try:
    lines = [line for line in original.decode().splitlines() if line.split('=', 1)[0].strip() not in keys]
    updated = ('\n'.join(lines) + '\nBILLING_SUBSCRIPTIONS_ENABLED=1\nBILLING_AUTORENEW_ENABLED=1\n').encode()
    replace_env(updated)
    changed = True
    health = restart()
    pid = subprocess.check_output(['systemctl', 'show', 'temichevvet_pwa.service', '-p', 'MainPID', '--value'], text=True).strip()
    process_env = dict(entry.split(b'=', 1) for entry in Path('/proc/' + pid + '/environ').read_bytes().split(b'\0') if b'=' in entry)
    assert all(process_env.get(k.encode()) == b'1' for k in keys), 'running process flags differ'
    command = 'from app.config import get_settings; from app.billing import stats; import json; print(json.dumps(stats(get_settings())))'
    billing_stats = json.loads(subprocess.check_output([str(root / '.venv/bin/python'), '-c', command], text=True))
    assert billing_stats['enabled'] is True and billing_stats['renewals_enabled'] is True
    for path in ['/app', '/admin', '/offer']:
        assert read_http(path)[0] == 200
    landing = read_http('/app')[1]
    assert '200 ₽ каждые 30 дней' in landing
    assert 'Оплата разовая, автосписаний нет' not in landing
    assert 'отдельного согласия' in read_http('/offer')[1]
    assert read_http('/api/billing/subscription')[0] == 401
    assert read_http('/api/admin/billing')[0] == 401
    assert states() == before, 'neighbor services changed'
    with closing(sqlite3.connect('file:' + dbpath + '?mode=ro', uri=True)) as c:
        c.execute('PRAGMA query_only=ON')
        assert c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        data_after = snapshot(c)
        assert data_after == data_before, 'billing activity or paid access changed during enablement'
    assert all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in expected.items())
    receipt = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'shop_id': '1376677',
               'backup': str(backup), 'subscriptions_enabled': True, 'autorenew_enabled': True,
               'running_process_flags_verified': True, 'paid_periods_preserved': True,
               'billing_counts': data_after['billing'], 'quick_check': 'ok', 'foreign_key_violations': 0,
               'neighbor_services': before, 'pwa_service': 'active',
               'retention_flags': {k: values.get(k, '0') for k in ['RETENTION_ENABLED', 'RETENTION_WEEKLY_SERIES']},
               'payment_created': False, 'live_charge_or_renewal_verified': False, 'application_hashes': expected}
    (backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
except Exception:
    if changed:
        replace_env(original)
        restart()
        print(json.dumps({'rolled_back': True, 'backup': str(backup)}))
    raise
