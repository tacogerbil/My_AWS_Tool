from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                               QPushButton, QFileDialog, QFormLayout, QProgressBar, 
                               QMessageBox, QGroupBox, QComboBox, QListWidget, QListWidgetItem, QTextEdit, QCompleter, QApplication)
from PySide6.QtCore import Qt
import os
import logging
from ui.gui.resource_browser import ResourceBrowser

class LandingWindow(QMainWindow):
    """
    Primary Application Window (formerly ImportVmDialog).
    Features:
    - Split Layout (Presets vs Config)
    - Subnet population logic fixed.
    - Integration with ResourceBrowser (Secondary Window).
    """
    
    def __init__(self, service, current_region, config=None, config_adapter=None):
        super().__init__()
        self.service = service
        self.region = current_region
        self._config = config
        self._config_adapter = config_adapter
        self.logger = logging.getLogger("LandingWindow")
        
        # We need an orchestrator. Ideally passed in or created via adapter.
        # Since this is now the main entry, we get it from service.
        self.orchestrator = self.service.adapter.get_import_orchestrator()

        self.setWindowTitle("AWS Tool - VM Import/Export")
        self.resize(1000, 700)
        
        # Keep reference to secondary window so it doesn't GC
        self.resource_browser = None
        self.abort_flag = False 
        
        # Central Widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Top Bar (Menu-like)
        top_layout = QHBoxLayout()
        self.browser_btn = QPushButton("Open Resource Browser")
        self.browser_btn.clicked.connect(self.open_resource_browser)
        top_layout.addWidget(QLabel(f"Region: {self.region}"))
        top_layout.addStretch()
        top_layout.addWidget(self.browser_btn)
        
        # Main Split Content
        self.main_layout = QHBoxLayout()
        
        self._setup_left_panel()
        self._setup_right_panel()
        
        # Global Layout
        global_layout = QVBoxLayout(central)
        global_layout.addLayout(top_layout)
        global_layout.addLayout(self.main_layout)
        
        # Load Data
        self.load_data()

    def open_resource_browser(self):
        """Opens the browsing window non-modally."""
        if self.resource_browser is None:
            self.resource_browser = ResourceBrowser(self.service, self.region)
        
        self.resource_browser.show()
        self.resource_browser.raise_()
        self.resource_browser.activateWindow()

    def _setup_left_panel(self):
        """Constructs the Left Panel (AWS Resources Presets)."""
        self.left_panel = QGroupBox("AWS Resources (Presets)")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_panel.setFixedWidth(350)
        
        # VPC
        self.left_layout.addWidget(QLabel("Select VPC:"))
        self.vpc_combo = QComboBox()
        self.vpc_combo.currentIndexChanged.connect(self.on_vpc_changed)
        self.left_layout.addWidget(self.vpc_combo)
        
        # Subnet
        self.left_layout.addWidget(QLabel("Select Subnet:"))
        self.subnet_combo = QComboBox()
        self.subnet_combo.currentIndexChanged.connect(self.update_info_box)
        self.left_layout.addWidget(self.subnet_combo)
        
        # Instance Type
        self.left_layout.addWidget(QLabel("Select Instance Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["t2.micro", "t3.medium", "m5.large", "c5.large"])
        self.type_combo.setEditable(True) 
        self.type_combo.currentTextChanged.connect(self.update_info_box)
        self.left_layout.addWidget(self.type_combo)
        
        # Existing Instances List
        self.left_layout.addWidget(QLabel("Existing Instances:"))
        self.instance_list = QListWidget()
        self.instance_list.itemClicked.connect(self.on_instance_clicked)
        self.left_layout.addWidget(self.instance_list)
        
        self.main_layout.addWidget(self.left_panel)

    def _setup_right_panel(self):
        """Constructs the Right Panel (Import Configuration)."""
        self.right_panel = QGroupBox("VM Import & Configuration")
        self.right_layout = QVBoxLayout(self.right_panel)
        
        # Form for File/Bucket
        self.form_layout = QFormLayout()
        
        self.file_input = QLineEdit()
        self.file_btn = QPushButton("Browse...")
        self.file_btn.clicked.connect(self.browse_file)
        
        browse_layout = QHBoxLayout()
        browse_layout.addWidget(self.file_input)
        browse_layout.addWidget(self.file_btn)
        
        # S3 Bucket (Dropdown)
        self.bucket_combo = QComboBox()
        self.bucket_combo.setEditable(True) 
        self.bucket_combo.setPlaceholderText("Select or enter bucket name")
        # Enable "MatchContains" (substring matching) for the dropdown
        self.bucket_combo.completer().setFilterMode(Qt.MatchContains)
        self.bucket_combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("My Server Image")
        
        # Advanced Settings Group
        self.advanced_group = QGroupBox("Import Settings")
        adv_layout = QFormLayout(self.advanced_group)
        
        # Boot Mode
        self.boot_combo = QComboBox()
        self.boot_combo.addItems(["legacy-bios", "uefi"])
        
        # Platform
        self.plat_combo = QComboBox()
        self.plat_combo.addItems(["Windows", "Linux"])
        
        # Architecture
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["x86_64", "arm64"])
        
        # License
        self.lic_combo = QComboBox()
        self.lic_combo.addItems(["BYOL", "AWS"])
        self.lic_combo.setToolTip("BYOL: Use your own license. AWS: Use AWS provided license (if available).")

        adv_layout.addRow("Boot Mode:", self.boot_combo)
        adv_layout.addRow("Platform:", self.plat_combo)
        adv_layout.addRow("Architecture:", self.arch_combo)
        adv_layout.addRow("License:", self.lic_combo)

        self.form_layout.addRow("VM File:", browse_layout)
        self.form_layout.addRow("S3 Bucket:", self.bucket_combo)
        self.form_layout.addRow("Description:", self.desc_input)
        self.form_layout.addRow(self.advanced_group)
        
        self.right_layout.addLayout(self.form_layout)
        
        # Info / Summary Area
        self.right_layout.addWidget(QLabel("Selected Resources Information:"))
        self.info_area = QTextEdit()
        self.info_area.setReadOnly(True)
        self.right_layout.addWidget(self.info_area)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        # Use helper for initial style (0%)
        from ui.common.styles import get_progress_bar_style
        self.progress_bar.setStyleSheet(get_progress_bar_style(0))
        self.right_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.right_layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel Upload")
        self.cancel_btn.clicked.connect(self.request_cancellation)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 6px;")
        
        self.import_btn = QPushButton("Start Import")
        self.import_btn.clicked.connect(self.start_import)
        self.import_btn.setStyleSheet("background-color: #2c7bb6; color: white; font-weight: bold; padding: 6px;")
        
        # Removed Cancel, not needed on Main Window
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.import_btn)
        self.right_layout.addLayout(btn_layout)
        
        self.main_layout.addWidget(self.right_panel)

    def load_data(self):
        """Fetches VPCs and Instances to populate widgets."""
        try:
            # VPCs
            vpcs = self.service.list_all_vpcs(self.region)
            self.vpc_combo.blockSignals(True)
            self.vpc_combo.clear()
            self.vpcs_map = {} # Cache VPC objects
            
            for v in vpcs:
                name = v.name if v.name else v.vpc_id
                self.vpc_combo.addItem(f"{name} ({v.cidr_block})", v.vpc_id)
                self.vpcs_map[v.vpc_id] = v
                
            self.vpc_combo.blockSignals(False)
            
            # Initial subnet load for first VPC
            if self.vpc_combo.count() > 0:
                self.on_vpc_changed(0) 
                
            # Instances
            self.instances_map = {} 
            instances = self.service.list_instances(self.region)
            self.instance_list.clear()
            for i in instances:
                name = i.name if i.name else i.instance_id
                label = f"{name} - {i.instance_type}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, i.instance_id)
                self.instance_list.addItem(item)
                self.instances_map[i.instance_id] = i

            # Load Buckets
            buckets = self.service.list_buckets()
            self.bucket_combo.clear()
            self.bucket_combo.addItems(buckets)
                
        except Exception as e:
            self.logger.error(f"Failed to load data: {e}")
            QMessageBox.warning(self, "Data Load Error", str(e))

    def on_vpc_changed(self, index):
        """Loads subnets for the selected VPC."""
        vpc_id = self.vpc_combo.itemData(index)
        if not vpc_id:
            return
            
        try:
            subnets = self.service.list_subnets_for_vpc(self.region, vpc_id)
            self.subnet_combo.blockSignals(True)
            self.subnet_combo.clear()
            self.subnets_map = {} # Cache Subnet objects
            
            for s in subnets:
                name = s.name if s.name else s.subnet_id
                self.subnet_combo.addItem(f"{name} ({s.cidr_block})", s.subnet_id)
                self.subnets_map[s.subnet_id] = s
                
            self.subnet_combo.blockSignals(False)
            
            self.update_info_box()
            
        except Exception as e:
            self.logger.error(f"Failed to load subnets: {e}")

    def on_instance_clicked(self, item):
        """Populates fields based on selected instance."""
        inst_id = item.data(Qt.UserRole)
        instance = self.instances_map.get(inst_id)
        if not instance:
            return
            
        # 1. Type
        idx = self.type_combo.findText(instance.instance_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        else:
            self.type_combo.setEditText(instance.instance_type)
            
        # 2. VPC
        found_vpc = False
        for i in range(self.vpc_combo.count()):
            if self.vpc_combo.itemData(i) == instance.vpc_id:
                self.vpc_combo.setCurrentIndex(i) 
                found_vpc = True
                break
        
        if found_vpc:
            # 3. Subnet 
            for i in range(self.subnet_combo.count()):
                if self.subnet_combo.itemData(i) == instance.subnet_id:
                    self.subnet_combo.setCurrentIndex(i)
                    break

        self.desc_input.setText(f"Import based on {instance.name or instance.instance_id}")
        self.update_info_box()

    def update_info_box(self, _=None):
        """Updates the info text area with rich HTML details."""
        vpc_html = self._format_vpc_html()
        subnet_html = self._format_subnet_html()
        type_html = self._format_type_html()

        # Combine into Table-like layout using HTML
        html_content = f"""
        <h3>Target Configuration</h3>
        <table width="100%" cellspacing="4">
            <tr>
                <td valign="top" width="50%">
                    <h4>VPC Details</h4>
                     {vpc_html}
                </td>
                <td valign="top" width="50%">
                    <h4>Subnet Details</h4>
                    {subnet_html}
                </td>
            </tr>
            <tr>
                <td colspan="2">
                    <h4>Instance Specification</h4>
                    {type_html}
                </td>
            </tr>
        </table>
        """
        self.info_area.setHtml(html_content)

    def _format_vpc_html(self) -> str:
        vpc_id = self.vpc_combo.currentData()
        vpc_obj = self.vpcs_map.get(vpc_id)
        if not vpc_obj:
            return "<i>None selected</i>"
            
        state_color = "green" if vpc_obj.state == "available" else "red"
        return (
            f"<b>ID:</b> {vpc_obj.vpc_id}<br>"
            f"<b>CIDR:</b> {vpc_obj.cidr_block}<br>"
            f"<b>State:</b> <span style='color:{state_color}; font-weight:bold'>{vpc_obj.state}</span><br>"
            f"<b>Default:</b> {vpc_obj.is_default}"
        )

    def _format_subnet_html(self) -> str:
        subnet_id = self.subnet_combo.currentData()
        subnet_map = getattr(self, 'subnets_map', {})
        subnet_obj = subnet_map.get(subnet_id)
        if not subnet_obj:
            return "<i>None selected</i>"

        s_state_color = "green" if subnet_obj.state == "available" else "red"
        return (
            f"<b>ID:</b> {subnet_obj.subnet_id}<br>"
            f"<b>CIDR:</b> {subnet_obj.cidr_block}<br>"
            f"<b>AZ:</b> {subnet_obj.availability_zone}<br>"
            f"<b>IPs Available:</b> {subnet_obj.available_ip_address_count}<br>"
            f"<b>State:</b> <span style='color:{s_state_color}; font-weight:bold'>{subnet_obj.state}</span>"
        )

    def _format_type_html(self) -> str:
        inst_type = self.type_combo.currentText()
        if not inst_type:
             return "<i>None selected</i>"
             
        data = self.service.get_instance_type_info(inst_type)
        details = data.label if data else "Unknown"
        return f"<b>{inst_type}</b><br>{details}"

    def browse_file(self):
        start_dir = ""
        if self._config and self._config.last_vm_dir:
            start_dir = self._config.last_vm_dir

        fname, _ = QFileDialog.getOpenFileName(
            self, "Select VM Image", start_dir,
            "VM Images (*.ova *.vhd *.vhdx *.vmdk *.raw)",
        )
        if fname:
            self.file_input.setText(fname)
            if self._config is not None and self._config_adapter is not None:
                self._config.last_vm_dir = os.path.dirname(fname)
                self._config_adapter.save(self._config)

    def request_cancellation(self):
        """Sets the abort flag."""
        self.abort_flag = True
        self.status_label.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)

    def start_import(self):
        file_path = self.file_input.text()
        bucket = self.bucket_combo.currentText()
        desc = self.desc_input.text()
        
        if not file_path or not bucket:
            QMessageBox.warning(self, "Missing Info", "Please provide File and Bucket.")
            return
            
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Error", "File does not exist.")
            return
            
        if not self.orchestrator:
             QMessageBox.critical(self, "Error", "Orchestrator not initialized.")
             return

        self.import_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing upload...")
        
        self.abort_flag = False

        from ui.common.styles import get_progress_bar_style

        def progress_callback(msg, percent):
            self.status_label.setText(msg)
            self.progress_bar.setValue(percent)
            self.progress_bar.setStyleSheet(get_progress_bar_style(percent))
            QApplication.processEvents() 
            
        def abort_check():
            QApplication.processEvents() # Ensure clicks are registered
            return self.abort_flag
            
        boot_mode = self.boot_combo.currentText()
        platform = self.plat_combo.currentText()
        license_type = self.lic_combo.currentText()
        arch = self.arch_combo.currentText()
        
        try:
            task_id = self.orchestrator.upload_and_import(
                file_path, bucket, desc, progress_callback, abort_check,
                boot_mode, platform, license_type, arch
            )
            
            if task_id:
                # Success - Launch Monitor
                from tools.vm_importer.ui.monitor import TaskMonitorDialog
                monitor = TaskMonitorDialog(self.orchestrator, task_id, self.region, self)
                monitor.exec()
                self.close() 
            else:
                 # Should rely on exception for failures. 
                 # If we get here with None, it means weird state or user cancel that didn't raise?
                 if self.abort_flag:
                    self.status_label.setText("Upload Cancelled.")
                    QMessageBox.information(self, "Cancelled", "Upload was cancelled by user.")
                    
        except Exception as e:
            self.logger.error(f"UI Error: {e}")
            QMessageBox.critical(self, "Error", f"Exception: {e}")
        finally:
            self.import_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
