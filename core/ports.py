from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

from core.models import (
    CreatedKeyPair,
    InboundRule,
    Instance,
    InstanceTypeInfo,
    SecurityGroup,
    Subnet,
    Vpc,
)

if TYPE_CHECKING:
    from tools.ec2_launcher.models import LaunchConfig, LaunchResult


@runtime_checkable
class VmImportPort(Protocol):
    """Minimal contract that callers of get_import_orchestrator depend on.

    Concrete implementations live in tools/vm_importer/services.py.
    Defined here as a Protocol so the adapter need not import service types.
    """

    def import_vm(self, *args: Any, **kwargs: Any) -> Any: ...

class CloudProviderPort(ABC):
    """
    Abstract Interface for Cloud Provider interactions.
    Adheres to the Dependency Inversion Principle.
    """

    @abstractmethod
    def list_vpcs(self, region: str) -> List[Vpc]:
        """List all VPCs in a given region."""
        pass

    @abstractmethod
    def list_subnets(self, region: str, vpc_id: Optional[str] = None) -> List[Subnet]:
        """List subnets, optionally filtered by VPC."""
        pass

    @abstractmethod
    def list_security_groups(self, region: str, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        """List security groups, optionally filtered by VPC."""
        pass

    @abstractmethod
    def describe_instances(
        self,
        region: str,
        instance_ids: Optional[List[str]] = None,
        tag_filters: Optional[List[Dict[str, str]]] = None,
        states: Optional[List[str]] = None,
    ) -> List[Instance]:
        """Describe EC2 instances.

        Parameters
        ----------
        states:
            Optional list of instance state names to filter by
            (e.g. ``['running', 'stopped']``).  When ``None`` the adapter
            returns all states — callers are responsible for filtering.
        """

    @abstractmethod
    def list_amis(
        self,
        region: str,
        owners: List[str],
        filters: Optional[List[Dict]] = None,
    ) -> List['Ami']:
        """List AMIs filtered by owners and optional boto3-style filters."""
        pass
        
    @abstractmethod
    def list_key_pairs(self, region: str) -> List['KeyPair']:
        """List available EC2 key pairs."""
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate that credentials are set up and working."""
        pass
        
    @abstractmethod
    def get_available_regions(self) -> List[str]:
        """List available AWS regions."""
        pass

    @abstractmethod
    def get_import_orchestrator(self) -> VmImportPort:
        """Return an object that satisfies VmImportPort (VM import orchestrator)."""
        pass

    @abstractmethod
    def get_instance_type_info(self, instance_type: str) -> InstanceTypeInfo:
        """Return structured metadata for an instance type.

        Result is a typed ``InstanceTypeInfo`` dataclass — no raw dicts cross
        the adapter boundary.
        """
        pass
    @abstractmethod
    def list_buckets(self) -> List[str]:
        """List all S3 buckets available to the account."""
        pass

    @abstractmethod
    def create_security_group(
        self,
        region: str,
        name: str,
        description: str,
        vpc_id: str,
        rules: List[InboundRule],
    ) -> SecurityGroup:
        """Create a new SG, authorise inbound rules, return the new SecurityGroup."""
        pass

    @abstractmethod
    def run_instances(self, region: str, config: "LaunchConfig") -> "LaunchResult":
        """Launch EC2 instances described by config.

        Returns a LaunchResult with the assigned instance IDs. On complete
        failure the result has an empty ``instance_ids`` list and a non-None
        ``error`` string.
        """
        pass

    @abstractmethod
    def list_instance_profiles(self) -> List[str]:
        """List all EC2 instance profile names available in the account.

        Returns a sorted list of profile names (strings).  Instance profiles
        are the mechanism that grants EC2 instances permission to call other
        AWS services (e.g. reading credentials from Parameter Store, or
        accepting Systems Manager remote-desktop connections).
        """
        pass

    @abstractmethod
    def create_key_pair(
        self,
        region: str,
        name: str,
        key_type: str = "rsa",
        key_format: str = "pem",
    ) -> CreatedKeyPair:
        """Create a new EC2 key pair and return it.

        ``key_material`` in the result is the private key — available once only.
        Callers must write it to disk immediately and discard the in-memory value.

        Parameters
        ----------
        key_type:   "rsa" | "ed25519"
        key_format: "pem" | "ppk"
        """
        pass

    @abstractmethod
    def put_ssm_parameters(self, region: str, params: Dict[str, str]) -> None:
        """Write key/value pairs to SSM Parameter Store as SecureString (KMS-encrypted).

        Existing parameters are overwritten.  Callers should discard the
        plain-text values immediately after this call returns.
        """
        pass
