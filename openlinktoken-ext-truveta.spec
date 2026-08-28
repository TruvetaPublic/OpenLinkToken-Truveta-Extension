# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the bundled OpenLinkToken CLI + Truveta extension distributable.

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Anchor to spec file location for reproducible builds.
# SPECPATH is provided by PyInstaller when executing the spec.
base_dir = os.path.abspath(SPECPATH)
sys.path.insert(0, os.path.join(base_dir, "src", "main"))

from openlinktoken_ext_truveta.util.inferencing_assets import collect_ml1_assets

datas = []
binaries = []
hiddenimports = []

for package_name in (
    "openlinktoken",
    "openlinktoken.core",
    "pyarrow",
    "pandas",
    "csv2parquet",
    "cryptography",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for module in ("openlinktoken", "openlinktoken_cli", "openlinktoken_ext_truveta"):
    hiddenimports += collect_submodules(module)

inferencing_assets_source = os.environ.get("OLT_INFERENCING_ASSETS_SOURCE")
if not inferencing_assets_source:
    raise RuntimeError(
        "OLT_INFERENCING_ASSETS_SOURCE must point to OpenLinkToken's "
        "resources/inferencing/ml1 directory"
    )
datas += collect_ml1_assets(inferencing_assets_source)
datas += [
    (os.path.join(base_dir, "standalone", "registry.json"), "openlinktoken/extensions")
]

import importlib.util as _ilu
import pathlib as _pl

_spec = _ilu.find_spec("openlinktoken_cli.main")
_entrypoint = str(_pl.Path(_spec.origin).as_posix())

a = Analysis(
    [_entrypoint],
    pathex=[base_dir, os.path.join(base_dir, "src", "main")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[
        os.path.join(
            base_dir,
            "src",
            "main",
            "openlinktoken_ext_truveta",
            "standalone_runtime_hook.py",
        )
    ],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="olt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    target_arch=os.environ.get("OLT_TARGET_ARCH"),
    console=True,
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="olt",
)
