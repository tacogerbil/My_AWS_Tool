from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, QListWidget, 
                               QListWidgetItem, QComboBox, QCheckBox, QGroupBox, QFormLayout, 
                               QHBoxLayout, QPushButton, QStackedWidget, QGridLayout, QFrame)
from ui.common.widgets import SearchableComboBox, CheckableComboBox
from PySide6.QtCore import Qt, Signal

class Stage1_Image(QWidget):
    ami_selected = Signal(str)
    clone_selected = Signal(dict) # Emits full instance data for cloning

    def __init__(self):
        super().__init__()
        self.catalog_amis_data = []
        self.my_amis_data = []
        self.quick_amis_data = []
        layout = QVBoxLayout(self)
        
        # --- TAB BUTTONS ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_catalog = self._create_tab_btn("Catalog")
        self.btn_recents = self._create_tab_btn("Recents")
        self.btn_my_amis = self._create_tab_btn("My AMIs", is_active=True)
        self.btn_quick = self._create_tab_btn("Quick Start")
        self.btn_clone = self._create_tab_btn("Clone Existing")
        
        btn_layout.addWidget(self.btn_catalog)
        btn_layout.addWidget(self.btn_recents)
        btn_layout.addWidget(self.btn_my_amis)
        btn_layout.addWidget(self.btn_quick)
        btn_layout.addWidget(self.btn_clone)
        layout.addLayout(btn_layout)
        
        # --- DYNAMIC CONTENT ---
        self.stack = QStackedWidget()
        
        # View 1: Catalog
        self.view_catalog = self._create_list_view("Search Public Catalog...")
        
        # View 2: Recents
        self.view_recents = QListWidget()
        self.view_recents.itemClicked.connect(lambda i: self.ami_selected.emit(i.text()))
        
        # View 3: My AMIs (Default)
        self.view_my_amis = QWidget()
        v3_layout = QVBoxLayout(self.view_my_amis)
        v3_layout.setContentsMargins(0,0,0,0)
        self.chk_imports_only = QCheckBox("Show Only My Imports (CreatedBy: AWS_Tool)")
        self.chk_imports_only.setChecked(True)
        self.chk_imports_only.stateChanged.connect(self._refresh_my_amis)
        
        self.list_my_amis = QListWidget()
        self.list_my_amis.itemClicked.connect(lambda i: self.ami_selected.emit(i.text()))
        v3_layout.addWidget(self.chk_imports_only)
        v3_layout.addWidget(self.list_my_amis)
        self._refresh_my_amis()
        
        # View 4: Quick Start
        self.view_quick = QWidget()
        self.v4_grid = QGridLayout(self.view_quick)
        self.qs_buttons = [] # Track buttons to update them
                
        # View 5: Clone Existing
        self.view_clone = QWidget()
        clone_layout = QVBoxLayout(self.view_clone)
        
        # Filter Input
        self.clone_search = QLineEdit()
        self.clone_search.setPlaceholderText("Filter by Name, ID, or Tag (e.g. Env=Dev)")
        
        # Clone List
        self.list_clone = QListWidget()
        self.list_clone.itemClicked.connect(self._on_clone_selected)
        
        clone_layout.addWidget(QLabel("Select a running/stopped instance to clone its settings:"))
        clone_layout.addWidget(self.clone_search)
        clone_layout.addWidget(self.list_clone)
        
        self.stack.addWidget(self.view_catalog)      # 0
        self.stack.addWidget(self.view_recents)      # 1
        self.stack.addWidget(self.view_my_amis)      # 2
        self.stack.addWidget(self.view_quick)        # 3
        self.stack.addWidget(self.view_clone)        # 4
        
        # Separator Line styling
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        layout.addWidget(self.stack)
        
        # Events
        self.btn_catalog.clicked.connect(lambda: self._switch_tab(0, self.btn_catalog))
        self.btn_recents.clicked.connect(lambda: self._switch_tab(1, self.btn_recents))
        self.btn_my_amis.clicked.connect(lambda: self._switch_tab(2, self.btn_my_amis))
        self.btn_quick.clicked.connect(lambda: self._switch_tab(3, self.btn_quick))
        self.btn_clone.clicked.connect(lambda: self._switch_tab(4, self.btn_clone))
        
        self.buttons = [self.btn_catalog, self.btn_recents, self.btn_my_amis, self.btn_quick, self.btn_clone]
        
        # Set Default
        self.stack.setCurrentIndex(2) 

    def _create_tab_btn(self, text, is_active=False):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFlat(True)
        btn.setFixedHeight(40)
        style = "font-weight: bold; border-bottom: 2px solid transparent;"
        if is_active:
            btn.setChecked(True)
            style = "font-weight: bold; border-bottom: 3px solid #3498db; color: #3498db;"
        btn.setStyleSheet(style)
        return btn

    def _switch_tab(self, index, active_btn):
        self.stack.setCurrentIndex(index)
        for btn in self.buttons:
            btn.setStyleSheet("font-weight: bold; border-bottom: 2px solid transparent; color: black;")
            btn.setChecked(False)
        
        active_btn.setChecked(True)
        active_btn.setStyleSheet("font-weight: bold; border-bottom: 3px solid #3498db; color: #3498db;")

    def _create_list_view(self, placeholder):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0,0,0,0)
        search = QLineEdit()
        search.setPlaceholderText(placeholder)
        lst = QListWidget()
        lst.itemClicked.connect(lambda i: self.ami_selected.emit(str(i.text())))
        l.addWidget(search)
        l.addWidget(lst)
        w.list_widget = lst
        return w

    def _refresh_my_amis(self):
        self.list_my_amis.clear()
        only_imports = self.chk_imports_only.isChecked()
        for ami in self.my_amis_data:
            is_import = any(t.value == 'AWS_Tool_Import' for t in ami.tags)
            
            if only_imports and not is_import:
                continue
                
            desc = f"{ami.name if ami.name else 'Unnamed'} ({ami.image_id})"
            item = QListWidgetItem(desc)
            if is_import:
                item.setForeground(Qt.blue)
                item.setText(desc + " [IMPORTED]")
            
            item.setData(Qt.UserRole, ami)
            self.list_my_amis.addItem(item)

    def set_amis(self, catalog_amis, my_amis, quick_amis):
        """Populates the AMI lists."""
        self.catalog_amis_data = catalog_amis
        self.my_amis_data = my_amis
        self.quick_amis_data = quick_amis
        
        # Populate Catalog
        self.view_catalog.list_widget.clear()
        for ami in catalog_amis:
            item = QListWidgetItem(f"{ami.name if ami.name else 'Unnamed'} ({ami.image_id})")
            item.setData(Qt.UserRole, ami)
            self.view_catalog.list_widget.addItem(item)
            
        # Repopulate My AMIs
        self._refresh_my_amis()
        
        # Recents not implemented yet
        self.view_recents.clear() 
        
        # Populate Quick Start
        # Clear existing buttons
        while self.v4_grid.count():
            child = self.v4_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        row, col = 0, 0
        for qs in quick_amis:
            name = qs.name if qs.name else qs.description
            btn = QPushButton(name)
            btn.setFixedSize(150, 100)
            btn.setStyleSheet("background-color: #ecf0f1; border: 1px solid #bdc3c7; border-radius: 8px;")
            btn.clicked.connect(lambda ch, n=name: self.ami_selected.emit(n))
            self.v4_grid.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
            
    def set_clone_instances(self, instances):
        self.list_clone.clear()
        for inst in instances:
            desc = f"{inst.name if inst.name else 'Unnamed'} ({inst.instance_id}) - {inst.instance_type} in {inst.vpc_id}"
            item = QListWidgetItem(desc)
            item.setData(Qt.UserRole, inst)
            self.list_clone.addItem(item)

    def _on_clone_selected(self, item):
        inst_data = item.data(Qt.UserRole)
        self.clone_selected.emit(inst_data)

