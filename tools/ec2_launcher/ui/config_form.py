"""
ConfigForm — unified scrollable launch-configuration form.

Single responsibility: capture all EC2 launch parameters in one view.
No AWS calls; populated via set_data(); patched via apply_patch().

Sections
--------
1. Image     — AMI picker + "my imports" filter
2. Hardware  — instance type, volume size/type
3. Network   — VPC (+ badge), Subnet (+ badge, filtered by VPC)
4. Security  — SG chips (checkable), key-pair picker
5. Tags      — editable key/value table
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QSizePolicy,
)
from PySide6.QtCore import Qt

from core.models import Ami, KeyPair, SecurityGroup, Subnet, Vpc
from tools.ec2_launcher.models import LaunchConfig, SectionPatch
from tools.ec2_launcher.ui.sg_chips import SgChipsWidget
from tools.ec2_launcher.ui.vpc_badge import VpcBadge
from ui.common.widgets import SearchableComboBox

_VOLUME_TYPES = ["gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"]
_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""


class _ImageSection(QGroupBox):
    """Section 1: AMI selection."""

    def __init__(self, parent=None) -> None:
        super().__init__("Image", parent)
        layout = QVBoxLayout(self)

        self._imports_only = QCheckBox("My imports only (CreatedBy=AWS_Tool_Import)")
        layout.addWidget(self._imports_only)

        self._ami_combo = SearchableComboBox()
        self._ami_combo.setMinimumWidth(420)
        layout.addWidget(self._ami_combo)

        self._all_amis: List[Ami] = []
        self._imports_only.stateChanged.connect(self._refresh_ami_list)

    def populate(self, amis: List[Ami]) -> None:
        self._all_amis = amis
        self._refresh_ami_list()

    def _refresh_ami_list(self) -> None:
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


class _HardwareSection(QGroupBox):
    """Section 2: Instance type + volume."""

    def __init__(self, parent=None) -> None:
        super().__init__("Hardware", parent)
        layout = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Instance type:"))
        self._type_combo = SearchableComboBox()
        self._type_combo.setMinimumWidth(200)
        row1.addWidget(self._type_combo)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Root volume (GiB):"))
        self._vol_size = QLineEdit("30")
        self._vol_size.setFixedWidth(80)
        row2.addWidget(self._vol_size)
        row2.addSpacing(16)
        row2.addWidget(QLabel("Type:"))
        self._vol_type = QComboBox()
        self._vol_type.addItems(_VOLUME_TYPES)
        row2.addWidget(self._vol_type)
        row2.addStretch()
        layout.addLayout(row2)

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


class _NetworkSection(QGroupBox):
    """Section 3: VPC + Subnet, each with a color badge."""

    def __init__(self, parent=None) -> None:
        super().__init__("Network", parent)
        layout = QVBoxLayout(self)

        vpc_row = QHBoxLayout()
        self._vpc_badge = VpcBadge()
        vpc_row.addWidget(self._vpc_badge)
        vpc_row.addWidget(QLabel("VPC:"))
        self._vpc_combo = SearchableComboBox()
        self._vpc_combo.setMinimumWidth(320)
        vpc_row.addWidget(self._vpc_combo)
        vpc_row.addStretch()
        layout.addLayout(vpc_row)

        subnet_row = QHBoxLayout()
        self._subnet_badge = VpcBadge()
        subnet_row.addWidget(self._subnet_badge)
        subnet_row.addWidget(QLabel("Subnet:"))
        self._subnet_combo = SearchableComboBox()
        self._subnet_combo.setMinimumWidth(320)
        subnet_row.addWidget(self._subnet_combo)
        subnet_row.addStretch()
        layout.addLayout(subnet_row)

        self._all_subnets: List[Subnet] = []
        self._vpc_combo.currentIndexChanged.connect(self._on_vpc_changed)

    def populate(self, vpcs: List[Vpc], subnets: List[Subnet]) -> None:
        self._all_subnets = subnets
        self._vpc_combo.blockSignals(True)
        self._vpc_combo.clear()
        for vpc in vpcs:
            label = vpc.name or vpc.vpc_id
            display = f"{vpc.vpc_id}  {label}  {vpc.cidr_block}"
            self._vpc_combo.addItem(display, userData=vpc.vpc_id)
        self._vpc_combo.blockSignals(False)
        self._on_vpc_changed()

    def _on_vpc_changed(self) -> None:
        vpc_id = self._vpc_combo.currentData() or ""
        self._vpc_badge.set_vpc(vpc_id)
        self._reload_subnets(vpc_id)

    def _reload_subnets(self, vpc_id: str) -> None:
        self._subnet_combo.clear()
        subs = [s for s in self._all_subnets if not vpc_id or s.vpc_id == vpc_id]
        for sub in subs:
            label = sub.name or sub.subnet_id
            display = f"{sub.subnet_id}  {label}  {sub.cidr_block}  {sub.availability_zone}"
            self._subnet_combo.addItem(display, userData=sub.subnet_id)
        # Badge follows the same VPC color
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


class _SecuritySection(QGroupBox):
    """Section 4: SG chips + Key Pair."""

    def __init__(self, parent=None) -> None:
        super().__init__("Security", parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Security Groups (click to select):"))
        self._sg_chips = SgChipsWidget(checkable=True)
        layout.addWidget(self._sg_chips)

        kp_row = QHBoxLayout()
        kp_row.addWidget(QLabel("Key Pair:"))
        self._kp_combo = SearchableComboBox()
        self._kp_combo.setMinimumWidth(240)
        kp_row.addWidget(self._kp_combo)
        kp_row.addStretch()
        layout.addLayout(kp_row)

    def populate(self, sgs: List[SecurityGroup], key_pairs: List[KeyPair]) -> None:
        self._sg_chips.set_groups(sgs)
        self._kp_combo.clear()
        for kp in key_pairs:
            self._kp_combo.addItem(kp.key_name, userData=kp.key_name)

    def get_sg_ids(self) -> List[str]:
        return self._sg_chips.get_selected_ids()

    def get_key_name(self) -> Optional[str]:
        return self._kp_combo.currentText() or None

    def set_sg_ids(self, ids: List[str]) -> None:
        self._sg_chips.set_selected_ids(ids)

    def set_key_name(self, name: str) -> None:
        idx = self._kp_combo.findText(name)
        if idx >= 0:
            self._kp_combo.setCurrentIndex(idx)
        else:
            self._kp_combo.setEditText(name)

    def mark_error(self, has_error: bool) -> None:
        style = _ERROR_STYLE if has_error else _NORMAL_STYLE
        self._kp_combo.setStyleSheet(style)


class _TagsSection(QGroupBox):
    """Section 5: Editable key/value tag table."""

    def __init__(self, parent=None) -> None:
        super().__init__("Tags", parent)
        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Key", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setMinimumHeight(100)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Row")
        btn_add.setFixedWidth(90)
        btn_remove = QPushButton("Remove Row")
        btn_remove.setFixedWidth(100)
        btn_add.clicked.connect(self._add_row)
        btn_remove.clicked.connect(self._remove_row)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def get_tags(self) -> Dict[str, str]:
        tags: Dict[str, str] = {}
        for row in range(self._table.rowCount()):
            key_item = self._table.item(row, 0)
            val_item = self._table.item(row, 1)
            key = (key_item.text().strip() if key_item else "")
            val = (val_item.text().strip() if val_item else "")
            if key:
                tags[key] = val
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
        selected = self._table.currentRow()
        if selected >= 0:
            self._table.removeRow(selected)


class ConfigForm(QScrollArea):
    """Unified scrollable form for all EC2 launch parameters.

    Public API
    ----------
    set_data(amis, instance_types, vpcs, subnets, sgs, key_pairs)
        Populate all pickers.
    apply_patch(patch: SectionPatch)
        Update only the fields in patch that are not None.
    get_launch_config() -> Optional[LaunchConfig]
        Validate and return; returns None and shows inline errors if incomplete.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        self._image = _ImageSection()
        self._hardware = _HardwareSection()
        self._network = _NetworkSection()
        self._security = _SecuritySection()
        self._tags = _TagsSection()

        for section in (self._image, self._hardware, self._network,
                        self._security, self._tags):
            layout.addWidget(section)

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
        """Populate all section pickers with the supplied data."""
        self._image.populate(amis)
        self._hardware.populate(instance_types)
        self._network.populate(vpcs, subnets)
        self._security.populate(sgs, key_pairs)

    def apply_patch(self, patch: SectionPatch) -> None:
        """Apply non-None fields from patch into the form."""
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
        """Validate form and return LaunchConfig, or None on validation failure."""
        errors: Dict[str, bool] = {
            "image": False,
            "hardware": False,
            "vpc": False,
            "subnet": False,
            "key": False,
        }

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
        )
