from typing import List
from ui.gui.widgets.base_table import BaseTableWidget
from core.models import Vpc

class VpcTableWidget(BaseTableWidget):
    """
    Widget to display a list of VPCs.
    """
    def __init__(self):
        headers = ["VPC ID", "CIDR", "Name", "State", "Is Default"]
        super().__init__(headers)

    def update_data(self, vpcs: List[Vpc]):
        """Refreshes the table with new data."""
        self.clear()
        for vpc in vpcs:
            name = vpc.name if vpc.name else "-"
            self._add_row([
                vpc.vpc_id,
                vpc.cidr_block,
                name,
                vpc.state,
                str(vpc.is_default)
            ])
