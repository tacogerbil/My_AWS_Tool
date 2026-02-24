import pytest
from unittest.mock import MagicMock
from tools.ec2_launcher.services import LauncherService
from core.models import Ami, Instance, KeyPair, Vpc, Subnet, SecurityGroup

@pytest.fixture
def mock_adapter():
    return MagicMock()

@pytest.fixture
def service(mock_adapter):
    return LauncherService(adapter=mock_adapter, region="us-west-2")

def test_list_my_amis_success(service, mock_adapter):
    mock_ami = Ami(image_id="ami-123", name="Test Ami", description="Desc", platform="Linux")
    mock_adapter.list_amis.return_value = [mock_ami]

    result = service.list_my_amis()
    
    # Assert side-effect logic properly delegates to port
    mock_adapter.list_amis.assert_called_once_with("us-west-2", owners=['self'])
    assert len(result) == 1
    assert result[0].image_id == "ami-123"

def test_list_my_amis_bubbles_exceptions(service, mock_adapter):
    mock_adapter.list_amis.side_effect = Exception("Adapter Failure")
    
    # Assert Fail Fast Law
    with pytest.raises(Exception, match="Adapter Failure"):
        service.list_my_amis()

def test_list_quick_start_amis(service):
    # Pure function behavior verification
    result = service.list_quick_start_amis()
    assert len(result) == 3
    assert all(isinstance(ami, Ami) for ami in result)

def test_list_vpcs(service, mock_adapter):
    mock_vpc = Vpc(vpc_id="vpc-1", cidr_block="10.0.0.0/16", is_default=False, state="available")
    mock_adapter.list_vpcs.return_value = [mock_vpc]

    result = service.list_vpcs()

    mock_adapter.list_vpcs.assert_called_once_with("us-west-2")
    assert len(result) == 1
    assert result[0].vpc_id == "vpc-1"

def test_list_instances_for_cloning(service, mock_adapter):
    mock_instance = Instance(
        instance_id="i-123", instance_type="t3.micro", state="running",
        public_ip=None, private_ip=None, vpc_id="vpc-1", subnet_id="subnet-1"
    )
    mock_adapter.describe_instances.return_value = [mock_instance]
    tags = [{"Key": "Env", "Value": "Dev"}]
    
    result = service.list_instances_for_cloning(tag_filters=tags)

    mock_adapter.describe_instances.assert_called_once_with("us-west-2", tag_filters=tags)
    assert len(result) == 1
    assert result[0].instance_id == "i-123"
