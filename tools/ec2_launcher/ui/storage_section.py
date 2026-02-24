"""
storage_section.py — EBS block device configuration.

Starts with one non-removable root volume.  Additional data volumes can be
added with the "+ Add volume" button.  IOPS and throughput fields appear only
for volume types that support them (gp3, io1, io2).

Public API (used by ConfigForm):
    get_volumes() -> List[VolumeConfig]
    set_volumes(volumes: List[VolumeConfig])
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tools.ec2_launcher.models import VolumeConfig

_VOLUME_TYPES = ["gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"]
_IOPS_TYPES = {"gp3", "io1", "io2"}
_THROUGHPUT_TYPES = {"gp3"}

_ROW_STYLE = """
    QFrame {
        background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;
    }
"""
_FIELD_STYLE = """
    QLineEdit, QComboBox {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 3px 7px; font-size: 12px;
        background: white; color: #2c3e50; min-height: 24px;
    }
"""
_RM_BTN_STYLE = (
    "QPushButton { border: none; color: #e74c3c; font-size: 15px; background: transparent; }"
    "QPushButton:hover { color: #c0392b; }"
)


class _VolumeRow(QFrame):
    """One EBS volume row: device, size, type, IOPS/throughput, flags."""

    remove_requested: Signal = Signal(object)

    def __init__(
        self, config: VolumeConfig, removable: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(_ROW_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_row1(config, removable))
        outer.addLayout(self._build_row2(config))
        outer.addLayout(self._build_row3(config))

        self._vtype.currentTextChanged.connect(self._on_type_changed)
        self._enc_chk.toggled.connect(self._on_encrypted_changed)
        self._on_type_changed(config.volume_type)
        self._on_encrypted_changed(config.encrypted)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self) -> VolumeConfig:
        vtype = self._vtype.currentText()
        try:
            size = int(self._size.text())
        except ValueError:
            size = 30
        iops = self._parse_int(self._iops.text()) if vtype in _IOPS_TYPES else None
        tp = self._parse_int(self._tp.text()) if vtype in _THROUGHPUT_TYPES else None
        encrypted = self._enc_chk.isChecked()
        kms_raw = self._kms_key.currentText().strip() if encrypted else None
        kms_key_id = None if (not kms_raw or kms_raw == "aws/ebs (default)") else kms_raw
        init_rate = "maximum" if self._init_rate.currentIndex() == 1 else "default"
        return VolumeConfig(
            device_name=self._device.text().strip() or "/dev/sda1",
            size_gb=size,
            volume_type=vtype,
            delete_on_termination=self._del_chk.isChecked(),
            encrypted=encrypted,
            iops=iops,
            throughput_mbps=tp,
            kms_key_id=kms_key_id,
            initialization_rate=init_rate,
        )

    # ------------------------------------------------------------------
    # Private — UI builders
    # ------------------------------------------------------------------

    def _build_row1(self, config: VolumeConfig, removable: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Device:"))
        self._device = QLineEdit(config.device_name)
        self._device.setFixedWidth(90)
        self._device.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._device)

        row.addWidget(QLabel("Size (GiB):"))
        self._size = QLineEdit(str(config.size_gb))
        self._size.setFixedWidth(65)
        self._size.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._size)

        row.addWidget(QLabel("Type:"))
        self._vtype = QComboBox()
        self._vtype.addItems(_VOLUME_TYPES)
        self._vtype.setStyleSheet(_FIELD_STYLE)
        idx = self._vtype.findText(config.volume_type)
        if idx >= 0:
            self._vtype.setCurrentIndex(idx)
        row.addWidget(self._vtype)
        row.addStretch()

        if removable:
            rm = QPushButton("✕")
            rm.setFixedSize(26, 26)
            rm.setStyleSheet(_RM_BTN_STYLE)
            rm.clicked.connect(lambda: self.remove_requested.emit(self))
            row.addWidget(rm)

        return row

    def _build_row2(self, config: VolumeConfig) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._iops_lbl = QLabel("IOPS:")
        self._iops = QLineEdit(str(config.iops) if config.iops else "3000")
        self._iops.setFixedWidth(70)
        self._iops.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._iops_lbl)
        row.addWidget(self._iops)

        self._tp_lbl = QLabel("Throughput (MiB/s):")
        self._tp = QLineEdit(str(config.throughput_mbps) if config.throughput_mbps else "125")
        self._tp.setFixedWidth(60)
        self._tp.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._tp_lbl)
        row.addWidget(self._tp)

        self._del_chk = QCheckBox("Delete on termination")
        self._del_chk.setChecked(config.delete_on_termination)
        row.addWidget(self._del_chk)

        self._enc_chk = QCheckBox("Encrypted")
        self._enc_chk.setChecked(config.encrypted)
        row.addWidget(self._enc_chk)

        row.addStretch()
        return row

    def _build_row3(self, config: VolumeConfig) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._kms_lbl = QLabel("KMS Key:")
        self._kms_key = QComboBox()
        self._kms_key.setEditable(True)
        self._kms_key.addItem("aws/ebs (default)")
        if config.kms_key_id:
            self._kms_key.setCurrentText(config.kms_key_id)
        self._kms_key.setMinimumWidth(200)
        self._kms_key.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._kms_lbl)
        row.addWidget(self._kms_key)

        row.addSpacing(16)

        row.addWidget(QLabel("Initialization:"))
        self._init_rate = QComboBox()
        self._init_rate.addItems(["Default", "Maximum (full initialization)"])
        self._init_rate.setStyleSheet(_FIELD_STYLE)
        if config.initialization_rate == "maximum":
            self._init_rate.setCurrentIndex(1)
        row.addWidget(self._init_rate)

        row.addStretch()
        return row

    def _on_encrypted_changed(self, checked: bool) -> None:
        self._kms_lbl.setVisible(checked)
        self._kms_key.setVisible(checked)

    def _on_type_changed(self, vtype: str) -> None:
        show_iops = vtype in _IOPS_TYPES
        show_tp = vtype in _THROUGHPUT_TYPES
        self._iops_lbl.setVisible(show_iops)
        self._iops.setVisible(show_iops)
        self._tp_lbl.setVisible(show_tp)
        self._tp.setVisible(show_tp)

    @staticmethod
    def _parse_int(text: str) -> Optional[int]:
        try:
            return int(text)
        except ValueError:
            return None


class StorageSection(QWidget):
    """EBS volume list with an Add volume button."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[_VolumeRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(4)
        outer.addWidget(self._container)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add volume")
        add_btn.setFixedWidth(110)
        add_btn.clicked.connect(self._add_default_volume)
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        # Default root volume — not removable
        self._add_volume(VolumeConfig(), removable=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_volumes(self) -> List[VolumeConfig]:
        return [row.get_config() for row in self._rows]

    def set_volumes(self, volumes: List[VolumeConfig]) -> None:
        for row in list(self._rows):
            self._container_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        for i, vol in enumerate(volumes):
            self._add_volume(vol, removable=(i > 0))

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _add_volume(self, config: VolumeConfig, removable: bool = True) -> None:
        row = _VolumeRow(config, removable=removable)
        row.remove_requested.connect(self._remove_volume)
        self._container_layout.addWidget(row)
        self._rows.append(row)

    def _add_default_volume(self) -> None:
        letter = chr(ord("b") + len(self._rows))
        self._add_volume(VolumeConfig(device_name=f"/dev/sd{letter}", size_gb=20))

    def _remove_volume(self, row: _VolumeRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._container_layout.removeWidget(row)
            row.deleteLater()
