"""
Adapter for persisting AppConfig to the OS-standard user config directory.
No AWS interaction — pure filesystem I/O.
"""
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from core.app_config import AppConfig

logger = logging.getLogger(__name__)

_APP_DIR_NAME = "AWSToolSuite"
_CONFIG_FILE = "config.json"


def _get_config_dir() -> Path:
    """Return the OS-appropriate user config directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # XDG spec with ~/.config fallback
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".config"

    return base / _APP_DIR_NAME


class ConfigAdapter:
    """
    Loads and saves AppConfig to the OS user config folder.

    Config path (example Linux): ~/.config/AWSToolSuite/config.json
    Config path (example Win):   %APPDATA%\\AWSToolSuite\\config.json
    Config path (example macOS): ~/Library/Application Support/AWSToolSuite/config.json
    """

    def __init__(self) -> None:
        self._config_dir: Path = _get_config_dir()

    @property
    def config_path(self) -> Path:
        """Full path to the JSON config file."""
        return self._config_dir / _CONFIG_FILE

    def load(self) -> AppConfig:
        """
        Read config from disk and return an AppConfig.
        Returns default AppConfig on any failure (missing file, bad JSON, etc.).
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Only keep keys that exist in AppConfig to guard against stale fields
            valid_keys = AppConfig.__dataclass_fields__.keys()
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return AppConfig(**filtered)
        except FileNotFoundError:
            logger.debug("Config file not found — using defaults.")
        except Exception as exc:
            logger.warning("Failed to load config (%s) — using defaults.", exc)
        return AppConfig()

    def save(self, config: AppConfig) -> None:
        """
        Persist AppConfig to disk.
        Creates the config directory if it does not yet exist.
        """
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(asdict(config), fh, indent=2)
            logger.debug("Config saved to %s", self.config_path)
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)
