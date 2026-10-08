"""Local fictional preview; disables all outbound providers."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(APP_ENV='development',APP_BASE_URL='http://127.0.0.1:8096',
    DATABASE_PATH='/tmp/tvv-retention-preview.db',DEV_AUTH_CODE_LOG='1',
    SMTP_HOST='',MAX_BOT_TOKEN='',TELEGRAM_AUTH_SECRET='',BOT_DATABASE_PATH='',
    YOOKASSA_SHOP_ID='',YOOKASSA_SECRET_KEY='',RETENTION_ENABLED='0',
    RETENTION_WEEKLY_SERIES='0',ADMIN_USERNAME='preview',
    SESSION_SECRET='local-fictional-preview-only-key-123456789')
from app.security import make_password_hash
os.environ['ADMIN_PASSWORD_HASH']=make_password_hash('retention-preview-pass')
from app import main,db,retention
from contextlib import closing
from datetime import timedelta
user=db.get_or_create_user_by_email(main.settings.database_path,'owner@mail.ru')
with closing(db.connect(main.settings.database_path)) as c:
    c.execute('UPDATE users SET created_at=? WHERE id=?',((main.utc_now()-timedelta(days=3)).isoformat(),user['id']))
    c.commit()
retention.enqueue(main.settings)
token=main.make_token()
db.create_session(main.settings.database_path,user_id=int(user['id']),
    token_hash=main.hash_value(token,main.settings.session_secret),
    expires_at=(main.utc_now()+timedelta(hours=1)).isoformat())
@main.app.get('/qa-preview-user-login')
def local_login():
    response=main.RedirectResponse('/app?action=notifications',status_code=303)
    main._set_user_session_cookie(response,token)
    return response
main.app.router.routes.insert(0,main.app.router.routes.pop())
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=8096,log_level='warning')
