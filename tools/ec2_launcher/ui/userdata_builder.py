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
  - Retrieves domain credentials from SSM Parameter Store (never embedded).
  - Registers a one-shot scheduled task for Phase 2.
  - Calls Add-Computer -NewName <<INSTANCE_NAME>> -OUPath ... → reboot.

Phase 2 (next boot, SYSTEM scheduled task):
  - Sets the AD computer object Description via Set-ADComputer.
  - Self-destructs (Unregister-ScheduledTask).

Phase 2 script is base64-encoded inside Phase 1 to avoid all
PowerShell quoting / escaping issues.
"""

from __future__ import annotations

import base64

from tools.ec2_launcher.models import WindowsDomainConfig

# Marker replaced by the adapter with the concrete instance name
INSTANCE_NAME_MARKER = "<<INSTANCE_NAME>>"


def build_windows_userdata(cfg: WindowsDomainConfig) -> str:
    """Return a PowerShell UserData template, or '' if domain join is disabled."""
    if not cfg.enabled or not cfg.domain or not cfg.ou_dn:
        return ""

    ssm_user = f"{cfg.ssm_path}/username"
    ssm_pass = f"{cfg.ssm_path}/password"

    phase2 = _build_phase2(ssm_user, ssm_pass, cfg.description) if cfg.description else ""

    lines = _build_phase1(cfg.domain, cfg.dc_host, cfg.ou_dn, ssm_user, ssm_pass, phase2)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_phase2(ssm_user: str, ssm_pass: str, description: str) -> str:
    """Base64-encode the Phase 2 script so it embeds safely in Phase 1."""
    safe_desc = _escape_ps_dq(description)
    script_lines = [
        "Import-Module ActiveDirectory -ErrorAction SilentlyContinue",
        f'$u = (Get-SSMParameter -Name "{ssm_user}" -WithDecryption $true).Value',
        f'$p = (Get-SSMParameter -Name "{ssm_pass}" -WithDecryption $true).Value `',
        "      | ConvertTo-SecureString -AsPlainText -Force",
        "$c = New-Object System.Management.Automation.PSCredential($u, $p)",
        f'Set-ADComputer -Identity $env:COMPUTERNAME -Description "{safe_desc}" -Credential $c',
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
) -> list:
    """Return Phase 1 script lines (list avoids f-string brace conflicts with PS)."""
    safe_dc = _escape_ps_dq(dc_host)
    lines = [
        "<powershell>",
        "$ErrorActionPreference = 'Stop'",
        "",
        "function Write-Log {",
        "    param([string]$Msg)",
        "    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
        '    "$ts  $Msg" | Out-File -Append "C:\\Windows\\Temp\\launcher-setup.log"',
        "    Write-Host $Msg",
        "}",
        "",
        "try {",
        f'    Write-Log "Phase 1 start — computer: {INSTANCE_NAME_MARKER}  domain: {domain}"',
        "",
        "    # Retrieve credentials from SSM Parameter Store (never stored on disk)",
        f'    $u = (Get-SSMParameter -Name "{ssm_user}" -WithDecryption $true).Value',
        f'    $p = (Get-SSMParameter -Name "{ssm_pass}" -WithDecryption $true).Value `',
        "          | ConvertTo-SecureString -AsPlainText -Force",
        "    $cred = New-Object System.Management.Automation.PSCredential($u, $p)",
        '    Write-Log "Credentials retrieved from SSM."',
        "",
        "    # Layer 4: AD pre-check — hard-stop if this computer name already exists.",
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
        "        exit 1",
        "    }",
        '    Write-Log "AD pre-check passed: \'$computerName\' is available."',
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
            "",
        ]

    lines += [
        "    # Rename computer + join domain — triggers automatic reboot",
        "    Add-Computer `",
        f'        -DomainName "{domain}" `',
        f'        -NewName    "{INSTANCE_NAME_MARKER}" `',
        f'        -OUPath     "{ou_dn}" `',
        "        -Credential $cred `",
        "        -Restart `",
        "        -Force",
        '    Write-Log "Add-Computer issued — reboot imminent."',
        "}",
        "catch {",
        '    Write-Log "ERROR in Phase 1: $_"',
        "    # Instance stays up so the error log can be reviewed via SSM Session Manager",
        "}",
        "</powershell>",
    ]
    return lines


def _escape_ps_dq(text: str) -> str:
    """Escape text for safe embedding inside a PowerShell double-quoted string."""
    return text.replace("`", "``").replace('"', '`"').replace("$", "`$")
