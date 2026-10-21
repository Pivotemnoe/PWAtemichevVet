"""Build signed local release candidates. Never publishes or uploads anything."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SIGNING = Path.home() / '.local/share/temichevvet/android-signing'
JAVA = Path('/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home')
parser = argparse.ArgumentParser()
parser.add_argument('--init-key', action='store_true', help='Create the initial app signing key only if none exists')
parser.add_argument('--gradle', default=str(ROOT / 'android/gradlew'))
parser.add_argument('--maven-init', type=Path)
parser.add_argument('--offline', action='store_true', help='Use already downloaded Gradle dependencies')
args = parser.parse_args()
package = json.loads((ROOT / 'package.json').read_text())
version = package['version']
if not all(part.isdigit() for part in version.split('.')) or len(version.split('.')) != 3:
    raise SystemExit('Release version must contain three numeric components')
env = os.environ.copy()
env['JAVA_HOME'] = str(JAVA)
env['GRADLE_USER_HOME'] = str(ROOT / '.mobile-tools/gradle')
env.pop('TVV_DEBUG_API', None)
env.pop('TVV_API_BASE', None)
env['TVV_PLATFORM'] = 'android'
key = SIGNING / 'temichevvet-app-signing.p12'
credentials = SIGNING / 'signing.json'
if args.init_key and not key.exists() and not credentials.exists():
    SIGNING.mkdir(parents=True, exist_ok=True, mode=0o700)
    SIGNING.chmod(0o700)
    password = secrets.token_urlsafe(48)
    signing = {'keystore': str(key), 'alias': 'temichevvet', 'password': password}
    env['TVV_KEY_CREATION_PASSWORD'] = password
    subprocess.run([str(JAVA / 'bin/keytool'), '-genkeypair', '-keystore', str(key), '-storetype', 'PKCS12',
        '-storepass:env', 'TVV_KEY_CREATION_PASSWORD', '-keypass:env', 'TVV_KEY_CREATION_PASSWORD',
        '-alias', signing['alias'], '-keyalg', 'RSA', '-keysize', '3072', '-sigalg', 'SHA256withRSA',
        '-validity', '10000', '-dname', 'CN=TemichevVet Android, O=TemichevVet, C=RU'], env=env, check=True)
    key.chmod(0o600)
    descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(signing, output, indent=2)
        output.write('\n')
    env.pop('TVV_KEY_CREATION_PASSWORD')
if not key.exists() or not credentials.exists():
    raise SystemExit('App signing key is missing. Restore the original key, or use --init-key for the first release.')
signing = json.loads(credentials.read_text())
env.update(TVV_ANDROID_KEYSTORE=signing['keystore'], TVV_ANDROID_KEY_ALIAS=signing['alias'],
           TVV_ANDROID_STORE_PASSWORD=signing['password'], TVV_ANDROID_KEY_PASSWORD=signing['password'])
subprocess.run(['npm', 'run', 'mobile:sync'], cwd=ROOT, env=env, check=True)
command = [args.gradle, '-p', str(ROOT / 'android')]
if args.maven_init:
    command += ['-I', str(args.maven_init.resolve())]
if args.offline:
    command += ['--offline']
subprocess.run(command + [':app:assembleRelease', ':app:bundleRelease', ':app:testReleaseUnitTest', '--console=plain'], cwd=ROOT, env=env, check=True)
out = ROOT / 'output/mobile' / version
out.mkdir(parents=True, exist_ok=True)
apk = out / f'TemichevVet-{version}.apk'
bundle = out / f'TemichevVet-{version}.aab'
shutil.copy2(ROOT / 'android/app/build/outputs/apk/release/app-release.apk', apk)
shutil.copy2(ROOT / 'android/app/build/outputs/bundle/release/app-release.aab', bundle)
sdk = ROOT / '.mobile-tools/sdk/build-tools/36.0.0'
verification = subprocess.check_output([str(sdk / 'apksigner'), 'verify', '--verbose', '--print-certs', str(apk)], env=env, text=True)
(out / 'apk-signature.txt').write_text(verification)
bundle_verification = subprocess.run([str(JAVA / 'bin/jarsigner'), '-verify', str(bundle)], env=env, check=True, capture_output=True, text=True)
(out / 'aab-signature.txt').write_text(bundle_verification.stdout + bundle_verification.stderr)
hashes = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in [apk, bundle]}
(out / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in hashes.items()))
public_directory = ROOT / 'releases/android'
public_directory.mkdir(parents=True, exist_ok=True)
shutil.copy2(apk, public_directory / apk.name)
source_files = [ROOT / 'package.json', ROOT / 'package-lock.json', ROOT / 'capacitor.config.json']
source_files += sorted((ROOT / 'web').rglob('*'))
source_files += sorted((ROOT / 'mobile').glob('*.js')) + [ROOT / 'mobile/build.mjs', ROOT / 'mobile/release.py']
source_files += sorted((ROOT / 'android/app/src/main/java').rglob('*.java'))
manifest = {
    'version': version, 'android_version_code': package['androidVersionCode'],
    'built_at': datetime.now(timezone.utc).isoformat(),
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'working_tree': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True).splitlines(),
    'mobile_build': json.loads((ROOT / 'dist/mobile-build.json').read_text()),
    'artifacts': {file.name: {'sha256': hashes[file.name], 'bytes': file.stat().st_size} for file in [apk, bundle]},
    'source_sha256': {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest()
                      for file in source_files if file.is_file()},
}
(out / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('Signed local candidates:', out)
print('Private signing material kept separately:', SIGNING)
