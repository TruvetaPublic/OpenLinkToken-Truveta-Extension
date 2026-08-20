# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the bundled OpenLinkToken CLI + Truveta extension distributable.

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Anchor to spec file location for reproducible builds.
# SPECPATH is provided by PyInstaller when executing the spec.
base_dir = os.path.abspath(SPECPATH)

datas = []
binaries = []
hiddenimports = []

for package_name in ("cryptography",):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for module in ("openlinktoken", "openlinktoken_cli", "openlinktoken_ext_truveta"):
    hiddenimports += collect_submodules(module)

import importlib.util as _ilu
import pathlib as _pl

_spec = _ilu.find_spec("openlinktoken_cli.main")
_entrypoint = str(_pl.Path(_spec.origin).as_posix())

a = Analysis(
    [_entrypoint],
    pathex=[base_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="olt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
