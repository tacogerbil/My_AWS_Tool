"""
SgChipsWidget — renders SecurityGroup objects as inline chip labels.

Single responsibility: chip rendering + toggle selection.
No AWS calls, no business logic.
"""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal

from core.models import SecurityGroup

_CHIP_BASE = """
    QLabel {{
        border-left: 4px solid {color};
        background-color: #ecf0f1;
        color: #2c3e50;
        border-radius: 3px;
        padding: 2px 6px 2px 4px;
        font-size: 12px;
    }}
"""

_CHIP_SELECTED = """
    QLabel {{
        border-left: 4px solid {color};
        background-color: #d6eaf8;
        color: #1a5276;
        border-radius: 3px;
        padding: 2px 6px 2px 4px;
        font-size: 12px;
        font-weight: bold;
    }}
"""


def _chip_color(sg_id: str) -> str:
    """Deterministic muted color from sg_id hash."""
    palette = [
        "#7f8c8d", "#2980b9", "#8e44ad",
        "#16a085", "#c0392b", "#d35400",
    ]
    return palette[hash(sg_id) % len(palette)]


class _SgChip(QLabel):
    """A single clickable chip label for one SecurityGroup."""

    toggled = Signal(str, bool)  # (group_id, selected)

    def __init__(self, sg: SecurityGroup, checkable: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._sg = sg
        self._checkable = checkable
        self._selected = False
        self._color = _chip_color(sg.group_id)

        self.setText(sg.group_name)
        self.setToolTip(f"{sg.group_id}\n{sg.description}")
        self.setCursor(Qt.PointingHandCursor if checkable else Qt.ArrowCursor)
        self._refresh_style()

    @property
    def group_id(self) -> str:
        return self._sg.group_id

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, value: bool) -> None:
        self._selected = value
        self._refresh_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._checkable and event.button() == Qt.LeftButton:
            self._selected = not self._selected
            self._refresh_style()
            self.toggled.emit(self._sg.group_id, self._selected)
        super().mousePressEvent(event)

    def _refresh_style(self) -> None:
        tmpl = _CHIP_SELECTED if self._selected else _CHIP_BASE
        self.setStyleSheet(tmpl.format(color=self._color))


class SgChipsWidget(QWidget):
    """Displays SecurityGroup objects as a horizontal flow of chip labels.

    When checkable=True (default), chips toggle on click and
    selection_changed is emitted with the current list of selected IDs.
    When checkable=False, chips are display-only (used in ReferencePanel).
    """

    selection_changed = Signal(list)   # List[str] of selected group_ids
    chip_toggled = Signal(object)      # SecurityGroup of the chip just clicked

    def __init__(self, checkable: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._checkable = checkable
        self._chips: List[_SgChip] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addStretch()  # placeholder so chips left-align

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_groups(self, sgs: List[SecurityGroup]) -> None:
        """Replace chip list with the supplied SecurityGroups."""
        self._clear_chips()
        layout = self.layout()
        # Remove the trailing stretch before inserting chips
        item = layout.takeAt(layout.count() - 1)
        del item

        for sg in sgs:
            chip = _SgChip(sg, checkable=self._checkable)
            chip.toggled.connect(self._on_chip_toggled)
            self._chips.append(chip)
            layout.addWidget(chip)

        layout.addStretch()

    def set_selected_ids(self, ids: List[str]) -> None:
        """Mark chips whose group_id is in ids as selected."""
        for chip in self._chips:
            chip.set_selected(chip.group_id in ids)

    def get_selected_ids(self) -> List[str]:
        """Return list of currently selected group_ids."""
        return [c.group_id for c in self._chips if c.selected]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_chip_toggled(self, group_id: str, _state: bool) -> None:
        self.selection_changed.emit(self.get_selected_ids())
        chip = next((c for c in self._chips if c.group_id == group_id), None)
        if chip:
            self.chip_toggled.emit(chip._sg)

    def _clear_chips(self) -> None:
        layout = self.layout()
        for chip in self._chips:
            layout.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()
