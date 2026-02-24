from typing import List, Dict, Any, Optional
import logging
from core.models import Ami, Instance, KeyPair, Vpc, Subnet, SecurityGroup
from core.ports import CloudProviderPort

logger = logging.getLogger(__name__)

class LauncherService:
    """
    Business logic for EC2 Launcher.
    Handles fetching resources and launching instances.
    """
    def __init__(self, adapter: CloudProviderPort, region: str = "us-west-2"):
        self.adapter = adapter
        self.region = region

    def list_my_amis(self) -> List[Ami]:
        """
        Lists AMIs owned by the current account ('self').
        """
        try:
            return self.adapter.list_amis(self.region, owners=['self'])
        except Exception as e:
            logger.error(f"Error listing AMIs: {e}")
            raise

    def list_quick_start_amis(self) -> List[Ami]:
        """
        Returns a hardcoded list of Quick Start AMIs (Amazon Linux, Ubuntu, Windows).
        In a real app, this might query Parameter Store.
        """
        # For prototype, we'll return a static list but structured like real AMIs
        return [
            Ami(image_id='ami-0c55b159cbfafe1f0', name='Amazon Linux 2023', description='Amazon Linux 2023 AMI', platform='Linux/UNIX'),
            Ami(image_id='ami-053b0d53c279acc90', name='Ubuntu Server 22.04 LTS', description='Canonical, Ubuntu, 22.04 LTS', platform='Linux/UNIX'),
            Ami(image_id='ami-0d5eff06f840b45e9', name='Microsoft Windows Server 2022 Base', description='Microsoft Windows Server 2022 Base', platform='Windows')
        ]

    def list_instance_types(self) -> List[str]:
        return [
            "t2.micro", "t3.micro", "t3.small", "t3.medium", "t3.large", "t3.xlarge", 
            "m5.large", "m5.xlarge", "c5.large", "c5.xlarge", "c6i.large", "r5.large"
        ]

    def list_vpcs(self) -> List[Vpc]:
        try:
            return self.adapter.list_vpcs(self.region)
        except Exception as e:
            logger.error(f"Error listing VPCs: {e}")
            raise

    def list_subnets(self, vpc_id: Optional[str] = None) -> List[Subnet]:
        try:
            return self.adapter.list_subnets(self.region, vpc_id=vpc_id)
        except Exception as e:
            logger.error(f"Error listing Subnets: {e}")
            raise

    def list_security_groups(self, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        try:
            return self.adapter.list_security_groups(self.region, vpc_id=vpc_id)
        except Exception as e:
            logger.error(f"Error listing SGs: {e}")
            raise

    def list_key_pairs(self) -> List[KeyPair]:
        try:
            return self.adapter.list_key_pairs(self.region)
        except Exception as e:
            logger.error(f"Error listing Key Pairs: {e}")
            raise

    def list_instances_for_cloning(self, tag_filters: Optional[List[Dict[str, str]]] = None) -> List[Instance]:
        """
        Lists instances to support the 'Clone' feature.
        Can filter by tags (e.g. [{'Key': 'Env', 'Value': 'Dev'}]).
        """
        try:
            return self.adapter.describe_instances(self.region, tag_filters=tag_filters)
        except Exception as e:
            logger.error(f"Error scanning instances: {e}")
            raise
