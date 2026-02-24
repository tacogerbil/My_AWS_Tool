"""
ui_prefs.py — Lightweight JSON-backed UI preference store.

Pure I/O adapter: no Qt, no AWS.  Persists to execution/ui_prefs.json.
Keys are simple strings; values must be JSON-serialisable.

Public API
----------
    get_pref(key, default=None) -> Any
    set_pref(key, value)        -> None
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

_PREFS_PATH = Path(__file__).parent.parent.parent / "ui_prefs.json"
logger = logging.getLogger(__name__)


def _load() -> Dict[str, Any]:
    try:
        return json.loads(_PREFS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_pref(key: str, default: Any = None) -> Any:
    """Return the stored value for *key*, or *default* if not found."""
    return _load().get(key, default)


def set_pref(key: str, value: Any) -> None:
    """Persist *key* → *value*, merging with any existing prefs."""
    try:
        existing = _load()
        existing[key] = value
        _PREFS_PATH.write_text(json.dumps(existing, indent=2))
    except OSError as exc:
        logger.warning("Could not save UI pref '%s': %s", key, exc)
