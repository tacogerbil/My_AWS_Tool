"""
windows_setup_section.py — Windows domain-join configuration section.

Three sub-panels:
  1. Credentials  — domain, DC host, username, password, SSM path, timezone
  2. Placement    — [Query AD] button + searchable OU/Container dropdown
  3. Computer     — AD description field + IAM instance profile

Public API (used by ConfigForm):
    get_domain_config() -> Optional[WindowsDomainConfig]
        Returns a populated WindowsDomainConfig if the section has enough
        data to perform a domain join, otherwise None.
    get_timezone() -> str
        Returns the Windows tzutil timezone ID (always non-empty).
"""

from __future__ import annotations

from typing import List, Optional, Set

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import AdPrincipal, OrgUnit
from tools.ec2_launcher.models import WindowsDomainConfig
from ui.common.widgets import SearchableComboBox

_STATUS_IDLE     = ""
_STATUS_QUERYING  = "Querying AD…"
_STATUS_OK_TPL   = "✓ {n} containers/OUs loaded"
_STATUS_ERR_TPL  = "✗ {msg}"
_STATUS_PRIN_OK  = "✓ {n} principals loaded"

_HINT_STYLE = (
    "background: #fffde7; border: 1px solid #f9a825; border-radius: 4px;"
    "padding: 4px 8px; color: #5d4037; font-size: 11px;"
)


