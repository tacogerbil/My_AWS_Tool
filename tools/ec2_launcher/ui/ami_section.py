"""
ami_section.py — Tabbed AMI picker.

Tabs: Quick Start | My AMIs | Marketplace | Community | Recents

Load strategy
-------------
Quick Start and My AMIs are pre-loaded by LauncherWindow and injected via
populate().  Marketplace and Community are on-demand: the user types a search
term and clicks "Search"; the fetch runs in a background QThread so the UI
stays responsive.  Quick Start and My AMIs both have a "Reload" button that
re-fetches from AWS in the background.

Public API (used by ConfigForm):
    populate(quick_start_amis, my_amis)
    set_service(service)
    get_image_id() -> Optional[str]
    set_image_id(image_id: str)
    mark_error(has_error: bool)
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from PySide6.QtCore import QThread, Signal
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

logger = logging.getLogger(__name__)

_ERROR_STYLE = "border: 1px solid #e74c3c;"
_NORMAL_STYLE = ""

# Above this many AMIs in the My AMIs list, require a search string
# before populating the combo — avoids freezing the UI thread.
_MAX_COMBO_ITEMS = 300

# OS category → lowercase substrings matched against ami.name.
# Must cover both AWS console-style names ("Amazon Linux 2023") AND
# the actual AMI name prefixes AWS uses in describe_images results
# (e.g. "al2023-ami-...", "amzn2-ami-hvm-...", "Windows_Server-...").
_OS_FILTERS = {
    "Amazon Linux": ["amazon linux", "al2023", "amzn2", "amzn-ami"],
    "macOS":        ["macos", "mac os", "mac-"],
    "Ubuntu":       ["ubuntu"],
    "Windows":      ["windows"],
    "Red Hat":      ["red hat", "rhel"],
    "SUSE":         ["suse", "sles"],
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
_LOAD_BTN_STYLE = (
    "QPushButton { padding: 4px 12px; border-radius: 4px; font-size: 12px; "
    "background: #2980b9; color: white; border: none; min-height: 26px; } "
    "QPushButton:hover { background: #2471a3; } "
    "QPushButton:disabled { background: #95a5a6; }"
)
_CARD_STYLE = "QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }"

# Tab indices — keep in sync with the order tabs are added in __init__.
_TAB_QUICK_START = 0
_TAB_MY_AMIS     = 1
_TAB_MARKETPLACE = 2
_TAB_COMMUNITY   = 3
_TAB_RECENTS     = 4


# ---------------------------------------------------------------------------
# Background loader
# ---------------------------------------------------------------------------

class _AmiLoadThread(QThread):
    """Run an AMI fetch callable on a background thread.

    Emits ``finished`` with the result list on success, ``errored`` with a
    message on failure.  Callers must keep a reference to the thread until
    it finishes (Qt does not keep one automatically).
    """
    finished = Signal(list)   # List[Ami]
    errored  = Signal(str)

    def __init__(self, fetch_fn: Callable[[], List[Ami]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._fetch_fn = fetch_fn

    def run(self) -> None:
        try:
            amis = self._fetch_fn()
            self.finished.emit(amis)
        except Exception as exc:
            logger.error("AMI load thread failed: %s", exc)
            self.errored.emit(str(exc))


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class AmiSection(QWidget):
    """AMI picker: Quick Start / My AMIs / Marketplace / Community / Recents."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._service = None
        self._quick_start_amis: List[Ami] = []
        self._my_amis:          List[Ami] = []
        self._marketplace_amis: List[Ami] = []
        self._community_amis:   List[Ami] = []
        self._all_amis:         List[Ami] = []

        # OS/radio-filtered source lists; text search applied on top.
        self._qs_source: List[Ami] = []
        self._my_source: List[Ami] = []

        # Active loader threads — kept alive until finished.
        self._loaders: List[_AmiLoadThread] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_quick_start_tab(), "Quick Start")
        self._tabs.addTab(self._build_my_amis_tab(),     "My AMIs")
        self._tabs.addTab(self._build_marketplace_tab(), "Marketplace")
        self._tabs.addTab(self._build_community_tab(),   "Community")
        self._tabs.addTab(self._build_recents_tab(),     "Recents")
        outer.addWidget(self._tabs)
        outer.addWidget(self._build_detail_card())

        self._tabs.currentChanged.connect(self._on_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, quick_start_amis: List[Ami], my_amis: List[Ami]) -> None:
        self._quick_start_amis = quick_start_amis
        self._my_amis          = my_amis
        self._rebuild_all_amis_index()
        self._refresh_quick_start()
        self._refresh_my_amis()
        self._refresh_recents()

    def set_service(self, service) -> None:
        """Inject the LauncherService so Load/Reload buttons can call AWS."""
        self._service = service

    def get_image_id(self) -> Optional[str]:
        return self._active_combo().currentData()

    def set_image_id(self, image_id: str) -> None:
        for combo in (self._qs_combo, self._my_combo,
                      self._mkt_combo, self._com_combo, self._rec_combo):
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

        search_row = QHBoxLayout()
        self._qs_search = QLineEdit()
        self._qs_search.setPlaceholderText("Search by name or AMI ID…")
        self._qs_search.setStyleSheet(_SEARCH_STYLE)
        self._qs_search.setClearButtonEnabled(True)
        search_row.addWidget(self._qs_search)

        self._qs_reload_btn = QPushButton("Reload")
        self._qs_reload_btn.setStyleSheet(_LOAD_BTN_STYLE)
        self._qs_reload_btn.setFixedWidth(70)
        self._qs_reload_btn.setToolTip("Reload Quick Start AMIs from AWS")
        search_row.addWidget(self._qs_reload_btn)
        layout.addLayout(search_row)

        self._qs_status = QLabel("")
        self._qs_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(self._qs_status)

        self._qs_combo = QComboBox()
        layout.addWidget(self._qs_combo)

        self._os_group.buttonClicked.connect(self._on_os_clicked)
        self._qs_search.textChanged.connect(self._on_qs_search)
        self._qs_combo.currentIndexChanged.connect(self._on_changed)
        self._qs_reload_btn.clicked.connect(self._on_qs_reload)
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

        search_row = QHBoxLayout()
        self._my_search = QLineEdit()
        self._my_search.setPlaceholderText("Search by name or AMI ID…")
        self._my_search.setStyleSheet(_SEARCH_STYLE)
        self._my_search.setClearButtonEnabled(True)
        search_row.addWidget(self._my_search)

        self._my_reload_btn = QPushButton("Reload")
        self._my_reload_btn.setStyleSheet(_LOAD_BTN_STYLE)
        self._my_reload_btn.setFixedWidth(70)
        self._my_reload_btn.setToolTip("Reload My AMIs from AWS")
        search_row.addWidget(self._my_reload_btn)
        layout.addLayout(search_row)

        self._my_status_label = QLabel("")
        self._my_status_label.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 0;")
        layout.addWidget(self._my_status_label)

        self._my_combo = QComboBox()
        layout.addWidget(self._my_combo)

        self._owned_radio.toggled.connect(self._refresh_my_amis)
        self._my_search.textChanged.connect(self._on_my_search)
        self._my_combo.currentIndexChanged.connect(self._on_changed)
        self._my_reload_btn.clicked.connect(self._on_my_reload)
        return tab

    def _build_marketplace_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        hint = QLabel("Search the AWS Marketplace for commercial and free AMIs.")
        hint.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self._mkt_search = QLineEdit()
        self._mkt_search.setPlaceholderText("e.g. Windows Server, CentOS, deep learning…")
        self._mkt_search.setStyleSheet(_SEARCH_STYLE)
        self._mkt_search.setClearButtonEnabled(True)
        search_row.addWidget(self._mkt_search)

        self._mkt_search_btn = QPushButton("Search")
        self._mkt_search_btn.setStyleSheet(_LOAD_BTN_STYLE)
        self._mkt_search_btn.setFixedWidth(70)
        self._mkt_search_btn.setEnabled(False)
        search_row.addWidget(self._mkt_search_btn)
        layout.addLayout(search_row)

        self._mkt_status = QLabel("Enter a search term and click Search.")
        self._mkt_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(self._mkt_status)

        self._mkt_combo = QComboBox()
        layout.addWidget(self._mkt_combo)

        self._mkt_search.returnPressed.connect(self._on_mkt_search)
        self._mkt_search_btn.clicked.connect(self._on_mkt_search)
        self._mkt_search.textChanged.connect(self._on_mkt_text_changed)
        self._mkt_combo.currentIndexChanged.connect(self._on_changed)
        return tab

    def _build_community_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        hint = QLabel("Search community AMIs (public, from any account). Results capped at 200.")
        hint.setStyleSheet("color: #6c757d; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self._com_search = QLineEdit()
        self._com_search.setPlaceholderText("e.g. ubuntu 24.04, kali, minecraft…")
        self._com_search.setStyleSheet(_SEARCH_STYLE)
        self._com_search.setClearButtonEnabled(True)
        search_row.addWidget(self._com_search)

        self._com_search_btn = QPushButton("Search")
        self._com_search_btn.setStyleSheet(_LOAD_BTN_STYLE)
        self._com_search_btn.setFixedWidth(70)
        self._com_search_btn.setEnabled(False)
        search_row.addWidget(self._com_search_btn)
        layout.addLayout(search_row)

        self._com_status = QLabel("Enter a search term and click Search.")
        self._com_status.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(self._com_status)

        self._com_combo = QComboBox()
        layout.addWidget(self._com_combo)

        self._com_search.returnPressed.connect(self._on_com_search)
        self._com_search_btn.clicked.connect(self._on_com_search)
        self._com_search.textChanged.connect(self._on_com_text_changed)
        self._com_combo.currentIndexChanged.connect(self._on_changed)
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

        self._card_name = QLabel("—")
        self._card_name.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #2c3e50; border: none;"
        )
        layout.addWidget(self._card_name)

        self._card_id   = QLabel("")
        self._card_desc = QLabel("")
        self._card_desc.setWordWrap(True)
        for lbl in (self._card_id, self._card_desc):
            lbl.setStyleSheet("color: #6c757d; font-size: 11px; border: none;")
            layout.addWidget(lbl)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(24)
        self._meta_arch = self._make_meta_col(meta_row, "Architecture")
        self._meta_date = self._make_meta_col(meta_row, "Publish Date")
        self._meta_virt = self._make_meta_col(meta_row, "Virtualization")
        self._meta_ena  = self._make_meta_col(meta_row, "ENA Support")
        self._meta_root = self._make_meta_col(meta_row, "Root device")
        meta_row.addStretch()
        layout.addLayout(meta_row)

        return card

    @staticmethod
    def _make_meta_col(parent_layout: QHBoxLayout, label: str) -> QLabel:
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
        return val

    # ------------------------------------------------------------------
    # Reload / search handlers
    # ------------------------------------------------------------------

    def _on_qs_reload(self) -> None:
        if self._service is None:
            return
        self._start_load(
            fetch_fn=self._service.list_quick_start_amis,
            btn=self._qs_reload_btn,
            status=self._qs_status,
            on_done=self._on_qs_loaded,
        )

    def _on_qs_loaded(self, amis: List[Ami]) -> None:
        self._quick_start_amis = amis
        self._rebuild_all_amis_index()
        self._refresh_quick_start()
        self._qs_status.setText(f"{len(amis)} AMIs loaded")

    def _on_my_reload(self) -> None:
        if self._service is None:
            return
        self._start_load(
            fetch_fn=self._service.list_my_amis,
            btn=self._my_reload_btn,
            status=self._my_status_label,
            on_done=self._on_my_loaded,
        )

    def _on_my_loaded(self, amis: List[Ami]) -> None:
        self._my_amis = amis
        self._rebuild_all_amis_index()
        self._refresh_my_amis()

    def _on_mkt_text_changed(self, text: str) -> None:
        self._mkt_search_btn.setEnabled(bool(text.strip()))

    def _on_mkt_search(self) -> None:
        term = self._mkt_search.text().strip()
        if not term or self._service is None:
            return
        self._start_load(
            fetch_fn=lambda: self._service.search_marketplace_amis(term),
            btn=self._mkt_search_btn,
            status=self._mkt_status,
            on_done=self._on_mkt_loaded,
        )

    def _on_mkt_loaded(self, amis: List[Ami]) -> None:
        self._marketplace_amis = amis
        self._rebuild_all_amis_index()
        self._rebuild_combo(self._mkt_combo, amis, "")
        self._mkt_status.setText(f"{len(amis)} results")

    def _on_com_text_changed(self, text: str) -> None:
        self._com_search_btn.setEnabled(bool(text.strip()))

    def _on_com_search(self) -> None:
        term = self._com_search.text().strip()
        if not term or self._service is None:
            return
        self._start_load(
            fetch_fn=lambda: self._service.search_community_amis(term),
            btn=self._com_search_btn,
            status=self._com_status,
            on_done=self._on_com_loaded,
        )

    def _on_com_loaded(self, amis: List[Ami]) -> None:
        self._community_amis = amis
        self._rebuild_all_amis_index()
        self._rebuild_combo(self._com_combo, amis, "")
        self._com_status.setText(f"{len(amis)} results (capped at 200)")

    # ------------------------------------------------------------------
    # Background loader helper
    # ------------------------------------------------------------------

    def _start_load(
        self,
        fetch_fn: Callable[[], List[Ami]],
        btn: QPushButton,
        status: QLabel,
        on_done: Callable[[List[Ami]], None],
    ) -> None:
        """Kick off a background AMI fetch.  Disables btn while running."""
        original_text = btn.text()
        btn.setEnabled(False)
        btn.setText("Loading…")
        status.setText("Fetching from AWS…")

        thread = _AmiLoadThread(fetch_fn, parent=self)
        self._loaders.append(thread)

        def _finish(amis: List[Ami]) -> None:
            btn.setEnabled(True)
            btn.setText(original_text)
            on_done(amis)
            self._loaders = [t for t in self._loaders if t.isRunning()]

        def _error(msg: str) -> None:
            btn.setEnabled(True)
            btn.setText(original_text)
            status.setText(f"Error: {msg}")
            self._loaders = [t for t in self._loaders if t.isRunning()]

        thread.finished.connect(_finish)
        thread.errored.connect(_error)
        thread.start()

    # ------------------------------------------------------------------
    # Private — refresh / filter
    # ------------------------------------------------------------------

    def _rebuild_all_amis_index(self) -> None:
        """Merge all source lists into _all_amis for the detail card lookup."""
        seen: dict = {}
        for ami in (self._quick_start_amis + self._my_amis
                    + self._marketplace_amis + self._community_amis):
            seen.setdefault(ami.image_id, ami)
        self._all_amis = list(seen.values())

    def _refresh_quick_start(self) -> None:
        self._on_os_clicked(self._os_group.checkedButton())

    def _on_os_clicked(self, btn: Optional[QPushButton]) -> None:
        keywords = _OS_FILTERS.get(btn.text() if btn else "All", [])
        self._qs_source = [
            a for a in self._quick_start_amis
            if not keywords or any(k in a.name.lower() for k in keywords)
        ]
        search = self._qs_search.text() if hasattr(self, "_qs_search") else ""
        self._rebuild_combo(self._qs_combo, self._qs_source, search)

    def _on_qs_search(self, text: str) -> None:
        self._rebuild_combo(self._qs_combo, self._qs_source, text)

    def _refresh_my_amis(self) -> None:
        shared = hasattr(self, "_shared_radio") and self._shared_radio.isChecked()
        self._my_source = [
            a for a in self._my_amis
            if not shared or any(t.key == "CreatedBy" for t in a.tags)
        ]
        search_text = self._my_search.text() if hasattr(self, "_my_search") else ""
        total = len(self._my_source)
        if total > _MAX_COMBO_ITEMS and not search_text.strip():
            self._my_combo.blockSignals(True)
            self._my_combo.clear()
            self._my_combo.blockSignals(False)
            self._my_status_label.setText(f"{total:,} AMIs — type in the search box to filter")
            self._on_changed()
        else:
            self._my_status_label.setText("")
            self._rebuild_combo(self._my_combo, self._my_source, search_text)

    def _on_my_search(self, text: str) -> None:
        if not text.strip() and len(self._my_source) > _MAX_COMBO_ITEMS:
            self._refresh_my_amis()
            return
        self._rebuild_combo(self._my_combo, self._my_source, text)
        shown = self._my_combo.count()
        total = len(self._my_source)
        if text.strip() and total > _MAX_COMBO_ITEMS:
            self._my_status_label.setText(f"Showing {shown:,} of {total:,} AMIs")

    def _refresh_recents(self) -> None:
        self._rec_combo.clear()
        sorted_amis = sorted(self._all_amis, key=lambda a: a.creation_date or "", reverse=True)
        for ami in sorted_amis[:100]:
            self._rec_combo.addItem(f"{ami.name}  ({ami.image_id})", userData=ami.image_id)
        self._rec_combo.setCurrentIndex(-1)

    def _rebuild_combo(self, combo: QComboBox, source: List[Ami], text: str) -> None:
        """Repopulate combo with AMIs whose name or ID contain text."""
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
        elif combo.count() > 0:
            combo.setCurrentIndex(0)
        else:
            combo.setCurrentIndex(-1)
        combo.blockSignals(False)
        self._on_changed()

    def _active_combo(self) -> QComboBox:
        combos = [
            self._qs_combo, self._my_combo,
            self._mkt_combo, self._com_combo, self._rec_combo,
        ]
        return combos[self._tabs.currentIndex()]

    def _on_changed(self, _index: int = 0) -> None:
        image_id = self._active_combo().currentData()
        ami = next((a for a in self._all_amis if a.image_id == image_id), None)
        if ami:
            self._card_name.setText(ami.name)
            self._card_id.setText(f"{ami.image_id}    ·    {ami.platform}")
            self._card_desc.setText(ami.description or "")
            arch_map = {"x86_64": "64-bit (x86)", "arm64": "64-bit (Arm)", "i386": "32-bit (x86)"}
            self._meta_arch.setText(arch_map.get(ami.architecture or "", ami.architecture or "—"))
            pub = (ami.creation_date or "").split("T")[0] or "—"
            self._meta_date.setText(pub)
            self._meta_virt.setText(ami.virtualization_type or "—")
            self._meta_ena.setText(
                "Enabled" if ami.ena_support else ("—" if ami.ena_support is None else "Disabled")
            )
            self._meta_root.setText(ami.root_device_type or "—")
        else:
            self._card_name.setText("—")
            self._card_id.setText("")
            self._card_desc.setText("")
            for lbl in (self._meta_arch, self._meta_date, self._meta_virt,
                        self._meta_ena, self._meta_root):
                lbl.setText("—")
