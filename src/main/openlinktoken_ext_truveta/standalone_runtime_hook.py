"""
Copyright (c) Truveta. All rights reserved.

Configure extension discovery for a frozen PyInstaller bundle.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    embedded_registry_dir = bundle_root / "openlinktoken" / "extensions"
    os.environ.setdefault("OLT_EXTENSIONS_DIR", str(embedded_registry_dir))
