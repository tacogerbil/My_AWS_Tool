"""
test_userdata_builder.py — Unit tests for build_windows_userdata.

Pure function: no AWS, no Qt, no network.  Verifies that the generated
PowerShell script contains the correct commands for all options:
  - Timezone (tzutil)
  - DNS servers (Set-DnsClientServerAddress)
  - SSM endpoint override (-EndpointUrl)
  - EC2 tag milestones (_Set-InstanceTag calls with DomainJoinStatus key)
  - Log path (C:\\tmp\\EC2_creation\\ec2.log)
  - Local Administrators assignment (Add-LocalGroupMember in Phase 2)
"""

import pytest
from tools.ec2_launcher.models import WindowsDomainConfig
from tools.ec2_launcher.ui.userdata_builder import (
    DOMAIN_JOIN_TAG_KEY,
    INSTANCE_NAME_MARKER,
    build_windows_userdata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_cfg() -> WindowsDomainConfig:
    """Minimal valid domain config for testing."""
    return WindowsDomainConfig(
        enabled=True,
        domain="corp.example.com",
        ou_dn="OU=Servers,DC=corp,DC=example,DC=com",
        dc_host="dc01.corp.example.com",
        username="CORP\\svc-join",
        password="secret",
    )


# ---------------------------------------------------------------------------
# Basic output tests
# ---------------------------------------------------------------------------

def test_returns_empty_when_disabled(minimal_cfg: WindowsDomainConfig) -> None:
    """build_windows_userdata returns '' when domain join is disabled."""
    minimal_cfg.enabled = False
    result = build_windows_userdata(minimal_cfg)
    assert result == ""


def test_returns_empty_when_no_domain(minimal_cfg: WindowsDomainConfig) -> None:
    minimal_cfg.domain = ""
    result = build_windows_userdata(minimal_cfg)
    assert result == ""


def test_returns_empty_when_no_ou(minimal_cfg: WindowsDomainConfig) -> None:
    minimal_cfg.ou_dn = ""
    result = build_windows_userdata(minimal_cfg)
    assert result == ""


def test_script_has_powershell_tags(minimal_cfg: WindowsDomainConfig) -> None:
    script = build_windows_userdata(minimal_cfg)
    assert "<powershell>" in script
    assert "</powershell>" in script


def test_script_contains_instance_name_marker(minimal_cfg: WindowsDomainConfig) -> None:
    script = build_windows_userdata(minimal_cfg)
    assert INSTANCE_NAME_MARKER in script


# ---------------------------------------------------------------------------
# Timezone tests
# ---------------------------------------------------------------------------

def test_default_timezone_is_pst(minimal_cfg: WindowsDomainConfig) -> None:
    """Default timezone is Pacific Standard Time."""
    script = build_windows_userdata(minimal_cfg)
    assert 'tzutil /s "Pacific Standard Time"' in script


def test_custom_timezone_injected(minimal_cfg: WindowsDomainConfig) -> None:
    script = build_windows_userdata(minimal_cfg, timezone="Eastern Standard Time")
    assert 'tzutil /s "Eastern Standard Time"' in script


# ---------------------------------------------------------------------------
# DNS server tests
# ---------------------------------------------------------------------------

def test_no_dns_command_when_empty(minimal_cfg: WindowsDomainConfig) -> None:
    """No DNS command injected when dns_servers list is empty."""
    script = build_windows_userdata(minimal_cfg, dns_servers=[])
    assert "Set-DnsClientServerAddress" not in script


def test_dns_servers_injected(minimal_cfg: WindowsDomainConfig) -> None:
    script = build_windows_userdata(minimal_cfg, dns_servers=["10.0.0.2", "10.0.0.3"])
    assert "Set-DnsClientServerAddress" in script
    assert '"10.0.0.2"' in script
    assert '"10.0.0.3"' in script


def test_single_dns_server(minimal_cfg: WindowsDomainConfig) -> None:
    script = build_windows_userdata(minimal_cfg, dns_servers=["192.168.1.1"])
    assert "Set-DnsClientServerAddress" in script
    assert '"192.168.1.1"' in script


# ---------------------------------------------------------------------------
# SSM endpoint override tests
# ---------------------------------------------------------------------------

def test_no_endpoint_arg_when_not_set(minimal_cfg: WindowsDomainConfig) -> None:
    """No -EndpointUrl injected when ssm_endpoint_override is None."""
    minimal_cfg.ssm_endpoint_override = None
    script = build_windows_userdata(minimal_cfg)
    assert "-EndpointUrl" not in script


def test_endpoint_override_injected(minimal_cfg: WindowsDomainConfig) -> None:
    """When ssm_endpoint_override is set, all Get-SSMParameter calls include -EndpointUrl."""
    minimal_cfg.ssm_endpoint_override = "18.246.120.242"
    script = build_windows_userdata(minimal_cfg)
    assert '-EndpointUrl "https://18.246.120.242"' in script


def test_endpoint_override_appears_in_every_ssm_call(minimal_cfg: WindowsDomainConfig) -> None:
    """The override IP appears at least twice (username + password SSM calls)."""
    minimal_cfg.ssm_endpoint_override = "18.246.120.242"
    script = build_windows_userdata(minimal_cfg)
    count = script.count("https://18.246.120.242")
    assert count >= 2, f"Expected at least 2 endpoint override occurrences, got {count}"


# ---------------------------------------------------------------------------
# EC2 tag milestone tests
# ---------------------------------------------------------------------------

def test_domain_join_tag_key_present(minimal_cfg: WindowsDomainConfig) -> None:
    """The DomainJoinStatus tag key appears in milestone calls."""
    script = build_windows_userdata(minimal_cfg)
    assert DOMAIN_JOIN_TAG_KEY in script


def test_tag_helper_function_defined(minimal_cfg: WindowsDomainConfig) -> None:
    """The _Set-InstanceTag helper is defined in the script."""
    script = build_windows_userdata(minimal_cfg)
    assert "function _Set-InstanceTag" in script


def test_tag_milestones_present(minimal_cfg: WindowsDomainConfig) -> None:
    """Key milestone tag values appear in the script."""
    script = build_windows_userdata(minimal_cfg)
    assert "Phase1: Started" in script
    assert "Phase1: Credentials retrieved" in script
    assert "Phase1: AD pre-check passed" in script
    assert "Phase1: Joining domain" in script


def test_error_tag_on_ad_block(minimal_cfg: WindowsDomainConfig) -> None:
    """AD pre-check failure tags the instance with an error status."""
    script = build_windows_userdata(minimal_cfg)
    assert "already exists in AD" in script


# ---------------------------------------------------------------------------
# Log path tests
# ---------------------------------------------------------------------------

def test_log_path_updated(minimal_cfg: WindowsDomainConfig) -> None:
    """Log file is written to the new path."""
    script = build_windows_userdata(minimal_cfg)
    assert r"C:\tmp\EC2_creation\ec2.log" in script
    # Old path must NOT be present
    assert r"C:\Windows\Temp\launcher-setup.log" not in script


def test_log_dir_creation_command_present(minimal_cfg: WindowsDomainConfig) -> None:
    """Script creates the log directory if it doesn't exist."""
    script = build_windows_userdata(minimal_cfg)
    assert r"C:\tmp\EC2_creation" in script
    assert "New-Item" in script


# ---------------------------------------------------------------------------
# LaunchConfig defaults tests
# ---------------------------------------------------------------------------

def test_launch_config_defaults() -> None:
    """LaunchConfig defaults for the 5 new fields are all correctly safe/set."""
    from tools.ec2_launcher.models import LaunchConfig

    cfg = LaunchConfig(
        image_id="ami-test",
        instance_type="t3.micro",
        volume_gb=30,
        volume_type="gp3",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        sg_ids=[],
        key_name="key",
    )

    assert cfg.associate_public_ip is False,          "Public IP must default to False"
    assert cfg.imdsv2_required is True,               "IMDSv2 must default to required"
    assert cfg.enable_termination_protection is True, "Termination protection must default to True"
    assert cfg.timezone == "Pacific Standard Time",   "Timezone must default to PST"
    assert cfg.dns_servers == [],                     "DNS servers must default to empty list"


# ---------------------------------------------------------------------------
# admin_principals / Local Administrators tests
# ---------------------------------------------------------------------------

import base64  # noqa: E402  (standard lib; placed here to keep it near usage)


def _decode_phase2(script: str) -> str:
    """Extract and base64-decode the embedded Phase 2 script from *script*."""
    import re
    match = re.search(r'\$b64 = "([A-Za-z0-9+/=]+)"', script)
    assert match, "Phase 2 base64 block not found in script"
    return base64.b64decode(match.group(1)).decode("utf-8")


def test_no_admin_block_when_principals_empty(minimal_cfg: WindowsDomainConfig) -> None:
    """Add-LocalGroupMember must NOT appear when admin_principals is empty."""
    minimal_cfg.admin_principals = []
    script = build_windows_userdata(minimal_cfg)
    assert "Add-LocalGroupMember" not in script


def test_admin_principals_injected_into_phase2(minimal_cfg: WindowsDomainConfig) -> None:
    """Each selected principal appears in the Phase 2 script."""
    minimal_cfg.admin_principals = ["Domain Admins", "john.smith"]
    script = build_windows_userdata(minimal_cfg)
    phase2 = _decode_phase2(script)
    assert "Add-LocalGroupMember" in phase2
    assert "Domain Admins" in phase2
    assert "john.smith" in phase2


def test_admin_block_is_non_fatal(minimal_cfg: WindowsDomainConfig) -> None:
    """Each Add-LocalGroupMember call has its own try/catch so failures are non-fatal."""
    minimal_cfg.admin_principals = ["IT-Helpdesk"]
    script = build_windows_userdata(minimal_cfg)
    phase2 = _decode_phase2(script)
    # A [WARN] log message must exist inside a catch block
    assert "[WARN]" in phase2
    assert "catch" in phase2


def test_phase2_generated_with_only_principals(minimal_cfg: WindowsDomainConfig) -> None:
    """Phase 2 is created even when description is blank, as long as principals are set."""
    minimal_cfg.description = ""          # no description
    minimal_cfg.admin_principals = ["Server-Operators"]
    script = build_windows_userdata(minimal_cfg)
    # Phase 2 block exists (base64 variable present)
    assert '$b64 = "' in script
    phase2 = _decode_phase2(script)
    assert "Server-Operators" in phase2
    # SSM credential fetch must NOT be present (no description = no creds needed)
    assert "Get-SSMParameter" not in phase2


def test_phase2_has_ssm_creds_only_when_description_set(minimal_cfg: WindowsDomainConfig) -> None:
    """SSM credential fetch only runs when a description is also configured."""
    minimal_cfg.description = "Prod server"
    minimal_cfg.admin_principals = ["Domain Admins"]
    script = build_windows_userdata(minimal_cfg)
    phase2 = _decode_phase2(script)
    # Both SSM calls AND admin block should be present
    assert "Get-SSMParameter" in phase2
    assert "Add-LocalGroupMember" in phase2