class Stage2_Hardware(QWidget):
    type_changed = Signal(str)
    storage_changed = Signal(str, str) # size, type

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Instance Type Group
        grp_type = QGroupBox("Hardware Performance")
        f_layout = QFormLayout(grp_type)
        
        self.type_combo = SearchableComboBox()
        self.type_combo.currentTextChanged.connect(self.type_changed.emit)
        
        f_layout.addRow("Instance Type:", self.type_combo)
        layout.addWidget(grp_type)
        
        # Storage Group
        grp_store = QGroupBox("Storage Configuration")
        s_layout = QFormLayout(grp_store)
        
        self.vol_size = QLineEdit("50")
        self.vol_size.textChanged.connect(self._emit_storage)

        self.vol_type = SearchableComboBox()
        self.vol_type.addItems(["gp3 (General Purpose SSD)", "io2 (Provisioned IOPS)", "standard (Magnetic)"])
        self.vol_type.currentTextChanged.connect(self._emit_storage)
        
        s_layout.addRow("Root Volume (GiB):", self.vol_size)
        s_layout.addRow("Volume Type:", self.vol_type)
        layout.addWidget(grp_store)
        
        layout.addStretch()

    def _emit_storage(self):
        self.storage_changed.emit(self.vol_size.text(), self.vol_type.currentText())

    def set_data(self, instance_types):
        # Preserve current selection if possible? Or reset?
        curr = self.type_combo.currentText()
        self.type_combo.clear()
        self.type_combo.addItems(instance_types)
        if curr in instance_types:
             self.type_combo.setCurrentText(curr)
        
    def set_selected_type(self, type_str):
        self.type_combo.setCurrentText(type_str)
        # Force emit?
        self.type_changed.emit(type_str)
        
    def set_volume_config(self, size, vol_type):
        self.vol_size.setText(str(size))
        # Map vol_type to combo... fuzzy?
        self.vol_type.setCurrentText(vol_type)

