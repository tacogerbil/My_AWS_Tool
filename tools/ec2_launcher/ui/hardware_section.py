"""
hardware_section.py — Instance type selector + root EBS volume config.

The instance-type info card shows vCPU / RAM / network from a local lookup
table so users can make an informed choice without a live DescribeInstanceTypes
call.  The table covers the most common types; unknown types show a prompt to
check the AWS documentation.

Public API (used by ConfigForm):
    populate(instance_types: List[str])
    get_instance_type() -> str
    get_volume_gb() -> Optional[int]
    get_volume_type() -> str
    set_instance_type(itype: str)
    set_volume(gb: int, vtype: str)
    mark_error(has_error: bool)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""
_VOLUME_TYPES = ["gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"]

# (vCPU count, RAM, network) — offline reference; covers the most common types
_INSTANCE_SPECS: Dict[str, Tuple[str, str, str]] = {
    "t2.micro":    ("1 vCPU",   "1 GiB",   "Low to Moderate"),
    "t2.small":    ("1 vCPU",   "2 GiB",   "Low to Moderate"),
    "t2.medium":   ("2 vCPU",   "4 GiB",   "Low to Moderate"),
    "t2.large":    ("2 vCPU",   "8 GiB",   "Low to Moderate"),
    "t3.micro":    ("2 vCPU",   "1 GiB",   "Up to 5 Gbps"),
    "t3.small":    ("2 vCPU",   "2 GiB",   "Up to 5 Gbps"),
    "t3.medium":   ("2 vCPU",   "4 GiB",   "Up to 5 Gbps"),
    "t3.large":    ("2 vCPU",   "8 GiB",   "Up to 5 Gbps"),
    "t3.xlarge":   ("4 vCPU",   "16 GiB",  "Up to 5 Gbps"),
    "t3.2xlarge":  ("8 vCPU",   "32 GiB",  "Up to 5 Gbps"),
    "m5.large":    ("2 vCPU",   "8 GiB",   "Up to 10 Gbps"),
    "m5.xlarge":   ("4 vCPU",   "16 GiB",  "Up to 10 Gbps"),
    "m5.2xlarge":  ("8 vCPU",   "32 GiB",  "Up to 10 Gbps"),
    "m5.4xlarge":  ("16 vCPU",  "64 GiB",  "Up to 10 Gbps"),
    "m5.8xlarge":  ("32 vCPU",  "128 GiB", "10 Gbps"),
    "c5.large":    ("2 vCPU",   "4 GiB",   "Up to 10 Gbps"),
    "c5.xlarge":   ("4 vCPU",   "8 GiB",   "Up to 10 Gbps"),
    "c5.2xlarge":  ("8 vCPU",   "16 GiB",  "Up to 10 Gbps"),
    "c5.4xlarge":  ("16 vCPU",  "32 GiB",  "Up to 10 Gbps"),
    "r5.large":    ("2 vCPU",   "16 GiB",  "Up to 10 Gbps"),
    "r5.xlarge":   ("4 vCPU",   "32 GiB",  "Up to 10 Gbps"),
    "r5.2xlarge":  ("8 vCPU",   "64 GiB",  "Up to 10 Gbps"),
    "g4dn.xlarge": ("4 vCPU",   "16 GiB",  "Up to 25 Gbps"),
    "g4dn.2xlarge":("8 vCPU",   "32 GiB",  "Up to 25 Gbps"),
    "p3.2xlarge":  ("8 vCPU",   "61 GiB",  "Up to 10 Gbps"),
}

_CARD_STYLE = """
    QFrame {
        background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;
    }
    QLabel { color: #495057; font-size: 11px; border: none; }
"""


class HardwareSection(QWidget):
    """Instance type + root volume size / type + live info card."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Row 1: instance type combo + info card side-by-side
        type_row = QHBoxLayout()
        type_row.setSpacing(10)
        type_row.addWidget(QLabel("Instance type:"))
        self._type_combo = SearchableComboBox()
        self._type_combo.setMinimumWidth(200)
        type_row.addWidget(self._type_combo)
        type_row.addWidget(self._build_info_card())
        type_row.addStretch()
        layout.addLayout(type_row)

        # Row 2: root volume
        vol_row = QHBoxLayout()
        vol_row.setSpacing(8)
        vol_row.addWidget(QLabel("Root volume (GiB):"))
        self._vol_size = QLineEdit("30")
        self._vol_size.setFixedWidth(80)
        vol_row.addWidget(self._vol_size)
        vol_row.addSpacing(16)
        vol_row.addWidget(QLabel("Type:"))
        self._vol_type = QComboBox()
        self._vol_type.addItems(_VOLUME_TYPES)
        vol_row.addWidget(self._vol_type)
        vol_row.addStretch()
        layout.addLayout(vol_row)

        self._type_combo.currentTextChanged.connect(self._update_card)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, instance_types: List[str]) -> None:
        self._type_combo.clear()
        self._type_combo.addItems(instance_types)

    def get_instance_type(self) -> str:
        return self._type_combo.currentText()

    def get_volume_gb(self) -> Optional[int]:
        try:
            return int(self._vol_size.text())
        except ValueError:
            return None

    def get_volume_type(self) -> str:
        return self._vol_type.currentText()

    def set_instance_type(self, itype: str) -> None:
        idx = self._type_combo.findText(itype)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        else:
            self._type_combo.setEditText(itype)

    def set_volume(self, gb: int, vtype: str) -> None:
        self._vol_size.setText(str(gb))
        idx = self._vol_type.findText(vtype)
        if idx >= 0:
            self._vol_type.setCurrentIndex(idx)

    def mark_error(self, has_error: bool) -> None:
        self._vol_size.setStyleSheet(_ERROR_STYLE if has_error else _NORMAL_STYLE)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_info_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_STYLE)
        card.setFixedHeight(60)
        card.setMinimumWidth(230)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(1)

        self._info_cpu = QLabel("Select a type to see specs")
        self._info_mem = QLabel("")
        self._info_net = QLabel("")
        for lbl in (self._info_cpu, self._info_mem, self._info_net):
            layout.addWidget(lbl)
        return card

    def _update_card(self, itype: str) -> None:
        specs = _INSTANCE_SPECS.get(itype)
        if specs:
            vcpu, mem, net = specs
            self._info_cpu.setText(f"CPU: {vcpu}")
            self._info_mem.setText(f"RAM: {mem}")
            self._info_net.setText(f"Network: {net}")
        else:
            self._info_cpu.setText("No local spec data — check AWS docs")
            self._info_mem.setText("")
            self._info_net.setText("")
