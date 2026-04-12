"""
processing/writer.py
====================
Crash-safe atomic JSON writer.

Writes to a temp file beside the target, then os.replace() — which is
atomic on all POSIX systems. A half-written file can never corrupt the
output because the rename only happens after the full write succeeds.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_json(data: Any, path: str | Path) -> Path:
    """Write `data` as pretty JSON to `path` atomically. Returns the resolved Path."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(data, indent=2, ensure_ascii=False, default=str)

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    logger.info("Wrote %d bytes → %s", len(payload), path)
    return path


def load_json(path: str | Path) -> Any:
    """Load and parse a JSON file. Raises FileNotFoundError if missing."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)
