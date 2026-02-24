"""
ami_section.py — Tabbed AMI picker with Quick Start, My AMIs, and Recents.

Each tab exposes the same underlying SearchableComboBox, filtered differently.
A detail card below the tabs shows name, AMI ID, platform, and description
for whichever image is currently selected.

Public API (used by ConfigForm):
    populate(amis: List[Ami])
    get_image_id() -> Optional[str]
    set_image_id(image_id: str)
    mark_error(has_error: bool)
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Ami
from ui.common.widgets import SearchableComboBox

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""

# OS category label → lowercase substrings to match against ami.name
_OS_FILTERS = {
    "Amazon Linux": ["amazon"],
    "macOS":        ["macos", "mac os"],
    "Ubuntu":       ["ubuntu"],
    "Windows":      ["windows"],
    "Red Hat":      ["red hat", "rhel"],
    "SUSE":         ["suse"],
    "Debian":       ["debian"],
    "All":          [],
}

_OS_BTN_STYLE = """
    QPushButton {
        padding: 5px 12px; border-radius: 4px; font-size: 12px;
        background-color: #ecf0f1; color: #2c3e50;
        border: 1px solid #ced4da;
    }
    QPushButton:hover   { background-color: #d5d8dc; }
    QPushButton:checked {
        background-color: #2980b9; color: white; border-color: #2475aa;
    }
"""

_CARD_STYLE = """
    QFrame {
        background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;
    }
"""


class AmiSection(QWidget):
    """AMI picker: Quick Start / My AMIs / Recents tabs + detail card."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._quick_start_amis: List[Ami] = []
        self._my_amis: List[Ami] = []
        self._all_amis: List[Ami] = []   # combined; used for detail card + set_image_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_quick_start_tab(), "Quick Start")
        self._tabs.addTab(self._build_my_amis_tab(), "My AMIs")
        self._tabs.addTab(self._build_recents_tab(), "Recents")
        outer.addWidget(self._tabs)
        outer.addWidget(self._build_detail_card())

        self._tabs.currentChanged.connect(self._on_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(
        self, quick_start_amis: List[Ami], my_amis: List[Ami]
    ) -> None:
        """Load Quick Start (AWS-provided) and My AMIs (account-owned) separately."""
        self._quick_start_amis = quick_start_amis
        self._my_amis = my_amis
        # Combined unique set — used by detail card, Recents, and set_image_id
        seen: dict = {}
        for ami in (quick_start_amis + my_amis):
            seen.setdefault(ami.image_id, ami)
        self._all_amis = list(seen.values())
        self._refresh_quick_start()
        self._refresh_my_amis()
        self._refresh_recents()

    def get_image_id(self) -> Optional[str]:
        return self._active_combo().currentData()

    def set_image_id(self, image_id: str) -> None:
        for combo in (self._qs_combo, self._my_combo, self._rec_combo):
            idx = combo.findData(image_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return

    def mark_error(self, has_error: bool) -> None:
        self._active_combo().setStyleSheet(_ERROR_STYLE if has_error else _NORMAL_STYLE)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_quick_start_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._os_group = QButtonGroup(tab)
        self._os_group.setExclusive(True)
        for os_name in _OS_FILTERS:
            btn = QPushButton(os_name)
            btn.setCheckable(True)
            btn.setStyleSheet(_OS_BTN_STYLE)
            if os_name == "All":
                btn.setChecked(True)
            self._os_group.addButton(btn)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._qs_combo = SearchableComboBox()
        layout.addWidget(self._qs_combo)

        self._os_group.buttonClicked.connect(self._on_os_clicked)
        self._qs_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_my_amis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        radio_row = QHBoxLayout()
        self._owned_radio = QRadioButton("Owned by me")
        self._owned_radio.setChecked(True)
        self._shared_radio = QRadioButton("Shared with me")
        radio_row.addWidget(self._owned_radio)
        radio_row.addWidget(self._shared_radio)
        radio_row.addStretch()
        layout.addLayout(radio_row)

        self._my_combo = SearchableComboBox()
        layout.addWidget(self._my_combo)

        self._owned_radio.toggled.connect(self._refresh_my_amis)
        self._my_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_recents_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        self._rec_combo = SearchableComboBox()
        layout.addWidget(self._rec_combo)
        self._rec_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_detail_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self._card_name = QLabel("—")
        self._card_name.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #2c3e50; border: none;"
        )
        layout.addWidget(self._card_name)

        self._card_id = QLabel("")
        self._card_platform = QLabel("")
        self._card_desc = QLabel("")
        self._card_desc.setWordWrap(True)
        for lbl in (self._card_id, self._card_platform, self._card_desc):
            lbl.setStyleSheet("color: #6c757d; font-size: 11px; border: none;")
            layout.addWidget(lbl)

        return card

    # ------------------------------------------------------------------
    # Private — refresh / filter
    # ------------------------------------------------------------------

    def _refresh_quick_start(self) -> None:
        checked = self._os_group.checkedButton()
        self._on_os_clicked(checked)

    def _on_os_clicked(self, btn: Optional[QPushButton]) -> None:
        keywords = _OS_FILTERS.get(btn.text() if btn else "All", [])
        self._qs_combo.blockSignals(True)
        self._qs_combo.clear()
        for ami in self._quick_start_amis:
            if not keywords or any(k in ami.name.lower() for k in keywords):
                self._qs_combo.addItem(
                    f"{ami.name}  ({ami.image_id})", userData=ami.image_id
                )
        self._qs_combo.blockSignals(False)
        self._on_changed()

    def _refresh_my_amis(self) -> None:
        shared = hasattr(self, "_shared_radio") and self._shared_radio.isChecked()
        self._my_combo.blockSignals(True)
        self._my_combo.clear()
        for ami in self._my_amis:
            is_imported = any(t.key == "CreatedBy" for t in ami.tags)
            if shared and not is_imported:
                continue
            self._my_combo.addItem(
                f"{ami.name}  ({ami.image_id})", userData=ami.image_id
            )
        self._my_combo.blockSignals(False)
        self._on_changed()

    def _refresh_recents(self) -> None:
        self._rec_combo.clear()
        for ami in self._all_amis:
            self._rec_combo.addItem(
                f"{ami.name}  ({ami.image_id})", userData=ami.image_id
            )

    def _active_combo(self) -> SearchableComboBox:
        return [self._qs_combo, self._my_combo, self._rec_combo][
            self._tabs.currentIndex()
        ]

    def _on_changed(self, _index: int = 0) -> None:
        image_id = self._active_combo().currentData()
        ami = next((a for a in self._all_amis if a.image_id == image_id), None)
        if ami:
            self._card_name.setText(ami.name)
            self._card_id.setText(f"AMI ID: {ami.image_id}")
            self._card_platform.setText(f"Platform: {ami.platform}")
            self._card_desc.setText(ami.description)
        else:
            self._card_name.setText("—")
            for lbl in (self._card_id, self._card_platform, self._card_desc):
                lbl.setText("")
