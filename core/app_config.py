"""
Pure dataclass for persisted user preferences.
No I/O — all loading/saving is handled by adapters/config_adapter.py.
"""
from dataclasses import dataclass


@dataclass
class AppConfig:
    """User preferences persisted to the OS config folder."""

    aws_profile: str = "default"
    region: str = "us-west-2"
    last_vm_dir: str = ""
    window_x: int = 100
    window_y: int = 100
    window_w: int = 800
    window_h: int = 500
