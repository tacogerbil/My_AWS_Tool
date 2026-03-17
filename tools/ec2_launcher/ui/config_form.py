"""
config_form.py — Unified scrollable EC2 launch-configuration form.

Pure composition root: creates section widgets, wraps each in a
CollapsibleSection, and exposes a single public API to the launcher window.
No AWS calls; all data injected via set_data().

Section order
-------------
1. Instances  — count spinbox + pre-named instance rows
2. Image       — tabbed AMI picker (Quick Start / My AMIs / Recents)
3. Hardware    — instance type + spec info card
4. Storage     — EBS volume list (root + additional)
5. Network     — VPC / Subnet with VPC color badges
6. Security    — SG creator/browser + Key Pair
7. Tags        — key/value table (collapsed by default)

Public API
----------
    set_data(my_amis, quick_start_amis, instance_types, vpcs, subnets, sgs, key_pairs)
    apply_patch(patch: SectionPatch)
    get_launch_config() -> Optional[LaunchConfig]
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# NetBIOS computer-name rules: 1–15 chars, letters/digits/hyphens,
# must not start or end with a hyphen.
_NETBIOS_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-]{0,13}[A-Za-z0-9])?$")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from core.models import Ami, KeyPair, SecurityGroup, Subnet, Vpc
from ui.common.styles import get_checkbox_style
from tools.ec2_launcher.models import LaunchConfig, SectionPatch
from tools.ec2_launcher.ui.ami_section import AmiSection
from tools.ec2_launcher.ui.hardware_section import HardwareSection
from tools.ec2_launcher.ui.instance_names import InstanceNamesSection
from tools.ec2_launcher.ui.network_section import NetworkSection
from tools.ec2_launcher.ui.security_section import SecuritySection
from tools.ec2_launcher.ui.storage_section import StorageSection
from tools.ec2_launcher.ui.tags_section import TagsSection
from tools.ec2_launcher.ui.windows_setup_section import WindowsSetupSection
from ui.common.collapsible import CollapsibleSection

# QSpinBox sub-controls must be explicitly defined when any stylesheet is set,
# otherwise Qt zeroes out the button geometry and the arrows become unclickable.
#
# margin-top: 1px on inputs/buttons prevents the top border from being clipped
# by the layout cell edge — a known Qt/Linux stylesheet rendering quirk.
def _build_form_style() -> str:
    return """
    QLineEdit {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 10px; min-height: 28px;
        background: white; color: #2c3e50; font-size: 13px;
    }
    /* QComboBox must use pt (not px) — Qt stores px fonts as pointSize=-1
       internally, which gets propagated to popup views and triggers:
       "QFont::setPointSize: Point size <= 0 (-1)" */
    QComboBox {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 10px; min-height: 28px;
        background: white; color: #2c3e50; font-size: 10pt;
    }
    QLineEdit:focus, QComboBox:focus { border-color: #3498db; }
    QSpinBox {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 22px 5px 10px; min-height: 28px;
        background: white; color: #2c3e50; font-size: 13px;
    }
    QSpinBox:focus { border-color: #3498db; }
    QSpinBox::up-button {
        subcontrol-origin: padding; subcontrol-position: top right;
        width: 20px; height: 15px;
        background: #ecf0f1;
        border-left: 1px solid #ced4da; border-bottom: 1px solid #ced4da;
        border-top-right-radius: 3px;
    }
    QSpinBox::up-button:hover   { background: #d5d8dc; }
    QSpinBox::up-button:pressed { background: #bdc3c7; }
    QSpinBox::up-arrow   { width: 8px; height: 8px; }
    QSpinBox::down-button {
        subcontrol-origin: padding; subcontrol-position: bottom right;
        width: 20px; height: 15px;
        background: #ecf0f1;
        border-left: 1px solid #ced4da; border-top: 1px solid #ced4da;
        border-bottom-right-radius: 3px;
    }
    QSpinBox::down-button:hover   { background: #d5d8dc; }
    QSpinBox::down-button:pressed { background: #bdc3c7; }
    QSpinBox::down-arrow { width: 8px; height: 8px; }
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
""" + get_checkbox_style()

_FORM_STYLE = _build_form_style()

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
        self._windows   = WindowsSetupSection()

        self._sec_instances = self._wrap("Instances",     self._instances)
        self._sec_image     = self._wrap("Image",         self._image)
        self._sec_hardware  = self._wrap("Hardware",      self._hardware)
        self._sec_storage   = self._wrap("Storage",       self._storage)
        self._sec_network   = self._wrap("Network",       self._network)
        self._sec_security  = self._wrap("Security",      self._security)
        self._sec_tags      = self._wrap("Tags",          self._tags,    collapsed=True)
        self._sec_windows   = self._wrap("Windows Setup", self._windows, collapsed=True)

        for sec in (
            self._sec_instances, self._sec_image, self._sec_hardware,
            self._sec_storage, self._sec_network, self._sec_security,
            self._sec_tags, self._sec_windows,
        ):
            layout.addWidget(sec)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(
        self,
        my_amis: List[Ami],
        quick_start_amis: List[Ami],
        instance_types: List[str],
        vpcs: List[Vpc],
        subnets: List[Subnet],
        sgs: List[SecurityGroup],
        key_pairs: List[KeyPair],
    ) -> None:
        """Populate all section pickers from injected data."""
        self._image.populate(quick_start_amis=quick_start_amis, my_amis=my_amis)
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
            # Grab current root vol to preserve whichever field wasn't patched
            current_vols = self._storage.get_volumes()
            root = current_vols[0] if current_vols else None
            from tools.ec2_launcher.models import VolumeConfig
            new_root = VolumeConfig(
                device_name=root.device_name if root else "/dev/sda1",
                size_gb=patch.volume_gb or (root.size_gb if root else 30),
                volume_type=patch.volume_type or (root.volume_type if root else "gp3"),
                delete_on_termination=root.delete_on_termination if root else True,
                encrypted=root.encrypted if root else False,
            )
            self._storage.set_volumes([new_root] + (current_vols[1:] if current_vols else []))
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
            image=False, instance_type=False, storage=False,
            vpc=False, subnet=False, key=False, sg=False
        )

        image_id = self._image.get_image_id()
        if not image_id:
            errors["image"] = True

        instance_type = self._hardware.get_instance_type()
        if not instance_type:
            errors["instance_type"] = True

        # Volume settings come exclusively from StorageSection
        volumes = self._storage.get_volumes()
        root_vol = volumes[0] if volumes else None
        volume_gb   = root_vol.size_gb   if root_vol else None
        volume_type = root_vol.volume_type if root_vol else "gp3"
        if not volume_gb:
            errors["storage"] = True

        vpc_id = self._network.get_vpc_id()
        if not vpc_id:
            errors["vpc"] = True

        subnet_id = self._network.get_subnet_id()
        if not subnet_id:
            errors["subnet"] = True

        key_name = self._security.get_key_name()
        if not key_name:
            errors["key"] = True

        # At least one SG must be explicitly selected or a new SG form must be filled.
        # AWS will NOT fall back to a default SG — launching with an empty list is
        # a security violation in this environment.
        sg_ids = self._security.get_sg_ids()
        if not sg_ids and not self.has_pending_sg():
            errors["sg"] = True

        self._image.mark_error(errors["image"])
        self._hardware.mark_error(errors["instance_type"])
        self._network.mark_error(errors["vpc"], errors["subnet"])
        self._security.mark_error(errors["key"], errors["sg"])

        # Auto-expand sections that failed validation so errors are visible
        if errors["image"]:                              self._sec_image.expand()
        if errors["instance_type"]:                      self._sec_hardware.expand()
        if errors["storage"]:                            self._sec_storage.expand()
        if errors["vpc"] or errors["subnet"]:            self._sec_network.expand()
        if errors["key"] or errors["sg"]:                self._sec_security.expand()

        if any(errors.values()):
            return None

        # Layer 1 — domain-join name validation (no fallbacks allowed).
        if self._windows.get_domain_config() is not None:
            blank_indices = self._instances.mark_blank_errors()
            dj_errors = self._domain_join_name_errors(blank_indices)
            if dj_errors:
                self._sec_instances.expand()
                return None

        domain_cfg = self._windows.get_domain_config()
        if domain_cfg is not None:
            from tools.ec2_launcher.ui.userdata_builder import build_windows_userdata
            user_data_template = build_windows_userdata(
                cfg=domain_cfg,
                timezone=self._windows.get_timezone(),
                dns_servers=self._windows.get_dns_servers(),
            )
            iam_profile = domain_cfg.iam_profile
        else:
            # No domain join — still apply timezone and DNS via minimal UserData.
            # tzutil /s is Windows-only; on Linux it is a no-op.
            from tools.ec2_launcher.ui.userdata_builder import build_timezone_userdata
            user_data_template = build_timezone_userdata(
                timezone=self._windows.get_timezone(),
                dns_servers=self._windows.get_dns_servers(),
            )
            iam_profile = None

        return LaunchConfig(
            image_id=image_id,
            instance_type=instance_type,
            volume_gb=volume_gb,
            volume_type=volume_type,
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            sg_ids=self._security.get_sg_ids(),
            key_name=key_name,
            tags=self._tags.get_tags(),
            instance_count=self._instances.get_count(),
            instance_names=self._instances.get_instance_names(),
            volumes=volumes,
            user_data_template=user_data_template,
            iam_instance_profile=iam_profile,
            # Network section fields (moved from Advanced)
            associate_public_ip=self._network.get_associate_public_ip(),
            imdsv2_required=self._network.get_imdsv2_required(),
            enable_termination_protection=self._network.get_termination_protection(),
            timezone=self._windows.get_timezone(),
            dns_servers=self._windows.get_dns_servers(),
        )

    def get_validation_errors(self) -> List[str]:
        """Return human-readable list of validation failures (no UI side effects)."""
        missing: List[str] = []
        if not self._image.get_image_id():
            missing.append("AMI / Image")
        if not self._hardware.get_instance_type():
            missing.append("Instance Type")
        volumes = self._storage.get_volumes()
        root_vol = volumes[0] if volumes else None
        if not (root_vol and root_vol.size_gb):
            missing.append("Root Volume Size (Storage section)")
        if not self._network.get_vpc_id():
            missing.append("VPC")
        if not self._network.get_subnet_id():
            missing.append("Subnet")
        if not self._security.get_key_name():
            missing.append("Key Pair")

        if not self._security.get_sg_ids() and not self.has_pending_sg():
            missing.append(
                "Security Group — at least one must be selected "
                "(no default SG will be applied)"
            )

        if self._windows.get_domain_config() is not None:
            blank_indices = self._instances.mark_blank_errors()
            missing.extend(self._domain_join_name_errors(blank_indices))

        return missing

    def set_service(self, service) -> None:
        """Inject the LauncherService so sub-sections can make AWS calls (e.g. key pair creation)."""
        self._security.set_service(service)

    def set_instance_profiles(self, profiles: List[str]) -> None:
        """Populate the permission profile dropdown in the Windows Setup section."""
        self._windows.populate_profiles(profiles)

    def get_domain_config(self):
        """Return WindowsDomainConfig if Windows Setup is filled, else None."""
        return self._windows.get_domain_config()

    def has_pending_sg(self) -> bool:
        """True if the New SG form has a name — SG will be created at launch."""
        return self._security.has_new_sg()

    def get_new_sg_data(self) -> tuple:
        """Return (name, description, rules) from the New SG form."""
        return self._security.get_new_sg_data()

    def get_current_vpc_id(self) -> Optional[str]:
        """Return the currently selected VPC ID (needed to scope new SGs)."""
        return self._network.get_vpc_id()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _domain_join_name_errors(self, blank_indices: List[int]) -> List[str]:
        """Return domain-join name validation error strings (no UI mutations).

        Parameters
        ----------
        blank_indices: 0-based row indices already determined to be blank.
                       Obtained from ``InstanceNamesSection.mark_blank_errors()``.

        Returns
        -------
        List of human-readable error strings; empty when all names are valid.
        """
        errors: List[str] = []

        if blank_indices:
            human = [str(i + 1) for i in blank_indices]
            errors.append(
                "Instance names are required for domain join — "
                f"blank: {', '.join(human)}"
            )

        for i, name in enumerate(self._instances.get_instance_names()):
            if not _NETBIOS_RE.match(name):
                errors.append(
                    f"Instance {i + 1}: '{name}' is not a valid computer name "
                    "(max 15 chars, letters/digits/hyphens, "
                    "no leading/trailing hyphens)"
                )

        return errors

    @staticmethod
    def _wrap(
        title: str, widget: QWidget, collapsed: bool = False
    ) -> CollapsibleSection:
        sec = CollapsibleSection(title, collapsed=collapsed)
        sec.set_content(widget)
        return sec
