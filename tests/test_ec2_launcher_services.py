import pytest
from unittest.mock import MagicMock, call
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

    mock_adapter.list_amis.assert_called_once_with("us-west-2", owners=["self"])
    assert len(result) == 1
    assert result[0].image_id == "ami-123"


def test_list_my_amis_bubbles_exceptions(service, mock_adapter):
    mock_adapter.list_amis.side_effect = Exception("Adapter Failure")

    with pytest.raises(Exception, match="Adapter Failure"):
        service.list_my_amis()


def test_list_quick_start_amis_fetches_from_aws(service, mock_adapter):
    """Quick Start should call adapter.list_amis for each OS owner group."""
    mock_ami = Ami(
        image_id="ami-abc",
        name="al2023-ami-2023.4.1-kernel-6.1-x86_64",
        description="Amazon Linux 2023",
        platform="Linux/UNIX",
        creation_date="2024-01-01T00:00:00.000Z",
    )
    mock_adapter.list_amis.return_value = [mock_ami]

    result = service.list_quick_start_amis()

    # One call per unique owner group (amazon, Canonical, RedHat, SUSE, Debian)
    assert mock_adapter.list_amis.call_count == 5
    assert all(isinstance(a, Ami) for a in result)
    assert len(result) >= 1


def test_list_quick_start_amis_picks_latest_per_pattern(service, mock_adapter):
    """When multiple AMIs match a pattern, only the newest is returned."""
    old = Ami("ami-old", "al2023-ami-2023.1.0-kernel-6.1-x86_64", "", "Linux/UNIX",
              creation_date="2023-01-01T00:00:00.000Z")
    new = Ami("ami-new", "al2023-ami-2023.4.0-kernel-6.1-x86_64", "", "Linux/UNIX",
              creation_date="2024-06-01T00:00:00.000Z")

    def _side_effect(region, owners, filters=None):
        if "amazon" in owners:
            return [old, new]
        return []

    mock_adapter.list_amis.side_effect = _side_effect

    result = service.list_quick_start_amis()

    ids = [a.image_id for a in result]
    assert "ami-new" in ids
    assert "ami-old" not in ids


def test_list_quick_start_amis_falls_back_on_error(service, mock_adapter):
    """Falls back to hardcoded list if all AWS calls fail."""
    mock_adapter.list_amis.side_effect = Exception("AWS error")

    result = service.list_quick_start_amis()

    assert len(result) >= 1
    assert all(isinstance(a, Ami) for a in result)


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
