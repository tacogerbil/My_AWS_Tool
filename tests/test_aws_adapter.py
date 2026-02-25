import sys
import pytest
import boto3
from botocore.stub import Stubber
from adapters.aws_adapter import AwsAdapter
from core.models import Vpc, Subnet
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# check_computer_exists
# ---------------------------------------------------------------------------
# ldap3 is imported lazily inside the function body, so we must inject a mock
# via sys.modules rather than patch module-level names in ad_adapter.

def _build_mock_ldap3(entries):
    """Return a mock ldap3 module whose Connection returns entries on .search()."""
    mock_ldap3 = MagicMock()
    mock_conn = MagicMock()
    mock_conn.entries = entries
    mock_ldap3.Connection.return_value = mock_conn
    # Expose the constants the function uses (ALL, NTLM, SUBTREE)
    mock_ldap3.ALL = "ALL"
    mock_ldap3.NTLM = "NTLM"
    mock_ldap3.SUBTREE = "SUBTREE"
    return mock_ldap3, mock_conn


def test_check_computer_exists_found():
    """Returns the DN string when the computer account exists in AD."""
    from adapters.ad_adapter import check_computer_exists

    existing_dn = "CN=WEBSERVER-01,OU=Servers,DC=corp,DC=example,DC=com"
    mock_entry = MagicMock()
    mock_entry.distinguishedName.__str__ = lambda _: existing_dn

    mock_ldap3, mock_conn = _build_mock_ldap3([mock_entry])

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        result = check_computer_exists(
            dc_host="dc01.corp.example.com",
            domain="corp.example.com",
            username="CORP\\svc-launcher",
            password="secret",
            computer_name="WEBSERVER-01",
        )

    assert result == existing_dn
    mock_conn.search.assert_called_once()
    search_args = mock_conn.search.call_args
    assert "(&(objectClass=computer)(sAMAccountName=WEBSERVER-01$))" in str(search_args)


def test_check_computer_exists_not_found():
    """Returns None when no matching computer account exists."""
    from adapters.ad_adapter import check_computer_exists

    mock_ldap3, _ = _build_mock_ldap3([])  # empty result set

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        result = check_computer_exists(
            dc_host="dc01.corp.example.com",
            domain="corp.example.com",
            username="CORP\\svc-launcher",
            password="secret",
            computer_name="NEW-SERVER-01",
        )

    assert result is None


def test_check_computer_exists_connection_error():
    """Propagates the exception on LDAP connection failure."""
    from adapters.ad_adapter import check_computer_exists

    mock_ldap3 = MagicMock()
    mock_ldap3.Connection.side_effect = Exception("LDAP connection refused")
    mock_ldap3.ALL = "ALL"
    mock_ldap3.NTLM = "NTLM"
    mock_ldap3.SUBTREE = "SUBTREE"

    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        with pytest.raises(Exception, match="LDAP connection refused"):
            check_computer_exists(
                dc_host="unreachable.example.com",
                domain="corp.example.com",
                username="CORP\\svc-launcher",
                password="secret",
                computer_name="ANY-NAME",
            )
