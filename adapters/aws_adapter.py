import boto3
import logging
from typing import List, Optional, Dict
from botocore.exceptions import ClientError, BotoCoreError
from core.models import Vpc, Subnet, SecurityGroup, InboundRule, Instance, Tag, Ami, KeyPair
from core.ports import CloudProviderPort

# MCCC: Explicit Logging Configuration
logger = logging.getLogger(__name__)


def _fmt_port_range(protocol: str, from_port: Optional[int], to_port: Optional[int]) -> str:
    if protocol == "all" or (from_port == -1 and to_port == -1):
        return "All"
    if from_port is None or to_port is None:
        return ""
    if from_port == to_port:
        return str(from_port)
    return f"{from_port}-{to_port}"


def _parse_inbound_rules(permissions: List[Dict]) -> List[InboundRule]:
    rules: List[InboundRule] = []
    for perm in permissions:
        raw_proto = perm.get("IpProtocol", "-1")
        protocol = "all" if raw_proto == "-1" else raw_proto
        port_range = _fmt_port_range(protocol, perm.get("FromPort"), perm.get("ToPort"))
        for ip in perm.get("IpRanges", []):
            rules.append(InboundRule(protocol=protocol, port_range=port_range,
                                     cidr=ip.get("CidrIp", "0.0.0.0/0"),
                                     description=ip.get("Description", "")))
        for ip6 in perm.get("Ipv6Ranges", []):
            rules.append(InboundRule(protocol=protocol, port_range=port_range,
                                     cidr=ip6.get("CidrIpv6", "::/0"),
                                     description=ip6.get("Description", "")))
    return rules

