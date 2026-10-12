# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
import sys

root = Path(SPECPATH).parent
version = runpy.run_path(str(root / 'src/config.py'))['global_version']
a = Analysis(
    [str(root / 'qtui.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root / 'assets'), 'assets')], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='SJTURunning',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=str(root / 'assets/SJTURM.png'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SJTURunning')
if sys.platform == 'darwin':
    app = BUNDLE(
        coll, name='SJTURunning.app', icon=str(root / 'assets/SJTURM.png'),
        bundle_identifier='io.github.yichenbert.sjturunning',
        info_plist={'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                    'NSHighResolutionCapable': True},
    )
