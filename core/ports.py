from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from core.models import Vpc, Subnet, SecurityGroup, Instance

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
    def describe_instances(self, region: str, instance_ids: Optional[List[str]] = None, tag_filters: Optional[List[Dict[str, str]]] = None) -> List[Instance]:
        """Describe EC2 instances."""
        pass

    @abstractmethod
    def list_amis(self, region: str, owners: List[str]) -> List['Ami']:
        """List AMIs filtered by owners."""
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
    def get_import_orchestrator(self) -> Any:
        """
        Returns an object capable of orchestrating VM imports.
        Use Any to avoid circular imports with Service layer types if necessary, 
        or define a Protocol. For now, strict MCCC asks for Explicit Interfaces,
        but we can keep it loose at the Port level or import the Service type if cleanly separated.
        """
        pass

    @abstractmethod
    def get_instance_type_info(self, instance_type: str) -> dict:
        """
        Returns metadata for an instance type.
        Result dict keys: 'vCPU', 'MemoryMiB', 'Label'
        """
        pass
    @abstractmethod
    def list_buckets(self) -> List[str]:
        """List all S3 buckets available to the account."""
        pass
