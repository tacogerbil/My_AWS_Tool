from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from typing import List, Any
import logging

class BaseTableWidget(QWidget):
    """
    Base widget for displaying resources in a table.
    Follows MCCC: Specific Responsibility (Display Data).
    """
    def __init__(self, headers: List[str]):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only
        self.layout.addWidget(self.table)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _add_row(self, items: List[str]):
        """Helper to add a row to the table."""
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        for col_idx, item in enumerate(items):
            self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(item)))

    def clear(self):
        self.table.setRowCount(0)
