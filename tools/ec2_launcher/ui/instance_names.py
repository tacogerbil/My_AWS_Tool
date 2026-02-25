"""
instance_names.py — Pre-name every instance before launching.

Single responsibility: capture N instance names so users never have to
hunt down newly launched EC2s to rename them after the fact.

Features
--------
- Spinbox (1–20) controls the number of rows dynamically.
- Each row has a colored numbered badge + name QLineEdit.
- New rows fade in; removed rows disappear cleanly.
- "Auto-fill" generates sequential names from a base string
  (e.g. "web-server" → web-server-01, web-server-02 …).

Public API
----------
    get_count() -> int
    get_instance_names() -> List[str]
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Cycling palette for per-instance badge colors
_BADGE_COLORS = [
    "#3498db",  # blue
    "#27ae60",  # green
    "#e67e22",  # orange
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e74c3c",  # red
    "#2980b9",  # dark blue
    "#f39c12",  # amber
]

_FIELD_STYLE = """
    QLineEdit {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 5px 10px;
        background: white;
        font-size: 13px;
        color: #2c3e50;
        min-height: 28px;
    }
    QLineEdit:focus { border-color: #3498db; }
"""

_ROW_STYLE = """
    QWidget {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
"""


# ---------------------------------------------------------------------------
# _InstanceRow — single named-instance card
# ---------------------------------------------------------------------------

class _InstanceRow(QWidget):
    """Numbered badge + name field for one instance."""

    def __init__(self, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_ROW_STYLE)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)

        color = _BADGE_COLORS[(index - 1) % len(_BADGE_COLORS)]
        badge = QLabel(str(index))
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {color}; color: white;"
            " border-radius: 14px; font-weight: bold; font-size: 12px;"
            " border: none;"
        )
        row.addWidget(badge)

        self._field = QLineEdit()
        self._field.setPlaceholderText(f"instance-{index:02d}")
        self._field.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._field)

    def get_name(self) -> str:
        """Return the entered name, or the placeholder if blank."""
        txt = self._field.text().strip()
        return txt if txt else self._field.placeholderText()

    def set_name(self, name: str) -> None:
        self._field.setText(name)

    def is_blank(self) -> bool:
        """True if the user left this field empty (placeholder does NOT count)."""
        return self._field.text().strip() == ""

    def mark_error(self, on: bool) -> None:
        """Apply or remove a red border to signal a validation error."""
        if on:
            self._field.setStyleSheet(
                _FIELD_STYLE + "QLineEdit { border: 1px solid #e74c3c; }"
            )
        else:
            self._field.setStyleSheet(_FIELD_STYLE)

    def fade_in(self) -> None:
        """Animate opacity 0 → 1 when the row first appears."""
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        anim.start()
        self._fade_anim = anim  # prevent GC before animation completes


# ---------------------------------------------------------------------------
# InstanceNamesSection — public widget
# ---------------------------------------------------------------------------

class InstanceNamesSection(QWidget):
    """Spinbox + dynamically-generated named-instance rows.

    Guarantees one name per instance so every EC2 is identifiable
    immediately after launch — no post-launch renaming required.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[_InstanceRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        outer.addLayout(self._build_controls())

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        outer.addWidget(self._rows_container)

        # Start with one row (no animation for the initial row)
        self._add_row(1, animate=False)
        self._count_spin.valueChanged.connect(self._sync_rows)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_count(self) -> int:
        """Number of instances to launch."""
        return self._count_spin.value()

    def get_instance_names(self) -> List[str]:
        """One name per instance, in order (placeholder returned for blank rows)."""
        return [row.get_name() for row in self._rows]

    def mark_blank_errors(self) -> List[int]:
        """Mark all blank rows with a red border; return 0-based indices of blank rows."""
        blank: List[int] = []
        for i, row in enumerate(self._rows):
            if row.is_blank():
                row.mark_error(True)
                blank.append(i)
        return blank

    def clear_errors(self) -> None:
        """Remove all error borders from every row."""
        for row in self._rows:
            row.mark_error(False)

    # ------------------------------------------------------------------
    # Private — UI construction
    # ------------------------------------------------------------------

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        count_lbl = QLabel("Count:")
        count_lbl.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 13px;")
        row.addWidget(count_lbl)

        import os
        ui_dir = os.path.dirname(os.path.abspath(__file__))
        up_arrow = os.path.join(ui_dir, "assets", "spin_up.svg").replace("\\", "/")
        dn_arrow = os.path.join(ui_dir, "assets", "spin_down.svg").replace("\\", "/")

        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 20)
        self._count_spin.setValue(1)
        self._count_spin.setFixedWidth(65)
        self._count_spin.setStyleSheet(f"""
            QSpinBox {{
                border: 1px solid #ced4da; border-radius: 4px;
                padding: 4px 10px; font-size: 13px; font-weight: bold;
                background: white; color: #2c3e50; min-height: 28px;
            }}
            QSpinBox:focus {{ border-color: #3498db; }}
            QSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 20px;
                background: #f8f9fa;
                border-left: 1px solid #ced4da; border-bottom: 1px solid #ced4da;
                border-top-right-radius: 3px;
                margin: 1px 1px 0 0;
            }}
            QSpinBox::up-button:hover   {{ background: #e9ecef; }}
            QSpinBox::up-button:pressed {{ background: #dee2e6; }}
            QSpinBox::up-arrow {{ 
                image: url({up_arrow});
                width: 10px; height: 6px;
                margin-bottom: 1px;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 20px;
                background: #f8f9fa;
                border-left: 1px solid #ced4da; border-top: 1px solid #ced4da;
                border-bottom-right-radius: 3px;
                margin: 0 1px 1px 0;
            }}
            QSpinBox::down-button:hover   {{ background: #e9ecef; }}
            QSpinBox::down-button:pressed {{ background: #dee2e6; }}
            QSpinBox::down-arrow {{ 
                image: url({dn_arrow});
                width: 10px; height: 6px;
                margin-top: 1px;
            }}
        """)
        row.addWidget(self._count_spin)

        row.addSpacing(16)

        base_lbl = QLabel("Base name:")
        base_lbl.setStyleSheet("color: #2c3e50; font-size: 13px;")
        row.addWidget(base_lbl)

        self._base_name = QLineEdit()
        self._base_name.setPlaceholderText("e.g. web-server")
        self._base_name.setFixedWidth(180)
        self._base_name.setStyleSheet(_FIELD_STYLE)
        row.addWidget(self._base_name)

        auto_btn = QPushButton("Auto-fill ▶")
        auto_btn.setFixedWidth(95)
        auto_btn.setToolTip(
            "Fill all name fields as <base>-01, <base>-02 …"
        )
        auto_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white;
                border: none; border-radius: 4px;
                padding: 5px 10px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:pressed { background-color: #1f6fa3; }
        """)
        auto_btn.clicked.connect(self._auto_fill)
        row.addWidget(auto_btn)
        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Private — row management
    # ------------------------------------------------------------------

    def _sync_rows(self, count: int) -> None:
        current = len(self._rows)
        for i in range(current, count):
            self._add_row(i + 1, animate=True)
        for _ in range(current - count):
            self._remove_last_row()

    def _add_row(self, index: int, animate: bool = False) -> None:
        row = _InstanceRow(index)
        self._rows_layout.addWidget(row)
        self._rows.append(row)
        if animate:
            row.fade_in()

    def _remove_last_row(self) -> None:
        if not self._rows:
            return
        self._rows.pop()
        item = self._rows_layout.takeAt(self._rows_layout.count() - 1)
        if item and item.widget():
            item.widget().deleteLater()

    def _auto_fill(self) -> None:
        base = self._base_name.text().strip() or "instance"
        count = len(self._rows)
        pad = max(len(str(count)), 2)
        for i, row in enumerate(self._rows):
            row.set_name(f"{base}-{str(i + 1).zfill(pad)}")
