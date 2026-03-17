from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QLabel, QFormLayout, 
                               QWidget, QFrame)
from PySide6.QtCore import Qt

class SummaryPanel(QGroupBox):
    """
    Right-hand static summary panel that updates as user configures the instance.
    """
    def __init__(self):
        super().__init__("Instance Summary")
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                background-color: #f8f9fa;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        
        self.layout = QFormLayout()
        self.layout.setSpacing(15)
        self.setLayout(self.layout)
        
        # Summary Fields (Labels)
        self.lbl_ami = QLabel("-")
        self.lbl_type = QLabel("t3.medium") # Default
        self.lbl_vpc = QLabel("-")
        self.lbl_sg = QLabel("-")
        self.lbl_audit = QLabel("Checking...") # Compliance Check
        
        self.lbl_storage = QLabel("-") # Storage Label
        
        # Styling for values
        for lbl in [self.lbl_ami, self.lbl_type, self.lbl_vpc, self.lbl_sg, self.lbl_storage]:
            lbl.setStyleSheet("font-weight: bold; color: #34495e;")
            lbl.setWordWrap(True)

        self.lbl_audit.setStyleSheet("color: orange; font-style: italic;")

        self.layout.addRow("AMI:", self.lbl_ami)
        self.layout.addRow("Type:", self.lbl_type)
        self.layout.addRow("Storage:", self.lbl_storage)
        self.layout.addRow("Network:", self.lbl_vpc)
        self.layout.addRow("Security:", self.lbl_sg)
        
        self.layout.addRow(QFrame()) # Separator
        
        self.layout.addRow("Status:", self.lbl_audit)

        # Cost Estimate (Fake)
        self.lbl_cost = QLabel("~$0.0416 / hr")
        self.lbl_cost.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 16px;")
        self.layout.addRow("Est. Cost:", self.lbl_cost)

    def update_ami(self, text):
        self.lbl_ami.setText(text)
        
    def update_instance_type(self, text):
        self.lbl_type.setText(text)
        # Mock Cost Update
        if "large" in text:
            self.lbl_cost.setText("~$0.0832 / hr")
        elif "xlarge" in text:
            self.lbl_cost.setText("~$0.1664 / hr")
        else:
            self.lbl_cost.setText("~$0.0416 / hr")

    def update_storage(self, size, vol_type):
        self.lbl_storage.setText(f"{size} GiB ({vol_type})")

    def update_network(self, vpc_text, subnet_text):
        self.lbl_vpc.setText(f"{vpc_text}\n{subnet_text}")

    def update_security_groups(self, groups):
        if not groups:
            self.lbl_sg.setText("None selected")
        else:
            self.lbl_sg.setText(", ".join(groups))
