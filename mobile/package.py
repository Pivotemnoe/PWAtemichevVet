"""Package published 0.1.1 artifacts and source, excluding data and signing material."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/mobile/0.1.1'
OUT.mkdir(parents=True, exist_ok=True)
def safe_source(path):
    return path.is_file() and not any(part in {'__pycache__', 'node_modules', '.gradle', 'build', '.idea'} for part in path.parts) \
        and path.name not in {'.env', '.DS_Store', 'local.properties', 'signing.json'} \
        and path.suffix not in {'.pyc', '.db', '.sqlite', '.sqlite3', '.p12', '.jks', '.keystore', '.log'}
def source_files(directory):
    return [p for p in (ROOT / directory).rglob('*') if safe_source(p)]
def archive(name, paths):
    with zipfile.ZipFile(OUT / name, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(set(paths)):
            if not safe_source(path): raise ValueError('private or generated file in source package: ' + str(path))
            bundle.write(path, path.relative_to(ROOT))

with zipfile.ZipFile(OUT / 'TemichevVet-0.1.1.apk') as apk:
    metadata = json.loads(apk.read('assets/public/mobile-build.json'))
    assert metadata['apiOrigin'] == 'https://temichevvet.ru' and metadata['debugApi'] is False
    assert b'20261013-mobile-14' in apk.read('assets/public/index.html')
with zipfile.ZipFile(OUT / 'TemichevVet-QA-0.1.1.apk') as apk:
    qa_metadata = json.loads(apk.read('assets/public/mobile-build.json'))
    assert qa_metadata['apiOrigin'] == 'http://127.0.0.1:8096' and qa_metadata['debugApi'] is True
    assert b'20261013-mobile-14' in apk.read('assets/public/index.html')

docs = [ROOT / 'docs/MOBILE_APP.md', ROOT / 'docs/MOBILE_QA_REPORT_20261013_REVISION.md', ROOT / 'docs/MOBILE_DEPLOYMENT_20261013.md']
archive('TemichevVet-PWA-server-0.1.1.zip', source_files('app') + source_files('web') + docs +
    [ROOT / 'requirements.txt', ROOT / 'Dockerfile', ROOT / 'releases/android/README.md', ROOT / 'releases/android/TemichevVet-0.1.1.apk'])
android = [p for p in source_files('android') if '/src/main/assets/public/' not in p.as_posix()]
archive('TemichevVet-Android-source-0.1.1.zip', android + source_files('mobile') + source_files('web') + docs +
    [ROOT / 'package.json', ROOT / 'package-lock.json', ROOT / 'capacitor.config.json'])
shutil.copy2(docs[1], OUT / 'QA_REPORT.md')
shutil.copy2(docs[0], OUT / 'BUILD_AND_DEPLOY.md')
shutil.copy2(docs[2], OUT / 'PRODUCTION_DEPLOYMENT.md')
screens = OUT / 'screenshots'
screens.mkdir(exist_ok=True)
for name in ['android-home-final.png', 'android-release-welcome.png', 'android-payment-warning.png', 'android-payment-success.png',
             'android-legal-modal.png', 'android-cat-card-final.png', 'android-offline-cold-final.png', 'android-offline-queue-final.png', 'android-offline-reminder.png', 'android-offline-weight.png',
             'pwa-pet-photo.png', 'pwa-offline-observation.png', 'pwa-cat-fallback-final.png', 'pwa-dog-fallback-final.png', 'pwa-species-list-final.png',
             'android-reminder-open.png', 'android-offline-retry.png', 'android-export-chooser.png', 'safari-390-home.png',
             'safari-320-health.png', 'safari-payment-dialog.png', 'safari-payment-canceled.png', 'download-page-final.png',
             'android-summary-final-1.png', 'android-summary-final-2.png', 'production-download-20261013.png', 'production-pwa-390-20261013.png']:
    shutil.copy2(ROOT / 'output/playwright' / name, screens / name)
samples = OUT / 'samples'
samples.mkdir(exist_ok=True)
shutil.copy2(ROOT / 'output/playwright/TemichevVet-Leo-QA-final-20261013.pdf', samples / 'QA-Leo-summary.pdf')
preview = OUT / 'preview'
preview.mkdir(exist_ok=True)
for source, target in [('web/android-download.css', 'android-download.css'), ('web/assets/app-icon-192.png', 'app-icon-192.png'),
                       ('web/assets/mobile/companions-v1.webp', 'companions-v1.webp')]:
    shutil.copy2(ROOT / source, preview / target)
html = (ROOT / 'web/android.html').read_text().replace('/static/android-download.css?v=20261013-1', 'preview/android-download.css') \
    .replace('/static/assets/app-icon-192.png', 'preview/app-icon-192.png') \
    .replace('/static/assets/mobile/companions-v1.webp', 'preview/companions-v1.webp') \
    .replace('/downloads/TemichevVet-0.1.1.apk', 'TemichevVet-0.1.1.apk') \
    .replace('href="/mobile"', 'href="https://temichevvet.ru/mobile"')
html = html.replace('<main>', '<main><p class="small">Копия опубликованной страницы установки. Здесь APK скачивается из пакета; PWA открывается на боевом сайте. Публичная страница: <a href="https://temichevvet.ru/android">temichevvet.ru/android</a>.</p>')
for route in ['privacy', 'terms', 'contacts']:
    html = html.replace(f'href="/{route}"', f'href="https://temichevvet.ru/{route}"')
(OUT / 'review.html').write_text(html)
(OUT / 'START_HERE.txt').write_text('TemichevVet 0.1.1 — опубликованный выпуск\n\n'
    'Установка Android и iPhone: https://temichevvet.ru/android\n'
    'PWA: https://temichevvet.ru/mobile\n\n'
    'TemichevVet-0.1.1.apk — подписанная обычная Android-версия с рабочим HTTPS API.\n'
    'TemichevVet-0.1.1.aab — подписанный кандидат для магазина; соответствие платёжной схеме проверяется отдельно.\n'
    'TemichevVet-QA-0.1.1.apk — тестовая версия: нужен Mac, QA-сервер и ADB reverse 8096.\n'
    'TemichevVet-PWA-server-0.1.1.zip — исходники опубликованного сервера, web/PWA и подписанный APK.\n'
    'TemichevVet-Android-source-0.1.1.zip — исходники приложения и сборки; npm-зависимости устанавливаются по lock-файлу.\n'
    'QA_REPORT.md — результаты и границы проверки. BUILD_AND_DEPLOY.md — сборка и подпись.\n'
    'PRODUCTION_DEPLOYMENT.md / .json и PUBLIC_VERIFICATION.json — подтверждения публикации.\n'
    'review.html — копия страницы скачивания. screenshots/ — подтверждения. samples/ — только вымышленные QA-данные.\n\n'
    'Пакет не содержит базы, .env, ключи подписи или пароли. Боевой сервер и PWA обновлены 13.10.2026.\n')
files = [p for p in OUT.iterdir() if p.is_file() and p.suffix in {'.apk', '.aab', '.zip'}]
hashes = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in files}
(OUT / 'SHA256SUMS.txt').write_text(''.join(f"{item['sha256']}  {name}\n" for name, item in sorted(hashes.items())))
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
publication = json.loads((OUT / 'PRODUCTION_DEPLOYMENT.json').read_text())
assert hashes['TemichevVet-0.1.1.apk']['sha256'] == publication['apk_sha256'], 'Packet APK differs from published APK'
(OUT / 'BUILD_MANIFEST.json').write_text(json.dumps({'version': '0.1.1', 'source_commit': commit, 'release': metadata,
    'qa': qa_metadata, 'publication': publication, 'artifacts': hashes}, ensure_ascii=False, indent=2) + '\n')
print('Local delivery packet:', OUT)
print('Archives exclude databases, environment files, caches and private signing material.')
