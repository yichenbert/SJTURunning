# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
import sys

root = Path(SPECPATH).parent
metadata = runpy.run_path(str(root / 'src/config.py'))
version = metadata['global_version']
app_name = metadata['APP_NAME']
app_icon = root / ('assets/SJTURunPlus.icns' if sys.platform == 'darwin' else 'assets/SJTURunPlus.ico')
a = Analysis(
    [str(root / 'qtui.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root / 'assets'), 'assets')], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=app_name,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=str(app_icon),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=app_name)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll, name=f'{app_name}.app', icon=str(app_icon),
        bundle_identifier='io.github.yichenbert.sjturunning',
        info_plist={'CFBundleName': app_name, 'CFBundleDisplayName': app_name,
                    'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                    'NSHighResolutionCapable': True},
    )
