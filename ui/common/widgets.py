from PySide6.QtWidgets import QComboBox, QCompleter
from PySide6.QtCore import Qt

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
    """
    A SearchableComboBox that supports multiple selection via checkboxes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pCompleter.setCompletionMode(QCompleter.PopupCompletion)
        self.pCompleter.setFilterMode(Qt.MatchContains)
        
        # Use StandardItemModel for Checkboxes
        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        
        # Keep popup open when clicking (requires custom view event filter, skipping for prototype simplicity)
        # However, we can make it so checking an item emits signal instantly.
        self.view().pressed.connect(self.handle_item_pressed)
        
        self.checked_items = []

    def handle_item_pressed(self, index):
        item = self.model.itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)
        self._update_text()

    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        self.model.appendRow(item)
        
    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def _update_text(self):
        # Collect checked items
        items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.Checked:
                items.append(item.text())
        
        self.checked_items = items
        # Show count or list
        if not items:
            self.setEditText("")
        else:
            self.setEditText(f"{len(items)} selected: " + ", ".join(items))
            
    def get_checked_items(self):
        # Return list of text for checked items
        items = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.Checked:
                items.append(item.text())
        return items
