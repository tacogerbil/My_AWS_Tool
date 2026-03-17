"""
LauncherService — orchestration layer for the EC2 Launcher tool.

No AWS calls here; all cloud I/O delegated to the injected adapter (CloudProviderPort).

Quick Start AMI strategy
------------------------
list_quick_start_amis() makes one batched describe_images call per AWS owner
(amazon, Canonical, Red Hat, SUSE, Debian).  For each name-pattern in the
batch, it selects the single most recently created matching AMI — giving exactly
the "latest" AMI per Quick Start slot.  Falls back to a minimal hardcoded list
if any AWS call fails (e.g. no credentials, network error).
"""

from __future__ import annotations

import logging
from fnmatch import fnmatch as _fnmatch
from typing import Dict, List, Optional, Tuple

from core.models import Ami, InboundRule, Instance, KeyPair, SecurityGroup, Subnet, Vpc
from core.ports import CloudProviderPort
from tools.ec2_launcher.models import LaunchConfig, LaunchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Quick Start specification
# ---------------------------------------------------------------------------
# Each entry: (owners, [name_glob, ...])
# AWS describe_images name-filter treats Values as OR — one API call per owner.
# Wildcards use the same syntax as Python fnmatch (AWS also uses * and ?).
_QS_SPECS: List[Tuple[List[str], List[str]]] = [
    (
        ["amazon"],
        [
            # Amazon Linux 2023
            "al2023-ami-2023*-kernel-6.1-x86_64",
            "al2023-ami-2023*-kernel-6.1-arm64",
            # Amazon Linux 2
            "amzn2-ami-hvm-*-x86_64-gp2",
            # Windows Server 2022
            "Windows_Server-2022-English-Full-Base-*",
            "Windows_Server-2022-English-Core-Base-*",
            "Windows_Server-2022-English-Full-SQL_2022_Express-*",
            "Windows_Server-2022-English-Full-SQL_2022_Standard-*",
            "Windows_Server-2022-English-Full-SQL_2022_Web-*",
            "Windows_Server-2022-English-Full-SQL_2022_Enterprise-*",
            # Windows Server 2019
            "Windows_Server-2019-English-Full-Base-*",
            "Windows_Server-2019-English-Core-Base-*",
            "Windows_Server-2019-English-Full-SQL_2019_Standard-*",
        ],
    ),
    (
        ["099720109477"],  # Canonical (Ubuntu)
        [
            "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
            "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*",
            "ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*",
        ],
    ),
    (
        ["309956199498"],  # Red Hat
        [
            "RHEL-9*_HVM-*-x86_64-*-GP2",
            "RHEL-8*_HVM-*-x86_64-*-GP2",
        ],
    ),
    (
        ["013907871322"],  # SUSE
        ["suse-sles-15-sp*-v*-hvm-ssd-x86_64"],
    ),
    (
        ["136693071363"],  # Debian
        ["debian-12-amd64-*"],
    ),
]

_QUICK_START_FALLBACK: List[Ami] = [
    Ami("ami-0c55b159cbfafe1f0", "Amazon Linux 2023",
        "Amazon Linux 2023 AMI", "Linux/UNIX"),
    Ami("ami-053b0d53c279acc90", "Ubuntu Server 22.04 LTS",
        "Canonical, Ubuntu, 22.04 LTS", "Linux/UNIX"),
    Ami("ami-0d5eff06f840b45e9", "Windows Server 2022 Base",
        "Microsoft Windows Server 2022 Base", "Windows"),
]


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------

