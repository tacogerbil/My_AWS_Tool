import logging
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QPushButton, QMessageBox, QLabel, QHBoxLayout
from core.services import ResourceService
from ui.gui.widgets.vpc_table import VpcTableWidget
from ui.gui.widgets.subnet_table import SubnetTableWidget
from ui.gui.widgets.instance_table import InstanceTableWidget

class ResourceBrowser(QMainWindow):
    """
    Secondary Window for browsing AWS Resources.
    Independently viewable from the Landing Window.
    """
    def __init__(self, service: ResourceService, current_region: str):
        super().__init__()
        self.service = service
        self.current_region = current_region
        self.logger = logging.getLogger("ResourceBrowser")
        
        self.setWindowTitle(f"AWS Resource Browser - {current_region}")
        self.resize(1024, 768)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # Header / Controls
        self.controls_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Resources")
        self.refresh_btn.clicked.connect(self.refresh_all)
        
        self.controls_layout.addWidget(self.refresh_btn)
        self.controls_layout.addStretch()
        self.main_layout.addLayout(self.controls_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Initialize Tabs
        self.vpc_tab = VpcTableWidget()
        self.tabs.addTab(self.vpc_tab, "VPCs")
        
        self.subnet_tab = SubnetTableWidget()
        self.tabs.addTab(self.subnet_tab, "Subnets")

        self.instance_tab = InstanceTableWidget()
        self.tabs.addTab(self.instance_tab, "Instances")
        
        # Initial Load
        self.refresh_all()

    def refresh_all(self):
        """Refreshes data in all active tabs."""
        self.logger.info("Refreshing browser data...")
        try:
            # VPCs
            vpcs = self.service.list_all_vpcs(self.current_region)
            self.vpc_tab.update_data(vpcs)
            
            # Subnets
            subnets = self.service.list_subnets_for_vpc(self.current_region, vpc_id=None)
            self.subnet_tab.update_data(subnets)

            # Instances
            instances = self.service.list_instances(self.current_region)
            self.instance_tab.update_data(instances)

            self.logger.info(f"Loaded {len(vpcs)} VPCs, {len(subnets)} Subnets, {len(instances)} Instances.")
        except Exception as e:
            self.logger.error(f"Error refreshing data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to refresh data:\n{e}")