def _policy_hint(text: str) -> QLabel:
    """Return a styled amber hint label for policy guidance."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(_HINT_STYLE)
    return lbl


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


class _AdPrincipalsQueryThread(QThread):
    """Runs query_principals_tree() off the UI thread."""

    result: Signal = Signal(list)   # List[AdPrincipal]
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
            from adapters.ad_adapter import query_principals_tree
            principals = query_principals_tree(
                self._dc_host, self._domain, self._username, self._password
            )
            self.result.emit(principals)
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
        self._principals: List[AdPrincipal] = []
        self._query_thread: Optional[_AdQueryThread] = None
        self._principals_thread: Optional[_AdPrincipalsQueryThread] = None

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self._build_credentials_group())
        outer.addWidget(self._build_placement_group())
        outer.addWidget(self._build_computer_group())
        outer.addWidget(self._build_local_admins_group())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_domain_config(self) -> Optional[WindowsDomainConfig]:
        """Return WindowsDomainConfig if domain + OU are filled, else None."""
        domain  = self._domain.text().strip()
        item    = self._ou_tree.currentItem()
        ou_dn   = item.data(0, Qt.UserRole) if item else None

        if not domain or not ou_dn:
            return None
        iam_profile_text = self._iam_profile.currentText().strip()

        return WindowsDomainConfig(
            enabled                = True,
            domain                 = domain,
            dc_host                = self._dc_host.text().strip(),
            username               = self._username.text().strip(),
            password               = self._password.text(),
            ssm_path               = self._ssm_path.text().strip() or "/domain/join",
            ou_dn                  = ou_dn,
            description            = self._description.text().strip(),
            iam_profile            = iam_profile_text if iam_profile_text else None,
            ssm_endpoint_override  = self.get_ssm_endpoint_override(),
            admin_principals       = self._get_selected_admin_principals(),
        )

    def get_timezone(self) -> str:
        """Windows tzutil timezone ID applied at first boot via UserData."""
        return self._timezone_edit.text().strip() or "Pacific Standard Time"

    def get_dns_servers(self) -> List[str]:
        """Return list of DNS server IPs from the comma-separated field.

        Empty strings and whitespace-only tokens are silently dropped.
        """
        raw = self._dns_servers.text().strip()
        if not raw:
            return []
        return [ip.strip() for ip in raw.split(",") if ip.strip()]

    def get_ssm_endpoint_override(self) -> Optional[str]:
        """Return the SSM endpoint IP override, or None if the field is blank."""
        val = self._ssm_endpoint_override.text().strip()
        return val if val else None

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
        from ui.common.ui_prefs import get_pref, set_pref
    
        box = QGroupBox("Credentials")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        self._domain   = QLineEdit(get_pref("win_domain", "")); self._domain.setPlaceholderText("corp.example.com")
        self._dc_host  = QLineEdit(get_pref("win_dchost", "")); self._dc_host.setPlaceholderText("dc01.corp.example.com")
        self._username = QLineEdit(get_pref("win_user", "")); self._username.setPlaceholderText("CORP\\svc-domain-join")
        self._password = QLineEdit(); self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("stored to SSM at launch — never written to disk")

        self._ssm_path = QLineEdit(get_pref("win_ssm", "/domain/join"))
        self._ssm_path.setToolTip(
            "SSM Parameter Store path prefix.\n"
            "Credentials are stored as:\n"
            "  {path}/username  (SecureString)\n"
            "  {path}/password  (SecureString)\n"
            "Encrypted at rest by KMS.  Access controlled by IAM."
        )

        self._dns_servers = QLineEdit(get_pref("win_dns", ""))
        self._dns_servers.setPlaceholderText("10.0.0.2, 10.0.0.3  (comma-separated, blank = DHCP default)")
        self._dns_servers.setToolTip(
            "DNS server IPs applied via Set-DnsClientServerAddress at first boot.\n"
            "Applied before domain join. Leave blank to keep DHCP-assigned DNS.\n"
            "Example: 10.0.0.2, 10.0.0.3"
        )
        self._dns_servers.textChanged.connect(lambda t: set_pref("win_dns", t))

        self._ssm_endpoint_override = QLineEdit(get_pref("win_ssm_ip", ""))
        self._ssm_endpoint_override.setPlaceholderText("18.246.120.242  (blank = let AWS resolve via DNS)")
        self._ssm_endpoint_override.setToolTip(
            "Pin SSM traffic to a specific IP instead of using DNS resolution.\n"
            "Useful when AWS routes SSM to an unreachable VPC endpoint IP.\n"
            "Fill in the IP that successfully passes Test-NetConnection on port 443.\n"
            "Leave blank for normal DNS-based routing."
        )
        self._ssm_endpoint_override.textChanged.connect(lambda t: set_pref("win_ssm_ip", t))

        self._timezone_edit = QLineEdit(get_pref("win_timezone", "Pacific Standard Time"))
        self._timezone_edit.setPlaceholderText("e.g. Pacific Standard Time")
        self._timezone_edit.setToolTip(
            "Windows timezone identifier applied via 'tzutil /s' on first boot.\n"
            "Examples: Pacific Standard Time, Eastern Standard Time, UTC\n"
            "Run 'tzutil /l' on any Windows machine for a full list."
        )
        self._timezone_edit.textChanged.connect(lambda t: set_pref("win_timezone", t))

        self._domain.textChanged.connect(lambda t: set_pref("win_domain", t))
        self._dc_host.textChanged.connect(lambda t: set_pref("win_dchost", t))
        self._username.textChanged.connect(lambda t: set_pref("win_user", t))
        self._ssm_path.textChanged.connect(lambda t: set_pref("win_ssm", t))

        for label, widget in [
            ("Domain:", self._domain),
            ("DC Host:", self._dc_host),
            ("Username:", self._username),
            ("Password:", self._password),
            ("SSM Path:", self._ssm_path),
            ("DNS Servers:", self._dns_servers),
        ]:
            form.addRow(label, widget)

        form.addRow("", _policy_hint(
            "⚠  Policy: DNS servers must point to the Domain Controllers, not AWS-provided DNS. "
            "AWS DNS (169.254.169.253) cannot resolve internal domain names."
        ))

        form.addRow("SSM Endpoint IP:", self._ssm_endpoint_override)
        form.addRow("Timezone:", self._timezone_edit)
        form.addRow("", _policy_hint(
            "⚠  Policy: All servers must use Pacific Standard Time."
        ))

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

        self._ou_search = QLineEdit()
        self._ou_search.setPlaceholderText("Filter OUs...")
        self._ou_search.textChanged.connect(self._on_ou_filter_changed)
        layout.addWidget(self._ou_search)

        self._ou_tree = QTreeWidget()
        self._ou_tree.setHeaderHidden(True)
        self._ou_tree.setMinimumHeight(200)
        self._ou_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #ced4da; border-radius: 4px; padding: 4px; }"
        )
        layout.addWidget(self._ou_tree)

        return box

    def _build_computer_group(self) -> QGroupBox:
        from ui.common.ui_prefs import get_pref, set_pref

        box = QGroupBox("Computer Object")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        self._description = QLineEdit(get_pref("win_desc", ""))
        self._description.setPlaceholderText(
            "Same description applied to all instances in this launch session"
        )
        self._description.textChanged.connect(lambda t: set_pref("win_desc", t))

        self._iam_profile = SearchableComboBox()
        self._iam_profile.setMinimumWidth(280)
        self._iam_profile.lineEdit().setPlaceholderText(
            "— select name, paste ARN, or leave blank —"
        )
        self._iam_profile.setToolTip(
            "Optional: The permission profile that allows this instance to read its\n"
            "domain credentials from secure storage on first boot.\n\n"
            "If your profile isn't listed, you can paste its full ARN here.\n"
            "If left blank, the instance will not perform an automated domain join."
        )

        form.addRow("Description:", self._description)
        form.addRow("Permission Profile:", self._iam_profile)
        return box

    def _build_local_admins_group(self) -> QGroupBox:
        """Build the Local Administrators picker panel.

        Mirrors the OU Placement panel:
        - [Query AD Principals] button + status label
        - Filter text box (real-time recursive tree filter)
        - QTreeWidget: OU/container folder nodes (non-checkable) + user/group
          leaf nodes (checkable via checkbox)
        - Selected principals QListWidget (read-only mirror of checked items)
        """
        box = QGroupBox("Local Administrators")
        layout = QVBoxLayout(box)

        # -- Query row --
        query_row = QHBoxLayout()
        self._principals_btn = QPushButton("Query AD Principals")
        self._principals_btn.setFixedWidth(170)
        self._principals_btn.clicked.connect(self._on_query_principals)
        self._principals_status_lbl = QLabel(_STATUS_IDLE)
        self._principals_status_lbl.setStyleSheet("color: #555; font-size: 11px;")
        query_row.addWidget(self._principals_btn)
        query_row.addWidget(self._principals_status_lbl)
        query_row.addStretch()
        layout.addLayout(query_row)

        layout.addWidget(QLabel(
            "Uses the Domain / DC Host / Username / Password already filled in above."
        ))

        # -- Filter box --
        self._principals_search = QLineEdit()
        self._principals_search.setPlaceholderText("Filter users/groups…")
        self._principals_search.textChanged.connect(self._on_principals_filter_changed)
        layout.addWidget(self._principals_search)

        # -- Principals tree --
        self._principals_tree = QTreeWidget()
        self._principals_tree.setHeaderHidden(True)
        self._principals_tree.setMinimumHeight(220)
        self._principals_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #ced4da; border-radius: 4px; padding: 4px; }"
        )
        # itemChanged fires when a checkbox is toggled
        self._principals_tree.itemChanged.connect(self._on_principal_checked)
        layout.addWidget(self._principals_tree)

        # -- Selected principals list --
        layout.addWidget(QLabel("Selected principals:"))
        self._selected_principals_list = QListWidget()
        self._selected_principals_list.setMaximumHeight(110)
        self._selected_principals_list.setStyleSheet(
            "QListWidget {"
            "  border: 1px solid #ced4da;"
            "  border-radius: 4px;"
            "  padding: 4px;"
            "  background: #f8f9fa;"
            "}"
        )
        layout.addWidget(self._selected_principals_list)

        return box

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_query(self) -> None:
        """Validate inputs then kick off the background LDAP query for OUs."""
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
        self._ou_tree.clear()
        
        nodes: dict[str, QTreeWidgetItem] = {}
        
        for ou in ous:
            dn = ou.distinguished_name
            # AD paths are like "OU=Child,OU=Parent,DC=corp,DC=local"
            # Parent DN is everything after the first comma
            idx = dn.find(",")
            parent_dn = dn[idx+1:] if idx != -1 else ""
            
            icon  = "📁" if ou.object_class == "container" else "🗂"
            label = f"{icon} {ou.name}"
            
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, dn)
            
            parent_item = nodes.get(parent_dn.upper())
            if parent_item:
                parent_item.addChild(item)
            else:
                self._ou_tree.addTopLevelItem(item)
                
            nodes[dn.upper()] = item

        self._ou_tree.expandAll()
        self._status_lbl.setText(_STATUS_OK_TPL.format(n=len(ous)))

    def _on_ou_filter_changed(self, text: str) -> None:
        text = text.lower()
        
        def filter_node(item: QTreeWidgetItem) -> bool:
            matches = text in item.text(0).lower()
            any_child_visible = False
            for i in range(item.childCount()):
                child = item.child(i)
                if filter_node(child):
                    any_child_visible = True
                    
            visible = matches or any_child_visible
            item.setHidden(not visible)
            
            if text and any_child_visible:
                item.setExpanded(True)
                
            return visible

        for i in range(self._ou_tree.topLevelItemCount()):
            filter_node(self._ou_tree.topLevelItem(i))

    def _on_query_error(self, msg: str) -> None:
        self._status_lbl.setText(_STATUS_ERR_TPL.format(msg=msg))

    # ------------------------------------------------------------------
    # Slots — principals tree
    # ------------------------------------------------------------------

    def _on_query_principals(self) -> None:
        """Validate inputs then kick off the background LDAP principals query."""
        domain   = self._domain.text().strip()
        dc_host  = self._dc_host.text().strip()
        username = self._username.text().strip()
        password = self._password.text()

        missing = [f for f, v in [
            ("Domain", domain), ("DC Host", dc_host),
            ("Username", username), ("Password", password),
        ] if not v]
        if missing:
            self._principals_status_lbl.setText(
                _STATUS_ERR_TPL.format(msg=f"Fill in above: {', '.join(missing)}")
            )
            return

        self._principals_btn.setEnabled(False)
        self._principals_status_lbl.setText(_STATUS_QUERYING)

        self._principals_thread = _AdPrincipalsQueryThread(
            dc_host, domain, username, password, self
        )
        self._principals_thread.result.connect(self._on_principals_result)
        self._principals_thread.error.connect(self._on_principals_error)
        self._principals_thread.finished.connect(
            lambda: self._principals_btn.setEnabled(True)
        )
        self._principals_thread.start()

    def _on_principals_result(self, principals: List[AdPrincipal]) -> None:
        """Populate the principals tree with folder nodes (OUs) and leaf nodes."""
        self._principals = principals
        # Block signals during bulk population to avoid per-item _on_principal_checked
        self._principals_tree.blockSignals(True)
        self._principals_tree.clear()

        folder_nodes: dict[str, QTreeWidgetItem] = {}  # keyed by ou_dn.upper()

        # Collect every unique ancestor OU DN needed to build the folder skeleton.
        # Walk up each principal's ou_dn until we hit the DC= root.
        all_ou_dns: set[str] = set()
        for p in principals:
            dn = p.ou_dn
            while dn and not dn.upper().startswith("DC="):
                all_ou_dns.add(dn)
                idx = dn.find(",")
                if idx == -1:
                    break
                dn = dn[idx + 1:]

        # Sort shallower OUs first so parents exist before their children.
        def _ou_depth(dn: str) -> int:
            return dn.upper().count("OU=") + dn.upper().count("CN=")

        for ou_dn in sorted(all_ou_dns, key=_ou_depth):
            first_rdn = ou_dn.split(",")[0]
            name = first_rdn.split("=", 1)[1] if "=" in first_rdn else first_rdn

            parent_dn_raw = ou_dn[ou_dn.find(",") + 1:] if "," in ou_dn else ""

            folder_item = QTreeWidgetItem([f"📁 {name}"])
            # Folder nodes: navigational only — not checkable, not selectable
            folder_item.setFlags(Qt.ItemIsEnabled)
            folder_item.setData(0, Qt.UserRole, None)

            parent_item = folder_nodes.get(parent_dn_raw.upper())
            if parent_item:
                parent_item.addChild(folder_item)
            else:
                self._principals_tree.addTopLevelItem(folder_item)

            folder_nodes[ou_dn.upper()] = folder_item

        # Add user/group leaf nodes under their parent folder
        for p in principals:
            icon  = "👥" if p.principal_type == "group" else "👤"
            label = f"{icon} {p.display_name}"

            leaf = QTreeWidgetItem([label])
            leaf.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            leaf.setCheckState(0, Qt.Unchecked)
            leaf.setData(0, Qt.UserRole, p.sam_account_name)

            parent_item = folder_nodes.get(p.ou_dn.upper())
            if parent_item:
                parent_item.addChild(leaf)
            else:
                # Fallback: principal lives directly under domain root
                self._principals_tree.addTopLevelItem(leaf)

        self._principals_tree.expandAll()
        self._principals_tree.blockSignals(False)
        self._principals_status_lbl.setText(_STATUS_PRIN_OK.format(n=len(principals)))

    def _on_principals_filter_changed(self, text: str) -> None:
        """Recursively show/hide tree nodes based on partial text match."""
        text = text.lower()

        def _filter_node(item: QTreeWidgetItem) -> bool:
            matches = text in item.text(0).lower()
            any_child_visible = False
            for i in range(item.childCount()):
                if _filter_node(item.child(i)):
                    any_child_visible = True
            visible = matches or any_child_visible
            item.setHidden(not visible)
            if text and any_child_visible:
                item.setExpanded(True)
            return visible

        for i in range(self._principals_tree.topLevelItemCount()):
            _filter_node(self._principals_tree.topLevelItem(i))

    def _on_principal_checked(self, _item: QTreeWidgetItem, _column: int) -> None:
        """Rebuild the selected-principals list whenever a checkbox toggles."""
        self._rebuild_selected_list()

    def _on_principals_error(self, msg: str) -> None:
        self._principals_status_lbl.setText(_STATUS_ERR_TPL.format(msg=msg))

    def _rebuild_selected_list(self) -> None:
        """Repopulate the selected-principals QListWidget from checked leaf nodes."""
        self._selected_principals_list.clear()
        for sam, display in self._collect_checked_leaves(
            self._principals_tree.invisibleRootItem()
        ):
            self._selected_principals_list.addItem(f"{display}   ({sam})")

    def _collect_checked_leaves(
        self, parent: QTreeWidgetItem
    ) -> List[tuple[str, str]]:
        """Return (sam_account_name, display_text) for every checked leaf node."""
        results: List[tuple[str, str]] = []
        for i in range(parent.childCount()):
            child = parent.child(i)
            sam = child.data(0, Qt.UserRole)
            if sam is not None and child.checkState(0) == Qt.Checked:
                results.append((sam, child.text(0)))
            results.extend(self._collect_checked_leaves(child))
        return results

    def _get_selected_admin_principals(self) -> List[str]:
        """Return sAMAccountNames of all checked principals."""
        return [
            sam
            for sam, _ in self._collect_checked_leaves(
                self._principals_tree.invisibleRootItem()
            )
        ]
