"""
launch_monitor.py — Real-time EC2 instance launch monitoring dialog.

Responsibilities (single):
    Display live status for one or more EC2 instances from the moment they
    are submitted until they reach a terminal state (running / failed).

Threading model:
    - LaunchWorker (QThread): calls service.launch_instances() off-thread;
      emits launched(LaunchResult) or failed(str).
    - QTimer (main thread): polls service.describe_instances_by_ids() every
      5 seconds and updates the per-instance rows.

No business logic; all AWS I/O delegated to the injected service layer.
"""

from __future__ import annotations

import logging
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import Instance
from tools.ec2_launcher.models import LaunchConfig, LaunchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_MS = 5_000   # 5 seconds between describe_instances polls
_TERMINAL_STATES  = {"running", "terminated", "stopped", "shutting-down"}
_FAILED_STATES    = {"terminated", "shutting-down"}

_PALETTE = {
    "bg":       "#1a1f2e",
    "card":     "#252b3b",
    "border":   "#2d3446",
    "accent":   "#3498db",
    "success":  "#27ae60",
    "danger":   "#e74c3c",
    "warning":  "#f39c12",
    "pending":  "#7f8c8d",
    "text":     "#ecf0f1",
    "subtext":  "#95a5a6",
    "log_bg":   "#111520",
}

_DIALOG_STYLE = f"""
QDialog {{
    background-color: {_PALETTE['bg']};
    color: {_PALETTE['text']};
}}
QLabel {{
    color: {_PALETTE['text']};
}}
QPushButton {{
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {_PALETTE['border']};
    background-color: {_PALETTE['card']};
    color: {_PALETTE['text']};
}}
QPushButton:hover   {{ background-color: #2d3446; }}
QPushButton:pressed {{ background-color: #1a1f2e; }}
QPushButton:disabled {{ color: {_PALETTE['subtext']}; border-color: #1e2436; }}
QTextEdit {{
    background-color: {_PALETTE['log_bg']};
    color: #a8c5da;
    border: 1px solid {_PALETTE['border']};
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 11px;
}}
QCheckBox {{ color: {_PALETTE['subtext']}; font-size: 12px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {_PALETTE['bg']}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_PALETTE['border']}; border-radius: 4px; min-height: 20px;
}}
"""

_STATE_COLORS: Dict[str, str] = {
    "pending":       _PALETTE["warning"],
    "running":       _PALETTE["success"],
    "stopped":       _PALETTE["subtext"],
    "terminated":    _PALETTE["danger"],
    "shutting-down": _PALETTE["danger"],
    "stopping":      _PALETTE["warning"],
    "error":         _PALETTE["danger"],
}

_STATE_ICONS: Dict[str, str] = {
    "pending":       "⏳",
    "running":       "✅",
    "stopped":       "⏹",
    "terminated":    "❌",
    "shutting-down": "❌",
    "stopping":      "⏳",
    "error":         "❌",
}


# ---------------------------------------------------------------------------
# Background worker: runs launch_instances() off the GUI thread
# ---------------------------------------------------------------------------

class LaunchWorker(QObject):
    """Thin QObject worker — runs inside a QThread."""

    launched = Signal(object)   # LaunchResult
    failed   = Signal(str)      # error message string

    def __init__(self, service, config: LaunchConfig) -> None:
        super().__init__()
        self._service = service
        self._config  = config

    def run(self) -> None:      # called by QThread.started
        try:
            result: LaunchResult = self._service.launch_instances(self._config)
            if result.error:
                self.failed.emit(result.error)
            else:
                self.launched.emit(result)
        except Exception as exc:
            logger.exception("LaunchWorker unhandled exception")
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Per-instance status row widget
# ---------------------------------------------------------------------------