class Stage3_Connectivity(QWidget):
    network_changed = Signal(str, str) # VPC, Subnet
    sg_changed = Signal(list) # List of selected SGs

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Network Group
        grp_net = QGroupBox("Network Location")
        n_layout = QFormLayout(grp_net)
        
        self.vpc_combo = SearchableComboBox()
        self.vpc_combo.currentTextChanged.connect(self._emit_net)
        
        self.subnet_combo = SearchableComboBox()
        self.subnet_combo.currentTextChanged.connect(self._emit_net)
        
        n_layout.addRow("VPC:", self.vpc_combo)
        n_layout.addRow("Subnet:", self.subnet_combo)
        layout.addWidget(grp_net)
        
        # Security Group
        grp_sec = QGroupBox("Firewall (Security Groups)")
        sec_layout = QVBoxLayout(grp_sec)
        
        self.sg_combo = CheckableComboBox()
        self.sg_combo.model.itemChanged.connect(self._emit_sg)

        sec_layout.addWidget(QLabel("Select Security Groups (Multiple):"))
        sec_layout.addWidget(self.sg_combo)
        layout.addWidget(grp_sec)
        
        # Key Pair
        grp_key = QGroupBox("Login Access")
        k_layout = QFormLayout(grp_key)
        self.key_combo = SearchableComboBox()
        k_layout.addRow("Key Pair:", self.key_combo)
        layout.addWidget(grp_key)

    def _emit_net(self):
        self.network_changed.emit(self.vpc_combo.currentText(), self.subnet_combo.currentText())

    def _emit_sg(self):
        items = self.sg_combo.get_checked_items()
        self.sg_changed.emit(items)

    def set_data(self, vpcs, subnets, security_groups, key_pairs):
        self.vpc_combo.clear()
        # Format: "Name (vpc-id)"
        self.vpc_combo.addItems([f"{v.name if v.name else ''} ({v.vpc_id})" for v in vpcs])
        
        self.subnet_combo.clear()
        self.subnet_combo.addItems([f"{s.subnet_id} ({s.availability_zone})" for s in subnets])
        
        self.sg_combo.clear()
        self.sg_combo.addItems([f"{sg.group_id} ({sg.group_name})" for sg in security_groups])
        
        self.key_combo.clear()
        self.key_combo.addItems([k.key_name for k in key_pairs])

    def set_selection(self, vpc_id, subnet_id, sg_ids, key_name):
        # We need to fuzzy match because items are "Name (ID)"
        # Simple approach: Search for ID in text
        if vpc_id:
            self.vpc_combo.setEditText(vpc_id) # Searchable combo handles text
            
        if subnet_id:
            self.subnet_combo.setEditText(subnet_id)
            
        if key_name:
            self.key_combo.setEditText(key_name)
            
        if sg_ids:
            # Clear all checked items
            for i in range(self.sg_combo.model.rowCount()):
                item = self.sg_combo.model.item(i)
                item.setCheckState(Qt.Unchecked)
                
            # Check matching items
            for item_idx in range(self.sg_combo.model.rowCount()):
                item = self.sg_combo.model.item(item_idx)
                for expected_sg in sg_ids: # match ID or name
                    if expected_sg in item.text():
                        item.setCheckState(Qt.Checked)
                        break
