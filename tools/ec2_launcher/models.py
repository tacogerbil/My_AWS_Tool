"""
EC2 Launcher domain models.

Pure dataclasses only — no I/O, no AWS SDK, no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
