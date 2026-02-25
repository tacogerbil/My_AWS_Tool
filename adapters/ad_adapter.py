"""
ad_adapter.py — LDAP adapter for querying Active Directory OUs and Containers.

Single responsibility: connect to a domain controller via NTLM and return
a flat list of OrgUnit objects.  No UI, no AWS, no business logic.

Credentials are passed as plain strings but are never written to disk —
callers hold them in memory only and should discard them promptly.
"""

from __future__ import annotations

import logging
from typing import List

from core.models import OrgUnit

logger = logging.getLogger(__name__)


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
        from ldap3 import ALL, NTLM, SUBTREE, Connection, Server
    except ImportError as exc:
        raise RuntimeError(
            "ldap3 is required for AD queries.  Install it: pip install ldap3"
        ) from exc

    base_dn = "DC=" + ",DC=".join(domain.split("."))
    logger.debug("AD query: host=%s base_dn=%s user=%s", dc_host, base_dn, username)

    server = Server(dc_host, get_info=ALL)
    conn = Connection(
        server,
        user=username,
        password=password,
        authentication=NTLM,
        auto_bind=True,   # raises LDAPBindError on auth failure
    )

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

    conn.unbind()
    logger.info("AD query returned %d OUs/Containers", len(results))
    return sorted(results, key=lambda o: (o.depth, o.name.lower()))


def _dn_depth(dn: str) -> int:
    """Count OU= and CN= components before the first DC= component."""
    dc_idx = dn.upper().find(",DC=")
    prefix = dn[:dc_idx] if dc_idx >= 0 else dn
    return max(0, prefix.upper().count("OU=") + prefix.upper().count("CN=") - 1)
