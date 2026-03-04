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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import InboundRule, KeyPair, SecurityGroup
from tools.ec2_launcher.ui.key_pair_dialog import CreateKeyPairDialog
from ui.common.ui_prefs import get_pref, set_pref
from ui.common.widgets import CheckableComboBox, SearchableComboBox

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


def _type_from_rule(protocol: str, port_range: str) -> str:
    """Reverse-lookup the named rule type for a given protocol + port range."""
    for name, (proto, port) in _RULE_TYPE_MAP.items():
        if name.startswith("Custom"):
            continue
        if proto == protocol and port == port_range:
            return name
    # Fallback to appropriate Custom type
    if protocol == "udp":
        return "Custom UDP"
    if protocol == "icmp":
        return "Custom ICMP"
    return "Custom TCP"


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

    def get_rules(self) -> List[InboundRule]:
        """Return current table contents as InboundRule objects."""
        rules: List[InboundRule] = []
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 0)
            proto_item = self._table.item(row, 1)
            port_item  = self._table.item(row, 2)
            src_item   = self._table.item(row, 3)
            desc_item  = self._table.item(row, 4)
            proto = proto_item.text() if proto_item else "tcp"
            proto = "all" if proto in ("-1", "all") else proto
            rules.append(InboundRule(
                protocol=proto,
                port_range=port_item.text()  if port_item  else "",
                cidr=src_item.text()         if src_item   else "0.0.0.0/0",
                description=desc_item.text() if desc_item  else "",
            ))
        return rules

    def clear_rules(self) -> None:
        self._table.setRowCount(0)

    def populate_from_rules(self, rules: List[InboundRule]) -> None:
        self.clear_rules()
        for rule in rules:
            type_ = _type_from_rule(rule.protocol, rule.port_range)
            self._add_rule(type_=type_, port=rule.port_range,
                           source=rule.cidr, desc=rule.description)


# ---------------------------------------------------------------------------
# SecuritySection — public widget
# ---------------------------------------------------------------------------

