"""Build-time checks; no signing material, account or network access is needed."""
import json
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(assets: Path, configuration: str) -> None:
    metadata = json.loads((assets / 'mobile-build.json').read_text())
    package = json.loads((ROOT / 'package.json').read_text())
    if metadata['platform'] != 'ios' or metadata['appVersion'] != package['version']:
        raise ValueError('Build fresh iOS assets with npm run ios:sync')
    release = configuration == 'Release'
    if release and (metadata['debugApi'] or metadata['apiOrigin'] != 'https://temichevvet.ru'):
        raise ValueError('Release must use the production HTTPS API, without QA access')
    if any(p.suffix in {'.db', '.sqlite', '.p12', '.p8', '.jks', '.keystore'} or p.name == '.env'
           for p in assets.rglob('*')):
        raise ValueError('Private runtime or signing material found in app assets')
    info_path = ROOT / 'ios/App/App' / ('Info.plist' if release else 'Info-Debug.plist')
    with info_path.open('rb') as stream:
        info = plistlib.load(stream)
    if release and info.get('NSAppTransportSecurity', {}).get('NSAllowsArbitraryLoads'):
        raise ValueError('Release cannot permit arbitrary HTTP loads')
    for key in ('NSCameraUsageDescription', 'NSPhotoLibraryUsageDescription', 'CFBundleURLTypes'):
        if not info.get(key):
            raise ValueError(f'Missing iOS usage configuration: {key}')
    with (ROOT / 'ios/App/App/PrivacyInfo.xcprivacy').open('rb') as stream:
        privacy = plistlib.load(stream)
    if privacy.get('NSPrivacyTracking'):
        raise ValueError('Tracking is not part of the mobile app')


if __name__ == '__main__':
    check(Path(sys.argv[1]), sys.argv[2])
    print('iOS bundle configuration verified')
