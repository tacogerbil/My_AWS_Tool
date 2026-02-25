from PySide6.QtWidgets import QComboBox, QCompleter
from PySide6.QtCore import Qt, Signal

class SearchableComboBox(QComboBox):
    """
    A QComboBox that allows fuzzy/partial searching of its items.
    MCCC: Reusable, Single Responsibility (Enhanced Selection).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        
        # Explicitly create completer to ensure correct behavior
        # QComboBox creates one by default, but we want full control
        self.pCompleter = QCompleter(self)
        self.pCompleter.setCompletionMode(QCompleter.PopupCompletion)
        self.pCompleter.setFilterMode(Qt.MatchContains)
        self.pCompleter.setCaseSensitivity(Qt.CaseInsensitive)
        
        # Initial Model Sync
        self.pCompleter.setModel(self.model())
        self.setCompleter(self.pCompleter)

        # Always show text from the beginning (left), not the end
        self.currentIndexChanged.connect(self._reset_cursor)

    def setModel(self, model):
        super().setModel(model)
        self.pCompleter.setModel(model)
        self.pCompleter.setFilterMode(Qt.MatchContains)
        self.pCompleter.setCaseSensitivity(Qt.CaseInsensitive)

    def addItem(self, text, userData=None):
        super().addItem(text, userData)
        # Completer usually auto-syncs because it shares the model, but sometimes needs a kick
        # Here we rely on shared model.

    def addItems(self, texts):
        super().addItems(texts)

    def _reset_cursor(self) -> None:
        """Move cursor to position 0 so long items show their start, not their end."""
        le = self.lineEdit()
        if le:
            le.home(False)


from PySide6.QtGui import QStandardItemModel, QStandardItem


class CheckableComboBox(SearchableComboBox):
    """Searchable, multi-select combo with per-item checkboxes.

    Signals:
        selection_changed(list): emits list of UserRole data for all checked rows.
        item_toggled(object):    emits the UserRole data of the last-toggled row.
    """

    selection_changed = Signal(list)
    item_toggled = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Disable inherited completer — filtering is done in-popup via _filter_popup.
        self.setCompleter(None)

        # Replace default model with one that supports checkboxes.
        self.model = QStandardItemModel(self)
        self.setModel(self.model)

        self.view().pressed.connect(self.handle_item_pressed)
        self.lineEdit().textChanged.connect(self._filter_popup)

    # ------------------------------------------------------------------
    # Popup behaviour
    # ------------------------------------------------------------------

    def hidePopup(self) -> None:
        """Keep popup open while typing or clicking checkboxes."""
        if self.view().underMouse() or self.lineEdit().hasFocus():
            return
        super().hidePopup()

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def addItem(self, text: str, data=None) -> None:  # type: ignore[override]
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        item.setData(data, Qt.UserRole)
        self.model.appendRow(item)

    def addItems(self, texts) -> None:  # type: ignore[override]
        for t in texts:
            self.addItem(t)

    # ------------------------------------------------------------------
    # Checkbox interaction
    # ------------------------------------------------------------------

    def handle_item_pressed(self, index) -> None:
        item = self.model.itemFromIndex(index)
        new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
        item.setCheckState(new_state)
        self._update_text()
        self.item_toggled.emit(item.data(Qt.UserRole))
        self.selection_changed.emit(self.get_checked_data())

    # ------------------------------------------------------------------
    # Public query / mutation
    # ------------------------------------------------------------------

    def get_checked_items(self) -> list:
        """Return display text of all checked rows."""
        return [
            self.model.item(i).text()
            for i in range(self.model.rowCount())
            if self.model.item(i).checkState() == Qt.Checked
        ]

    def get_checked_data(self) -> list:
        """Return UserRole data of all checked rows."""
        return [
            self.model.item(i).data(Qt.UserRole)
            for i in range(self.model.rowCount())
            if self.model.item(i).checkState() == Qt.Checked
        ]

    def set_checked_data(self, data_list: list) -> None:
        """Check all rows whose UserRole data appears in *data_list*."""
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            state = Qt.Checked if item.data(Qt.UserRole) in data_list else Qt.Unchecked
            item.setCheckState(state)
        self._update_text()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_popup(self, text: str) -> None:
        """Open popup once if not visible; filter rows by partial match."""
        if not self.view().isVisible():
            self.showPopup()
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            hidden = bool(text) and text.lower() not in item.text().lower()
            self.view().setRowHidden(row, hidden)

    def _update_text(self) -> None:
        """Refresh the edit-field summary without re-triggering _filter_popup."""
        items = self.get_checked_items()
        self.lineEdit().blockSignals(True)
        if not items:
            self.setEditText("")
        else:
            self.setEditText(f"{len(items)} selected: " + ", ".join(items))
        self.lineEdit().blockSignals(False)
