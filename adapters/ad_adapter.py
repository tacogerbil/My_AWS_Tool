"""
ad_adapter.py — LDAP adapter for querying Active Directory OUs and Containers.

Single responsibility: connect to a domain controller via NTLM and return
a flat list of OrgUnit objects.  No UI, no AWS, no business logic.

Credentials are passed as plain strings but are never written to disk —
callers hold them in memory only and should discard them promptly.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, List, Optional, Tuple

from core.models import AdPrincipal, OrgUnit

logger = logging.getLogger(__name__)


@contextmanager
def _ldap_connect(
    dc_host: str,
    domain: str,
    username: str,
    password: str,
) -> Generator[Tuple[object, str], None, None]:
    """Context manager: open an NTLM-authenticated LDAP connection and yield (conn, base_dn).

    Guarantees ``conn.unbind()`` on exit regardless of success or failure.

    Raises
    ------
    RuntimeError  if ldap3 is not installed.
    Exception     on connection or authentication failure (caller handles display).
    """
    try:
        from ldap3 import ALL, NTLM, Connection, Server
    except ImportError as exc:
        raise RuntimeError(
            "ldap3 is required for AD queries. Install it: pip install ldap3"
        ) from exc

    import hashlib
    try:
        hashlib.new("md4", b"")
    except ValueError:
        # Python 3.10+ / OpenSSL 3.0+ disables MD4 completely, which breaks NTLM.
        # We monkeypatch hashlib.new to use pycryptodome's MD4 fallback instead.
        try:
            from Crypto.Hash import MD4

            _orig_new = hashlib.new

            def _hashlib_new_patch(name, data=b""):
                if name.lower() == "md4":
                    return MD4.new(data)
                return _orig_new(name, data)

            hashlib.new = _hashlib_new_patch
        except ImportError as exc:
            raise RuntimeError(
                "Your Python version's OpenSSL lacks MD4, which is strictly required "
                "for NTLM authentication to Active Directory.\n\n"
                "Please run:  pip install pycryptodome\n\n"
                "This will provide a pure-Python fallback automatically."
            ) from exc

    base_dn = "DC=" + ",DC=".join(domain.split("."))
    logger.debug("LDAP connect: host=%s base_dn=%s user=%s", dc_host, base_dn, username)

    # ldap3 NTLM strictly requires the DOMAIN\\username format.
    # If the user just typed "svc-launcher", we prepend the domain automatically.
    if "\\" not in username and "@" not in username:
        # Extract the short NETBIOS domain (e.g. "corp" from "corp.example.com")
        short_domain = domain.split(".")[0].upper()
        formatted_username = f"{short_domain}\\{username}"
    else:
        formatted_username = username

    server = Server(dc_host, port=636, use_ssl=True, get_info=ALL, connect_timeout=5)
    conn = Connection(
        server,
        user=formatted_username,
        password=password,
        authentication=NTLM,
        auto_bind=True,   # raises LDAPBindError on auth failure
    )
    try:
        yield conn, base_dn
    finally:
        conn.unbind()


def query_org_units(
    dc_host: str,
    domain: str,
    username: str,
    password: str,
) -> List[OrgUnit]:
    """Query all OUs and Containers from an AD domain controller via LDAP/NTLM.

    Parameters
    ----------
    dc_host:  Hostname or IP of a domain controller (e.g. "dc01.corp.example.com").
    domain:   FQDN of the domain (e.g. "corp.example.com").
    username: DOMAIN\\user or UPN format (e.g. "CORP\\svc-launcher").
    password: Caller is responsible for clearing from memory after use.

    Returns
    -------
    Flat list of OrgUnit sorted by depth then name.

    Raises
    ------
    RuntimeError   if ldap3 is not installed.
    Exception      on connection or authentication failure (caller handles display).
    """
    try:
        from ldap3 import SUBTREE
    except ImportError as exc:
        raise RuntimeError(
            "ldap3 is required for AD queries.  Install it: pip install ldap3"
        ) from exc

    with _ldap_connect(dc_host, domain, username, password) as (conn, base_dn):
        conn.search(
            search_base=base_dn,
            search_filter="(|(objectClass=organizationalUnit)(objectClass=container))",
            search_scope=SUBTREE,
            attributes=["distinguishedName", "name", "objectClass"],
        )

        results: List[OrgUnit] = []
        for entry in conn.entries:
            dn = str(entry.distinguishedName)
            name = str(entry.name)
            classes = [c.lower() for c in entry.objectClass]
            obj_class = "container" if "container" in classes else "organizationalUnit"
            depth = _dn_depth(dn)
            results.append(OrgUnit(
                name=name,
                distinguished_name=dn,
                object_class=obj_class,
                depth=depth,
            ))

    logger.info("AD query returned %d OUs/Containers", len(results))
    return sorted(results, key=lambda o: (o.depth, o.name.lower()))


def query_principals_tree(
    dc_host: str,
    domain: str,
    username: str,
    password: str,
) -> List[AdPrincipal]:
    """Query all user and group objects from AD for local-Administrators assignment.

    Returns a flat list of AdPrincipal objects sorted groups-first then alphabetically.
    The UI builds the directory tree by grouping principals by their ou_dn.
    Computer accounts are excluded; only human users and security groups are returned.

    Parameters
    ----------
    dc_host:  Hostname or IP of a domain controller.
    domain:   FQDN of the domain (e.g. "corp.example.com").
    username: DOMAIN\\user or UPN format.
    password: In-memory only; never written to disk.

    Returns
    -------
    Flat list of AdPrincipal sorted by type (groups first) then display name.

    Raises
    ------
    RuntimeError  if ldap3 is not installed.
    Exception     on connection or authentication failure (caller handles display).
    """
    try:
        from ldap3 import SUBTREE
    except ImportError as exc:
        raise RuntimeError(
            "ldap3 is required for AD queries.  Install it: pip install ldap3"
        ) from exc

    # Exclude computer objects: they inherit objectClass=user in the AD schema
    # but are not human accounts and should not appear in the principals picker.
    search_filter = "(&(|(objectClass=group)(objectClass=user))(!(objectClass=computer)))"

    with _ldap_connect(dc_host, domain, username, password) as (conn, base_dn):
        conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "cn", "objectClass", "distinguishedName"],
        )

        results: List[AdPrincipal] = []
        for entry in conn.entries:
            dn        = str(entry.distinguishedName)
            sam       = str(entry.sAMAccountName) if entry.sAMAccountName else ""
            display   = str(entry.cn)             if entry.cn             else sam
            classes   = [c.lower() for c in entry.objectClass]

            # Skip entries with no sAMAccountName (e.g. built-in pseudo-objects)
            if not sam or sam.lower() == "none":
                continue

            principal_type = "group" if "group" in classes else "user"

            # Derive parent OU/Container DN by stripping the first RDN component
            idx    = dn.find(",")
            ou_dn  = dn[idx + 1:] if idx != -1 else base_dn

            results.append(AdPrincipal(
                sam_account_name=sam,
                display_name=display,
                principal_type=principal_type,
                ou_dn=ou_dn,
            ))

    logger.info("AD principals query returned %d users/groups", len(results))
    # Groups first (easier to find security groups at top), then users, both alphabetical
    return sorted(results, key=lambda p: (0 if p.principal_type == "group" else 1, p.display_name.lower()))


def check_computer_exists(
    dc_host: str,
    domain: str,
    username: str,
    password: str,
    computer_name: str,
) -> Optional[str]:
    """Return the existing DN if a computer account named ``computer_name`` already
    exists in AD, or ``None`` if the name is available.

    Uses the AD convention for computer accounts: ``sAMAccountName=<name>$``.

    Parameters
    ----------
    dc_host:       Hostname or IP of a domain controller.
    domain:        FQDN of the domain (e.g. "corp.example.com").
    username:      DOMAIN\\user or UPN format.
    password:      In-memory only; never written to disk.
    computer_name: Desired NetBIOS name (without trailing ``$``).

    Returns
    -------
    ``str`` — the distinguishedName of the existing account, or ``None`` if free.

    Raises
    ------
    RuntimeError  if ldap3 is not installed.
    Exception     on connection or authentication failure (caller handles display).
    """
    try:
        from ldap3 import SUBTREE
    except ImportError as exc:
        raise RuntimeError(
            "ldap3 is required for AD queries.  Install it: pip install ldap3"
        ) from exc

    sam = f"{computer_name}$"
    search_filter = f"(&(objectClass=computer)(sAMAccountName={sam}))"
    logger.debug("AD computer check: host=%s filter=%s", dc_host, search_filter)

    with _ldap_connect(dc_host, domain, username, password) as (conn, base_dn):
        conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
        )
        if conn.entries:
            dn = str(conn.entries[0].distinguishedName)
            logger.info("Computer '%s' already exists in AD at: %s", computer_name, dn)
            return dn

    logger.debug("Computer '%s' is available (not found in AD).", computer_name)
    return None


def _dn_depth(dn: str) -> int:
    """Count OU= and CN= components before the first DC= component."""
    dc_idx = dn.upper().find(",DC=")
    prefix = dn[:dc_idx] if dc_idx >= 0 else dn
    return max(0, prefix.upper().count("OU=") + prefix.upper().count("CN=") - 1)
