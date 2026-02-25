"""
windows_setup_section.py — Windows domain-join configuration section.

Three sub-panels:
  1. Credentials  — domain, DC host, username, password, SSM path
  2. Placement    — [Query AD] button + searchable OU/Container dropdown
  3. Computer     — AD description field + IAM instance profile

Public API (used by ConfigForm):
    get_domain_config() -> Optional[WindowsDomainConfig]
        Returns a populated WindowsDomainConfig if the section has enough
        data to perform a domain join, otherwise None.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import OrgUnit
from tools.ec2_launcher.models import WindowsDomainConfig
from ui.common.widgets import SearchableComboBox

_STATUS_IDLE    = ""
_STATUS_QUERYING = "Querying AD…"
_STATUS_OK_TPL  = "✓ {n} containers/OUs loaded"
_STATUS_ERR_TPL = "✗ {msg}"


# ---------------------------------------------------------------------------
# Background LDAP query thread
# ---------------------------------------------------------------------------

class _AdQueryThread(QThread):
    """Runs query_org_units() off the UI thread."""

    result: Signal = Signal(list)   # List[OrgUnit]
    error:  Signal = Signal(str)

    def __init__(
        self,
        dc_host: str,
        domain: str,
        username: str,
        password: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._dc_host  = dc_host
        self._domain   = domain
        self._username = username
        self._password = password

    def run(self) -> None:
        try:
            from adapters.ad_adapter import query_org_units
            ous = query_org_units(
                self._dc_host, self._domain, self._username, self._password
            )
            self.result.emit(ous)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# WindowsSetupSection
# ---------------------------------------------------------------------------

class WindowsSetupSection(QWidget):
    """Collapsible Windows domain-join configuration widget."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ous: List[OrgUnit] = []
        self._query_thread: Optional[_AdQueryThread] = None

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self._build_credentials_group())
        outer.addWidget(self._build_placement_group())
        outer.addWidget(self._build_computer_group())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_domain_config(self) -> Optional[WindowsDomainConfig]:
        """Return WindowsDomainConfig if domain + OU are filled, else None."""
        domain  = self._domain.text().strip()
        ou_dn   = self._ou_combo.currentData()
        if not domain or not ou_dn:
            return None
        return WindowsDomainConfig(
            enabled     = True,
            domain      = domain,
            dc_host     = self._dc_host.text().strip(),
            username    = self._username.text().strip(),
            password    = self._password.text(),
            ssm_path    = self._ssm_path.text().strip() or "/domain/join",
            ou_dn       = ou_dn,
            description = self._description.text().strip(),
            iam_profile = self._iam_profile.currentText().strip(),
        )

    def populate_profiles(self, profiles: List[str]) -> None:
        """Populate the permission profile dropdown from the account's existing profiles."""
        current = self._iam_profile.currentText().strip()
        self._iam_profile.clear()
        for name in profiles:
            self._iam_profile.addItem(name, userData=name)
        self._iam_profile.setCurrentIndex(-1)
        self._iam_profile.lineEdit().clear()
        # Restore any previously typed/selected value
        if current:
            idx = self._iam_profile.findText(current)
            if idx >= 0:
                self._iam_profile.setCurrentIndex(idx)
            else:
                self._iam_profile.setEditText(current)

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def _build_credentials_group(self) -> QGroupBox:
        box = QGroupBox("Credentials")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        self._domain   = QLineEdit(); self._domain.setPlaceholderText("corp.example.com")
        self._dc_host  = QLineEdit(); self._dc_host.setPlaceholderText("dc01.corp.example.com")
        self._username = QLineEdit(); self._username.setPlaceholderText("CORP\\svc-domain-join")
        self._password = QLineEdit(); self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("stored to SSM at launch — never written to disk")

        self._ssm_path = QLineEdit("/domain/join")
        self._ssm_path.setToolTip(
            "SSM Parameter Store path prefix.\n"
            "Credentials are stored as:\n"
            "  {path}/username  (SecureString)\n"
            "  {path}/password  (SecureString)\n"
            "Encrypted at rest by KMS.  Access controlled by IAM."
        )

        for label, widget in [
            ("Domain:", self._domain),
            ("DC Host:", self._dc_host),
            ("Username:", self._username),
            ("Password:", self._password),
            ("SSM Path:", self._ssm_path),
        ]:
            form.addRow(label, widget)

        return box

    def _build_placement_group(self) -> QGroupBox:
        box = QGroupBox("OU Placement")
        layout = QVBoxLayout(box)

        query_row = QHBoxLayout()
        self._query_btn = QPushButton("Query AD Containers")
        self._query_btn.setFixedWidth(160)
        self._query_btn.clicked.connect(self._on_query)
        self._status_lbl = QLabel(_STATUS_IDLE)
        self._status_lbl.setStyleSheet("color: #555; font-size: 11px;")
        query_row.addWidget(self._query_btn)
        query_row.addWidget(self._status_lbl)
        query_row.addStretch()
        layout.addLayout(query_row)

        self._ou_combo = SearchableComboBox()
        self._ou_combo.setMinimumWidth(400)
        self._ou_combo.setCurrentIndex(-1)
        self._ou_combo.lineEdit().setPlaceholderText("— query AD to populate —")
        layout.addWidget(self._ou_combo)

        return box

    def _build_computer_group(self) -> QGroupBox:
        box = QGroupBox("Computer Object")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        self._description = QLineEdit()
        self._description.setPlaceholderText(
            "Same description applied to all instances in this launch session"
        )

        self._iam_profile = SearchableComboBox()
        self._iam_profile.setMinimumWidth(280)
        self._iam_profile.lineEdit().setPlaceholderText(
            "— select or type a profile name —"
        )
        self._iam_profile.setToolTip(
            "The permission profile that allows this instance to read its\n"
            "domain credentials from secure storage on first boot.\n"
            "Ask your administrator for the correct profile name if unsure."
        )

        form.addRow("Description:", self._description)
        form.addRow("Permission Profile:", self._iam_profile)
        return box

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_query(self) -> None:
        """Validate inputs then kick off the background LDAP query."""
        domain   = self._domain.text().strip()
        dc_host  = self._dc_host.text().strip()
        username = self._username.text().strip()
        password = self._password.text()

        missing = [f for f, v in [
            ("Domain", domain), ("DC Host", dc_host),
            ("Username", username), ("Password", password),
        ] if not v]
        if missing:
            self._status_lbl.setText(
                _STATUS_ERR_TPL.format(msg=f"Fill in: {', '.join(missing)}")
            )
            return

        self._query_btn.setEnabled(False)
        self._status_lbl.setText(_STATUS_QUERYING)

        self._query_thread = _AdQueryThread(dc_host, domain, username, password, self)
        self._query_thread.result.connect(self._on_query_result)
        self._query_thread.error.connect(self._on_query_error)
        self._query_thread.finished.connect(lambda: self._query_btn.setEnabled(True))
        self._query_thread.start()

    def _on_query_result(self, ous: List[OrgUnit]) -> None:
        self._ous = ous
        self._ou_combo.clear()
        for ou in ous:
            indent = "  " * ou.depth
            icon   = "📁" if ou.object_class == "container" else "🗂"
            label  = f"{indent}{icon} {ou.name}"
            self._ou_combo.addItem(label, userData=ou.distinguished_name)
        self._ou_combo.setCurrentIndex(-1)
        self._ou_combo.lineEdit().clear()
        self._ou_combo.lineEdit().setPlaceholderText("— select OU / Container —")
        self._status_lbl.setText(_STATUS_OK_TPL.format(n=len(ous)))

    def _on_query_error(self, msg: str) -> None:
        self._status_lbl.setText(_STATUS_ERR_TPL.format(msg=msg))
