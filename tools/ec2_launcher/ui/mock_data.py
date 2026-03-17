# Mock Data for EC2 Launcher UI Prototype

MOCK_AMIS = [
    {"ImageId": "ami-0123456789abcdef0", "Name": "Windows_Server_2022_English_Full_Base", "Description": "Microsoft Windows Server 2022 Full Locale English AMI", "Platform": "Windows"},
    {"ImageId": "ami-0feb1904719abcdef", "Name": "Amazon-Linux-2023-AMI", "Description": "Amazon Linux 2023 Kernel 6.1", "Platform": "Linux"},
    {"ImageId": "ami-imported-001", "Name": "Imported-HyperV-01", "Description": "Legacy App Server (Imported)", "Platform": "Windows", "Tags": [{"Key": "CreatedBy", "Value": "AWS_Tool_Import"}]},
    {"ImageId": "ami-imported-002", "Name": "Ubuntu-22-Dev", "Description": "Development Environment", "Platform": "Linux"},
]

MOCK_INSTANCE_TYPES = [
    "t2.micro", "t3.micro", "t3.small", "t3.medium", "t3.large", "t3.xlarge", 
    "m5.large", "m5.xlarge", "c5.large", "c5.xlarge"
]

MOCK_VPCS = [
    {"VpcId": "vpc-11111111", "Name": "default-vpc", "IsDefault": True},
    {"VpcId": "vpc-22222222", "Name": "prod-vpc-01", "IsDefault": False},
]

MOCK_SUBNETS = [
    {"SubnetId": "subnet-1a", "VpcId": "vpc-11111111", "AvailabilityZone": "us-west-2a", "CidrBlock": "172.31.0.0/20"},
    {"SubnetId": "subnet-1b", "VpcId": "vpc-11111111", "AvailabilityZone": "us-west-2b", "CidrBlock": "172.31.16.0/20"},
    {"SubnetId": "subnet-2a", "VpcId": "vpc-22222222", "AvailabilityZone": "us-west-2a", "CidrBlock": "10.0.1.0/24"},
]

MOCK_SECURITY_GROUPS = [
    {"GroupId": "sg-111", "GroupName": "default", "Description": "default VPC security group"},
    {"GroupId": "sg-222", "GroupName": "web-server-sg", "Description": "Allow HTTP/HTTPS"},
    {"GroupId": "sg-333", "GroupName": "rdp-access", "Description": "Allow RDP from Office"},
]

MOCK_RECENTS = [
    {"ImageId": "ami-imported-001", "Name": "Imported-HyperV-01", "LastLaunched": "2023-10-25"},
    {"ImageId": "ami-0feb1904719abcdef", "Name": "Amazon-Linux-2023-AMI", "LastLaunched": "2023-10-20"},
]

MOCK_QUICKSTART = [
    {"Name": "Amazon Linux 2023", "Icon": "linux"},
    {"Name": "Ubuntu 22.04 LTS", "Icon": "ubuntu"},
    {"Name": "Windows Server 2022", "Icon": "windows"},
    {"Name": "Red Hat Enterprise Linux 9", "Icon": "redhat"},
]

MOCK_KEY_PAIRS = ["my-laptop-key", "prod-server-key", "dev-team-key"]
