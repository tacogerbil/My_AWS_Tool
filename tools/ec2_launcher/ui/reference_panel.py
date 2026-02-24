"""
ReferencePanel — right-hand panel for loading a reference instance
and selectively applying its settings to the ConfigForm.

Responsibilities
----------------
- Instance selector (SearchableComboBox + Load button)
- Section checkboxes (Image, Hardware, Network, Security, Key Pair, Tags)
- "Apply Checked" builds a SectionPatch and emits sections_applied
- History QListWidget records every apply action with provenance

No AWS calls; populated via set_instances().
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QListWidget, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from core.models import Instance, SecurityGroup
from tools.ec2_launcher.models import SectionPatch
from tools.ec2_launcher.ui.sg_chips import SgChipsWidget
from tools.ec2_launcher.ui.vpc_badge import VpcBadge
from ui.common.widgets import SearchableComboBox

_STATE_COLORS: Dict[str, str] = {
    "running": "#27ae60",
    "stopped": "#7f8c8d",
    "pending": "#f39c12",
    "stopping": "#e67e22",
    "terminated": "#e74c3c",
    "shutting-down": "#c0392b",
}


def _instance_label(inst: Instance) -> str:
    name = inst.name or "Unnamed"
    return f"{name} ({inst.instance_id}) — {inst.instance_type} — {inst.state}"


def _tags_summary(inst: Instance) -> str:
    parts = [f"{t.key}={t.value}" for t in inst.tags[:4]]
    return ", ".join(parts) or "(none)"


class ReferencePanel(QWidget):
    """Right-hand reference instance comparison panel.

    Signals
    -------
    sections_applied(SectionPatch)
        Emitted when the user clicks "Apply Checked".
    """

    sections_applied = Signal(object)  # SectionPatch

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._instances: Dict[str, Instance] = {}
        self._loaded: Optional[Instance] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        outer.addWidget(self._build_selector_zone())
        outer.addWidget(self._build_sections_zone())
        outer.addWidget(self._build_history_zone())

        self._sections_zone.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_instances(self, instances: List[Instance]) -> None:
        """Populate the instance selector combo."""
        self._instances = {inst.instance_id: inst for inst in instances}
        self._instance_combo.clear()
        for inst in instances:
            self._instance_combo.addItem(_instance_label(inst), userData=inst.instance_id)

    def add_history_entry(self, text: str) -> None:
        """Append a provenance line to the history list."""
        self._history_list.addItem(text)
        self._history_list.scrollToBottom()

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    def _build_selector_zone(self) -> QWidget:
        zone = QGroupBox("Reference Instance")
        layout = QHBoxLayout(zone)

        self._instance_combo = SearchableComboBox()
        self._instance_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._instance_combo)

        self._load_btn = QPushButton("Load →")
        self._load_btn.setFixedWidth(80)
        self._load_btn.clicked.connect(self._on_load)
        layout.addWidget(self._load_btn)

        self._selector_badge = VpcBadge()
        layout.addWidget(self._selector_badge)

        return zone

    def _build_sections_zone(self) -> QGroupBox:
        self._sections_zone = QGroupBox("Instance Details")
        layout = QVBoxLayout(self._sections_zone)

        # Instance header
        self._inst_header = QLabel("")
        self._inst_header.setWordWrap(True)
        layout.addWidget(self._inst_header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #bdc3c7;")
        layout.addWidget(sep)

        # Section checkboxes
        self._cb_image = QCheckBox()
        self._lbl_image = QLabel("")
        self._lbl_image.setWordWrap(True)
        layout.addLayout(self._checkbox_row(self._cb_image, "Image", self._lbl_image))

        self._cb_hardware = QCheckBox()
        self._lbl_hardware = QLabel("")
        layout.addLayout(self._checkbox_row(self._cb_hardware, "Hardware", self._lbl_hardware))

        self._cb_network = QCheckBox()
        self._net_row_widget = self._build_network_row()
        layout.addLayout(self._checkbox_row(self._cb_network, "Network", self._net_row_widget))

        self._cb_security = QCheckBox()
        self._sg_chips_ref = SgChipsWidget(checkable=False)
        layout.addLayout(self._checkbox_row(self._cb_security, "Security", self._sg_chips_ref))

        self._cb_keypair = QCheckBox()
        self._lbl_keypair = QLabel("")
        layout.addLayout(self._checkbox_row(self._cb_keypair, "Key Pair", self._lbl_keypair))

        self._cb_tags = QCheckBox()
        self._lbl_tags = QLabel("")
        self._lbl_tags.setWordWrap(True)
        layout.addLayout(self._checkbox_row(self._cb_tags, "Tags", self._lbl_tags))

        # Apply button
        self._apply_btn = QPushButton("← Apply Checked")
        self._apply_btn.setStyleSheet(
            "background-color: #27ae60; color: white; border-radius: 4px; padding: 6px 12px;"
        )
        self._apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self._apply_btn, alignment=Qt.AlignRight)

        return self._sections_zone

    def _build_network_row(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        self._net_badge = VpcBadge()
        self._lbl_network = QLabel("")
        row.addWidget(self._net_badge)
        row.addSpacing(4)
        row.addWidget(self._lbl_network)
        row.addStretch()
        return w

    def _build_history_zone(self) -> QGroupBox:
        box = QGroupBox("Apply History")
        layout = QVBoxLayout(box)
        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(120)
        layout.addWidget(self._history_list)
        return box

    @staticmethod
    def _checkbox_row(cb: QCheckBox, label: str, detail_widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        cb.setFixedWidth(20)
        row.addWidget(cb)
        lbl = QLabel(f"<b>{label}</b>")
        lbl.setFixedWidth(68)
        row.addWidget(lbl)
        row.addWidget(detail_widget)
        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_load(self) -> None:
        inst_id = self._instance_combo.currentData()
        if not inst_id:
            return
        inst = self._instances.get(inst_id)
        if not inst:
            return
        self._loaded = inst
        self._populate_sections(inst)
        self._selector_badge.set_vpc(inst.vpc_id)
        self._sections_zone.setVisible(True)

    def _populate_sections(self, inst: Instance) -> None:
        # Header
        state_color = _STATE_COLORS.get(inst.state, "#7f8c8d")
        name = inst.name or "Unnamed"
        self._inst_header.setText(
            f'<b>{name}</b> &nbsp; {inst.instance_id}<br>'
            f'{inst.instance_type} &nbsp; '
            f'<span style="color:{state_color};">{inst.state}</span>'
        )

        # Image
        self._lbl_image.setText(inst.image_id)

        # Hardware (no volume info on Instance model — show type)
        self._lbl_hardware.setText(inst.instance_type)

        # Network
        vpc_id = inst.vpc_id or ""
        self._net_badge.set_vpc(vpc_id)
        self._lbl_network.setText(f"{vpc_id}  /  {inst.subnet_id}")

        # Security
        self._sg_chips_ref.set_groups(inst.security_groups)

        # Key Pair
        self._lbl_keypair.setText(inst.key_name or "(none)")

        # Tags
        self._lbl_tags.setText(_tags_summary(inst))

    def _on_apply(self) -> None:
        if self._loaded is None:
            return

        inst = self._loaded
        patch = SectionPatch(
            source_instance_id=inst.instance_id,
            source_name=inst.name,
        )

        checked_sections: List[str] = []

        if self._cb_image.isChecked():
            patch.image_id = inst.image_id
            checked_sections.append("Image")

        if self._cb_hardware.isChecked():
            patch.instance_type = inst.instance_type
            checked_sections.append("Hardware")

        if self._cb_network.isChecked():
            patch.vpc_id = inst.vpc_id
            patch.subnet_id = inst.subnet_id
            checked_sections.append("Network")

        if self._cb_security.isChecked():
            patch.sg_ids = [sg.group_id for sg in inst.security_groups]
            checked_sections.append("Security")

        if self._cb_keypair.isChecked():
            patch.key_name = inst.key_name
            checked_sections.append("Key Pair")

        if self._cb_tags.isChecked():
            patch.tags = {t.key: t.value for t in inst.tags}
            checked_sections.append("Tags")

        if not checked_sections:
            return

        self.sections_applied.emit(patch)