class SecuritySection(QWidget):
    """Side-by-side New SG creator (left) and Existing SG browser (right).

    Fill in the New SG form and the SG will be created automatically when
    the Launch button is pressed.  The ← arrow copies an existing SG's
    name/description into the creator as a starting template.
    Key Pair selector lives below both panels.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all_sgs: List[SecurityGroup] = []
        self._last_sg: Optional[SecurityGroup] = None   # last chip toggled — used for copy-as-template
        self._service = None  # injected after data load via set_service()
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        outer.addWidget(self._build_panels())
        outer.addLayout(self._build_keypair_row())

        # Restore saved splitter ratio
        saved = get_pref("security_splitter_sizes")
        if saved and len(saved) == 2:
            self._splitter.setSizes(saved)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, sgs: List[SecurityGroup], key_pairs: List[KeyPair]) -> None:
        """Fill the SG dropdown and key-pair combo."""
        self._all_sgs = sgs
        self._last_sg = None
        self._sg_combo.model.clear()
        self._sg_combo.lineEdit().clear()
        for sg in sgs:
            self._sg_combo.addItem(
                f"{sg.group_id}  {sg.group_name}  {sg.description}", sg.group_id
            )
        self._sg_count_lbl.setText("None selected")
        self._sg_count_lbl.setStyleSheet("color: #555; font-size: 11px;")
        self._sg_info.setText("")
        self._kp_combo.clear()
        for kp in key_pairs:
            self._kp_combo.addItem(kp.key_name, userData=kp.key_name)
        self._kp_combo.setCurrentIndex(-1)
        self._kp_combo.lineEdit().clear()

    def get_sg_ids(self) -> List[str]:
        return self._sg_combo.get_checked_data()

    def get_key_name(self) -> Optional[str]:
        return self._kp_combo.currentText() or None

    def set_sg_ids(self, ids: List[str]) -> None:
        self._sg_combo.set_checked_data(ids)

    def set_key_name(self, name: str) -> None:
        idx = self._kp_combo.findText(name)
        if idx >= 0:
            self._kp_combo.setCurrentIndex(idx)
        else:
            self._kp_combo.setEditText(name)

    def mark_error(self, has_error: bool) -> None:
        self._kp_combo.setStyleSheet(_ERROR_STYLE if has_error else _NORMAL_STYLE)

    def set_service(self, service) -> None:
        """Inject the LauncherService so key pair creation can call AWS."""
        self._service = service

    def has_new_sg(self) -> bool:
        """True if the New SG form has a name filled in."""
        return bool(self._new_name.text().strip())

    def get_new_sg_data(self) -> tuple:
        """Return (name, description, rules) from the New SG form."""
        return (
            self._new_name.text().strip(),
            self._new_desc.text().strip(),
            self._rules_table.get_rules(),
        )

    # ------------------------------------------------------------------
    # Private — UI construction
    # ------------------------------------------------------------------

    def _build_panels(self) -> QSplitter:
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._build_new_sg_box())
        self._splitter.addWidget(self._build_existing_sg_box())
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        return self._splitter

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

    def _build_existing_sg_box(self) -> QGroupBox:
        box = QGroupBox("Select Security Groups  (AWS limit: 5)")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        layout.addWidget(_policy_hint(
            "📌 SCCM: If this instance requires SCCM management, ensure the SCCM "
            "security group is included here in addition to any other groups."
        ))

        self._sg_combo = CheckableComboBox()
        self._sg_combo.lineEdit().setPlaceholderText("Select security groups…")
        layout.addWidget(self._sg_combo)

        ctrl_row = QHBoxLayout()
        self._sg_count_lbl = QLabel("None selected")
        self._sg_count_lbl.setStyleSheet("color: #555; font-size: 11px;")
        ctrl_row.addWidget(self._sg_count_lbl)
        ctrl_row.addStretch()
        copy_btn = QPushButton("← Use as template")
        copy_btn.setFixedWidth(130)
        copy_btn.setToolTip(
            "Copy the last-clicked SG's name, description, and rules\n"
            "into the New Security Group form as a starting point."
        )
        copy_btn.clicked.connect(self._on_copy)
        ctrl_row.addWidget(copy_btn)
        layout.addLayout(ctrl_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #d5d8dc;")
        layout.addWidget(sep)

        self._sg_info = QLabel("")
        self._sg_info.setWordWrap(True)
        self._sg_info.setStyleSheet("color: #555; font-size: 11px; padding: 4px;")
        layout.addWidget(self._sg_info)
        layout.addStretch()

        self._sg_combo.item_toggled.connect(self._on_sg_item_toggled)
        self._sg_combo.selection_changed.connect(self._on_sg_selection_changed)
        return box

    def _build_keypair_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel("Key Pair:")
        lbl.setStyleSheet("font-weight: bold; color: #2c3e50;")
        row.addWidget(lbl)
        self._kp_combo = SearchableComboBox()
        self._kp_combo.setMinimumWidth(220)
        row.addWidget(self._kp_combo)
        new_btn = QPushButton("Create new…")
        new_btn.setFixedWidth(110)
        new_btn.setToolTip("Create a new key pair in AWS and download the private key")
        new_btn.clicked.connect(self._on_create_key_pair)
        row.addWidget(new_btn)
        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Private — slots
    # ------------------------------------------------------------------

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        set_pref("security_splitter_sizes", self._splitter.sizes())

    def _on_sg_item_toggled(self, sg_id: str) -> None:
        """Remember last-toggled SG for copy-as-template."""
        sg = next((s for s in self._all_sgs if s.group_id == sg_id), None)
        if sg is None:
            return
        self._last_sg = sg

    def _on_sg_selection_changed(self, ids: List[str]) -> None:
        """Update the selection count label and render details for all selected SGs."""
        n = len(ids)
        if n == 0:
            self._sg_count_lbl.setText("None selected")
            self._sg_count_lbl.setStyleSheet("color: #555; font-size: 11px;")
        elif n > 5:
            self._sg_count_lbl.setText(
                f"\u26a0  {n} selected \u2014 AWS allows a maximum of 5 per instance"
            )
            self._sg_count_lbl.setStyleSheet(
                "color: #e74c3c; font-size: 11px; font-weight: bold;"
            )
        else:
            self._sg_count_lbl.setText(f"{n} of 5 selected")
            self._sg_count_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")

        # Render list of all currently selected SGs below the dropdown
        info_html = []
        for sg_id in ids:
            sg = next((s for s in self._all_sgs if s.group_id == sg_id), None)
            if sg:
                info_html.append(
                    f"<b>{sg.group_name}</b><br>"
                    f"<span style='color: #6c757d; font-size: 10px;'>ID: {sg.group_id} &nbsp;|&nbsp; VPC: {sg.vpc_id}</span><br>"
                    f"{sg.description}"
                )
        self._sg_info.setText("<br><br>".join(info_html))

    def _on_copy(self) -> None:
        """Template the last-clicked SG into the New SG form as a starting point."""
        if self._last_sg is None:
            return
        self._new_name.setText(f"copy-of-{self._last_sg.group_name}")
        self._new_desc.setText(self._last_sg.description)
        self._rules_table.populate_from_rules(self._last_sg.inbound_rules)

    def _on_create_key_pair(self) -> None:
        """Open dialog, call AWS, prompt for save path, write private key."""
        from PySide6.QtWidgets import QFileDialog

        dlg = CreateKeyPairDialog(self)
        if not dlg.exec():
            return

        name       = dlg.key_name()
        key_type   = dlg.key_type()
        key_format = dlg.key_format()
        ext        = f".{key_format}"

        # Prompt for save path before making the AWS call so a cancelled
        # file dialog doesn't leave an orphaned key pair in the account.
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Private Key",
            f"{name}{ext}",
            f"Private Key (*{ext});;All Files (*)",
        )
        if not save_path:
            return  # user cancelled — no AWS call made

        if self._service is None:
            QMessageBox.warning(
                self, "No Connection",
                "Cannot create a key pair: no AWS service is connected.\n"
                "Launch the tool with valid credentials first.",
            )
            return

        try:
            result = self._service.create_key_pair(name, key_type, key_format)
        except Exception as exc:
            QMessageBox.critical(
                self, "Key Pair Creation Failed",
                f"AWS rejected the request:\n\n{exc}",
            )
            return

        # Write private key — this is the only opportunity to capture it.
        try:
            import os
            with open(save_path, "w", encoding="utf-8") as fh:
                fh.write(result.key_material)
            os.chmod(save_path, 0o600)  # owner read/write only
        except OSError as exc:
            QMessageBox.critical(
                self, "File Save Failed",
                f"Key pair was created in AWS but could not be saved to disk:\n\n{exc}\n\n"
                "The key pair exists in your account. Delete it from the AWS console "
                "if you cannot recover the private key.",
            )
            return

        QMessageBox.information(
            self, "Key Pair Created",
            f"Key pair <b>{name}</b> created successfully.\n\n"
            f"Private key saved to:\n{save_path}\n\n"
            "Keep this file secure. AWS will not give you the private key again.",
        )

        if self._kp_combo.findText(name) < 0:
            self._kp_combo.addItem(name, userData=name)
        self._kp_combo.setCurrentIndex(self._kp_combo.findText(name))
