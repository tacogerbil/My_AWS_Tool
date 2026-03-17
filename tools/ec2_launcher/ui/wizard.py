from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, 
                               QPushButton, QLabel, QFrame)
from PySide6.QtCore import Qt

# Import Panels
from tools.ec2_launcher.ui.summary import SummaryPanel
from tools.ec2_launcher.ui.stages import Stage1_Image, Stage2_Hardware, Stage3_Connectivity

class LauncherWizard(QWidget):
    """
    Main Split-Layout Wizard.
    Left: QStackedWidget (Stages)
    Right: SummaryPanel (Static)
    """
    def __init__(self, service=None):
        super().__init__()
        self.service = service
        self.resize(1100, 700)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- LEFT COLUMN (Config Stages) ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        
        # Header (Stage Tracker)
        self.header_lbl = QLabel("Step 1: Select Image")
        self.header_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        left_layout.addWidget(self.header_lbl)
        
        # Stacked Pages
        self.stack = QStackedWidget()
        self.stage1 = Stage1_Image()
        self.stage2 = Stage2_Hardware()
        self.stage3 = Stage3_Connectivity()
        
        self.stack.addWidget(self.stage1)
        self.stack.addWidget(self.stage2)
        self.stack.addWidget(self.stage3)
        
        left_layout.addWidget(self.stack)
        
        # Navigation Buttons
        nav_layout = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_next = QPushButton("Next")
        
        # Styling
        for btn in [self.btn_back, self.btn_next]:
            btn.setFixedSize(120, 40)
            btn.setStyleSheet("""
                QPushButton { font-size: 16px; border-radius: 5px; }
                QPushButton:enabled { background-color: #3498db; color: white; }
                QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
            """)
        
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next.clicked.connect(self.go_next)
        
        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_next)
        left_layout.addLayout(nav_layout)
        
        # --- RIGHT COLUMN (Summary) ---
        self.summary = SummaryPanel()
        
        # --- WIRING SIGNALS ---
        # Stage 1: AMI
        self.stage1.ami_selected.connect(self.summary.update_ami)
        self.stage1.clone_selected.connect(self.apply_clone_config)
        
        # Stage 2: Hardware
        self.stage2.type_changed.connect(self.summary.update_instance_type)
        self.stage2.storage_changed.connect(self.summary.update_storage)
        
        # Stage 3: Network
        self.stage3.network_changed.connect(self.summary.update_network)
        self.stage3.sg_changed.connect(self.summary.update_security_groups)
        
        # Add to Layout
        main_layout.addWidget(left_container, stretch=2) # 66% width
        main_layout.addWidget(self.summary, stretch=1)   # 33% width
        
        # Init State
        self.update_nav_state()
        
        # Load Data
        if self.service:
            self.load_data()
        else:
            print("Running with Mock Data (Service not connected)")

    def load_data(self):
        """Fetches data from AWS Service and populates Stages."""
        print("Loading AWS Data...")
        # 1. AMIs
        my_amis = self.service.list_my_amis()
        quick_amis = self.service.list_quick_start_amis()
        self.stage1.set_amis([], my_amis, quick_amis)
        
        # 2. Instances (for clone)
        instances = self.service.list_instances_for_cloning()
        self.stage1.set_clone_instances(instances)
        
        # 3. Hardware (Types)
        instance_types = self.service.list_instance_types()
        self.stage2.set_data(instance_types)
        
        # 4. Network
        vpcs = self.service.list_vpcs()
        subnets = self.service.list_subnets()
        sgs = self.service.list_security_groups()
        keys = self.service.list_key_pairs()
        
        self.stage3.set_data(vpcs, subnets, sgs, keys)
        print("AWS Data Loaded.")

    def apply_clone_config(self, inst_data):
        """Pre-fills the wizard based on cloned instance data."""
        from PySide6.QtWidgets import QMessageBox
        
        print(f"Cloning configuration from {inst_data.instance_id}...")
        
        # Step 1: AMI
        ami_id = inst_data.image_id
        self.stage1.ami_selected.emit(f"Cloned: {ami_id}") # Update summary
        # TODO: Select in list if present
        
        # Step 2: Hardware
        inst_type = inst_data.instance_type
        self.stage2.set_selected_type(inst_type)
        
        # Step 3: Network
        vpc = inst_data.vpc_id
        subnet = inst_data.subnet_id
        key = inst_data.key_name
        sgs = [sg.group_id for sg in inst_data.security_groups]
        
        self.stage3.set_selection(vpc, subnet, sgs, key)
        
        QMessageBox.information(self, "Clone Successful", 
                                f"Configuration copied from {inst_data.name if inst_data.name else 'Unnamed'}.\n"
                                f"Type: {inst_type}\nVPC: {vpc}")
        
        # Advance to next page?
        self.stack.setCurrentIndex(1) # Go to Hardware
        self.update_nav_state()

    def go_next(self):
        curr = self.stack.currentIndex()
        if curr < self.stack.count() - 1:
            self.stack.setCurrentIndex(curr + 1)
            self.update_nav_state()

    def go_back(self):
        curr = self.stack.currentIndex()
        if curr > 0:
            self.stack.setCurrentIndex(curr - 1)
            self.update_nav_state()
            
    def update_nav_state(self):
        curr = self.stack.currentIndex()
        self.btn_back.setEnabled(curr > 0)
        
        is_last = (curr == self.stack.count() - 1)
        self.btn_next.setText("Launch" if is_last else "Next")
        if is_last:
            self.btn_next.setStyleSheet("background-color: #2ecc71; color: white; border-radius: 5px; font-size: 16px;")
        else:
            self.btn_next.setStyleSheet("background-color: #3498db; color: white; border-radius: 5px; font-size: 16px;")
            
        # Update Header
        headers = ["Step 1: Select Image", "Step 2: Hardware Config", "Step 3: Network & Security"]
        self.header_lbl.setText(headers[curr])