def _pick_latest_per_pattern(amis: List[Ami], patterns: List[str]) -> List[Ami]:
    """For each pattern return the most recently created matching AMI (one per pattern)."""
    result: List[Ami] = []
    for pattern in patterns:
        matches = [a for a in amis if _fnmatch(a.name, pattern)]
        if matches:
            latest = max(matches, key=lambda a: a.creation_date or "")
            result.append(latest)
    return result


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LauncherService:
    """Business logic for EC2 Launcher.  All AWS I/O delegated to adapter."""

    def __init__(self, adapter: CloudProviderPort, region: str = "us-west-2") -> None:
        self.adapter = adapter
        self.region = region

    # ------------------------------------------------------------------
    # AMI methods
    # ------------------------------------------------------------------

    def list_my_amis(self) -> List[Ami]:
        """AMIs owned by the current account ('self')."""
        try:
            return self.adapter.list_amis(self.region, owners=["self"])
        except Exception as exc:
            logger.error("Error listing AMIs: %s", exc)
            raise

    def list_quick_start_amis(self) -> List[Ami]:
        """Fetch Quick Start AMIs from AWS per OS category.

        Makes one batched describe_images call per unique AWS owner.
        For each name pattern, returns only the most recently created match.
        Falls back to a small hardcoded list on any error.
        """
        try:
            results: List[Ami] = []
            for owners, patterns in _QS_SPECS:
                name_filter = [{"Name": "name", "Values": patterns}]
                batch = self.adapter.list_amis(self.region, owners, filters=name_filter)
                results.extend(_pick_latest_per_pattern(batch, patterns))
            return results if results else _QUICK_START_FALLBACK
        except Exception as exc:
            logger.warning("Could not fetch Quick Start AMIs: %s — using fallback", exc)
            return _QUICK_START_FALLBACK

    # ------------------------------------------------------------------
    # Infrastructure methods
    # ------------------------------------------------------------------

    def list_instance_types(self) -> List[str]:
        return [
            "t2.micro", "t3.micro", "t3.small", "t3.medium", "t3.large", "t3.xlarge",
            "m5.large", "m5.xlarge", "c5.large", "c5.xlarge", "c6i.large", "r5.large",
        ]

    def list_vpcs(self) -> List[Vpc]:
        try:
            return self.adapter.list_vpcs(self.region)
        except Exception as exc:
            logger.error("Error listing VPCs: %s", exc)
            raise

    def list_subnets(self, vpc_id: Optional[str] = None) -> List[Subnet]:
        try:
            return self.adapter.list_subnets(self.region, vpc_id=vpc_id)
        except Exception as exc:
            logger.error("Error listing Subnets: %s", exc)
            raise

    def list_security_groups(self, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        try:
            return self.adapter.list_security_groups(self.region, vpc_id=vpc_id)
        except Exception as exc:
            logger.error("Error listing SGs: %s", exc)
            raise

    def list_key_pairs(self) -> List[KeyPair]:
        try:
            return self.adapter.list_key_pairs(self.region)
        except Exception as exc:
            logger.error("Error listing Key Pairs: %s", exc)
            raise

    def list_instances_for_cloning(
        self, tag_filters: Optional[List[Dict[str, str]]] = None
    ) -> List[Instance]:
        """Instances to support the 'Clone' feature (running + stopped only)."""
        try:
            return self.adapter.describe_instances(self.region, tag_filters=tag_filters)
        except Exception as exc:
            logger.error("Error scanning instances: %s", exc)
            raise

    def launch_instances(self, config: LaunchConfig) -> LaunchResult:
        """Delegate run_instances to the adapter; pure orchestration.

        Single responsibility: translate the service-layer call into the
        adapter-layer call and propagate any errors with context.
        """
        try:
            return self.adapter.run_instances(self.region, config)
        except Exception as exc:
            logger.error("Error launching instances: %s", exc)
            return LaunchResult(
                instance_ids=[],
                instance_names=[],
                region=self.region,
                error=str(exc),
            )

    def create_security_group(
        self,
        name: str,
        description: str,
        vpc_id: str,
        rules: List[InboundRule],
    ) -> SecurityGroup:
        """Create a new Security Group and authorise its inbound rules."""
        try:
            return self.adapter.create_security_group(
                self.region, name, description, vpc_id, rules
            )
        except Exception as exc:
            logger.error("Failed to create SG '%s': %s", name, exc)
            raise

    def list_instance_profiles(self) -> List[str]:
        """Return all IAM instance profile names available in the account.

        Returns an empty list (silently) when the caller's credentials do not
        include iam:ListInstanceProfiles — the field is optional in the UI.
        """
        try:
            return self.adapter.list_instance_profiles()
        except Exception as exc:
            logger.debug("Instance profiles unavailable: %s", exc)
            return []

    def create_key_pair(
        self,
        name: str,
        key_type: str = "rsa",
        key_format: str = "pem",
    ) -> "CreatedKeyPair":
        """Create a new EC2 key pair and return the private key material.

        The private key is returned exactly once — caller must write it to disk
        and discard the in-memory value immediately after.
        """
        from core.models import CreatedKeyPair  # noqa: F401 — type hint only
        return self.adapter.create_key_pair(self.region, name, key_type, key_format)

    def store_domain_credentials(self, ssm_path: str, username: str, password: str) -> None:
        """Write domain join credentials to SSM Parameter Store as SecureStrings.

        Callers should discard the plain-text strings immediately after this call.
        """
        params = {
            f"{ssm_path}/username": username,
            f"{ssm_path}/password": password,
        }
        self.adapter.put_ssm_parameters(self.region, params)

    def describe_instances_by_ids(self, instance_ids: List[str]) -> List[Instance]:
        """Poll current state for a specific list of instance IDs.

        Used by the LaunchMonitorDialog polling timer.
        """
        try:
            return self.adapter.describe_instances(self.region, instance_ids=instance_ids)
        except Exception as exc:
            logger.error("Error polling instance state: %s", exc)
            return []