class AwsAdapter(CloudProviderPort):
    """
    AWS Implementation of CloudProviderPort using Boto3.
    """

    def __init__(self, profile_name: Optional[str] = None, region: Optional[str] = None):
        self.session = boto3.Session(profile_name=profile_name, region_name=region)
        self.ec2 = self.session.client("ec2")
        self.sts = self.session.client("sts")

    def _get_tags(self, resource_dict: dict) -> List[Tag]:
        """Helper to extract tags from boto3 response."""
        return [Tag(key=t["Key"], value=t["Value"]) for t in resource_dict.get("Tags", [])]

    def _get_name_from_tags(self, tags: List[Tag]) -> Optional[str]:
        """Helper to find Name tag."""
        for tag in tags:
            if tag.key == "Name":
                return tag.value
        return None

    def list_vpcs(self, region: str) -> List[Vpc]:
        try:
            # Note: client is created in __init__ with session region, 
            # if dynamic region switching is needed, we should recreate client or pass region to calls if supported.
            # Simplified: Assuming session region matches request or re-init client.
            # Ideally, we might want a factory or property for the client if regions change frequently.
            if region != self.session.region_name:
                 self.ec2 = self.session.client("ec2", region_name=region)

            response = self.ec2.describe_vpcs()
            vpcs = []
            for item in response.get("Vpcs", []):
                tags = self._get_tags(item)
                vpcs.append(Vpc(
                    vpc_id=item["VpcId"],
                    cidr_block=item["CidrBlock"],
                    is_default=item.get("IsDefault", False),
                    tags=tags,
                    state=item["State"],
                    name=self._get_name_from_tags(tags)
                ))
            return vpcs
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error listing VPCs: {e}")
            return []

    def list_subnets(self, region: str, vpc_id: Optional[str] = None) -> List[Subnet]:
        try:
            if region != self.session.region_name:
                 self.ec2 = self.session.client("ec2", region_name=region)

            filters = []
            if vpc_id:
                filters.append({"Name": "vpc-id", "Values": [vpc_id]})

            response = self.ec2.describe_subnets(Filters=filters) if filters else self.ec2.describe_subnets()
            subnets = []
            for item in response.get("Subnets", []):
                tags = self._get_tags(item)
                subnets.append(Subnet(
                    subnet_id=item["SubnetId"],
                    vpc_id=item["VpcId"],
                    cidr_block=item["CidrBlock"],
                    availability_zone=item["AvailabilityZone"],
                    tags=tags,
                    available_ip_address_count=item.get("AvailableIpAddressCount", 0),
                    state=item["State"],
                    name=self._get_name_from_tags(tags)
                ))
            return subnets
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error listing Subnets: {e}")
            return []

    def list_security_groups(self, region: str, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        try:
            if region != self.session.region_name:
                 self.ec2 = self.session.client("ec2", region_name=region)

            filters = []
            if vpc_id:
                filters.append({"Name": "vpc-id", "Values": [vpc_id]})
            
            response = self.ec2.describe_security_groups(Filters=filters) if filters else self.ec2.describe_security_groups()
            sgs = []
            for item in response.get("SecurityGroups", []):
                tags = self._get_tags(item)
                sgs.append(SecurityGroup(
                    group_id=item["GroupId"],
                    group_name=item["GroupName"],
                    description=item.get("Description", ""),
                    vpc_id=item.get("VpcId", ""),
                    tags=tags,
                    inbound_rules=_parse_inbound_rules(item.get("IpPermissions", [])),
                ))
            return sgs
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error listing Security Groups: {e}")
            return []

    def describe_instances(self, region: str, instance_ids: Optional[List[str]] = None, tag_filters: Optional[List[Dict[str, str]]] = None) -> List[Instance]:
        try:
            if region != self.session.region_name:
                 self.ec2 = self.session.client("ec2", region_name=region)

            kwargs = {}
            if instance_ids:
                kwargs["InstanceIds"] = instance_ids
            
            filters = []
            # We add a default filter to only fetch running or stopped instances (ignore terminated/pending for generic views)
            # This follows the original clone logic which asked for running | stopped.
            filters.append({'Name': 'instance-state-name', 'Values': ['running', 'stopped']})
            if tag_filters:
                for tag in tag_filters:
                    filters.append({'Name': f"tag:{tag['Key']}", 'Values': [tag['Value']]})
            
            if filters:
                kwargs["Filters"] = filters
            
            response = self.ec2.describe_instances(**kwargs)
            instances = []
            for reservation in response.get("Reservations", []):
                for item in reservation.get("Instances", []):
                    tags = self._get_tags(item)
                    # Safe extraction for nested fields
                    state = item["State"]["Name"]
                    public_ip = item.get("PublicIpAddress")
                    private_ip = item.get("PrivateIpAddress")
                    
                    # SGs
                    sgs = [SecurityGroup(
                        group_id=sg["GroupId"],
                        group_name=sg["GroupName"],
                        description="", # Not provided in instance description
                        vpc_id=item.get("VpcId", ""),
                        tags=[]
                    ) for sg in item.get("SecurityGroups", [])]

                    instances.append(Instance(
                        instance_id=item["InstanceId"],
                        instance_type=item["InstanceType"],
                        state=state,
                        public_ip=public_ip,
                        private_ip=private_ip,
                        vpc_id=item.get("VpcId", ""),
                        subnet_id=item.get("SubnetId", ""),
                        security_groups=sgs,
                        tags=tags,
                        image_id=item.get("ImageId", ""),
                        key_name=item.get("KeyName"),
                        name=self._get_name_from_tags(tags)
                    ))
            return instances
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error describing instances: {e}")
            return []

    def list_amis(
        self,
        region: str,
        owners: List[str],
        filters: Optional[List[Dict]] = None,
    ) -> List[Ami]:
        try:
            if region != self.session.region_name:
                self.ec2 = self.session.client("ec2", region_name=region)

            effective_filters = [{"Name": "state", "Values": ["available"]}]
            if filters:
                effective_filters.extend(filters)

            response = self.ec2.describe_images(
                Owners=owners,
                Filters=effective_filters,
            )
            amis = []
            for item in response.get("Images", []):
                tags = self._get_tags(item)
                amis.append(Ami(
                    image_id=item["ImageId"],
                    name=item.get("Name", "Unnamed"),
                    description=item.get("Description", ""),
                    platform=item.get("PlatformDetails", "Linux/UNIX"),
                    tags=tags,
                    creation_date=item.get("CreationDate"),
                    architecture=item.get("Architecture"),
                    virtualization_type=item.get("VirtualizationType"),
                    root_device_type=item.get("RootDeviceType"),
                    ena_support=item.get("EnaSupport"),
                ))
            return amis
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error listing AMIs: {e}")
            return []

    def list_key_pairs(self, region: str) -> List[KeyPair]:
        try:
            if region != self.session.region_name:
                 self.ec2 = self.session.client("ec2", region_name=region)
                 
            response = self.ec2.describe_key_pairs()
            keys = []
            for item in response.get("KeyPairs", []):
                keys.append(KeyPair(key_name=item["KeyName"]))
            return keys
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error listing Key Pairs: {e}")
            return []

    def validate_connection(self) -> bool:
        try:
            self.sts.get_caller_identity()
            return True
        except (ClientError, BotoCoreError):
            return False

    def get_available_regions(self) -> List[str]:
        try:
            response = self.ec2.describe_regions()
            return [r["RegionName"] for r in response.get("Regions", [])]
        except (ClientError, BotoCoreError):
            return []

    def get_import_orchestrator(self):
        """
        Creates and returns a VmImportOrchestrator configured with this adapter's session.
        """
        try:
            from tools.vm_importer.services import VmImportOrchestrator
            # We explicitly create the s3 client here, keeping the session private to the adapter.
            s3_client = self.session.client("s3")
            return VmImportOrchestrator(self.ec2, s3_client)
        except Exception as e:
            logger.error(f"Failed to create orchestrator: {e}")
            return None

    def get_instance_type_info(self, instance_type: str) -> dict:
        """
        Fetches vCPU and Memory info for the given instance type.
        """
        try:
            resp = self.ec2.describe_instance_types(InstanceTypes=[instance_type])
            types = resp.get("InstanceTypes", [])
            if not types:
                return {}
            
            info = types[0]
            vcpu = info.get("VCpuInfo", {}).get("DefaultVCpus", 0)
            mem = info.get("MemoryInfo", {}).get("SizeInMiB", 0)
            
            # Expanded Metadata
            proc_info = info.get("ProcessorInfo", {})
            clock_speed = proc_info.get("SustainedClockSpeedInGhz", 0.0)
            archs = info.get("ProcessorInfo", {}).get("SupportedArchitectures", [])
            arch_str = ",".join(archs) if archs else "unknown"
            
            # Format Label
            # e.g., "t3.medium (2 vCPU @ 2.5GHz, 4.0 GiB, x86_64)"
            label = f"{instance_type} ({vcpu} vCPU"
            if clock_speed > 0:
                label += f" @ {clock_speed} GHz"
            label += f", {mem/1024:.1f} GiB, {arch_str})"
            
            return {
                "vCPU": vcpu,
                "MemoryMiB": mem,
                "ClockSpeedGhz": clock_speed,
                "Architecture": arch_str,
                "Label": label
            }
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to describe instance type {instance_type}: {e}")
            return {}

    def list_buckets(self) -> List[str]:
        """Lists all S3 buckets."""
        try:
            # S3 is global, but we use the adapter's session
            s3 = self.session.client("s3")
            response = s3.list_buckets()
            return [b["Name"] for b in response.get("Buckets", [])]
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to list buckets: {e}")
            return []

    def run_instances(self, region: str, config: "LaunchConfig") -> "LaunchResult":
        """Launch EC2 instances per LaunchConfig; returns LaunchResult with IDs.

        Translates our clean LaunchConfig into the full boto3 run_instances
        payload — block device mappings, tag specifications, network interface.
        Each instance gets its own Name tag so they appear individually named
        in the AWS console.
        """
        from tools.ec2_launcher.models import LaunchConfig, LaunchResult  # local to avoid circular

        if region != self.session.region_name:
            self.ec2 = self.session.client("ec2", region_name=region)

        launched_ids: List[str] = []
        errors: List[tuple] = []

        # Build common block device mapping (root volume + any extras)
        bdm = [
            {
                "DeviceName": v.device_name,
                "Ebs": {
                    "VolumeSize": v.size_gb,
                    "VolumeType": v.volume_type,
                    "DeleteOnTermination": v.delete_on_termination,
                    "Encrypted": v.encrypted,
                    **({"Iops": v.iops} if v.iops else {}),
                    **({"Throughput": v.throughput_mbps} if v.throughput_mbps else {}),
                },
            }
            for v in (config.volumes or [])
        ]
        if not bdm:
            # Fallback: at minimum set root volume size from volume_gb
            bdm = [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": config.volume_gb,
                        "VolumeType": config.volume_type,
                        "DeleteOnTermination": True,
                    },
                }
            ]

        # Launch one instance per name so each gets its own tagged Name
        names = config.instance_names or [f"Instance-{i+1}" for i in range(config.instance_count)]
        for name in names:
            tags = {**config.tags, "Name": name}
            tag_spec = [
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
                }
            ]
            try:
                resp = self.ec2.run_instances(
                    ImageId=config.image_id,
                    InstanceType=config.instance_type,
                    MinCount=1,
                    MaxCount=1,
                    KeyName=config.key_name,
                    NetworkInterfaces=[
                        {
                            "DeviceIndex": 0,
                            "SubnetId": config.subnet_id,
                            "Groups": config.sg_ids,
                            "AssociatePublicIpAddress": True,
                        }
                    ],
                    BlockDeviceMappings=bdm,
                    TagSpecifications=tag_spec,
                )
                iid = resp["Instances"][0]["InstanceId"]
                launched_ids.append(iid)
                logger.info("Launched instance %s (%s)", iid, name)
            except (ClientError, BotoCoreError) as exc:
                logger.error("Failed to launch '%s': %s", name, exc)
                errors.append((name, str(exc)))

        if not launched_ids and errors:
            return LaunchResult(
                instance_ids=[],
                instance_names=[],
                region=region,
                error=errors[0][1],
                per_instance_errors=errors,
            )

        return LaunchResult(
            instance_ids=launched_ids,
            instance_names=names[: len(launched_ids)],
            region=region,
            per_instance_errors=errors,
        )

