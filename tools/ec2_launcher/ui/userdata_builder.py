"""
userdata_builder.py — Pure function: WindowsDomainConfig → PowerShell UserData.

No side effects.  No I/O.  No Qt.  Unit-testable in isolation.

The returned string is a UserData template containing the marker
<<INSTANCE_NAME>> wherever the concrete computer name should go.
Callers replace this marker with the actual name just before calling
run_instances (one replacement per instance).

Two-phase approach
------------------
Phase 1 (first boot via UserData):
  - Sets timezone via tzutil.
  - Configures DNS servers via Set-DnsClientServerAddress (if provided).
  - Retrieves domain credentials from SSM Parameter Store (never embedded).
  - Runs AD pre-check: blocks if the computer name already exists.
  - Registers a one-shot scheduled task for Phase 2.
  - Calls Add-Computer -NewName <<INSTANCE_NAME>> -OUPath ... → reboot.
  - Tags the EC2 instance with timestamped status at each milestone.

Phase 2 (next boot, SYSTEM scheduled task):
  - Sets the AD computer object Description via Set-ADComputer.
  - Tags the instance with completion status.
  - Self-destructs (Unregister-ScheduledTask).

Phase 2 script is base64-encoded inside Phase 1 to avoid all
PowerShell quoting / escaping issues.
"""

from __future__ import annotations

import base64
from typing import List, Optional

from tools.ec2_launcher.models import WindowsDomainConfig

# Marker replaced by the adapter with the concrete instance name
INSTANCE_NAME_MARKER = "<<INSTANCE_NAME>>"

# Tag key used for domain join progress visible in EC2 console and the monitor
DOMAIN_JOIN_TAG_KEY = "DomainJoinStatus"


