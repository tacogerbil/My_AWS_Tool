"""
advanced_section.py — EC2 instance security and OS configuration controls.

Exposed in the config form between Security and Tags (collapsed by default).
All settings default to the safest/most correct value for production use.

Public API (used by ConfigForm):
    get_associate_public_ip() -> bool
    get_imdsv2_required() -> bool
    get_termination_protection() -> bool
    get_timezone() -> str
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QWidget,
)


class AdvancedSection(QWidget):
    """Security and OS settings for EC2 instance launch."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignRight)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        # --- Associate Public IP ---
        self._public_ip_chk = QCheckBox("Enable public IP / public DNS")
        self._public_ip_chk.setChecked(False)  # Default: OFF (private only)
        self._public_ip_chk.setToolTip(
            "When unchecked the instance gets no public IPv4 address or public DNS name.\n"
            "Leave OFF for all internal / VPN-accessible instances."
        )
        form.addRow("Public IP:", self._public_ip_chk)

        # --- IMDSv2 ---
        self._imdsv2_combo = QComboBox()
        self._imdsv2_combo.addItem("Required  (IMDSv2 only — recommended)", userData=True)
        self._imdsv2_combo.addItem("Optional  (IMDSv1 + IMDSv2 allowed)", userData=False)
        self._imdsv2_combo.setCurrentIndex(0)  # Default: Required
        self._imdsv2_combo.setToolTip(
            "IMDSv2 (Instance Metadata Service v2) uses session-oriented requests\n"
            "and is required by many security baselines (CIS, AWS Foundational).\n"
            "Only select 'Optional' if a specific workload requires IMDSv1."
        )
        form.addRow("Metadata (IMDSv2):", self._imdsv2_combo)

        # --- Termination Protection ---
        self._term_protect_chk = QCheckBox("Enable termination protection")
        self._term_protect_chk.setChecked(True)  # Default: ON
        self._term_protect_chk.setToolTip(
            "Prevents the instance from being terminated via the console or API\n"
            "without first disabling this setting.\n"
            "Highly recommended for production instances."
        )
        form.addRow("Termination:", self._term_protect_chk)

        # --- Timezone ---
        self._timezone_edit = QLineEdit("Pacific Standard Time")
        self._timezone_edit.setPlaceholderText("e.g. Pacific Standard Time")
        self._timezone_edit.setToolTip(
            "Windows timezone identifier applied via 'tzutil /s' at first boot.\n"
            "Examples:\n"
            "  Pacific Standard Time\n"
            "  Mountain Standard Time\n"
            "  Central Standard Time\n"
            "  Eastern Standard Time\n"
            "  UTC\n"
            "Run 'tzutil /l' on any Windows machine for a full list."
        )
        form.addRow("Timezone:", self._timezone_edit)

        # Info label
        note = QLabel(
            "ℹ️  Timezone is applied via UserData on first boot (Windows instances only)."
        )
        note.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        note.setWordWrap(True)
        form.addRow("", note)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_associate_public_ip(self) -> bool:
        """True if the instance should receive a public IP address."""
        return self._public_ip_chk.isChecked()

    def get_imdsv2_required(self) -> bool:
        """True → HttpTokens=required; False → HttpTokens=optional."""
        return bool(self._imdsv2_combo.currentData())

    def get_termination_protection(self) -> bool:
        """True if termination protection should be enabled post-launch."""
        return self._term_protect_chk.isChecked()

    def get_timezone(self) -> str:
        """Windows tzutil timezone ID string."""
        return self._timezone_edit.text().strip() or "Pacific Standard Time"
