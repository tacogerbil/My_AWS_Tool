"""
EC2 Launcher domain models.

Pure dataclasses only — no I/O, no AWS SDK, no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class VolumeConfig:
    """Configuration for one EBS block device."""

    device_name: str = "/dev/sda1"
    size_gb: int = 30
    volume_type: str = "gp3"
    delete_on_termination: bool = True
    encrypted: bool = False
    iops: Optional[int] = None
    throughput_mbps: Optional[int] = None
    kms_key_id: Optional[str] = None
    initialization_rate: str = "default"  # "default" | "maximum"


@dataclass
class SectionPatch:
    """Partial settings captured from a reference instance.

    Every field is Optional.  apply_patch in ConfigForm only updates
    fields that are not None, so callers set only the sections they want
    to copy.
    """

    source_instance_id: Optional[str] = None
    source_name: Optional[str] = None

    # Image
    image_id: Optional[str] = None

    # Hardware
    instance_type: Optional[str] = None
    volume_gb: Optional[int] = None
    volume_type: Optional[str] = None

    # Network
    vpc_id: Optional[str] = None
    subnet_id: Optional[str] = None

    # Security
    sg_ids: Optional[List[str]] = None
    key_name: Optional[str] = None

    # Tags
    tags: Optional[Dict[str, str]] = None


@dataclass
class WindowsDomainConfig:
    """Windows domain-join settings captured from the Windows Setup section.

    Credentials (username / password) are held in memory only.
    At launch time the launcher writes them to SSM Parameter Store
    (SecureString, KMS-encrypted) and they are never written to disk.
    """

    enabled: bool = False
    domain: str = ""          # FQDN, e.g. "corp.example.com"
    dc_host: str = ""         # DC hostname / IP for LDAP query
    username: str = ""        # DOMAIN\\user — used for LDAP query & SSM label
    password: str = ""        # In-memory only; stored to SSM at launch time
    ssm_path: str = "/domain/join"   # SSM path prefix for credentials
    ou_dn: str = ""           # Full DN of target OU/Container
    description: str = ""     # AD computer object description (post-join)
    iam_profile: Optional[str] = None     # IAM instance profile name or ARN for SSM access


@dataclass
class LaunchConfig:
    """Fully-validated configuration ready for ec2.run_instances.

    All fields required — ConfigForm.get_launch_config() only returns
    this when the form is complete and valid.
    """

    image_id: str
    instance_type: str
    volume_gb: int
    volume_type: str
    vpc_id: str
    subnet_id: str
    sg_ids: List[str]
    key_name: str
    tags: Dict[str, str] = field(default_factory=dict)
    # Multi-instance support: each instance gets its own name pre-launch
    instance_count: int = 1
    instance_names: List[str] = field(default_factory=list)
    volumes: List[VolumeConfig] = field(default_factory=list)
    # Windows domain join — UserData template uses <<INSTANCE_NAME>> marker
    user_data_template: Optional[str] = None
    iam_instance_profile: Optional[str] = None


@dataclass
class LaunchResult:
    """Outcome of a run_instances call.

    ``instance_ids`` and ``instance_names`` are parallel lists — index N in
    ``instance_ids`` matches index N in ``instance_names``.  On complete
    failure (e.g. auth error), ``instance_ids`` is empty and ``error`` is set.
    Individual per-instance errors are tracked via ``per_instance_errors``.
    """

    instance_ids: List[str]
    instance_names: List[str]          # Names from LaunchConfig (parallel to ids)
    region: str
    error: Optional[str] = None        # Non-None → entire launch failed
    per_instance_errors: List[Tuple[str, str]] = field(default_factory=list)
