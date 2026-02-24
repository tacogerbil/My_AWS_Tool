"""
config_form.py — Unified scrollable EC2 launch-configuration form.

Pure composition root: creates section widgets, wraps each in a
CollapsibleSection, and exposes a single public API to the launcher window.
No AWS calls; all data injected via set_data().

Section order
-------------
1. Instances  — count spinbox + pre-named instance rows
2. Image       — tabbed AMI picker (Quick Start / My AMIs / Recents)
3. Hardware    — instance type + info card + root volume
4. Network     — VPC / Subnet with VPC color badges
5. Security    — SG creator/browser + Key Pair
6. Storage     — EBS volume list (root + additional)
7. Tags        — key/value table (collapsed by default)

Public API
----------
    set_data(amis, instance_types, vpcs, subnets, sgs, key_pairs)
    apply_patch(patch: SectionPatch)
    get_launch_config() -> Optional[LaunchConfig]
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from core.models import Ami, KeyPair, SecurityGroup, Subnet, Vpc
from tools.ec2_launcher.models import LaunchConfig, SectionPatch
from tools.ec2_launcher.ui.ami_section import AmiSection
from tools.ec2_launcher.ui.hardware_section import HardwareSection
from tools.ec2_launcher.ui.instance_names import InstanceNamesSection
from tools.ec2_launcher.ui.network_section import NetworkSection
from tools.ec2_launcher.ui.security_section import SecuritySection
from tools.ec2_launcher.ui.storage_section import StorageSection
from tools.ec2_launcher.ui.tags_section import TagsSection
from ui.common.collapsible import CollapsibleSection

# QSpinBox sub-controls must be explicitly defined when any stylesheet is set,
# otherwise Qt zeroes out the button geometry and the arrows become unclickable.
_FORM_STYLE = """
    QLineEdit, QComboBox {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 10px; min-height: 28px;
        background: white; color: #2c3e50; font-size: 13px;
    }
    QLineEdit:focus, QComboBox:focus { border-color: #3498db; }
    QSpinBox {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 4px 5px 10px; min-height: 28px;
        background: white; color: #2c3e50; font-size: 13px;
    }
    QSpinBox:focus { border-color: #3498db; }
    QSpinBox::up-button {
        subcontrol-origin: border; subcontrol-position: top right;
        width: 20px; background: #ecf0f1;
        border-left: 1px solid #ced4da; border-bottom: 1px solid #ced4da;
        border-top-right-radius: 3px;
    }
    QSpinBox::up-button:hover   { background: #d5d8dc; }
    QSpinBox::up-button:pressed { background: #bdc3c7; }
    QSpinBox::down-button {
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 20px; background: #ecf0f1;
        border-left: 1px solid #ced4da; border-top: 1px solid #ced4da;
        border-bottom-right-radius: 3px;
    }
    QSpinBox::down-button:hover   { background: #d5d8dc; }
    QSpinBox::down-button:pressed { background: #bdc3c7; }
    QLabel { color: #34495e; font-size: 13px; }
    QPushButton {
        border-radius: 4px; padding: 5px 12px; font-size: 12px;
        background-color: #ecf0f1; color: #2c3e50; border: 1px solid #ced4da;
    }
    QPushButton:hover   { background-color: #d5d8dc; }
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

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""


class ConfigForm(QScrollArea):
    """Unified, scrollable, collapsible EC2 launch-configuration form."""

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

        self._instances = InstanceNamesSection()
        self._image     = AmiSection()
        self._hardware  = HardwareSection()
        self._network   = NetworkSection()
        self._security  = SecuritySection()
        self._storage   = StorageSection()
        self._tags      = TagsSection()

        self._sec_instances = self._wrap("Instances", self._instances)
        self._sec_image     = self._wrap("Image",     self._image)
        self._sec_hardware  = self._wrap("Hardware",  self._hardware)
        self._sec_network   = self._wrap("Network",   self._network)
        self._sec_security  = self._wrap("Security",  self._security)
        self._sec_storage   = self._wrap("Storage",   self._storage)
        self._sec_tags      = self._wrap("Tags",      self._tags, collapsed=True)

        for sec in (
            self._sec_instances, self._sec_image, self._sec_hardware,
            self._sec_network, self._sec_security, self._sec_storage,
            self._sec_tags,
        ):
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
        """Populate all section pickers from injected data."""
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
            gb    = patch.volume_gb   or self._hardware.get_volume_gb() or 30
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
        """Validate and return LaunchConfig, or None on validation failure."""
        errors: Dict[str, bool] = dict(
            image=False, hardware=False, vpc=False, subnet=False, key=False
        )

        image_id  = self._image.get_image_id()
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

        # Auto-expand sections that failed validation so errors are visible
        if errors["image"]:                        self._sec_image.expand()
        if errors["hardware"]:                     self._sec_hardware.expand()
        if errors["vpc"] or errors["subnet"]:      self._sec_network.expand()
        if errors["key"]:                          self._sec_security.expand()

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
            volumes=self._storage.get_volumes(),
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
