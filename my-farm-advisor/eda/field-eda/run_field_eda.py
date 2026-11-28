#!/usr/bin/env python3
"""Run the field EDA subskill from a checkout without installing it.

Example:
    python my-farm-advisor/eda/field-eda/run_field_eda.py --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from field_eda.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
