from typing import List
from ui.gui.widgets.base_table import BaseTableWidget
from core.models import Subnet

class SubnetTableWidget(BaseTableWidget):
    """
    Widget to display a list of Subnets.
    """
    def __init__(self):
        headers = ["Subnet ID", "CIDR", "AZ", "VPC ID", "IPs Available", "Name"]
        super().__init__(headers)

    def update_data(self, subnets: List[Subnet]):
        """Refreshes the table with new data."""
        self.clear()
        for sn in subnets:
            name = sn.name if sn.name else "-"
            self._add_row([
                sn.subnet_id,
                sn.cidr_block,
                sn.availability_zone,
                sn.vpc_id,
                str(sn.available_ip_address_count),
                name
            ])
