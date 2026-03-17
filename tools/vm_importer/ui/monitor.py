from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar, 
                               QTextEdit, QPushButton, QHBoxLayout, QMessageBox)
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from datetime import datetime
import logging

class TaskMonitorDialog(QDialog):
    """
    Monitors an active AWS VM Import Task.
    Polls status and provides Deep Link to Console upon completion.
    """
    def __init__(self, orchestrator, task_id: str, region: str, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.task_id = task_id
        self.region = region
        self.logger = logging.getLogger("TaskMonitor")
        
        self.setWindowTitle(f"Import Task Monitor - {task_id}")
        self.resize(600, 400)
        
        self.layout = QVBoxLayout(self)
        
        # Header
        self.layout.addWidget(QLabel(f"<b>Monitoring Task:</b> {task_id}"))
        self.status_label = QLabel("Status: Initializing...")
        self.layout.addWidget(self.status_label)
        
        # Progress (Indeterminate until we have data, or based on 'Progress' field)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        from ui.common.styles import get_progress_bar_style
        self.progress_bar.setStyleSheet(get_progress_bar_style(0))
        self.layout.addWidget(self.progress_bar)
        
        # Log Area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.layout.addWidget(self.log_area)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        self.console_btn = QPushButton("View AMI in AWS Console")
        self.console_btn.clicked.connect(self.open_console)
        self.console_btn.setVisible(False) 
        self.console_btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
        
        self.cancel_btn = QPushButton("Cancel Task")
        self.cancel_btn.clicked.connect(self.cancel_task)
        self.cancel_btn.setStyleSheet("background-color: #c0392b; color: white;")
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.console_btn)
        btn_layout.addWidget(self.close_btn)
        self.layout.addLayout(btn_layout)
        
        # Polling Timer (3s interval)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(3000)
        
        self.last_status = None
        self.last_msg = None
        self.final_ami_id = None
        
        self.log_msg("Monitor started. Polling AWS...")

    def log_msg(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{ts}] {msg}")

    def poll_status(self):
        try:
            # result = {'Status': '...', 'StatusMessage': '...', 'Progress': '...', 'ImageId': '...'}
            info = self.orchestrator.check_status(self.task_id)
            
            status = info.get("Status")
            msg = info.get("StatusMessage")
            progress = info.get("Progress") # String "45"
            image_id = info.get("ImageId")
            
            # Update UI
            self.status_label.setText(f"Status: {status.upper()} - {msg}")
            
            try:
                val = int(progress) if progress else 0
                self.progress_bar.setValue(val)
                from ui.common.styles import get_progress_bar_style
                self.progress_bar.setStyleSheet(get_progress_bar_style(val))
            except ValueError:
                pass
            
            # Log changes
            if status != self.last_status or msg != self.last_msg:
                self.log_msg(f"Status Update: {status} ({msg})")
                self.last_status = status
                self.last_msg = msg
                
            # Completion Check
            if status == "completed":
                self.timer.stop()
                self.progress_bar.setValue(100)
                self.final_ami_id = image_id
                self.log_msg(f"SUCCESS: AMI Created -> {image_id}")
                self.console_btn.setVisible(True)
                self.close_btn.setText("Done")
                
            elif status == "deleted":
                self.timer.stop()
                self.log_msg("TASK ENDED: Task was deleted.")
                
        except Exception as e:
            self.logger.error(f"Polling error: {e}")
            self.log_msg(f"Error polling AWS: {e}")

    def open_console(self):
        if not self.final_ami_id:
            return
            
        # Construct Deep Link
        # https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2#ImageDetails:imageId=ami-xyz
        url = (f"https://{self.region}.console.aws.amazon.com/ec2/home"
               f"?region={self.region}#ImageDetails:imageId={self.final_ami_id}")
        
        QDesktopServices.openUrl(QUrl(url))

    def cancel_task(self):
        reply = QMessageBox.question(self, "Confirm Cancel", 
                                   "Are you sure you want to cancel this import task?",
                                   QMessageBox.Yes | QMessageBox.No)
                                   
        if reply == QMessageBox.Yes:
            self.log_msg("Requesting Cancellation...")
            success = self.orchestrator.cancel_import(self.task_id)
            if success:
                self.log_msg("Cancellation request sent.")
                self.cancel_btn.setEnabled(False)
            else:
                QMessageBox.critical(self, "Error", "Failed to cancel task.")