def build_windows_userdata(
    cfg: WindowsDomainConfig,
    timezone: str = "Pacific Standard Time",
    dns_servers: Optional[List[str]] = None,
) -> str:
    """Return a PowerShell UserData template, or '' if domain join is disabled.

    Parameters
    ----------
    cfg:         Windows domain-join configuration.
    timezone:    Windows timezone identifier passed to tzutil (e.g. 'Pacific Standard Time').
    dns_servers: Optional list of DNS server IPs applied via Set-DnsClientServerAddress.
    """
    if not cfg.enabled or not cfg.domain or not cfg.ou_dn:
        return ""

    dns_servers = dns_servers or []
    ssm_user = f"{cfg.ssm_path}/username"
    ssm_pass = f"{cfg.ssm_path}/password"
    endpoint_arg = (
        f' -EndpointUrl "https://{cfg.ssm_endpoint_override}"'
        if cfg.ssm_endpoint_override
        else ""
    )

    admin_principals = list(cfg.admin_principals or [])
    needs_phase2 = bool(cfg.description or admin_principals)
    phase2 = (
        _build_phase2(ssm_user, ssm_pass, cfg.description, admin_principals, endpoint_arg)
        if needs_phase2
        else ""
    )

    lines = _build_phase1(
        domain=cfg.domain,
        dc_host=cfg.dc_host,
        ou_dn=cfg.ou_dn,
        ssm_user=ssm_user,
        ssm_pass=ssm_pass,
        phase2_b64=phase2,
        timezone=timezone,
        dns_servers=dns_servers,
        endpoint_arg=endpoint_arg,
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _tag_line(value_template: str) -> str:
    """Return a PowerShell block that tags the instance with a timestamped status.

    Uses IMDSv2 to obtain the instance ID and region from within the instance.
    If tagging fails it logs and continues — never fatal.
    """
    safe_value = _escape_ps_dq(value_template)
    return (
        f'    _Set-InstanceTag "{DOMAIN_JOIN_TAG_KEY}" "$(Get-Date -Format \'HH:mm:ss\') \u2014 {safe_value}"'
    )


def _build_tag_helper() -> List[str]:
    """Return the _Set-InstanceTag helper function definition lines."""
    return [
        "function _Set-InstanceTag {",
        "    param([string]$Key, [string]$Value)",
        "    try {",
        "        $token  = (Invoke-WebRequest -UseBasicParsing -Method PUT \\",
        '                     -Uri "http://169.254.169.254/latest/api/token" \\',
        '                     -Headers @{"X-aws-ec2-metadata-token-ttl-seconds"="60"}).Content',
        '        $iid    = (Invoke-WebRequest -UseBasicParsing -Uri "http://169.254.169.254/latest/meta-data/instance-id" \\',
        '                     -Headers @{"X-aws-ec2-metadata-token"=$token}).Content',
        '        $region = (Invoke-WebRequest -UseBasicParsing -Uri "http://169.254.169.254/latest/meta-data/placement/region" \\',
        '                     -Headers @{"X-aws-ec2-metadata-token"=$token}).Content',
        "        New-EC2Tag -Region $region -Resource $iid -Tag @{Key=$Key; Value=$Value} -ErrorAction Stop",
        "    } catch {",
        '        Write-Log "  [TAG WARN] Could not set tag \'$Key\': $_"',
        "    }",
        "}",
        "",
    ]


def _build_phase2(
    ssm_user: str,
    ssm_pass: str,
    description: str,
    admin_principals: List[str],
    endpoint_arg: str,
) -> str:
    """Base64-encode the Phase 2 script so it embeds safely in Phase 1.

    Runs as SYSTEM via a scheduled task on the second boot (post domain join).

    - description:       If non-empty, fetches SSM creds and runs Set-ADComputer.
    - admin_principals:  If non-empty, calls Add-LocalGroupMember for each entry.
                         No domain credentials needed — SYSTEM on a domain-joined
                         machine can add to local groups directly.
    """
    tag_done = (
        f'_Set-InstanceTag "{DOMAIN_JOIN_TAG_KEY}" '
        f'"$(Get-Date -Format \'HH:mm:ss\') \u2014 Complete"'
    )

    script_lines: List[str] = [
        "Import-Module ActiveDirectory -ErrorAction SilentlyContinue",
    ]

    # SSM credential fetch + AD description — only when a description is configured
    if description:
        safe_desc = _escape_ps_dq(description)
        script_lines += [
            f'$u = (Get-SSMParameter -Name "{ssm_user}" -WithDecryption $true{endpoint_arg}).Value',
            f'$p = (Get-SSMParameter -Name "{ssm_pass}" -WithDecryption $true{endpoint_arg}).Value `',
            "      | ConvertTo-SecureString -AsPlainText -Force",
            "$c = New-Object System.Management.Automation.PSCredential($u, $p)",
            f'Set-ADComputer -Identity $env:COMPUTERNAME -Description "{safe_desc}" -Credential $c',
        ]

    # Local-Administrators assignment — no domain creds needed (runs as SYSTEM)
    if admin_principals:
        script_lines += _build_admin_principals_block(admin_principals)

    script_lines += [
        tag_done,
        'Unregister-ScheduledTask -TaskName "LauncherPhase2" -Confirm:$false',
    ]

    raw = "\n".join(script_lines).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _build_phase1(
    domain: str,
    dc_host: str,
    ou_dn: str,
    ssm_user: str,
    ssm_pass: str,
    phase2_b64: str,
    timezone: str,
    dns_servers: List[str],
    endpoint_arg: str,
) -> list:
    """Return Phase 1 script lines (list avoids f-string brace conflicts with PS)."""
    safe_dc = _escape_ps_dq(dc_host)
    log_path = r"C:\tmp\EC2_creation\ec2.log"

    lines = [
        "<powershell>",
        "$ErrorActionPreference = 'Stop'",
        "",
        "# Ensure log directory exists",
        r"New-Item -ItemType Directory -Force -Path 'C:\tmp\EC2_creation' | Out-Null",
        "",
        "function Write-Log {",
        "    param([string]$Msg)",
        "    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
        f'    "$ts  $Msg" | Out-File -Append "{log_path}"',
        "    Write-Host $Msg",
        "}",
        "",
    ]

    # Inject the EC2 tagging helper
    lines += _build_tag_helper()

    lines += [
        "try {",
        f'    Write-Log "Phase 1 start \u2014 computer: {INSTANCE_NAME_MARKER}  domain: {domain}"',
        _tag_line("Phase1: Started"),
        "",
    ]

    # Timezone
    safe_tz = _escape_ps_dq(timezone)
    lines += [
        f'    Write-Log "Setting timezone to: {safe_tz}"',
        f'    tzutil /s "{safe_tz}"',
        _tag_line(f"Phase1: Timezone set ({safe_tz})"),
        "",
    ]

    # DNS servers
    if dns_servers:
        dns_csv = ", ".join(f'"{ip}"' for ip in dns_servers)
        lines += [
            f'    Write-Log "Configuring DNS servers: {", ".join(dns_servers)}"',
            f"    Set-DnsClientServerAddress -InterfaceAlias 'Ethernet*' -ServerAddresses ({dns_csv})",
            _tag_line(f"Phase1: DNS set ({', '.join(dns_servers)})"),
            "",
        ]

    # SSM credentials
    lines += [
        "    # Retrieve credentials from SSM Parameter Store (never stored on disk)",
        f'    $u = (Get-SSMParameter -Name "{ssm_user}" -WithDecryption $true{endpoint_arg}).Value',
        f'    $p = (Get-SSMParameter -Name "{ssm_pass}" -WithDecryption $true{endpoint_arg}).Value `',
        "          | ConvertTo-SecureString -AsPlainText -Force",
        "    $cred = New-Object System.Management.Automation.PSCredential($u, $p)",
        '    Write-Log "Credentials retrieved from SSM."',
        _tag_line("Phase1: Credentials retrieved"),
        "",
        "    # Layer 4: AD pre-check \u2014 hard-stop if this computer name already exists.",
        f'    $computerName = "{INSTANCE_NAME_MARKER}"',
        "    $plainPass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(",
        "        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($p))",
        f'    $ldapRoot = New-Object System.DirectoryServices.DirectoryEntry("LDAP://{safe_dc}", $u, $plainPass)',
        "    $searcher = New-Object System.DirectoryServices.DirectorySearcher($ldapRoot)",
        '    $searcher.Filter = "(&(objectClass=computer)(sAMAccountName=${computerName}$))"',
        "    $searcher.SearchScope = [System.DirectoryServices.SearchScope]::Subtree",
        "    $existing = $searcher.FindOne()",
        "    $plainPass = $null; [System.GC]::Collect()   # zero plain-text password immediately",
        "    if ($existing -ne $null) {",
        '        $existingDN = $existing.Properties["distinguishedname"][0]',
        '        Write-Log "LAUNCH BLOCKED: \'$computerName\' already exists in AD at: $existingDN"',
        '        Write-Log "Will not overwrite an existing computer account. Halting."',
        _tag_line("ERROR: Computer name already exists in AD"),
        "        exit 1",
        "    }",
        '    Write-Log "AD pre-check passed: \'$computerName\' is available."',
        _tag_line("Phase1: AD pre-check passed"),
        "",
    ]

    if phase2_b64:
        lines += [
            "    # Decode and write Phase 2 script (sets AD Description after reboot)",
            f'    $b64 = "{phase2_b64}"',
            "    [System.Text.Encoding]::UTF8.GetString(",
            "        [System.Convert]::FromBase64String($b64)",
            '    ) | Out-File "C:\\Windows\\Temp\\phase2.ps1" -Encoding UTF8',
            '    $act = New-ScheduledTaskAction -Execute "powershell.exe" `',
            '               -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\\Windows\\Temp\\phase2.ps1"',
            "    $trg = New-ScheduledTaskTrigger -AtStartup",
            '    Register-ScheduledTask -TaskName "LauncherPhase2" `',
            "        -Action $act -Trigger $trg -RunLevel Highest -User SYSTEM -Force",
            '    Write-Log "Phase 2 description task registered."',
            _tag_line("Phase1: Phase2 task scheduled"),
            "",
        ]

    lines += [
        "    # Rename computer + join domain \u2014 triggers automatic reboot",
        _tag_line("Phase1: Joining domain\u2026"),
        "    Add-Computer `",
        f'        -DomainName "{domain}" `',
        f'        -NewName    "{INSTANCE_NAME_MARKER}" `',
        f'        -OUPath     "{ou_dn}" `',
        "        -Credential $cred `",
        "        -Restart `",
        "        -Force",
        '    Write-Log "Add-Computer issued \u2014 reboot imminent."',
        "}",
        "catch {",
        '    Write-Log "ERROR in Phase 1: $_"',
        f'    _Set-InstanceTag "{DOMAIN_JOIN_TAG_KEY}" "$(Get-Date -Format \'HH:mm:ss\') \u2014 ERROR: $($_.ToString().Substring(0, [Math]::Min(100,$_.ToString().Length)))"',
        "    # Instance stays up so the error log can be reviewed via SSM Session Manager",
        "}",
        "</powershell>",
    ]
    return lines


def _escape_ps_dq(text: str) -> str:
    """Escape text for safe embedding inside a PowerShell double-quoted string."""
    return text.replace("`", "``").replace('"', '`"').replace("$", "`$")


def _build_admin_principals_block(principals: List[str]) -> List[str]:
    """Return PowerShell lines that add each AD principal to local Administrators.

    Each Add-LocalGroupMember call is wrapped in its own try/catch so a bad
    principal name (typo, deleted account) is non-fatal: it logs a warning and
    continues.  The domain short-name is derived at runtime from $env:USERDOMAIN
    so the script stays portable across domains.

    No SSM credentials are needed — SYSTEM can modify local groups directly on
    any domain-joined Windows machine.
    """
    lines: List[str] = [
        "",
        "# Add selected AD principals to local Administrators",
        "$_domain = $env:USERDOMAIN",
    ]
    for principal in principals:
        safe = _escape_ps_dq(principal)
        lines.append(
            f'try {{ Add-LocalGroupMember -Group "Administrators"'
            f' -Member "$_domain\\{safe}" -ErrorAction Stop;'
            f' Write-Log "Added to local Admins: $_domain\\{safe}" }}'
            f' catch {{ Write-Log "  [WARN] Could not add $_domain\\{safe} to local Admins: $_" }}'
        )
    return lines
