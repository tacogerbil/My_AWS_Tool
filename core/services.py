from typing import List, Optional
from core.models import InstanceTypeInfo, Subnet, Vpc, Instance
from core.ports import CloudProviderPort

class ResourceService:
    """
    Service layer for AWS Resource interactions.
    Strictly typed, MCCC compliant.
    """
    def __init__(self, adapter: CloudProviderPort):
        self.adapter = adapter

    def list_all_vpcs(self, region: str) -> List[Vpc]:
        """It lists all VPCs."""
        return self.adapter.list_vpcs(region)

    def list_subnets_for_vpc(self, region: str, vpc_id: str) -> List[Subnet]:
        """Lists subnets for a specific VPC."""
        return self.adapter.list_subnets(region, vpc_id=vpc_id)

    def list_instances(self, region: str) -> List[Instance]:
        """Lists all instances in the region."""
        return self.adapter.describe_instances(region)

    def check_connection(self) -> bool:
        """Verifies access to the Cloud Provider."""
        return self.adapter.validate_connection()

    def list_available_regions(self) -> List[str]:
        return self.adapter.get_available_regions()
        
    def get_instance_type_info(self, instance_type: str) -> InstanceTypeInfo:
        """Returns structured hardware metadata for an instance type."""
        return self.adapter.get_instance_type_info(instance_type)

    def list_buckets(self) -> List[str]:
        return self.adapter.list_buckets()
