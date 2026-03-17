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
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tools.ec2_launcher.models import SectionPatch
from tools.ec2_launcher.ui.config_form import ConfigForm
from tools.ec2_launcher.ui.launch_monitor import LaunchMonitorDialog
from tools.ec2_launcher.ui.reference_panel import ReferencePanel
from ui.common.styles import get_checkbox_style

logger = logging.getLogger(__name__)


class LauncherWindow(QWidget):
    """Main window for the EC2 Launcher tool."""

    def __init__(self, service=None, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self.setWindowTitle("EC2 Launcher")
        self.resize(1300, 800)

        # Apply checkbox style at the root level so every QCheckBox in the
        # entire window (ConfigForm, ReferencePanel, dialogs) is covered.
        self.setStyleSheet(get_checkbox_style())

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

            profiles = self._service.list_instance_profiles()
            self._config_form.set_data(
                my_amis, quick_start_amis, instance_types, vpcs, subnets, sgs, key_pairs
            )
            self._config_form.set_service(self._service)
            self._config_form.set_instance_profiles(profiles)
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

        # Quick Start = AWS-provided public images, mirroring the real AWS console catalog
        quick_start_amis = [
            # Amazon Linux
            Ami("ami-qs-al2023-x86",   "Amazon Linux 2023",
                "Amazon Linux 2023 AMI (Kernel 6.1, x86_64)", "Linux/UNIX"),
            Ami("ami-qs-al2023-arm",   "Amazon Linux 2023 (arm64)",
                "Amazon Linux 2023 AMI (Kernel 6.1, arm64/Graviton)", "Linux/UNIX"),
            Ami("ami-qs-al2-x86",      "Amazon Linux 2",
                "Amazon Linux 2 Kernel 5.10 AMI (x86_64)", "Linux/UNIX"),
            # Ubuntu
            Ami("ami-qs-ubuntu2404",   "Ubuntu Server 24.04 LTS",
                "Canonical, Ubuntu, 24.04 LTS, amd64 noble image", "Linux/UNIX"),
            Ami("ami-qs-ubuntu2204",   "Ubuntu Server 22.04 LTS",
                "Canonical, Ubuntu, 22.04 LTS, amd64 jammy image", "Linux/UNIX"),
            Ami("ami-qs-ubuntu2004",   "Ubuntu Server 20.04 LTS",
                "Canonical, Ubuntu, 20.04 LTS, amd64 focal image", "Linux/UNIX"),
            # Windows Server 2022
            Ami("ami-qs-win2022-base", "Windows Server 2022 Base",
                "Microsoft Windows Server 2022 Full Locale English AMI", "Windows"),
            Ami("ami-qs-win2022-core", "Windows Server 2022 Core",
                "Microsoft Windows Server 2022 Core Locale English AMI", "Windows"),
            Ami("ami-qs-win2022-sql22-exp",
                "Windows Server 2022 with SQL Server 2022 Express",
                "Windows Server 2022 + SQL Server 2022 Express", "Windows"),
            Ami("ami-qs-win2022-sql22-std",
                "Windows Server 2022 with SQL Server 2022 Standard",
                "Windows Server 2022 + SQL Server 2022 Standard", "Windows"),
            Ami("ami-qs-win2022-sql22-web",
                "Windows Server 2022 with SQL Server 2022 Web",
                "Windows Server 2022 + SQL Server 2022 Web Edition", "Windows"),
            Ami("ami-qs-win2022-sql22-ent",
                "Windows Server 2022 with SQL Server 2022 Enterprise",
                "Windows Server 2022 + SQL Server 2022 Enterprise", "Windows"),
            Ami("ami-qs-win2022-dotnet",
                "Windows Server 2022 with .NET Framework 4.8",
                "Windows Server 2022 + .NET Framework 4.8", "Windows"),
            Ami("ami-qs-win2022-vs2022",
                "Windows Server 2022 with Visual Studio 2022 Community",
                "Windows Server 2022 + Visual Studio 2022 Community Edition", "Windows"),
            # Windows Server 2019
            Ami("ami-qs-win2019-base", "Windows Server 2019 Base",
                "Microsoft Windows Server 2019 Full Locale English AMI", "Windows"),
            Ami("ami-qs-win2019-core", "Windows Server 2019 Core",
                "Microsoft Windows Server 2019 Core Locale English AMI", "Windows"),
            Ami("ami-qs-win2019-sql19-std",
                "Windows Server 2019 with SQL Server 2019 Standard",
                "Windows Server 2019 + SQL Server 2019 Standard", "Windows"),
            # Red Hat
            Ami("ami-qs-rhel9",   "Red Hat Enterprise Linux 9",
                "RHEL 9 (HVM), SSD Volume Type", "Linux/UNIX"),
            Ami("ami-qs-rhel8",   "Red Hat Enterprise Linux 8",
                "RHEL 8 (HVM), SSD Volume Type", "Linux/UNIX"),
            # SUSE
            Ami("ami-qs-suse15",  "SUSE Linux Enterprise Server 15 SP5",
                "SUSE Linux Enterprise Server 15 SP5 (HVM)", "Linux/UNIX"),
            # Debian
            Ami("ami-qs-debian12", "Debian 12 (Bookworm)",
                "Debian GNU/Linux 12 (Bookworm) amd64", "Linux/UNIX"),
            # macOS
            Ami("ami-qs-macos14", "macOS Sonoma 14",
                "macOS 14 Sonoma (x86_64)", "macOS"),
            Ami("ami-qs-macos13", "macOS Ventura 13",
                "macOS 13 Ventura (x86_64)", "macOS"),
        ]
        self._config_form.set_data(
            amis, quick_start_amis, MOCK_INSTANCE_TYPES, vpcs, subnets, sgs, key_pairs
        )
        from adapters.mock_adapter import MockAdapter
        from tools.ec2_launcher.services import LauncherService
        mock_svc = LauncherService(MockAdapter(), region="us-east-1")
        self._config_form.set_service(mock_svc)
        self._config_form.set_instance_profiles(mock_svc.list_instance_profiles())
        self._reference_panel.set_instances(mock_instances)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def _on_launch(self) -> None:
        import dataclasses

        config = self._config_form.get_launch_config()
        if config is None:
            missing = self._config_form.get_validation_errors()
            detail = "\n".join(f"  \u2022 {m}" for m in missing)
            QMessageBox.warning(
                self,
                "Incomplete Configuration",
                f"Please fill in the following required fields:\n\n{detail}",
            )
            return

        if self._service is None:
            from adapters.mock_adapter import MockAdapter
            from tools.ec2_launcher.services import LauncherService
            svc = LauncherService(MockAdapter(), region="us-east-1")
        else:
            svc = self._service

        # If the user filled in the New SG form, create that SG now —
        # atomically with the launch so no orphaned resources are left behind.
        if self._config_form.has_pending_sg():
            vpc_id = self._config_form.get_current_vpc_id()
            if not vpc_id:
                QMessageBox.warning(
                    self, "No VPC Selected",
                    "Please select a VPC before launching with a new Security Group.",
                )
                return
            name, desc, rules = self._config_form.get_new_sg_data()
            try:
                sg = svc.create_security_group(name, desc, vpc_id, rules)
                logger.info("Created SG %s (%s) for launch", sg.group_id, sg.group_name)
                config = dataclasses.replace(config, sg_ids=[sg.group_id] + config.sg_ids)
            except Exception as exc:
                QMessageBox.critical(
                    self, "Security Group Creation Failed",
                    f"Could not create Security Group '{name}':\n{exc}\n\n"
                    "Launch aborted — no instances were started."
                )
                return

        # Handle Windows domain-join configuration (optional section).
        domain_cfg = self._config_form.get_domain_config()
        if domain_cfg is not None:
            # Layer 2 — LDAP pre-check: abort hard if any name already exists in AD.
            try:
                QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
                conflicts = self._check_ad_name_conflicts(
                    domain_cfg, config.instance_names
                )
            except Exception as exc:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(
                    self,
                    "AD Pre-Check Failed",
                    f"Cannot connect to AD to verify names:\n{exc}\n\n"
                    "Launch aborted.",
                )
                return
            finally:
                QApplication.restoreOverrideCursor()

            if conflicts:
                detail = "\n".join(
                    f"  \u2022 {name}\n    \u2514 {dn}"
                    for name, dn in conflicts
                )
                QMessageBox.critical(
                    self,
                    "LAUNCH BLOCKED \u2014 AD Name Conflict",
                    "The following computer names already exist in Active Directory.\n"
                    "No instances were started and no changes were made.\n\n"
                    + detail
                    + "\n\nRename the instances in the Instances section and try again.",
                )
                return

            config = self._apply_domain_config(config, domain_cfg, svc)
            if config is None:
                return  # error already shown

        self._launch_btn.setEnabled(False)
        self._launch_btn.setText("Launching…")

        dlg = LaunchMonitorDialog(config=config, service=svc, parent=self)
        dlg.finished.connect(self._on_monitor_closed)
        dlg.show()

    @staticmethod
    def _check_ad_name_conflicts(
        domain_cfg: "WindowsDomainConfig",
        names: List[str],
    ) -> List[Tuple[str, str]]:
        """Return list of (name, existing_dn) for any name already in AD.

        Returns an empty list when all names are available.
        Raises on LDAP connection or authentication failure — caller shows the error.
        """
        from adapters.ad_adapter import check_computer_exists

        conflicts: List[Tuple[str, str]] = []
        for name in names:
            dn = check_computer_exists(
                domain_cfg.dc_host,
                domain_cfg.domain,
                domain_cfg.username,
                domain_cfg.password,
                name,
            )
            if dn is not None:
                conflicts.append((name, dn))
        return conflicts

    def _apply_domain_config(self, config, domain_cfg, svc) -> Optional[object]:
        """Store SSM credentials + embed UserData template; return updated config or None."""
        import dataclasses
        from tools.ec2_launcher.ui.userdata_builder import build_windows_userdata

        try:
            svc.store_domain_credentials(
                domain_cfg.ssm_path,
                domain_cfg.username,
                domain_cfg.password,
            )
            logger.info("Domain credentials stored to SSM at %s", domain_cfg.ssm_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "SSM Error",
                f"Could not store domain credentials in SSM Parameter Store:\n{exc}\n\n"
                "Launch aborted — no instances were started."
            )
            return None

        # Use timezone and DNS servers already resolved from the form into config,
        # so this rebuild matches what get_launch_config() computed.
        userdata = build_windows_userdata(
            domain_cfg,
            timezone=config.timezone,
            dns_servers=config.dns_servers,
        )
        iam_profile = domain_cfg.iam_profile or None
        return dataclasses.replace(
            config,
            user_data_template=userdata or None,
            iam_instance_profile=iam_profile,
        )

    def _on_monitor_closed(self) -> None:
        """Re-enable the launch button once the monitor dialog is dismissed."""
        self._launch_btn.setEnabled(True)
        self._launch_btn.setText("Launch Instance")

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
