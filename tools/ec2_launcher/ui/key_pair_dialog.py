"""
key_pair_dialog.py — "Create new key pair" dialog.

Mirrors the AWS console workflow: name, key type, file format.
The actual CreateKeyPair API call is deferred (wiring pending); the dialog
captures the desired parameters and shows a confirmation message.

Public API:
    CreateKeyPairDialog(parent) — QDialog, call .exec()
    .key_name() -> str          — name entered by the user
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
    QHBoxLayout,
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
    """Create-key-pair dialog (AWS wiring deferred)."""

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
                ("RSA",     "RSA — compatible with all SSH clients"),
                ("ED25519", "ED25519 — more secure; not supported on Windows Server 2019 and older"),
            ],
            attr="_ktype_group",
        ))

        layout.addWidget(self._build_radio_group(
            title="<b>Private key file format</b>",
            options=[
                (".pem", ".pem — for use with OpenSSH / Linux / macOS"),
                (".ppk", ".ppk — for use with PuTTY on Windows"),
            ],
            attr="_fmt_group",
        ))

        note = QLabel(
            "<i>Note: AWS wiring is pending. The key pair name has been captured "
            "and will be created when launch integration is complete.</i>"
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

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_radio_group(self, title: str, options: list, attr: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(_SECTION_STYLE)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(4)
        fl.addWidget(QLabel(title))

        group = QButtonGroup(frame)
        group.setExclusive(True)
        for i, (label, desc) in enumerate(options):
            row = QHBoxLayout()
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            group.addButton(rb)
            row.addWidget(rb)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #6c757d; font-size: 11px;")
            row.addWidget(desc_lbl)
            row.addStretch()
            fl.addLayout(row)

        setattr(self, attr, group)
        return frame

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Key pair name is required.")
            return
        QMessageBox.information(
            self,
            "Key Pair Queued",
            f"Key pair <b>{name}</b> will be created when launch is executed.\n\n"
            "AWS wiring is pending; your chosen name has been captured.",
        )
        self.accept()
