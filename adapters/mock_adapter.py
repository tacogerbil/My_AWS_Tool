from typing import List, Optional
from core.ports import CloudProviderPort
from core.models import Vpc, Subnet, SecurityGroup, Instance, Tag

class MockAdapter(CloudProviderPort):
    """
    Mock implementation for offline testing/GUI dev.
    """

    def __init__(self):
        self.vpcs = [
            Vpc("vpc-12345678", "10.0.0.0/16", False, [Tag("Name", "Prod-VPC")], "available", "Prod-VPC"),
            Vpc("vpc-87654321", "192.168.0.0/16", True, [Tag("Name", "Default-VPC")], "available", "Default-VPC")
        ]
        self.subnets = [
            Subnet("subnet-1", "vpc-12345678", "10.0.1.0/24", "us-east-1a", [Tag("Name", "Prod-Subnet-1")], 251, "available", "Prod-Subnet-1"),
            Subnet("subnet-2", "vpc-12345678", "10.0.2.0/24", "us-east-1b", [Tag("Name", "Prod-Subnet-2")], 251, "available", "Prod-Subnet-2")
        ]
        self.sgs = [
            SecurityGroup("sg-1", "web-sg", "Allow HTTP", "vpc-12345678", [Tag("Name", "Web-SG")])
        ]
        self.instances = [
            Instance("i-0abcdef1234567890", "t3.micro", "running", "1.2.3.4", "10.0.1.5", "vpc-12345678", "subnet-1", self.sgs, [Tag("Name", "WebServer")], "ami-123")
        ]

    def get_import_orchestrator(self):
        return None # Mock doesn't support import yet

    def get_instance_type_info(self, instance_type: str) -> dict:
        # Simple mock map
        mock_data = {
            "t2.micro": {"vCPU": 1, "MemoryMiB": 1024},
            "t3.medium": {"vCPU": 2, "MemoryMiB": 4096},
            "m5.large": {"vCPU": 2, "MemoryMiB": 8192},
            "c5.large": {"vCPU": 2, "MemoryMiB": 4096},
        }
        data = mock_data.get(instance_type, {"vCPU": 0, "MemoryMiB": 0})
        vcpu = data["vCPU"]
        mem = data["MemoryMiB"]
        return {
            "vCPU": vcpu,
            "MemoryMiB": mem,
            "Label": f"{instance_type} ({vcpu} vCPU, {mem/1024:.1f} GiB)"
        }

    def list_vpcs(self, region: str) -> List[Vpc]:
        return self.vpcs

    def list_subnets(self, region: str, vpc_id: Optional[str] = None) -> List[Subnet]:
        if vpc_id:
            return [s for s in self.subnets if s.vpc_id == vpc_id]
        return self.subnets

    def list_security_groups(self, region: str, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        if vpc_id:
            return [sg for sg in self.sgs if sg.vpc_id == vpc_id]
        return self.sgs

    def describe_instances(self, region: str, instance_ids: Optional[List[str]] = None) -> List[Instance]:
        if instance_ids:
            return [i for i in self.instances if i.instance_id in instance_ids]
        return self.instances

    def validate_connection(self) -> bool:
        return True

    def get_available_regions(self) -> List[str]:
        return ["us-east-1", "us-west-2", "eu-central-1"]
