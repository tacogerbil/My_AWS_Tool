"""
security_section.py — Security Group creator/browser + Key Pair selector.

Two-panel layout:
  Left  — New Security Group form (name, description, inbound rules table)
  ←     — Copy button: templates right-panel SG into left form
  Right — Select Existing SG (searchable, single-select; details shown below)

Below both panels: Key Pair selector.

Public API (used by ConfigForm)
--------------------------------
    populate(sgs, key_pairs)
    get_sg_ids() -> List[str]       # selected existing SG
    get_key_name() -> Optional[str]
    set_sg_ids(ids)
    set_key_name(name)
    mark_error(has_error)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import KeyPair, SecurityGroup
from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""

# Rule-type → (protocol, default_port)
_RULE_TYPE_MAP: Dict[str, tuple] = {
    "SSH":          ("tcp",  "22"),
    "HTTP":         ("tcp",  "80"),
    "HTTPS":        ("tcp",  "443"),
    "RDP":          ("tcp",  "3389"),
    "SMTP":         ("tcp",  "25"),
    "MySQL/Aurora": ("tcp",  "3306"),
    "PostgreSQL":   ("tcp",  "5432"),
    "MSSQL":        ("tcp",  "1433"),
    "All TCP":      ("tcp",  "0-65535"),
    "All UDP":      ("udp",  "0-65535"),
    "All Traffic":  ("all",  "All"),
    "Custom TCP":   ("tcp",  ""),
    "Custom UDP":   ("udp",  ""),
    "Custom ICMP":  ("icmp", ""),
}


# ---------------------------------------------------------------------------
# _SgRulesTable — editable inbound-rule rows
# ---------------------------------------------------------------------------

class _SgRulesTable(QWidget):
    """Editable table of inbound rules for a new security group.

    Columns: Type (combo) | Protocol (auto) | Port Range | Source | Description
    Type selection auto-fills Protocol and Port for well-known rule types.
    """

    _COLUMNS = ["Type", "Protocol", "Port Range", "Source", "Description"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setMinimumHeight(110)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Rule")
        add_btn.setFixedWidth(85)
        rm_btn = QPushButton("Remove")
        rm_btn.setFixedWidth(85)
        add_btn.clicked.connect(lambda: self._add_rule())
        rm_btn.clicked.connect(self._remove_rule)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _add_rule(
        self,
        type_: str = "Custom TCP",
        port: str = "",
        source: str = "0.0.0.0/0",
        desc: str = "",
    ) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        type_combo = QComboBox()
        type_combo.addItems(list(_RULE_TYPE_MAP.keys()))
        idx = type_combo.findText(type_)
        if idx >= 0:
            type_combo.setCurrentIndex(idx)
        type_combo.currentTextChanged.connect(self._on_type_changed)
        self._table.setCellWidget(row, 0, type_combo)

        proto, auto_port = _RULE_TYPE_MAP.get(type_, ("tcp", ""))
        proto_item = QTableWidgetItem(proto)
        proto_item.setFlags(Qt.ItemIsEnabled)
        self._table.setItem(row, 1, proto_item)

        fill_port = port if port else (auto_port if not type_.startswith("Custom") else "")
        self._table.setItem(row, 2, QTableWidgetItem(fill_port))
        self._table.setItem(row, 3, QTableWidgetItem(source))
        self._table.setItem(row, 4, QTableWidgetItem(desc))

    def _on_type_changed(self, type_: str) -> None:
        sender = self.sender()
        for row in range(self._table.rowCount()):
            if self._table.cellWidget(row, 0) is sender:
                proto, port = _RULE_TYPE_MAP.get(type_, ("tcp", ""))
                item1 = self._table.item(row, 1)
                if item1:
                    item1.setText(proto)
                else:
                    pi = QTableWidgetItem(proto)
                    pi.setFlags(Qt.ItemIsEnabled)
                    self._table.setItem(row, 1, pi)
                if not type_.startswith("Custom"):
                    item2 = self._table.item(row, 2)
                    if item2:
                        item2.setText(port)
                    else:
                        self._table.setItem(row, 2, QTableWidgetItem(port))
                break

    def _remove_rule(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)

    def clear_rules(self) -> None:
        self._table.setRowCount(0)


# ---------------------------------------------------------------------------
# SecuritySection — public widget
# ---------------------------------------------------------------------------

class SecuritySection(QWidget):
    """Side-by-side New SG creator (left) and Existing SG browser (right).

    The ← arrow copies the browsed SG's name/description into the creator
    as a starting template.  Key Pair selector lives below both panels.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all_sgs: List[SecurityGroup] = []
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        outer.addLayout(self._build_panels())
        outer.addLayout(self._build_keypair_row())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, sgs: List[SecurityGroup], key_pairs: List[KeyPair]) -> None:
        """Fill the existing-SG browser and key-pair combo."""
        self._all_sgs = sgs
        self._sg_combo.clear()
        for sg in sgs:
            self._sg_combo.addItem(
                f"{sg.group_name}  ({sg.group_id})", userData=sg.group_id
            )
        self._kp_combo.clear()
        for kp in key_pairs:
            self._kp_combo.addItem(kp.key_name, userData=kp.key_name)

    def get_sg_ids(self) -> List[str]:
        sg_id = self._sg_combo.currentData()
        return [sg_id] if sg_id else []

    def get_key_name(self) -> Optional[str]:
        return self._kp_combo.currentText() or None

    def set_sg_ids(self, ids: List[str]) -> None:
        if ids:
            idx = self._sg_combo.findData(ids[0])
            if idx >= 0:
                self._sg_combo.setCurrentIndex(idx)

    def set_key_name(self, name: str) -> None:
        idx = self._kp_combo.findText(name)
        if idx >= 0:
            self._kp_combo.setCurrentIndex(idx)
        else:
            self._kp_combo.setEditText(name)

    def mark_error(self, has_error: bool) -> None:
        self._kp_combo.setStyleSheet(_ERROR_STYLE if has_error else _NORMAL_STYLE)

    # ------------------------------------------------------------------
    # Private — UI construction
    # ------------------------------------------------------------------

    def _build_panels(self) -> QHBoxLayout:
        panels = QHBoxLayout()
        panels.setSpacing(4)
        panels.addWidget(self._build_new_sg_box(), stretch=3)
        panels.addWidget(self._build_arrow_btn(), alignment=Qt.AlignVCenter)
        panels.addWidget(self._build_existing_sg_box(), stretch=2)
        return panels

    def _build_new_sg_box(self) -> QGroupBox:
        box = QGroupBox("New Security Group")
        layout = QVBoxLayout(box)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._new_name = QLineEdit()
        name_row.addWidget(self._new_name)
        layout.addLayout(name_row)

        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel("Description:"))
        self._new_desc = QLineEdit()
        desc_row.addWidget(self._new_desc)
        layout.addLayout(desc_row)

        layout.addWidget(QLabel("Inbound Rules:"))
        self._rules_table = _SgRulesTable()
        layout.addWidget(self._rules_table)
        return box

    def _build_arrow_btn(self) -> QPushButton:
        btn = QPushButton("←")
        btn.setFixedSize(34, 34)
        btn.setToolTip("Copy selected SG settings into New SG form as template")
        btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; background-color: #3498db;
                color: white; border-radius: 4px; border: none;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        btn.clicked.connect(self._on_copy)
        return btn

    def _build_existing_sg_box(self) -> QGroupBox:
        box = QGroupBox("Select Existing SG")
        layout = QVBoxLayout(box)

        self._sg_combo = SearchableComboBox()
        layout.addWidget(self._sg_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #d5d8dc;")
        layout.addWidget(sep)

        self._sg_info = QLabel("")
        self._sg_info.setWordWrap(True)
        self._sg_info.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px;"
        )
        layout.addWidget(self._sg_info)
        layout.addStretch()

        self._sg_combo.currentIndexChanged.connect(self._on_sg_selected)
        return box

    def _build_keypair_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel("Key Pair:")
        lbl.setStyleSheet("font-weight: bold; color: #2c3e50;")
        row.addWidget(lbl)
        self._kp_combo = SearchableComboBox()
        self._kp_combo.setMinimumWidth(220)
        row.addWidget(self._kp_combo)
        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Private — slots
    # ------------------------------------------------------------------

    def _on_sg_selected(self) -> None:
        sg_id = self._sg_combo.currentData()
        sg = next((s for s in self._all_sgs if s.group_id == sg_id), None)
        if sg:
            self._sg_info.setText(
                f"<b>{sg.group_name}</b><br>"
                f"ID: {sg.group_id}<br>"
                f"VPC: {sg.vpc_id}<br>"
                f"{sg.description}"
            )
        else:
            self._sg_info.setText("")

    def _on_copy(self) -> None:
        """Template the selected existing SG into the new-SG form."""
        sg_id = self._sg_combo.currentData()
        sg = next((s for s in self._all_sgs if s.group_id == sg_id), None)
        if sg:
            self._new_name.setText(f"copy-of-{sg.group_name}")
            self._new_desc.setText(sg.description)
