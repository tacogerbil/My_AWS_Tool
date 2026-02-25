"""
ami_section.py — Tabbed AMI picker with Quick Start, My AMIs, and Recents.

Search architecture
-------------------
Each tab has a dedicated QLineEdit search field that filters the combo items
by exact case-insensitive substring match on AMI name OR AMI ID.  This is
intentionally different from the QCompleter used in the rest of the app:
AMI lists can be large, filter results must be precise, and completer
token-matching produces unexpected false positives.

Public API (used by ConfigForm):
    populate(quick_start_amis, my_amis)
    get_image_id() -> Optional[str]
    set_image_id(image_id: str)
    mark_error(has_error: bool)
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Ami

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""

# OS category → lowercase substrings matched against ami.name
_OS_FILTERS = {
    "Amazon Linux": ["amazon linux"],
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
_SEARCH_STYLE = """
    QLineEdit {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 4px 8px; font-size: 12px;
        background: white; color: #2c3e50; min-height: 26px;
    }
    QLineEdit:focus { border-color: #3498db; }
"""
_CARD_STYLE = "QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }"


class AmiSection(QWidget):
    """AMI picker: Quick Start / My AMIs / Recents tabs + detail card."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._quick_start_amis: List[Ami] = []
        self._my_amis: List[Ami] = []
        self._all_amis: List[Ami] = []
        # OS/radio-filtered source lists; text search is applied on top
        self._qs_source: List[Ami] = []
        self._my_source: List[Ami] = []

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

    def populate(self, quick_start_amis: List[Ami], my_amis: List[Ami]) -> None:
        self._quick_start_amis = quick_start_amis
        self._my_amis = my_amis
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

        self._qs_search = QLineEdit()
        self._qs_search.setPlaceholderText("Search by name or AMI ID…")
        self._qs_search.setStyleSheet(_SEARCH_STYLE)
        self._qs_search.setClearButtonEnabled(True)
        layout.addWidget(self._qs_search)

        self._qs_combo = QComboBox()
        layout.addWidget(self._qs_combo)

        self._os_group.buttonClicked.connect(self._on_os_clicked)
        self._qs_search.textChanged.connect(self._on_qs_search)
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

        self._my_search = QLineEdit()
        self._my_search.setPlaceholderText("Search by name or AMI ID…")
        self._my_search.setStyleSheet(_SEARCH_STYLE)
        self._my_search.setClearButtonEnabled(True)
        layout.addWidget(self._my_search)

        self._my_combo = QComboBox()
        layout.addWidget(self._my_combo)

        self._owned_radio.toggled.connect(self._refresh_my_amis)
        self._my_search.textChanged.connect(self._on_my_search)
        self._my_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_recents_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        self._rec_combo = QComboBox()
        layout.addWidget(self._rec_combo)
        self._rec_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_detail_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Row 1: bold name
        self._card_name = QLabel("—")
        self._card_name.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #2c3e50; border: none;"
        )
        layout.addWidget(self._card_name)

        # Row 2: AMI ID + description
        self._card_id   = QLabel("")
        self._card_desc = QLabel("")
        self._card_desc.setWordWrap(True)
        for lbl in (self._card_id, self._card_desc):
            lbl.setStyleSheet("color: #6c757d; font-size: 11px; border: none;")
            layout.addWidget(lbl)

        # Row 3: metadata columns (Architecture | Publish Date | Virtualization | ENA | Root device)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(24)
        self._meta_arch  = self._make_meta_col(meta_row, "Architecture")
        self._meta_date  = self._make_meta_col(meta_row, "Publish Date")
        self._meta_virt  = self._make_meta_col(meta_row, "Virtualization")
        self._meta_ena   = self._make_meta_col(meta_row, "ENA Support")
        self._meta_root  = self._make_meta_col(meta_row, "Root device")
        meta_row.addStretch()
        layout.addLayout(meta_row)

        return card

    @staticmethod
    def _make_meta_col(parent_layout: QHBoxLayout, label: str) -> QLabel:
        """Add a two-line label column (header + value) to parent_layout."""
        col = QVBoxLayout()
        col.setSpacing(1)
        hdr = QLabel(label)
        hdr.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #495057; "
            "text-transform: uppercase; letter-spacing: 0.5px; border: none;"
        )
        val = QLabel("—")
        val.setStyleSheet("font-size: 12px; color: #2c3e50; border: none;")
        col.addWidget(hdr)
        col.addWidget(val)
        parent_layout.addLayout(col)
        return val  # caller stores the value label to update it later

    # ------------------------------------------------------------------
    # Private — refresh / filter
    # ------------------------------------------------------------------

    def _refresh_quick_start(self) -> None:
        self._on_os_clicked(self._os_group.checkedButton())

    def _on_os_clicked(self, btn: Optional[QPushButton]) -> None:
        keywords = _OS_FILTERS.get(btn.text() if btn else "All", [])
        self._qs_source = [
            a for a in self._quick_start_amis
            if not keywords or any(k in a.name.lower() for k in keywords)
        ]
        self._rebuild_combo(self._qs_combo, self._qs_source,
                            self._qs_search.text() if hasattr(self, "_qs_search") else "")

    def _on_qs_search(self, text: str) -> None:
        self._rebuild_combo(self._qs_combo, self._qs_source, text)

    def _refresh_my_amis(self) -> None:
        shared = hasattr(self, "_shared_radio") and self._shared_radio.isChecked()
        self._my_source = [
            a for a in self._my_amis
            if not shared or any(t.key == "CreatedBy" for t in a.tags)
        ]
        self._rebuild_combo(self._my_combo, self._my_source,
                            self._my_search.text() if hasattr(self, "_my_search") else "")

    def _on_my_search(self, text: str) -> None:
        self._rebuild_combo(self._my_combo, self._my_source, text)

    def _refresh_recents(self) -> None:
        self._rec_combo.clear()
        for ami in self._all_amis:
            self._rec_combo.addItem(f"{ami.name}  ({ami.image_id})", userData=ami.image_id)

    def _rebuild_combo(self, combo: QComboBox, source: List[Ami], text: str) -> None:
        """Repopulate combo with AMIs whose name or ID contain text (exact substring)."""
        lower = text.strip().lower()
        prev_data = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for ami in source:
            if lower and lower not in ami.name.lower() and lower not in ami.image_id.lower():
                continue
            combo.addItem(f"{ami.name}  ({ami.image_id})", userData=ami.image_id)
        idx = combo.findData(prev_data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        self._on_changed()

    def _active_combo(self) -> QComboBox:
        return [self._qs_combo, self._my_combo, self._rec_combo][self._tabs.currentIndex()]

    def _on_changed(self, _index: int = 0) -> None:
        image_id = self._active_combo().currentData()
        ami = next((a for a in self._all_amis if a.image_id == image_id), None)
        if ami:
            self._card_name.setText(ami.name)
            self._card_id.setText(f"{ami.image_id}    ·    {ami.platform}")
            self._card_desc.setText(ami.description or "")

            # Architecture — format like AWS Console: "64-bit (x86)" or "64-bit (Arm)"
            arch_map = {
                "x86_64": "64-bit (x86)",
                "arm64":  "64-bit (Arm)",
                "i386":   "32-bit (x86)",
            }
            arch = arch_map.get(ami.architecture or "", ami.architecture or "—")
            self._meta_arch.setText(arch)

            # Publish date — strip the time component if present
            pub = (ami.creation_date or "").split("T")[0] or "—"
            self._meta_date.setText(pub)

            self._meta_virt.setText(ami.virtualization_type or "—")
            self._meta_ena.setText("Enabled" if ami.ena_support else ("—" if ami.ena_support is None else "Disabled"))
            self._meta_root.setText(ami.root_device_type or "—")
        else:
            self._card_name.setText("—")
            self._card_id.setText("")
            self._card_desc.setText("")
            for lbl in (self._meta_arch, self._meta_date, self._meta_virt,
                        self._meta_ena, self._meta_root):
                lbl.setText("—")
