"""
VpcBadge — a 14×14 colored square used inline next to VPC/Subnet combos.

Single responsibility: render a deterministic color for a given vpc_id.
No business logic; calls vpc_color() from the common module.
"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from ui.common.vpc_colors import vpc_color

_EMPTY_STYLE = "background-color: #bdc3c7; border-radius: 2px;"


class VpcBadge(QLabel):
    """A 14×14 colored square label whose color is tied to a vpc_id."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(_EMPTY_STYLE)
        self.setToolTip("")

    def set_vpc(self, vpc_id: str) -> None:
        """Set the badge color based on vpc_id. Pass '' to reset."""
        if not vpc_id:
            self.setStyleSheet(_EMPTY_STYLE)
            self.setToolTip("")
            return
        color = vpc_color(vpc_id)
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 2px;"
        )
        self.setToolTip(vpc_id)
