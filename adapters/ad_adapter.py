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

from core.models import OrgUnit

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
            "ldap3 is required for AD queries.  Install it: pip install ldap3"
        ) from exc

    base_dn = "DC=" + ",DC=".join(domain.split("."))
    logger.debug("LDAP connect: host=%s base_dn=%s user=%s", dc_host, base_dn, username)

    server = Server(dc_host, get_info=ALL)
    conn = Connection(
        server,
        user=username,
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
