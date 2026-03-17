"""
collapsible.py — Reusable animated collapsible section panel.

Single responsibility: toggleable dark header + smooth height animation.
Zero domain dependencies — safe to import anywhere in the UI layer.

Usage
-----
    sec = CollapsibleSection("Network Settings")
    sec.set_content(my_widget)
    layout.addWidget(sec)

    # Optional: show a summary line in the collapsed header
    sec.set_summary("vpc-abc / subnet-1a")
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget


# ---------------------------------------------------------------------------
# Private style helpers
# ---------------------------------------------------------------------------

def _header_style(bottom_round: bool) -> str:
    """Return QSS for the header button.  Bottom corners round when collapsed."""
    br = "6px" if bottom_round else "0px"
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #34495e, stop:1 #2c3e50);
            color: white;
            border: none;
            border-top-left-radius:  6px;
            border-top-right-radius: 6px;
            border-bottom-left-radius:  {br};
            border-bottom-right-radius: {br};
            text-align: left;
            padding-left: 14px;
            font-weight: bold;
            font-size: 13px;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3d566e, stop:1 #34495e);
        }}
        QPushButton:pressed {{ background: #1a252f; }}
    """


# IMPORTANT: Use the #objectName selector so this style ONLY applies to the
# body widget itself.  A bare "QWidget { ... }" selector would cascade to all
# descendant QWidget children (QLineEdit, QComboBox, QCheckBox …) and strip
# their top borders via the "border-top: none" rule.
_BODY_OBJ_NAME = "_collapsibleBody"
_BODY_STYLE = f"""
    #{_BODY_OBJ_NAME} {{
        background-color: #ffffff;
        border: 1px solid #d5d8dc;
        border-top: none;
        border-bottom-left-radius: 6px;
        border-bottom-right-radius: 6px;
    }}
"""


# ---------------------------------------------------------------------------
# Public widget
# ---------------------------------------------------------------------------

class CollapsibleSection(QWidget):
    """Animated collapsible section with a styled dark-gradient header.

    Parameters
    ----------
    title : str
        Text shown in the header.
    collapsed : bool
        Start collapsed if True (default False).
    """

    _DURATION = 220  # animation duration in ms

    def __init__(
        self, title: str, collapsed: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._summary = ""
        self._is_collapsed = collapsed
        self._anim: Optional[QPropertyAnimation] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 6)
        root.setSpacing(0)

        # Header button
        self._btn = QPushButton()
        self._btn.setFixedHeight(38)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.clicked.connect(self._toggle)
        root.addWidget(self._btn)

        # Body (content area)
        self._body = QWidget()
        self._body.setObjectName(_BODY_OBJ_NAME)
        self._body.setStyleSheet(_BODY_STYLE)
        body_inner = QVBoxLayout(self._body)
        body_inner.setContentsMargins(12, 10, 12, 10)
        root.addWidget(self._body)

        self._refresh_header()

        if collapsed:
            self._body.setMaximumHeight(0)
            self._body.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_content(self, widget: QWidget) -> None:
        """Place *widget* inside the collapsible body."""
        self._body.layout().addWidget(widget)

    def set_summary(self, text: str) -> None:
        """Summary shown in the header when collapsed (provenance hint)."""
        self._summary = text
        self._refresh_header()

    def expand(self) -> None:
        """Expand if currently collapsed."""
        if self._is_collapsed:
            self._toggle()

    def collapse(self) -> None:
        """Collapse if currently expanded."""
        if not self._is_collapsed:
            self._toggle()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _refresh_header(self) -> None:
        arrow = "▼" if not self._is_collapsed else "▶"
        summ = (
            f"   —   {self._summary}"
            if self._summary and self._is_collapsed
            else ""
        )
        self._btn.setText(f"  {arrow}   {self._title}{summ}")
        self._btn.setStyleSheet(_header_style(bottom_round=self._is_collapsed))

    def _toggle(self) -> None:
        self._is_collapsed = not self._is_collapsed
        self._refresh_header()

        if self._anim:
            self._anim.stop()

        self._anim = QPropertyAnimation(self._body, b"maximumHeight")
        self._anim.setDuration(self._DURATION)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

        if self._is_collapsed:
            self._anim.setStartValue(self._body.height())
            self._anim.setEndValue(0)
            self._anim.finished.connect(self._body.hide)
        else:
            self._body.show()
            target = max(self._body.sizeHint().height(), 80)
            self._body.setMaximumHeight(0)
            self._anim.setStartValue(0)
            self._anim.setEndValue(target)
            self._anim.finished.connect(
                lambda: self._body.setMaximumHeight(16777215)
            )

        self._anim.start()
