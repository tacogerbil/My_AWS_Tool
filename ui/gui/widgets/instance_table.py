from typing import List
from ui.gui.widgets.base_table import BaseTableWidget
from core.models import Instance

class InstanceTableWidget(BaseTableWidget):
    """
    Widget to display a list of Instances.
    """
    def __init__(self):
        headers = ["Instance ID", "Name", "Type", "State", "Public IP", "Private IP", "VPC ID"]
        super().__init__(headers)

    def update_data(self, instances: List[Instance]):
        """Refreshes the table with new data."""
        self.clear()
        for i in instances:
            name = i.name if i.name else "-"
            pub_ip = i.public_ip if i.public_ip else "-"
            priv_ip = i.private_ip if i.private_ip else "-"
            self._add_row([
                i.instance_id,
                name,
                i.instance_type,
                i.state,
                pub_ip,
                priv_ip,
                i.vpc_id
            ])
