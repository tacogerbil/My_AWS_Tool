from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class Tag:
    """Represents an AWS Tag."""
    key: str
    value: str

@dataclass
class Vpc:
    """Represents an AWS VPC."""
    vpc_id: str
    cidr_block: str
    is_default: bool
    tags: List[Tag] = field(default_factory=list)
    state: str = "available"
    name: Optional[str] = None  # Extracted from Name tag

@dataclass
class Subnet:
    """Represents an AWS Subnet."""
    subnet_id: str
    vpc_id: str
    cidr_block: str
    availability_zone: str
    tags: List[Tag] = field(default_factory=list)
    available_ip_address_count: int = 0
    state: str = "available"
    name: Optional[str] = None

@dataclass
class InboundRule:
    """One inbound permission entry in a Security Group."""
    protocol: str    # "tcp", "udp", "icmp", "all"
    port_range: str  # "22", "0-65535", "All", ""
    cidr: str        # "0.0.0.0/0", "::/0"
    description: str = ""


@dataclass
class SecurityGroup:
    """Represents an AWS Security Group."""
    group_id: str
    group_name: str
    description: str
    vpc_id: str
    tags: List[Tag] = field(default_factory=list)
    inbound_rules: List["InboundRule"] = field(default_factory=list)

@dataclass
class Instance:
    """Represents an AWS EC2 Instance."""
    instance_id: str
    instance_type: str
    state: str  # pending, running, shutting-down, terminated, stopping, stopped
    public_ip: Optional[str]
    private_ip: Optional[str]
    vpc_id: str
    subnet_id: str
    security_groups: List[SecurityGroup] = field(default_factory=list)
    tags: List[Tag] = field(default_factory=list)
    image_id: str = ""
    key_name: Optional[str] = None
    name: Optional[str] = None

@dataclass
class Ami:
    """Represents an Amazon Machine Image."""
    image_id: str
    name: str
    description: str
    platform: str
    tags: List[Tag] = field(default_factory=list)
    creation_date: Optional[str] = None       # ISO-8601; used for "latest" selection
    architecture: Optional[str] = None         # e.g. "x86_64", "arm64"
    virtualization_type: Optional[str] = None  # "hvm" | "paravirtual"
    root_device_type: Optional[str] = None     # "ebs" | "instance-store"
    ena_support: Optional[bool] = None

@dataclass
class KeyPair:
    """Represents an EC2 Key Pair."""
    key_name: str


@dataclass
class OrgUnit:
    """An Active Directory Organizational Unit or Container."""
    name: str                # Display name, e.g. "Prod"
    distinguished_name: str  # Full DN: "OU=Prod,OU=Servers,DC=corp,DC=example,DC=com"
    object_class: str = "organizationalUnit"  # "organizationalUnit" | "container"
    depth: int = 0           # Nesting depth — used for display indentation
