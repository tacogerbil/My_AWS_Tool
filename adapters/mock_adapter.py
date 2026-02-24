"""
MockAdapter — offline/GUI-dev stub for CloudProviderPort.

Simulates run_instances with staged state transitions so the
LaunchMonitorDialog can be exercised without real AWS credentials.
"""

from __future__ import annotations

import random
import string
from typing import Dict, List, Optional

from core.models import Ami, Instance, KeyPair, SecurityGroup, Subnet, Tag, Vpc
from core.ports import CloudProviderPort


def _rand_id() -> str:
    """Generate a fake-looking instance ID."""
    suffix = "".join(random.choices(string.hexdigits[:16], k=17))
    return f"i-{suffix}"


class MockAdapter(CloudProviderPort):
    """Mock implementation for offline testing / GUI development.

    ``run_instances`` adds fake instances to the internal list in
    ``pending`` state.  Each subsequent ``describe_instances`` call
    advances them one step: pending → running.  This gives the
    LaunchMonitorDialog at least two polling cycles to show transitions.
    """

    def __init__(self) -> None:
        self.vpcs = [
            Vpc("vpc-12345678", "10.0.0.0/16", False, [Tag("Name", "Prod-VPC")], "available", "Prod-VPC"),
            Vpc("vpc-87654321", "192.168.0.0/16", True, [Tag("Name", "Default-VPC")], "available", "Default-VPC"),
        ]
        self.subnets = [
            Subnet("subnet-1", "vpc-12345678", "10.0.1.0/24", "us-east-1a", [Tag("Name", "Prod-Subnet-1")], 251, "available", "Prod-Subnet-1"),
            Subnet("subnet-2", "vpc-12345678", "10.0.2.0/24", "us-east-1b", [Tag("Name", "Prod-Subnet-2")], 251, "available", "Prod-Subnet-2"),
        ]
        self.sgs = [
            SecurityGroup("sg-1", "web-sg", "Allow HTTP", "vpc-12345678", [Tag("Name", "Web-SG")])
        ]
        self.instances: List[Instance] = [
            Instance(
                "i-0abcdef1234567890", "t3.micro", "running",
                "1.2.3.4", "10.0.1.5", "vpc-12345678", "subnet-1",
                self.sgs, [Tag("Name", "WebServer")], "ami-123",
            )
        ]
        # poll_count[instance_id] tracks how many times that instance has
        # been returned by describe_instances — used to advance state.
        self._poll_count: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # CloudProviderPort implementation
    # ------------------------------------------------------------------

    def get_import_orchestrator(self):  # type: ignore[override]
        return None

    def get_instance_type_info(self, instance_type: str) -> dict:
        mock_data = {
            "t2.micro":  {"vCPU": 1, "MemoryMiB": 1024},
            "t3.micro":  {"vCPU": 2, "MemoryMiB": 1024},
            "t3.medium": {"vCPU": 2, "MemoryMiB": 4096},
            "m5.large":  {"vCPU": 2, "MemoryMiB": 8192},
            "c5.large":  {"vCPU": 2, "MemoryMiB": 4096},
        }
        data = mock_data.get(instance_type, {"vCPU": 0, "MemoryMiB": 0})
        vcpu, mem = data["vCPU"], data["MemoryMiB"]
        return {
            "vCPU": vcpu,
            "MemoryMiB": mem,
            "Label": f"{instance_type} ({vcpu} vCPU, {mem / 1024:.1f} GiB)",
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

    def describe_instances(
        self,
        region: str,
        instance_ids: Optional[List[str]] = None,
        tag_filters: Optional[List[Dict]] = None,
    ) -> List[Instance]:
        """Return instances, advancing mock states on each poll.

        State machine per instance:
            poll 0  → pending
            poll 1+ → running
        """
        pool = self.instances
        if instance_ids:
            pool = [i for i in pool if i.instance_id in instance_ids]

        for inst in pool:
            count = self._poll_count.get(inst.instance_id, 0)
            if count == 0 and inst.state == "pending":
                pass  # still pending first poll
            elif inst.state == "pending":
                inst.state = "running"
                inst.private_ip = "10.0.1." + str(random.randint(10, 200))
            self._poll_count[inst.instance_id] = count + 1

        return pool

    def list_amis(self, region: str, owners: List[str], filters: Optional[List[Dict]] = None) -> List[Ami]:
        return []  # LauncherWindow._load_mock_data() provides AMIs directly

    def list_key_pairs(self, region: str) -> List[KeyPair]:
        return []

    def list_buckets(self) -> List[str]:
        return []

    def validate_connection(self) -> bool:
        return True

    def get_available_regions(self) -> List[str]:
        return ["us-east-1", "us-west-2", "eu-central-1"]

    def run_instances(self, region: str, config: "LaunchConfig") -> "LaunchResult":  # type: ignore[name-defined]
        """Simulate a launch by creating pending mock instances.

        The new instances start in ``pending`` state and transition to
        ``running`` on the second ``describe_instances`` poll, giving the
        LaunchMonitorDialog something meaningful to display.
        """
        from tools.ec2_launcher.models import LaunchConfig, LaunchResult  # local import

        names = config.instance_names or [f"Instance-{i + 1}" for i in range(config.instance_count)]
        new_ids: List[str] = []

        for name in names:
            iid = _rand_id()
            mock_inst = Instance(
                instance_id=iid,
                instance_type=config.instance_type,
                state="pending",
                public_ip=None,
                private_ip=None,
                vpc_id=config.vpc_id,
                subnet_id=config.subnet_id,
                security_groups=[],
                tags=[Tag("Name", name)],
                image_id=config.image_id,
                key_name=config.key_name,
                name=name,
            )
            self.instances.append(mock_inst)
            self._poll_count[iid] = 0
            new_ids.append(iid)

        return LaunchResult(
            instance_ids=new_ids,
            instance_names=names,
            region=region,
        )
