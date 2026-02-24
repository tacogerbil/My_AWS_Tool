"""
LauncherWindow — composition root for the EC2 Launcher.

Single responsibility: wire ConfigForm + ReferencePanel together.
No business logic; no AWS calls; no form validation logic.

Layout
------
Toolbar  [title label .................. Launch button]
───────────────────────────────────────────────────────
ConfigForm (60%)  |  ReferencePanel (40%)
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt

from tools.ec2_launcher.models import SectionPatch
from tools.ec2_launcher.ui.config_form import ConfigForm
from tools.ec2_launcher.ui.reference_panel import ReferencePanel

logger = logging.getLogger(__name__)


class LauncherWindow(QWidget):
    """Main window for the EC2 Launcher tool."""

    def __init__(self, service=None, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self.setWindowTitle("EC2 Launcher")
        self.resize(1300, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_body(), stretch=1)

        self._wire_signals()
        self._load_data()

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background-color: #2c3e50;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)

        title = QLabel("EC2 Launcher")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        row.addWidget(title)
        row.addStretch()

        self._launch_btn = QPushButton("Launch Instance")
        self._launch_btn.setFixedWidth(140)
        self._launch_btn.setStyleSheet(
            "background-color: #27ae60; color: white; border-radius: 4px; padding: 6px;"
        )
        self._launch_btn.clicked.connect(self._on_launch)
        row.addWidget(self._launch_btn)

        return bar

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)

        self._config_form = ConfigForm()
        self._reference_panel = ReferencePanel()

        splitter.addWidget(self._config_form)
        splitter.addWidget(self._reference_panel)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        return splitter

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._reference_panel.sections_applied.connect(self._on_sections_applied)

    def _on_sections_applied(self, patch: SectionPatch) -> None:
        self._config_form.apply_patch(patch)
        sections = self._applied_section_names(patch)
        source = patch.source_name or patch.source_instance_id or "unknown"
        entry = f"{sections} ← {patch.source_instance_id} '{source}'"
        self._reference_panel.add_history_entry(entry)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        if self._service is None:
            self._load_mock_data()
            return
        try:
            my_amis = self._service.list_my_amis()
            quick_start_amis = self._service.list_quick_start_amis()
            instance_types = self._service.list_instance_types()
            vpcs = self._service.list_vpcs()
            subnets = self._service.list_subnets()
            sgs = self._service.list_security_groups()
            key_pairs = self._service.list_key_pairs()
            instances = self._service.list_instances_for_cloning()

            self._config_form.set_data(
                my_amis, quick_start_amis, instance_types, vpcs, subnets, sgs, key_pairs
            )
            self._reference_panel.set_instances(instances)
        except Exception as exc:
            logger.error("Failed to load AWS data: %s", exc)
            QMessageBox.warning(self, "Load Error", f"Could not load AWS data:\n{exc}")

    def _load_mock_data(self) -> None:
        """Populate with mock data when no service is available."""
        from tools.ec2_launcher.ui.mock_data import (
            MOCK_AMIS, MOCK_INSTANCE_TYPES, MOCK_VPCS,
            MOCK_SUBNETS, MOCK_SECURITY_GROUPS, MOCK_KEY_PAIRS,
        )
        from core.models import Ami, Vpc, Subnet, SecurityGroup, KeyPair, Tag, Instance

        amis = [
            Ami(
                image_id=a["ImageId"],
                name=a["Name"],
                description=a.get("Description", ""),
                platform=a.get("Platform", ""),
                tags=[Tag(t["Key"], t["Value"]) for t in a.get("Tags", [])],
            )
            for a in MOCK_AMIS
        ]
        vpcs = [
            Vpc(
                vpc_id=v["VpcId"],
                cidr_block=v.get("CidrBlock", "10.0.0.0/16"),
                is_default=v.get("IsDefault", False),
                name=v.get("Name"),
            )
            for v in MOCK_VPCS
        ]
        subnets = [
            Subnet(
                subnet_id=s["SubnetId"],
                vpc_id=s["VpcId"],
                cidr_block=s["CidrBlock"],
                availability_zone=s["AvailabilityZone"],
            )
            for s in MOCK_SUBNETS
        ]
        sgs = [
            SecurityGroup(
                group_id=g["GroupId"],
                group_name=g["GroupName"],
                description=g["Description"],
                vpc_id="vpc-11111111",
            )
            for g in MOCK_SECURITY_GROUPS
        ]
        key_pairs = [KeyPair(key_name=k) for k in MOCK_KEY_PAIRS]

        # Build a couple of mock instances for the reference panel
        mock_instances = [
            Instance(
                instance_id="i-0abc123",
                instance_type="m5.large",
                state="running",
                public_ip="1.2.3.4",
                private_ip="10.0.1.5",
                vpc_id="vpc-11111111",
                subnet_id="subnet-1a",
                security_groups=[sgs[0], sgs[1]],
                tags=[Tag("Name", "WebServer"), Tag("Env", "prod")],
                image_id=amis[0].image_id,
                key_name=MOCK_KEY_PAIRS[0],
                name="WebServer",
            ),
            Instance(
                instance_id="i-0xyz456",
                instance_type="t3.medium",
                state="stopped",
                public_ip=None,
                private_ip="10.0.2.8",
                vpc_id="vpc-22222222",
                subnet_id="subnet-2a",
                security_groups=[sgs[2]],
                tags=[Tag("Name", "API"), Tag("Env", "dev")],
                image_id=amis[1].image_id,
                key_name=MOCK_KEY_PAIRS[1],
                name="API",
            ),
        ]

        # Quick Start = standard AWS-provided images; My AMIs = account imports
        quick_start_amis = [
            Ami(image_id="ami-qs-amzn2023",  name="Amazon Linux 2023",
                description="Amazon Linux 2023 Kernel 6.1", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-ubuntu2204", name="Ubuntu Server 22.04 LTS",
                description="Canonical, Ubuntu, 22.04 LTS, amd64 jammy image", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-ubuntu2004", name="Ubuntu Server 20.04 LTS",
                description="Canonical, Ubuntu, 20.04 LTS, amd64 focal image", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-win2022",   name="Windows Server 2022 Base",
                description="Microsoft Windows Server 2022 Full Locale English", platform="Windows"),
            Ami(image_id="ami-qs-win2019",   name="Windows Server 2019 Base",
                description="Microsoft Windows Server 2019 Full Locale English", platform="Windows"),
            Ami(image_id="ami-qs-rhel9",     name="Red Hat Enterprise Linux 9",
                description="RHEL 9 (HVM), SSD Volume Type", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-suse15",    name="SUSE Linux Enterprise Server 15 SP5",
                description="SUSE Linux Enterprise Server 15 SP5", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-debian12",  name="Debian 12 (Bookworm)",
                description="Debian 12 (Bookworm) amd64", platform="Linux/UNIX"),
            Ami(image_id="ami-qs-macos13",   name="macOS Ventura 13",
                description="macOS 13 Ventura", platform="macOS"),
        ]
        self._config_form.set_data(
            amis, quick_start_amis, MOCK_INSTANCE_TYPES, vpcs, subnets, sgs, key_pairs
        )
        self._reference_panel.set_instances(mock_instances)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def _on_launch(self) -> None:
        config = self._config_form.get_launch_config()
        if config is None:
            QMessageBox.warning(
                self,
                "Incomplete Configuration",
                "Please fill in all required fields (highlighted in red).",
            )
            return

        msg = (
            f"Launch instance?\n\n"
            f"AMI:       {config.image_id}\n"
            f"Type:      {config.instance_type}\n"
            f"Volume:    {config.volume_gb} GiB {config.volume_type}\n"
            f"VPC:       {config.vpc_id}\n"
            f"Subnet:    {config.subnet_id}\n"
            f"SGs:       {', '.join(config.sg_ids) or '(none)'}\n"
            f"Key Pair:  {config.key_name}"
        )
        reply = QMessageBox.question(
            self, "Confirm Launch", msg,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # run_instances wiring deferred — placeholder only
        QMessageBox.information(
            self, "Not Yet Implemented",
            "run_instances() wiring is pending.\nConfiguration validated successfully.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _applied_section_names(patch: SectionPatch) -> str:
        names = []
        if patch.image_id is not None:
            names.append("Image")
        if patch.instance_type is not None:
            names.append("Hardware")
        if patch.vpc_id is not None or patch.subnet_id is not None:
            names.append("Network")
        if patch.sg_ids is not None:
            names.append("Security")
        if patch.key_name is not None:
            names.append("Key Pair")
        if patch.tags is not None:
            names.append("Tags")
        return " + ".join(names) if names else "Nothing"
