"""
config_form.py — Unified scrollable EC2 launch-configuration form.

Composition root for all launch-parameter sections.  No AWS calls; all data
injected via set_data().  Each section lives inside a CollapsibleSection so
the user can minimise anything they've already configured.

Section order
-------------
1. Instances  — count spinbox + pre-named instance rows
2. Image       — AMI picker
3. Hardware    — instance type + volume
4. Network     — VPC / Subnet with color badges
5. Security    — SG creator/browser + Key Pair
6. Tags        — key/value table (collapsed by default)

Public API
----------
    set_data(amis, instance_types, vpcs, subnets, sgs, key_pairs)
    apply_patch(patch: SectionPatch)
    get_launch_config() -> Optional[LaunchConfig]
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Ami, KeyPair, SecurityGroup, Subnet, Vpc
from tools.ec2_launcher.models import LaunchConfig, SectionPatch
from tools.ec2_launcher.ui.instance_names import InstanceNamesSection
from tools.ec2_launcher.ui.security_section import SecuritySection
from tools.ec2_launcher.ui.vpc_badge import VpcBadge
from ui.common.collapsible import CollapsibleSection
from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""
_VOLUME_TYPES = ["gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"]

# Applied to the scroll container so every input inherits consistent styling
_FORM_STYLE = """
    QLineEdit, QComboBox, QSpinBox {
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 5px 10px;
        min-height: 28px;
        background: white;
        color: #2c3e50;
        font-size: 13px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
        border-color: #3498db;
    }
    QLabel { color: #34495e; font-size: 13px; }
    QPushButton {
        border-radius: 4px; padding: 5px 12px; font-size: 12px;
        background-color: #ecf0f1; color: #2c3e50;
        border: 1px solid #ced4da;
    }
    QPushButton:hover  { background-color: #d5d8dc; }
    QPushButton:pressed { background-color: #bdc3c7; }
    QGroupBox {
        font-weight: bold; color: #2c3e50;
        border: 1px solid #d5d8dc; border-radius: 4px;
        margin-top: 8px; padding-top: 8px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QTableWidget {
        border: 1px solid #d5d8dc; border-radius: 4px;
        gridline-color: #e9ecef;
        selection-background-color: #d6eaf8; font-size: 12px;
    }
    QHeaderView::section {
        background-color: #ecf0f1; border: none;
        border-right: 1px solid #d5d8dc; border-bottom: 1px solid #d5d8dc;
        padding: 4px 8px; font-weight: bold; color: #2c3e50; font-size: 12px;
    }
"""


# ---------------------------------------------------------------------------
# Section widgets
# ---------------------------------------------------------------------------

class _ImageSection(QWidget):
    """AMI picker with optional 'my imports only' filter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._imports_only = QCheckBox("My imports only (CreatedBy=AWS_Tool_Import)")
        layout.addWidget(self._imports_only)

        self._ami_combo = SearchableComboBox()
        layout.addWidget(self._ami_combo)

        self._all_amis: List[Ami] = []
        self._imports_only.stateChanged.connect(self._refresh)

    def populate(self, amis: List[Ami]) -> None:
        self._all_amis = amis
        self._refresh()

    def _refresh(self) -> None:
        self._ami_combo.blockSignals(True)
        self._ami_combo.clear()
        source = self._all_amis
        if self._imports_only.isChecked():
            source = [
                a for a in source
                if any(t.key == "CreatedBy" and t.value == "AWS_Tool_Import"
                       for t in a.tags)
            ]
        for ami in source:
            self._ami_combo.addItem(f"{ami.image_id}  {ami.name}", userData=ami.image_id)
        self._ami_combo.blockSignals(False)

    def get_image_id(self) -> Optional[str]:
        return self._ami_combo.currentData()

    def set_image_id(self, image_id: str) -> None:
        idx = self._ami_combo.findData(image_id)
        if idx >= 0:
            self._ami_combo.setCurrentIndex(idx)

    def mark_error(self, has_error: bool) -> None:
        self._ami_combo.setStyleSheet(_ERROR_STYLE if has_error else _NORMAL_STYLE)


class _HardwareSection(QWidget):
    """Instance type, volume size and volume type."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Instance type:"))
        self._type_combo = SearchableComboBox()
        self._type_combo.setMinimumWidth(200)
        r1.addWidget(self._type_combo)
        r1.addStretch()
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Root volume (GiB):"))
        self._vol_size = QLineEdit("30")
        self._vol_size.setFixedWidth(80)
        r2.addWidget(self._vol_size)
        r2.addSpacing(16)
        r2.addWidget(QLabel("Type:"))
        self._vol_type = QComboBox()
        self._vol_type.addItems(_VOLUME_TYPES)
        r2.addWidget(self._vol_type)
        r2.addStretch()
        layout.addLayout(r2)

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


class _NetworkSection(QWidget):
    """VPC and Subnet selectors, each with a deterministic color badge."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

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

    def populate(self, vpcs: List[Vpc], subnets: List[Subnet]) -> None:
        self._all_subnets = subnets
        self._vpc_combo.blockSignals(True)
        self._vpc_combo.clear()
        for vpc in vpcs:
            label = vpc.name or vpc.vpc_id
            self._vpc_combo.addItem(
                f"{vpc.vpc_id}  {label}  {vpc.cidr_block}", userData=vpc.vpc_id
            )
        self._vpc_combo.blockSignals(False)
        self._on_vpc_changed()

    def _on_vpc_changed(self) -> None:
        vpc_id = self._vpc_combo.currentData() or ""
        self._vpc_badge.set_vpc(vpc_id)
        self._subnet_combo.clear()
        for sub in self._all_subnets:
            if not vpc_id or sub.vpc_id == vpc_id:
                label = sub.name or sub.subnet_id
                self._subnet_combo.addItem(
                    f"{sub.subnet_id}  {label}  {sub.cidr_block}  {sub.availability_zone}",
                    userData=sub.subnet_id,
                )
        self._subnet_badge.set_vpc(vpc_id)

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


class _TagsSection(QWidget):
    """Editable key / value tag table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Key", "Value"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 160)
        self._table.setMinimumHeight(100)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        for label, slot in [("Add Row", self._add_row), ("Remove Row", self._remove_row)]:
            btn = QPushButton(label)
            btn.setFixedWidth(100)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def get_tags(self) -> Dict[str, str]:
        tags: Dict[str, str] = {}
        for row in range(self._table.rowCount()):
            k = (self._table.item(row, 0) or QTableWidgetItem("")).text().strip()
            v = (self._table.item(row, 1) or QTableWidgetItem("")).text().strip()
            if k:
                tags[k] = v
        return tags

    def set_tags(self, tags: Dict[str, str]) -> None:
        self._table.setRowCount(0)
        for key, val in tags.items():
            self._add_row(key, val)

    def _add_row(self, key: str = "", value: str = "") -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(key))
        self._table.setItem(row, 1, QTableWidgetItem(value))

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)


# ---------------------------------------------------------------------------
# ConfigForm — public composition
# ---------------------------------------------------------------------------

class ConfigForm(QScrollArea):
    """Unified, scrollable, collapsible launch-configuration form.

    All sections default to expanded; Tags starts collapsed.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget()
        container.setStyleSheet(_FORM_STYLE)
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        # Section widgets (kept for direct method access)
        self._instances = InstanceNamesSection()
        self._image = _ImageSection()
        self._hardware = _HardwareSection()
        self._network = _NetworkSection()
        self._security = SecuritySection()
        self._tags = _TagsSection()

        # Wrap each in a CollapsibleSection
        self._sec_instances = self._wrap("Instances", self._instances)
        self._sec_image = self._wrap("Image", self._image)
        self._sec_hardware = self._wrap("Hardware", self._hardware)
        self._sec_network = self._wrap("Network", self._network)
        self._sec_security = self._wrap("Security", self._security)
        self._sec_tags = self._wrap("Tags", self._tags, collapsed=True)

        for sec in (self._sec_instances, self._sec_image, self._sec_hardware,
                    self._sec_network, self._sec_security, self._sec_tags):
            layout.addWidget(sec)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(
        self,
        amis: List[Ami],
        instance_types: List[str],
        vpcs: List[Vpc],
        subnets: List[Subnet],
        sgs: List[SecurityGroup],
        key_pairs: List[KeyPair],
    ) -> None:
        """Populate all section pickers."""
        self._image.populate(amis)
        self._hardware.populate(instance_types)
        self._network.populate(vpcs, subnets)
        self._security.populate(sgs, key_pairs)

    def apply_patch(self, patch: SectionPatch) -> None:
        """Apply non-None fields from a SectionPatch to the form."""
        if patch.image_id is not None:
            self._image.set_image_id(patch.image_id)
        if patch.instance_type is not None:
            self._hardware.set_instance_type(patch.instance_type)
        if patch.volume_gb is not None or patch.volume_type is not None:
            gb = patch.volume_gb or self._hardware.get_volume_gb() or 30
            vtype = patch.volume_type or self._hardware.get_volume_type()
            self._hardware.set_volume(gb, vtype)
        if patch.vpc_id is not None:
            self._network.set_vpc_id(patch.vpc_id)
        if patch.subnet_id is not None:
            self._network.set_subnet_id(patch.subnet_id)
        if patch.sg_ids is not None:
            self._security.set_sg_ids(patch.sg_ids)
        if patch.key_name is not None:
            self._security.set_key_name(patch.key_name)
        if patch.tags is not None:
            self._tags.set_tags(patch.tags)

    def get_launch_config(self) -> Optional[LaunchConfig]:
        """Validate form and return LaunchConfig, or None on error."""
        errors = dict(image=False, hardware=False, vpc=False, subnet=False, key=False)

        image_id = self._image.get_image_id()
        if not image_id:
            errors["image"] = True

        volume_gb = self._hardware.get_volume_gb()
        if volume_gb is None:
            errors["hardware"] = True

        vpc_id = self._network.get_vpc_id()
        if not vpc_id:
            errors["vpc"] = True

        subnet_id = self._network.get_subnet_id()
        if not subnet_id:
            errors["subnet"] = True

        key_name = self._security.get_key_name()
        if not key_name:
            errors["key"] = True

        self._image.mark_error(errors["image"])
        self._hardware.mark_error(errors["hardware"])
        self._network.mark_error(errors["vpc"], errors["subnet"])
        self._security.mark_error(errors["key"])

        # Auto-expand sections with errors
        if errors["image"]:
            self._sec_image.expand()
        if errors["hardware"]:
            self._sec_hardware.expand()
        if errors["vpc"] or errors["subnet"]:
            self._sec_network.expand()
        if errors["key"]:
            self._sec_security.expand()

        if any(errors.values()):
            return None

        return LaunchConfig(
            image_id=image_id,
            instance_type=self._hardware.get_instance_type(),
            volume_gb=volume_gb,
            volume_type=self._hardware.get_volume_type(),
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            sg_ids=self._security.get_sg_ids(),
            key_name=key_name,
            tags=self._tags.get_tags(),
            instance_count=self._instances.get_count(),
            instance_names=self._instances.get_instance_names(),
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(
        title: str, widget: QWidget, collapsed: bool = False
    ) -> CollapsibleSection:
        sec = CollapsibleSection(title, collapsed=collapsed)
        sec.set_content(widget)
        return sec
