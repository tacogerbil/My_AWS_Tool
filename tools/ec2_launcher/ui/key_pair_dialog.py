"""
key_pair_dialog.py — "Create new key pair" dialog.

Mirrors the AWS console workflow: name, key type, file format.

Public API:
    CreateKeyPairDialog(parent) — QDialog, call .exec()
    .key_name()   -> str   — name the user typed
    .key_type()   -> str   — "rsa" | "ed25519"
    .key_format() -> str   — "pem" | "ppk"
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

_FIELD_STYLE = """
    QLineEdit {
        border: 1px solid #ced4da; border-radius: 4px;
        padding: 5px 10px; font-size: 13px;
        background: white; color: #2c3e50; min-height: 28px;
    }
    QLineEdit:focus { border-color: #3498db; }
"""

_SECTION_STYLE = """
    QFrame {
        background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;
    }
"""


class CreateKeyPairDialog(QDialog):
    """Collect key pair parameters; caller handles the AWS call and file save."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Key Pair")
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        layout.addWidget(QLabel("<b>Key pair name</b>"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. my-key-pair")
        self._name_edit.setStyleSheet(_FIELD_STYLE)
        layout.addWidget(self._name_edit)

        layout.addWidget(self._build_radio_group(
            title="<b>Key pair type</b>",
            options=[
                ("rsa",     "RSA",     "Compatible with all SSH clients"),
                ("ed25519", "ED25519", "More secure; not supported on Windows Server 2019 and older"),
            ],
            attr="_ktype_group",
        ))

        layout.addWidget(self._build_radio_group(
            title="<b>Private key file format</b>",
            options=[
                ("pem", ".pem", "For use with OpenSSH / Linux / macOS"),
                ("ppk", ".ppk", "For use with PuTTY on Windows"),
            ],
            attr="_fmt_group",
        ))

        note = QLabel(
            "<i>The private key will be downloaded once and cannot be retrieved "
            "again. Store it securely.</i>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Create key pair")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def key_name(self) -> str:
        return self._name_edit.text().strip()

    def key_type(self) -> str:
        """Return "rsa" or "ed25519"."""
        checked = self._ktype_group.checkedButton()
        return checked.property("value") if checked else "rsa"

    def key_format(self) -> str:
        """Return "pem" or "ppk"."""
        checked = self._fmt_group.checkedButton()
        return checked.property("value") if checked else "pem"

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_radio_group(self, title: str, options: list, attr: str) -> QFrame:
        """Build a labeled radio-button group.

        ``options`` is a list of (value, label, description) tuples.
        The first option is pre-selected.  Each QRadioButton stores its
        value via a dynamic property so key_type() / key_format() can read it.
        """
        frame = QFrame()
        frame.setStyleSheet(_SECTION_STYLE)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(4)
        fl.addWidget(QLabel(title))

        group = QButtonGroup(frame)
        group.setExclusive(True)
        for i, (value, label, desc) in enumerate(options):
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            if i == 0:
                rb.setChecked(True)
            group.addButton(rb)

            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")

            from PySide6.QtWidgets import QHBoxLayout
            row = QHBoxLayout()
            row.addWidget(rb)
            row.addWidget(desc_lbl)
            row.addStretch()
            fl.addLayout(row)

        setattr(self, attr, group)
        return frame

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Key pair name is required.")
            return
        self.accept()
