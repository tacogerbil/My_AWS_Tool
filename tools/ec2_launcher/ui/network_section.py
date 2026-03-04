"""
network_section.py — VPC + Subnet selectors with deterministic color badges.

Each VPC always gets the same color across sessions (hash-based palette).
Subnet list auto-filters when the VPC selection changes.

Public API (used by ConfigForm):
    populate(vpcs: List[Vpc], subnets: List[Subnet])
    get_vpc_id() -> Optional[str]
    get_subnet_id() -> Optional[str]
    set_vpc_id(vpc_id: str)
    set_subnet_id(subnet_id: str)
    mark_error(vpc_error: bool, subnet_error: bool)
    get_associate_public_ip() -> bool
    get_imdsv2_required() -> bool
    get_termination_protection() -> bool
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import Subnet, Vpc
from tools.ec2_launcher.ui.vpc_badge import VpcBadge
from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""

_HINT_STYLE = (
    "background: #fffde7; border: 1px solid #f9a825; border-radius: 3px;"
    "padding: 2px 6px; color: #5d4037; font-size: 10px; font-style: italic;"
)


def _policy_hint(text: str) -> QLabel:
    """Return a styled amber hint label for policy guidance."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(_HINT_STYLE)
    return lbl


class NetworkSection(QWidget):
    """VPC / Subnet selectors with VpcBadge color coding."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        vpc_row = QHBoxLayout()
        self._vpc_badge = VpcBadge()
        vpc_row.addWidget(self._vpc_badge)
        vpc_row.addWidget(QLabel("VPC:"))
        self._vpc_combo = SearchableComboBox()
        self._vpc_combo.setMinimumWidth(320)
        self._vpc_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        vpc_row.addWidget(self._vpc_combo)
        layout.addLayout(vpc_row)

        sn_row = QHBoxLayout()
        self._subnet_badge = VpcBadge()
        sn_row.addWidget(self._subnet_badge)
        sn_row.addWidget(QLabel("Subnet:"))
        self._subnet_combo = SearchableComboBox()
        self._subnet_combo.setMinimumWidth(320)
        self._subnet_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sn_row.addWidget(self._subnet_combo)
        layout.addLayout(sn_row)

        self._all_subnets: List[Subnet] = []
        self._vpc_combo.currentIndexChanged.connect(self._on_vpc_changed)

        # ---------------------------------------------------------------
        # Instance / security options that belong logically with networking
        # ---------------------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #d5d8dc;")
        layout.addWidget(sep)

        net_form = QFormLayout()
        net_form.setLabelAlignment(Qt.AlignRight)
        net_form.setSpacing(8)

        self._public_ip_chk = QCheckBox("Enable public IP / public DNS")
        self._public_ip_chk.setChecked(False)
        self._public_ip_chk.setToolTip(
            "When unchecked the instance gets no public IPv4 address or public DNS name.\n"
            "Leave OFF for all internal / VPN-accessible instances."
        )
        net_form.addRow("Public IP:", self._public_ip_chk)

        self._imdsv2_combo = QComboBox()
        self._imdsv2_combo.addItem("Required  (IMDSv2 only — recommended)", userData=True)
        self._imdsv2_combo.addItem("Optional  (IMDSv1 + IMDSv2 allowed)", userData=False)
        self._imdsv2_combo.setCurrentIndex(0)
        self._imdsv2_combo.setToolTip(
            "IMDSv2 uses session-oriented requests and is required by many security\n"
            "baselines (CIS, AWS Foundational Security).\n"
            "Only select 'Optional' if a specific workload requires IMDSv1."
        )
        net_form.addRow("Metadata (IMDSv2):", self._imdsv2_combo)
        net_form.addRow("", _policy_hint(
            "⚠  Policy: IMDSv2 must be set to Required at all times. "
            "IMDSv1 is disabled by default in this environment."
        ))

        self._term_protect_chk = QCheckBox("Enable termination protection")
        self._term_protect_chk.setChecked(True)
        self._term_protect_chk.setToolTip(
            "Prevents accidental termination via the console or API.\n"
            "Highly recommended for production instances."
        )
        net_form.addRow("Termination:", self._term_protect_chk)
        net_form.addRow("", _policy_hint(
            "⚠  Policy: Termination protection must always remain enabled on production instances."
        ))

        layout.addLayout(net_form)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, vpcs: List[Vpc], subnets: List[Subnet]) -> None:
        self._all_subnets = subnets
        self._vpc_combo.blockSignals(True)
        self._vpc_combo.clear()
        for vpc in vpcs:
            label = vpc.name or vpc.vpc_id
            self._vpc_combo.addItem(
                f"{vpc.vpc_id}  {label}  {vpc.cidr_block}", userData=vpc.vpc_id
            )
        self._vpc_combo.setCurrentIndex(-1)
        self._vpc_combo.lineEdit().clear()
        self._vpc_combo.blockSignals(False)
        self._vpc_badge.set_vpc("")
        self._subnet_combo.clear()
        self._subnet_combo.lineEdit().clear()
        self._subnet_badge.set_vpc("")

    def get_vpc_id(self) -> Optional[str]:
        return self._vpc_combo.currentData()

    def get_subnet_id(self) -> Optional[str]:
        return self._subnet_combo.currentData()

    def set_vpc_id(self, vpc_id: str) -> None:
        idx = self._vpc_combo.findData(vpc_id)
        if idx >= 0:
            self._vpc_combo.setCurrentIndex(idx)

    def set_subnet_id(self, subnet_id: str) -> None:
        idx = self._subnet_combo.findData(subnet_id)
        if idx >= 0:
            self._subnet_combo.setCurrentIndex(idx)

    def mark_error(self, vpc_error: bool, subnet_error: bool) -> None:
        self._vpc_combo.setStyleSheet(_ERROR_STYLE if vpc_error else _NORMAL_STYLE)
        self._subnet_combo.setStyleSheet(_ERROR_STYLE if subnet_error else _NORMAL_STYLE)

    def get_associate_public_ip(self) -> bool:
        """True if the instance should receive a public IP address."""
        return self._public_ip_chk.isChecked()

    def get_imdsv2_required(self) -> bool:
        """True → HttpTokens=required; False → HttpTokens=optional."""
        return bool(self._imdsv2_combo.currentData())

    def get_termination_protection(self) -> bool:
        """True if termination protection should be enabled post-launch."""
        return self._term_protect_chk.isChecked()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_vpc_changed(self) -> None:
        vpc_id = self._vpc_combo.currentData() or ""
        self._vpc_badge.set_vpc(vpc_id)
        self._subnet_combo.clear()
        if vpc_id:
            for sub in self._all_subnets:
                if sub.vpc_id == vpc_id:
                    label = sub.name or sub.subnet_id
                    self._subnet_combo.addItem(
                        f"{sub.subnet_id}  {label}  {sub.cidr_block}  {sub.availability_zone}",
                        userData=sub.subnet_id,
                    )
            self._subnet_combo.setCurrentIndex(-1)
            self._subnet_combo.lineEdit().clear()
        self._subnet_badge.set_vpc(vpc_id)
