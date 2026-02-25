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
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.models import Subnet, Vpc
from tools.ec2_launcher.ui.vpc_badge import VpcBadge
from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""


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
        vpc_row.addWidget(self._vpc_combo)
        vpc_row.addStretch()
        layout.addLayout(vpc_row)

        sn_row = QHBoxLayout()
        self._subnet_badge = VpcBadge()
        sn_row.addWidget(self._subnet_badge)
        sn_row.addWidget(QLabel("Subnet:"))
        self._subnet_combo = SearchableComboBox()
        self._subnet_combo.setMinimumWidth(320)
        sn_row.addWidget(self._subnet_combo)
        sn_row.addStretch()
        layout.addLayout(sn_row)

        self._all_subnets: List[Subnet] = []
        self._vpc_combo.currentIndexChanged.connect(self._on_vpc_changed)

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
