import pytest
import boto3
from botocore.stub import Stubber
from adapters.aws_adapter import AwsAdapter
from core.models import Vpc, Subnet

@pytest.fixture
def aws_adapter():
    """Returns an AwsAdapter with mocked clients."""
    adapter = AwsAdapter(region="us-east-1")
    return adapter

def test_list_vpcs(aws_adapter):
    # Activate stubber
    with Stubber(aws_adapter.ec2) as stubber:
        # Define expected response
        response = {
            "Vpcs": [
                {
                    "VpcId": "vpc-123",
                    "CidrBlock": "10.0.0.0/16",
                    "State": "available",
                    "IsDefault": False,
                    "Tags": [{"Key": "Name", "Value": "Test-VPC"}]
                }
            ]
        }
        stubber.add_response("describe_vpcs", response)
        
        # Call method
        vpcs = aws_adapter.list_vpcs("us-east-1")
        
        # Verify
        assert len(vpcs) == 1
        assert vpcs[0].vpc_id == "vpc-123"
        assert vpcs[0].name == "Test-VPC"
        assert vpcs[0].cidr_block == "10.0.0.0/16"

def test_list_subnets_with_filter(aws_adapter):
    with Stubber(aws_adapter.ec2) as stubber:
        response = {
            "Subnets": [
                {
                    "SubnetId": "subnet-1",
                    "VpcId": "vpc-123",
                    "CidrBlock": "10.0.1.0/24",
                    "AvailabilityZone": "us-east-1a",
                    "State": "available",
                    "AvailableIpAddressCount": 250,
                    "Tags": [{"Key": "Name", "Value": "Subnet-1"}]
                }
            ]
        }
        # Expectation includes filter
        expected_params = {"Filters": [{"Name": "vpc-id", "Values": ["vpc-123"]}]}
        stubber.add_response("describe_subnets", response, expected_params)
        
        subnets = aws_adapter.list_subnets("us-east-1", vpc_id="vpc-123")
        
        assert len(subnets) == 1
        assert subnets[0].subnet_id == "subnet-1"
        assert subnets[0].vpc_id == "vpc-123"

def test_validate_connection_success(aws_adapter):
    with Stubber(aws_adapter.sts) as stubber:
        stubber.add_response("get_caller_identity", {"Account": "123", "Arn": "arn:aws:iam::123:user/test", "UserId": "AID..."})
        assert aws_adapter.validate_connection() is True

def test_validate_connection_fail(aws_adapter):
    with Stubber(aws_adapter.sts) as stubber:
        stubber.add_client_error("get_caller_identity", "AuthFailure")
        assert aws_adapter.validate_connection() is False
