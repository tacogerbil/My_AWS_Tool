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
    """Multi-select combo with checkboxes.

    Search works identically to SearchableComboBox — the inherited QCompleter
    handles it.  Selecting a completion toggles that item's checkbox instead of
    navigating to it.  The main dropdown also supports clicking to check/uncheck.

    Signals:
        selection_changed(list): UserRole data for all checked rows.
        item_toggled(object):    UserRole data of the last-toggled row.
    """

    selection_changed = Signal(list)
    item_toggled = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Swap in a checkable model; SearchableComboBox.setModel syncs the completer.
        self.model = QStandardItemModel(self)
        self.setModel(self.model)

        # Intercept completer selection → toggle checkbox instead of navigating.
        self.pCompleter.activated.connect(self._on_completer_activated)
        # Clicking a row in the main dropdown also toggles its checkbox.
        self.view().pressed.connect(self.handle_item_pressed)

    # ------------------------------------------------------------------
    # Keep main dropdown open while clicking checkboxes
    # ------------------------------------------------------------------

    def hidePopup(self) -> None:
        if not self.view().underMouse():
            super().hidePopup()

    # ------------------------------------------------------------------
    # Item management
    # ------------------------------------------------------------------

    def addItem(self, text: str, data=None) -> None:  # type: ignore[override]
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        item.setData(data, Qt.UserRole)
        self.model.appendRow(item)

    def addItems(self, texts) -> None:  # type: ignore[override]
        for t in texts:
            self.addItem(t)

    # ------------------------------------------------------------------
    # Checkbox interaction
    # ------------------------------------------------------------------

    def _on_completer_activated(self, text: str) -> None:
        """Toggle the checkbox for whichever item the completer just picked."""
        for i in range(self.model.rowCount()):
            if self.model.item(i).text() == text:
                self._toggle_index(i)
                break
        self._update_text()

    def handle_item_pressed(self, index) -> None:
        self._toggle_index(index.row())
        self._update_text()

    def _toggle_index(self, row: int) -> None:
        item = self.model.item(row)
        new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
        item.setCheckState(new_state)
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
    # Private
    # ------------------------------------------------------------------

    def _update_text(self) -> None:
        items = self.get_checked_items()
        self.lineEdit().blockSignals(True)
        if not items:
            self.setEditText("")
        else:
            self.setEditText(f"{len(items)} selected: " + ", ".join(items))
        self.lineEdit().blockSignals(False)
