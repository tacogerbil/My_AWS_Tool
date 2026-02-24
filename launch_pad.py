"""
LaunchPad — main hub window for AWS Tool Suite.

Responsibilities:
- Load/save user config (profile, region, geometry) via ConfigAdapter.
- Build AwsAdapter from config; rebuild it when settings change.
- Render the settings bar (profile, region, status dot, refresh).
- Open tool sub-windows with the active service/region.
"""
import sys
import os
import logging

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QGridLayout, QComboBox,
)
from PySide6.QtCore import Qt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.app_config import AppConfig
from core.services import ResourceService
from adapters.config_adapter import ConfigAdapter

logger = logging.getLogger(__name__)

_COMMON_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ca-central-1",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
    "sa-east-1",
]


class LaunchPad(QMainWindow):
    """Main hub window. Owns the active adapter/service and passes them to tools."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AWS Tool Suite")

        self._config_adapter = ConfigAdapter()
        self._config: AppConfig = self._config_adapter.load()

        self.adapter = None
        self.service = None
        self._rebuild_adapter()

        self._setup_settings_bar()
        self._setup_ui()

        self.setGeometry(
            self._config.window_x,
            self._config.window_y,
            self._config.window_w,
            self._config.window_h,
        )

    def _rebuild_adapter(self) -> None:
        """Create (or recreate) the AWS adapter from the current config."""
        try:
            from adapters.aws_adapter import AwsAdapter
            self.adapter = AwsAdapter(
                profile_name=self._config.aws_profile,
                region=self._config.region,
            )
            self.service = ResourceService(self.adapter)
        except Exception as exc:
            logger.warning("Failed to init AwsAdapter (%s). Offline mode.", exc)
            self.adapter = None
            self.service = None

    def _setup_settings_bar(self) -> None:
        self._settings_bar = QWidget()
        bar_layout = QHBoxLayout(self._settings_bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        bar_layout.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(140)
        self._populate_profiles()
        bar_layout.addWidget(self._profile_combo)

        bar_layout.addSpacing(16)

        bar_layout.addWidget(QLabel("Region:"))
        self._region_combo = QComboBox()
        self._region_combo.setMinimumWidth(140)
        self._populate_regions()
        bar_layout.addWidget(self._region_combo)

        bar_layout.addSpacing(16)

        self._status_dot = QLabel("\u25cf")
        self._status_dot.setFixedWidth(20)
        self._update_status_dot()
        bar_layout.addWidget(self._status_dot)

        self._status_label = QLabel("")
        bar_layout.addWidget(self._status_label)

        bar_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(70)
        refresh_btn.clicked.connect(self._on_settings_changed)
        bar_layout.addWidget(refresh_btn)

        self._profile_combo.currentTextChanged.connect(self._on_settings_changed)
        self._region_combo.currentTextChanged.connect(self._on_settings_changed)

    def _populate_profiles(self) -> None:
        try:
            import boto3
            profiles = boto3.Session().available_profiles or ["default"]
        except Exception:
            profiles = ["default"]

        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItems(profiles)
        idx = self._profile_combo.findText(self._config.aws_profile)
        self._profile_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._profile_combo.blockSignals(False)

    def _populate_regions(self) -> None:
        regions = list(_COMMON_REGIONS)
        if self._config.region not in regions:
            regions.insert(0, self._config.region)

        self._region_combo.blockSignals(True)
        self._region_combo.clear()
        self._region_combo.addItems(regions)
        idx = self._region_combo.findText(self._config.region)
        self._region_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._region_combo.blockSignals(False)

    def _update_status_dot(self) -> None:
        connected = self.adapter is not None and self.adapter.validate_connection()
        if connected:
            self._status_dot.setStyleSheet("color: #27ae60; font-size: 16px;")
            self._status_dot.setToolTip("Connected")
        else:
            self._status_dot.setStyleSheet("color: #e74c3c; font-size: 16px;")
            self._status_dot.setToolTip("Not connected / offline")

    def _on_settings_changed(self) -> None:
        self._profile_combo.blockSignals(True)
        self._region_combo.blockSignals(True)

        self._config.aws_profile = self._profile_combo.currentText()
        self._config.region = self._region_combo.currentText()

        self._profile_combo.blockSignals(False)
        self._region_combo.blockSignals(False)

        self._rebuild_adapter()
        self._update_status_dot()
        self._config_adapter.save(self._config)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._settings_bar)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(sep)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        header = QLabel("AWS Tool Suite")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #34495e; margin: 20px;")
        inner_layout.addWidget(header)

        grid_layout = QGridLayout()
        inner_layout.addLayout(grid_layout)

        btn_import = self._create_tool_button("VM Importer", "Import Hyper-V/VMware images to AMIs", "#2c3e50")
        btn_import.clicked.connect(self._launch_vm_importer)
        grid_layout.addWidget(btn_import, 0, 0)

        btn_launcher = self._create_tool_button("EC2 Launcher", "Launch Instances from AMIs\n(Prototype)", "#27ae60")
        btn_launcher.clicked.connect(self._launch_ec2_launcher)
        grid_layout.addWidget(btn_launcher, 0, 1)

        inner_layout.addStretch()

        footer = QLabel("v1.0 - Modular Architecture")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #7f8c8d; margin: 10px;")
        inner_layout.addWidget(footer)

        layout.addWidget(inner)

    def _create_tool_button(self, title: str, desc: str, color: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(250, 150)
        btn.setText(f"{title}\n\n{desc}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-size: 18px;
                border-radius: 10px;
                text-align: center;
                white-space: pre-wrap;
            }}
            QPushButton:hover {{
                background-color: #34495e;
            }}
        """)
        return btn

    def _launch_vm_importer(self) -> None:
        from tools.vm_importer.ui.main_window import LandingWindow
        self.vm_window = LandingWindow(
            self.service, self._config.region,
            self._config, self._config_adapter,
        )
        self.vm_window.show()

    def _launch_ec2_launcher(self) -> None:
        from tools.ec2_launcher.ui.launcher_window import LauncherWindow
        from tools.ec2_launcher.services import LauncherService

        if self.adapter:
            launcher_service = LauncherService(self.adapter)
        else:
            logger.warning("Offline mode: EC2 Launcher has no real adapter.")
            launcher_service = None

        self.ec2_window = LauncherWindow(service=launcher_service)
        self.ec2_window.show()

    def closeEvent(self, event) -> None:  # noqa: N802
        geo = self.geometry()
        self._config.window_x = geo.x()
        self._config.window_y = geo.y()
        self._config.window_w = geo.width()
        self._config.window_h = geo.height()
        self._config_adapter.save(self._config)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LaunchPad()
    window.show()
    sys.exit(app.exec())
