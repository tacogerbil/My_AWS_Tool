import boto3
import logging
from typing import Any, Dict, List, Optional
from botocore.exceptions import ClientError, BotoCoreError
from core.models import (
    Ami, CreatedKeyPair, InstanceTypeInfo,
    InboundRule, Instance, KeyPair, SecurityGroup, Subnet, Tag, Vpc,
)
from core.ports import CloudProviderPort, VmImportPort

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


def _rules_to_permissions(rules: List[InboundRule]) -> List[Dict]:
    """Convert InboundRule list to boto3 IpPermissions format."""
    perms: List[Dict] = []
    for rule in rules:
        proto = "-1" if rule.protocol == "all" else rule.protocol
        perm: Dict = {"IpProtocol": proto}
        if rule.protocol != "all" and rule.port_range not in ("", "All"):
            if "-" in rule.port_range:
                lo, hi = rule.port_range.split("-", 1)
                perm["FromPort"] = int(lo)
                perm["ToPort"]   = int(hi)
            elif rule.port_range.isdigit():
                perm["FromPort"] = int(rule.port_range)
                perm["ToPort"]   = int(rule.port_range)
        perm["IpRanges"] = [{"CidrIp": rule.cidr, "Description": rule.description}]
        perms.append(perm)
    return perms


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
    AWS implementation of CloudProviderPort, backed by boto3.

    All AWS I/O is isolated here; no boto3 types cross the adapter boundary.
    Region switching is handled by _ec2_for(region) which caches clients
    per-region — no shared mutable state, safe across threads.
    """

    def __init__(self, profile_name: Optional[str] = None, region: Optional[str] = None) -> None:
        self._session = boto3.Session(profile_name=profile_name, region_name=region)
        self._sts = self._session.client("sts")
        # Per-region EC2 client cache — populated lazily by _ec2_for(region).
        # Using a dict avoids the shared-state mutation that the old self.ec2 pattern caused.
        self._ec2_cache: Dict[str, Any] = {}

    def _ec2_for(self, region: str) -> Any:
        """Return a cached EC2 client for *region*, creating one on first use.

        This is the single place EC2 clients are created.  All read/write methods
        call this instead of mutating a shared self.ec2 attribute, making the
        adapter safe to call from multiple threads without data races.
        """
        if region not in self._ec2_cache:
            self._ec2_cache[region] = self._session.client("ec2", region_name=region)
        return self._ec2_cache[region]

    def _get_tags(self, resource_dict: dict) -> List[Tag]:
        """Extract Tag list from a boto3 response dict."""
        return [Tag(key=t["Key"], value=t["Value"]) for t in resource_dict.get("Tags", [])]

    def _get_name_from_tags(self, tags: List[Tag]) -> Optional[str]:
        """Return the value of the 'Name' tag, or None."""
        return next((t.value for t in tags if t.key == "Name"), None)

    def list_vpcs(self, region: str) -> List[Vpc]:
        try:
            ec2 = self._ec2_for(region)
            response = ec2.describe_vpcs()
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
            logger.error("Error listing VPCs: %s", e)
            return []

    def list_subnets(self, region: str, vpc_id: Optional[str] = None) -> List[Subnet]:
        try:
            ec2 = self._ec2_for(region)
            filters = ([{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else [])

            kwargs = {"Filters": filters} if filters else {}
            response = ec2.describe_subnets(**kwargs)
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
            logger.error("Error listing Subnets: %s", e)
            return []

    def list_security_groups(self, region: str, vpc_id: Optional[str] = None) -> List[SecurityGroup]:
        try:
            ec2 = self._ec2_for(region)
            filters = ([{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else [])
            kwargs = {"Filters": filters} if filters else {}
            response = ec2.describe_security_groups(**kwargs)
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
            logger.error("Error listing Security Groups: %s", e)
            return []

    def create_security_group(
        self,
        region: str,
        name: str,
        description: str,
        vpc_id: str,
        rules: List[InboundRule],
    ) -> SecurityGroup:
        ec2 = self._ec2_for(region)
        try:
            sg_id = ec2.create_security_group(
                GroupName=name, Description=description, VpcId=vpc_id
            )["GroupId"]
            if rules:
                ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=_rules_to_permissions(rules),
                )
            return SecurityGroup(
                group_id=sg_id, group_name=name,
                description=description, vpc_id=vpc_id, inbound_rules=rules,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Failed to create security group '%s': %s", name, exc)
            raise

    def describe_instances(
        self,
        region: str,
        instance_ids: Optional[List[str]] = None,
        tag_filters: Optional[List[Dict[str, str]]] = None,
        states: Optional[List[str]] = None,
    ) -> List[Instance]:
        """Describe EC2 instances, filtered by IDs, tags, and/or state.

        The ``states`` parameter is explicit — callers decide which states
        they care about rather than this adapter imposing hidden assumptions.
        """
        try:
            ec2 = self._ec2_for(region)

            kwargs: Dict = {}
            if instance_ids:
                kwargs["InstanceIds"] = instance_ids
            filters: List[Dict] = []
            if states:
                filters.append({"Name": "instance-state-name", "Values": states})
            if tag_filters:
                for tag in tag_filters:
                    filters.append({"Name": f"tag:{tag['Key']}", "Values": [tag["Value"]]})
            if filters:
                kwargs["Filters"] = filters
            response = ec2.describe_instances(**kwargs)
            instances = []
            for reservation in response.get("Reservations", []):
                for item in reservation.get("Instances", []):
                    tags = self._get_tags(item)
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
                        state=item["State"]["Name"],
                        public_ip=item.get("PublicIpAddress"),
                        private_ip=item.get("PrivateIpAddress"),
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
            logger.error("Error describing instances: %s", e)
            return []

    def list_amis(
        self,
        region: str,
        owners: List[str],
        filters: Optional[List[Dict]] = None,
    ) -> List[Ami]:
        try:
            ec2 = self._ec2_for(region)
            effective_filters = [{"Name": "state", "Values": ["available"]}]
            if filters:
                effective_filters.extend(filters)
            response = ec2.describe_images(Owners=owners, Filters=effective_filters)
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
            logger.error("Error listing AMIs: %s", e)
            return []

    def list_instance_profiles(self) -> List[str]:
        """Return sorted list of IAM instance profile names.

        IAM is a global service — no region parameter needed.
        Uses pagination so accounts with many profiles are handled correctly.
        """
        try:
            iam = self._session.client("iam")
            paginator = iam.get_paginator("list_instance_profiles")
            names: List[str] = [
                profile["InstanceProfileName"]
                for page in paginator.paginate()
                for profile in page.get("InstanceProfiles", [])
            ]
            return sorted(names)
        except (ClientError, BotoCoreError) as exc:
            # AccessDenied here is expected when the caller's IAM credentials
            # don't include iam:ListInstanceProfiles.  The field is optional,
            # so we degrade gracefully to an empty list rather than erroring.
            logger.debug("list_instance_profiles unavailable (likely IAM permission): %s", exc)
            return []

    def list_key_pairs(self, region: str) -> List[KeyPair]:
        try:
            ec2 = self._ec2_for(region)
            response = ec2.describe_key_pairs()
            return [KeyPair(key_name=item["KeyName"]) for item in response.get("KeyPairs", [])]
        except (ClientError, BotoCoreError) as e:
            logger.error("Error listing Key Pairs: %s", e)
            return []

    def create_key_pair(
        self,
        region: str,
        name: str,
        key_type: str = "rsa",
        key_format: str = "pem",
    ) -> CreatedKeyPair:
        """Create a new EC2 key pair and return the private key material (available once only)."""
        ec2 = self._ec2_for(region)
        response = ec2.create_key_pair(KeyName=name, KeyType=key_type, KeyFormat=key_format)
        return CreatedKeyPair(
            key_name=response["KeyName"],
            key_material=response["KeyMaterial"],
            key_fingerprint=response.get("KeyFingerprint", ""),
            key_type=key_type,
        )

    def validate_connection(self) -> bool:
        try:
            self._sts.get_caller_identity()
            return True
        except (ClientError, BotoCoreError):
            return False

    def get_available_regions(self) -> List[str]:
        try:
            ec2 = self._ec2_for(self._session.region_name or "us-east-1")
            response = ec2.describe_regions()
            return [r["RegionName"] for r in response.get("Regions", [])]
        except (ClientError, BotoCoreError):
            return []

    def get_import_orchestrator(self) -> VmImportPort:
        """Return a VmImportOrchestrator configured with this adapter's boto3 session."""
        try:
            from tools.vm_importer.services import VmImportOrchestrator
            s3_client = self._session.client("s3")
            ec2_client = self._ec2_for(self._session.region_name or "us-east-1")
            return VmImportOrchestrator(ec2_client, s3_client)  # type: ignore[return-value]
        except Exception as exc:
            logger.error("Failed to create import orchestrator: %s", exc)
            raise

    def get_instance_type_info(self, instance_type: str) -> InstanceTypeInfo:
        """Fetch and return structured metadata for an EC2 instance type."""
        try:
            ec2 = self._ec2_for(self._session.region_name or "us-east-1")
            resp = ec2.describe_instance_types(InstanceTypes=[instance_type])
            types = resp.get("InstanceTypes", [])
            if not types:
                return InstanceTypeInfo(instance_type=instance_type, vcpu=0, memory_mib=0)

            info         = types[0]
            vcpu         = info.get("VCpuInfo", {}).get("DefaultVCpus", 0)
            memory_mib   = info.get("MemoryInfo", {}).get("SizeInMiB", 0)
            clock_speed  = info.get("ProcessorInfo", {}).get("SustainedClockSpeedInGhz", 0.0)
            archs        = info.get("ProcessorInfo", {}).get("SupportedArchitectures", [])
            architecture = ",".join(archs) if archs else "unknown"

            label = f"{instance_type} ({vcpu} vCPU"
            if clock_speed > 0:
                label += f" @ {clock_speed} GHz"
            label += f", {memory_mib / 1024:.1f} GiB, {architecture})"

            return InstanceTypeInfo(
                instance_type=instance_type,
                vcpu=vcpu,
                memory_mib=memory_mib,
                clock_speed_ghz=clock_speed,
                architecture=architecture,
                label=label,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Failed to describe instance type %s: %s", instance_type, exc)
            return InstanceTypeInfo(instance_type=instance_type, vcpu=0, memory_mib=0)

    def put_ssm_parameters(self, region: str, params: Dict[str, str]) -> None:
        """Write credentials to SSM Parameter Store as KMS-encrypted SecureStrings."""
        from botocore.config import Config
        boto_config = Config(connect_timeout=5, read_timeout=5)
        ssm = self._session.client("ssm", region_name=region, config=boto_config)
        for name, value in params.items():
            ssm.put_parameter(Name=name, Value=value, Type="SecureString", Overwrite=True)
            logger.info("SSM parameter stored: %s", name)

    def list_buckets(self) -> List[str]:
        """List all S3 buckets (global service)."""
        try:
            s3 = self._session.client("s3")
            response = s3.list_buckets()
            return [b["Name"] for b in response.get("Buckets", [])]
        except (ClientError, BotoCoreError) as e:
            logger.error("Failed to list buckets: %s", e)
            return []

    # ------------------------------------------------------------------
    # run_instances — split into focused private helpers (SRP)
    # ------------------------------------------------------------------

    def run_instances(self, region: str, config: "LaunchConfig") -> "LaunchResult":
        """Launch EC2 instances per LaunchConfig; returns LaunchResult with IDs."""
        from tools.ec2_launcher.models import LaunchConfig, LaunchResult

        ec2 = self._ec2_for(region)
        # Domain join requires explicit instance names — no silent fallback.
        if config.user_data_template and not config.instance_names:
            raise ValueError(
                "Domain join requires explicit instance names. "
                "Auto-generated fallback names are forbidden when domain join is active."
            )
        bdm   = self._build_bdm(config)
        names = config.instance_names or [f"Instance-{i+1}" for i in range(config.instance_count)]
        launched_ids: List[str] = []
        errors: List[tuple]     = []

        for name in names:
            launched, error = self._launch_one(ec2, name, config, bdm)
            if launched:
                launched_ids.append(launched)
            if error:
                errors.append((name, error))

        if not launched_ids and errors:
            return LaunchResult(
                instance_ids=[], instance_names=[], region=region,
                error=errors[0][1], per_instance_errors=errors,
            )
        return LaunchResult(
            instance_ids=launched_ids,
            instance_names=names[:len(launched_ids)],
            region=region,
            per_instance_errors=errors,
        )

    def _build_bdm(self, config: "LaunchConfig") -> List[Dict]:
        """Build the EBS block device mapping list from LaunchConfig."""
        if config.volumes:
            return [
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
                for v in config.volumes
            ]
        # Fallback: set root volume from volume_gb
        return [{
            "DeviceName": "/dev/sda1",
            "Ebs": {
                "VolumeSize": config.volume_gb,
                "VolumeType": config.volume_type,
                "DeleteOnTermination": True,
            },
        }]

    @staticmethod
    def _build_tag_spec(name: str, tags: Dict[str, str]) -> List[Dict]:
        """Build a boto3 TagSpecification list for one instance."""
        merged = {**tags, "Name": name}
        return [{
            "ResourceType": "instance",
            "Tags": [{"Key": k, "Value": v} for k, v in merged.items()],
        }]

    def _launch_one(
        self,
        ec2: Any,
        name: str,
        config: "LaunchConfig",
        bdm: List[Dict],
    ) -> tuple:
        """Launch a single named instance; return (instance_id | None, error | None)."""
        userdata = (
            config.user_data_template.replace("<<INSTANCE_NAME>>", name)
            if config.user_data_template else None
        )
        kwargs: Dict = dict(
            ImageId=config.image_id,
            InstanceType=config.instance_type,
            MinCount=1,
            MaxCount=1,
            KeyName=config.key_name,
            NetworkInterfaces=[{
                "DeviceIndex": 0,
                "SubnetId": config.subnet_id,
                "Groups": config.sg_ids,
                "AssociatePublicIpAddress": config.associate_public_ip,
            }],
            BlockDeviceMappings=bdm,
            TagSpecifications=self._build_tag_spec(name, config.tags),
            MetadataOptions={
                "HttpTokens":   "required" if config.imdsv2_required else "optional",
                "HttpEndpoint": "enabled",
            },
        )
        if userdata:
            kwargs["UserData"] = userdata
        if config.iam_instance_profile:
            key = "Arn" if config.iam_instance_profile.startswith("arn:aws:iam::") else "Name"
            kwargs["IamInstanceProfile"] = {key: config.iam_instance_profile}
        try:
            resp = ec2.run_instances(**kwargs)
            iid  = resp["Instances"][0]["InstanceId"]
            logger.info("Launched instance %s (%s)", iid, name)
            if config.enable_termination_protection:
                self._enable_termination_protection(ec2, iid)
            return iid, None
        except (ClientError, BotoCoreError) as exc:
            logger.error("Failed to launch '%s': %s", name, exc)
            return None, str(exc)

    def _enable_termination_protection(self, ec2: Any, instance_id: str) -> None:
        """Best-effort: enable termination protection; logs warning on failure."""
        try:
            ec2.modify_instance_attribute(
                InstanceId=instance_id,
                DisableApiTermination={"Value": True},
            )
            logger.info("Termination protection enabled for %s", instance_id)
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "Could not enable termination protection for %s: %s", instance_id, exc
            )