class _InstanceRow(QFrame):
    """One row showing live status for a single EC2 instance."""

    def __init__(self, name: str, instance_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._instance_id = instance_id
        self._name        = name
        self._region      = ""

        self.setStyleSheet(
            f"QFrame {{ background-color: {_PALETTE['card']}; "
            f"border: 1px solid {_PALETTE['border']}; border-radius: 6px; }}"
        )
        self.setFixedHeight(68)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(12)

        # State icon
        self._icon_lbl = QLabel("⏳")
        self._icon_lbl.setFixedWidth(22)
        self._icon_lbl.setStyleSheet("font-size: 16px; border: none;")
        row.addWidget(self._icon_lbl)

        # Name + ID stack
        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {_PALETTE['text']}; border: none;"
        )
        self._id_lbl = QLabel(instance_id)
        self._id_lbl.setStyleSheet(
            f"font-size: 11px; color: {_PALETTE['subtext']}; border: none;"
        )
        info.addWidget(self._name_lbl)
        info.addWidget(self._id_lbl)
        row.addLayout(info, stretch=1)

        # State badge
        self._state_badge = QLabel("pending")
        self._state_badge.setFixedWidth(100)
        self._state_badge.setAlignment(Qt.AlignCenter)
        self._state_badge.setStyleSheet(self._badge_style("pending"))
        row.addWidget(self._state_badge)

        # Private IP
        self._ip_lbl = QLabel("—")
        self._ip_lbl.setFixedWidth(110)
        self._ip_lbl.setStyleSheet(
            f"font-size: 11px; color: {_PALETTE['subtext']}; border: none;"
        )
        row.addWidget(self._ip_lbl)

        # Open in Console button
        self._console_btn = QPushButton("🔗 Console")
        self._console_btn.setFixedWidth(90)
        self._console_btn.setEnabled(False)
        self._console_btn.setToolTip("Open this instance in the AWS Console")
        self._console_btn.clicked.connect(self._open_in_console)
        row.addWidget(self._console_btn)

    # ------------------------------------------------------------------

    def update_from_instance(self, inst: Instance, region: str) -> None:
        """Refresh this row from a live Instance model."""
        self._region = region
        state = inst.state or "pending"
        self._icon_lbl.setText(_STATE_ICONS.get(state, "⏳"))
        self._state_badge.setText(state)
        self._state_badge.setStyleSheet(self._badge_style(state))
        self._ip_lbl.setText(inst.private_ip or "—")
        self._console_btn.setEnabled(state == "running")

    def mark_error(self, message: str) -> None:
        self._icon_lbl.setText("❌")
        self._state_badge.setText("error")
        self._state_badge.setStyleSheet(self._badge_style("error"))
        self._id_lbl.setText(message[:60])

    # ------------------------------------------------------------------

    @staticmethod
    def _badge_style(state: str) -> str:
        colour = _STATE_COLORS.get(state, _PALETTE["subtext"])
        return (
            f"background-color: {colour}22; color: {colour}; "
            f"border: 1px solid {colour}55; border-radius: 10px; "
            f"font-size: 11px; font-weight: 700; padding: 2px 8px;"
        )

    def _open_in_console(self) -> None:
        region = self._region or "us-east-1"
        url = (
            f"https://console.aws.amazon.com/ec2/v2/home?region={region}"
            f"#Instances:instanceId={self._instance_id}"
        )
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class LaunchMonitorDialog(QDialog):
    """Real-time launch status dialog.

    Opens immediately after the launch worker thread submits run_instances.
    Polls EC2 describe_instances every 5 s, updating per-instance rows and
    appending to the scrollable log panel.  Closes automatically (if the
    checkbox is ticked) once all instances are running.
    """

    def __init__(
        self,
        config: LaunchConfig,
        service,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config        = config
        self._service       = service
        self._result: Optional[LaunchResult] = None
        self._rows: Dict[str, _InstanceRow] = {}   # instance_id → row widget
        self._timer         = QTimer(self)
        self._thread: Optional[QThread] = None
        self._worker: Optional[LaunchWorker] = None

        self.setWindowTitle("EC2 Launch Monitor")
        self.resize(820, 580)
        self.setModal(False)
        self.setStyleSheet(_DIALOG_STYLE)

        self._build_ui()
        self._start_launch()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_instance_area(), stretch=2)
        root.addWidget(self._build_log_panel(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            f"background-color: {_PALETTE['card']}; border-radius: 6px;"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)

        title = QLabel("🚀  EC2 Launch Monitor")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_PALETTE['text']};"
        )
        row.addWidget(title)
        row.addStretch()

        meta = QLabel(
            f"AMI: <b>{self._config.image_id}</b>  ·  "
            f"Type: <b>{self._config.instance_type}</b>  ·  "
            f"Count: <b>{self._config.instance_count}</b>"
        )
        meta.setStyleSheet(f"font-size: 11px; color: {_PALETTE['subtext']};")
        meta.setTextFormat(Qt.RichText)
        row.addWidget(meta)

        return bar

    def _build_instance_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self._instance_container = QWidget()
        self._instance_container.setStyleSheet("background: transparent;")
        self._instance_layout = QVBoxLayout(self._instance_container)
        self._instance_layout.setSpacing(6)
        self._instance_layout.setContentsMargins(0, 0, 0, 0)

        # Pre-create placeholder rows for all expected instances
        names = self._config.instance_names or [
            f"Instance-{i + 1}" for i in range(self._config.instance_count)
        ]
        for name in names:
            row = _InstanceRow(name=name, instance_id="pending…")
            self._instance_layout.addWidget(row)
            # Keyed by name initially; re-keyed by real ID on launch
            self._rows[name] = row

        self._instance_layout.addStretch()
        scroll.setWidget(self._instance_container)
        return scroll

    def _build_log_panel(self) -> QWidget:
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        lbl = QLabel("Event Log")
        lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {_PALETTE['subtext']};"
            "text-transform: uppercase; letter-spacing: 1px;"
        )
        lay.addWidget(lbl)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        lay.addWidget(self._log)

        return pane

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        self._auto_close_chk = QCheckBox("Auto-close when all instances are running")
        self._auto_close_chk.setChecked(True)
        row.addWidget(self._auto_close_chk)
        row.addStretch()

        self._abort_btn = QPushButton("⛔  Abort")
        self._abort_btn.setStyleSheet(
            f"background-color: {_PALETTE['danger']}33; color: {_PALETTE['danger']};"
            f"border: 1px solid {_PALETTE['danger']}55;"
        )
        self._abort_btn.clicked.connect(self._on_abort)
        row.addWidget(self._abort_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        row.addWidget(self._close_btn)

        return bar

    # ------------------------------------------------------------------
    # Launch worker
    # ------------------------------------------------------------------

    def _start_launch(self) -> None:
        self._log_event("Submitting launch request…")
        self._abort_btn.setEnabled(True)

        self._worker = LaunchWorker(self._service, self._config)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.launched.connect(self._on_launched)
        self._worker.failed.connect(self._on_launch_failed)

        # Clean up once the thread finishes
        self._worker.launched.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)

        self._thread.start()

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_launched(self, result: LaunchResult) -> None:
        self._result = result
        self._log_event(
            f"✅ Launch submitted — {len(result.instance_ids)} instance(s) requested."
        )

        # Match each real instance ID to an existing placeholder row by position.
        # We update the row in-place (no new widgets) so there are never duplicate rows.
        placeholder_rows = list(self._rows.values())
        self._rows.clear()

        for i, (iid, name) in enumerate(zip(result.instance_ids, result.instance_names)):
            if i < len(placeholder_rows):
                # Re-use the existing row widget — just update its ID label
                row = placeholder_rows[i]
                row._id_lbl.setText(iid)
                row._instance_id = iid
            else:
                # More instances than placeholders (shouldn't happen, but be safe)
                row = _InstanceRow(name=name, instance_id=iid)
                self._instance_layout.insertWidget(
                    self._instance_layout.count() - 1, row
                )
            self._rows[iid] = row
            self._log_event(f"  Instance '{name}' assigned ID: {iid}")

        # Log any per-instance errors reported at launch time
        for name, err in result.per_instance_errors:
            row = _InstanceRow(name=name, instance_id="launch-failed")
            row.mark_error(err)
            self._instance_layout.insertWidget(self._instance_layout.count() - 1, row)
            self._log_event(f"⚠️  '{name}' failed to launch: {err}")

        self._abort_btn.setEnabled(False)
        self._start_polling()

    def _on_launch_failed(self, error: str) -> None:
        self._log_event(f"❌ Launch failed: {error}")
        self._abort_btn.setEnabled(False)
        # Mark all placeholder rows as failed
        for row in self._rows.values():
            row.mark_error(error)

    def _on_abort(self) -> None:
        """Best-effort abort: stop the worker thread and close."""
        self._log_event("⛔ Abort requested by user.")
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        self._timer.stop()
        self._abort_btn.setEnabled(False)
        self._log_event("Worker stopped. Note: instances already submitted to AWS may still be launching.")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._poll()   # immediate first poll

    def _poll(self) -> None:
        if not self._result:
            return
        ids = self._result.instance_ids
        if not ids:
            return

        instances = self._service.describe_instances_by_ids(ids)
        region = self._result.region

        state_map: Dict[str, Instance] = {i.instance_id: i for i in instances}

        all_terminal = True
        for iid, row in self._rows.items():
            inst = state_map.get(iid)
            if inst is None:
                all_terminal = False
                continue
            prev_state = row._state_badge.text()
            row.update_from_instance(inst, region)
            new_state  = inst.state or "pending"
            if new_state != prev_state:
                self._log_event(f"  {inst.name or iid}: {prev_state} → {new_state}")
            if new_state not in _TERMINAL_STATES:
                all_terminal = False

        if all_terminal:
            self._timer.stop()
            self._log_event("🎉 All instances have reached a terminal state.")
            if self._auto_close_chk.isChecked():
                self._log_event("Auto-closing dialog…")
                QTimer.singleShot(1500, self.accept)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_event(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.append(f"<span style='color:#556677;'>[{ts}]</span> {message}")
        # Scroll to bottom
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._timer.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        super().closeEvent(event)
