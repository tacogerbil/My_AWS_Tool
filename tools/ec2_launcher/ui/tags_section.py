"""
tags_section.py — Editable key/value AWS tag table.

Public API (used by ConfigForm):
    get_tags() -> Dict[str, str]
    set_tags(tags: Dict[str, str])
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TagsSection(QWidget):
    """Editable key / value tag table with Add / Remove row buttons."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Key", "Value"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 160)
        self._table.setMinimumHeight(100)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        for label, slot in [("Add Row", self._add_row), ("Remove Row", self._remove_row)]:
            btn = QPushButton(label)
            btn.setFixedWidth(100)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tags(self) -> Dict[str, str]:
        tags: Dict[str, str] = {}
        for row in range(self._table.rowCount()):
            k = (self._table.item(row, 0) or QTableWidgetItem("")).text().strip()
            v = (self._table.item(row, 1) or QTableWidgetItem("")).text().strip()
            if k:
                tags[k] = v
        return tags

    def set_tags(self, tags: Dict[str, str]) -> None:
        self._table.setRowCount(0)
        for key, val in tags.items():
            self._add_row(key, val)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _add_row(self, key: str = "", value: str = "") -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(key))
        self._table.setItem(row, 1, QTableWidgetItem(value))

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
