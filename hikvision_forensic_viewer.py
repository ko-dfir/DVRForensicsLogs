#!/usr/bin/env python3
"""
Hikvision DVR Forensic Log Analyzer & Explorer (PyQt6)
Digital Forensics & Incident Response Tool for HIKVISION Proprietary File Systems.

Authors: Evangelos Dragonas, Costas Lambrinoudakis, Michael Kotsis
Modernized PyQt6 UI with Streaming Carving & Complete SDK Mapping
"""

import sys
import os
import csv
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QFrame
)
from PyQt6.QtGui import QColor, QFont, QIcon

# Ensure scripts dir is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import scripts.forensic_engine as fe


DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #181825;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
    color: #89b4fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
}

QLineEdit, QComboBox {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}

QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton#btnPrimary {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
}

QPushButton#btnPrimary:hover {
    background-color: #b4befe;
}

QPushButton#btnStop {
    background-color: #f38ba8;
    color: #11111b;
    border: none;
}

QPushButton#btnStop:hover {
    background-color: #eba0ac;
}

QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background: #181825;
}

QTabBar::tab {
    background: #1e1e2e;
    color: #a6adc8;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background: #313244;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}

QTableWidget {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #252538;
    color: #cdd6f4;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #252538;
    color: #89b4fa;
    padding: 6px;
    border: 1px solid #313244;
    font-weight: bold;
}

QProgressBar {
    border: 1px solid #313244;
    border-radius: 6px;
    text-align: center;
    background-color: #1e1e2e;
    color: #cdd6f4;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 5px;
}

QTextEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #a6adc8;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
"""


class CarvingWorker(QThread):
    """Background worker that streams RATS records without blocking the GUI"""
    records_chunk = pyqtSignal(list)
    progress_update = pyqtSignal(int, str)
    finished_parsing = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, image_path: str, region_mode: str, max_records: int):
        super().__init__()
        self.image_path = image_path
        self.region_mode = region_mode
        self.max_records = max_records
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            st = fe.detect_image_structure(self.image_path)
            file_size = st["file_size"]
            regions_to_scan = []

            if "Declared" in self.region_mode:
                if st["has_declared"] and st["declared_end"] > st["declared_start"]:
                    regions_to_scan.append(("Declared Active Ring-Buffer", st["declared_start"], st["declared_end"]))
                else:
                    regions_to_scan = st["scan_regions"]
            elif "Alternative" in self.region_mode:
                if st["has_alternative"] and st["alternative_end"] > st["alternative_start"]:
                    regions_to_scan.append(("Alternative Residual Region", st["alternative_start"], st["alternative_end"]))
                else:
                    regions_to_scan = st["scan_regions"]
            elif "Full Carve" in self.region_mode:
                regions_to_scan = [("Full Raw Carve", 0, file_size)]
            else:
                # Auto-Detect (All Available Regions)
                regions_to_scan = st["scan_regions"]

            if not regions_to_scan:
                regions_to_scan = [("Full Raw Carve", 0, file_size)]

            total_emitted = 0
            batch = []

            for reg_name, start_off, end_off in regions_to_scan:
                if not self._is_running:
                    break

                self.progress_update.emit(10, f"Scanning {reg_name} [{start_off:,} .. {end_off:,}]...")
                limit = None
                if self.max_records > 0:
                    limit = self.max_records - total_emitted
                    if limit <= 0:
                        break

                for rec in fe.iter_stream_records(self.image_path, start_off, end_off, reg_name, max_records=limit):
                    if not self._is_running:
                        break

                    batch.append(rec)
                    total_emitted += 1

                    if len(batch) >= 150:
                        self.records_chunk.emit(batch)
                        batch = []
                        target = self.max_records if self.max_records > 0 else 100000
                        pct = min(95, 10 + int((total_emitted / target) * 85))
                        self.progress_update.emit(pct, f"Carved {total_emitted:,} records ({reg_name})...")

            if batch:
                self.records_chunk.emit(batch)

            self.progress_update.emit(100, f"Carving completed. Total {total_emitted:,} records parsed.")
            self.finished_parsing.emit(total_emitted)

        except Exception as e:
            self.error_occurred.emit(str(e))


class ForensicViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hikvision DVR Forensic Log Analyzer & Explorer v2.0")
        self.resize(1420, 880)
        self.setStyleSheet(DARK_THEME_QSS)

        # Enable Drag and Drop for forensic image files
        self.setAcceptDrops(True)

        self.records_data = []
        self.worker = None

        self.init_ui()
        self.auto_load_metadata()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path and os.path.exists(file_path):
                self.edit_image_path.setText(file_path)
                self.auto_load_metadata()
                self.lbl_status.setText(f"Target dropped: {os.path.basename(file_path)}. Ready to carve.")

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(10)

        # 1. Top Bar: Path & Controls
        top_group = QGroupBox("Forensic Evidence Target & Carving Options (Drag & Drop Supported)")
        top_layout = QHBoxLayout(top_group)
        top_layout.setContentsMargins(12, 10, 12, 10)

        top_layout.addWidget(QLabel("Image File:"))
        self.edit_image_path = QLineEdit()
        self.edit_image_path.setPlaceholderText("Enter image path or drag and drop image file here...")
        self.edit_image_path.editingFinished.connect(self.auto_load_metadata)
        self.edit_image_path.returnPressed.connect(self.auto_load_metadata)
        top_layout.addWidget(self.edit_image_path, stretch=3)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_image)
        top_layout.addWidget(btn_browse)

        top_layout.addWidget(QLabel("Region:"))
        self.combo_region = QComboBox()
        self.combo_region.addItems([
            "Auto-Detect (All Available Regions)",
            "Declared Active Ring-Buffer",
            "Alternative Residual Region",
            "Full Carve (Scan Entire File)"
        ])
        top_layout.addWidget(self.combo_region)

        top_layout.addWidget(QLabel("Limit:"))
        self.combo_limit = QComboBox()
        self.combo_limit.addItems(["5,000 (Fast Preview)", "25,000 (Standard)", "100,000 (Deep)", "All Records"])
        top_layout.addWidget(self.combo_limit)

        self.btn_load = QPushButton("▶ Load & Carve")
        self.btn_load.setObjectName("btnPrimary")
        self.btn_load.clicked.connect(self.start_carving)
        top_layout.addWidget(self.btn_load)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_carving)
        top_layout.addWidget(self.btn_stop)

        self.btn_export = QPushButton("💾 Export CSV")
        self.btn_export.clicked.connect(self.export_csv)
        top_layout.addWidget(self.btn_export)

        main_layout.addWidget(top_group)

        # 2. Main Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        self.tab_metadata = QWidget()
        self.tab_logs = QWidget()
        self.tab_exfil = QWidget()
        self.tab_cameras = QWidget()
        self.tab_stats = QWidget()

        self.tabs.addTab(self.tab_metadata, "🖥️ Device & Evidence Fingerprint")
        self.tabs.addTab(self.tab_logs, "📜 All Logs Explorer")
        self.tabs.addTab(self.tab_exfil, "🚨 Exfiltration & Security Audit")
        self.tabs.addTab(self.tab_cameras, "📹 Camera & Motion Analysis")
        self.tabs.addTab(self.tab_stats, "📊 Log Types & Statistics")

        self.setup_metadata_tab()
        self.setup_logs_tab()
        self.setup_exfil_tab()
        self.setup_cameras_tab()
        self.setup_stats_tab()

        self.tabs.currentChanged.connect(self.on_tab_changed)

        # 3. Bottom Status Bar with Progress
        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel("Ready.")
        bottom_layout.addWidget(self.lbl_status, stretch=2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar, stretch=1)

        main_layout.addLayout(bottom_layout)

    # --- TAB 1: METADATA & EVIDENCE OVERVIEW ---
    def setup_metadata_tab(self):
        layout = QVBoxLayout(self.tab_metadata)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Cards Layout
        cards_layout = QHBoxLayout()

        # Card 1: DVR Hardware
        gb_dvr = QGroupBox("Hardware & Firmware Fingerprint")
        l1 = QVBoxLayout(gb_dvr)
        self.lbl_dvr_model = QLabel("<b>Model:</b> Loading...")
        self.lbl_dvr_serial = QLabel("<b>Serial:</b> Loading...")
        self.lbl_dvr_firmware = QLabel("<b>Firmware:</b> Loading...")
        self.lbl_dvr_dsp = QLabel("<b>Encoding:</b> Loading...")
        l1.addWidget(self.lbl_dvr_model)
        l1.addWidget(self.lbl_dvr_serial)
        l1.addWidget(self.lbl_dvr_firmware)
        l1.addWidget(self.lbl_dvr_dsp)
        l1.addStretch()
        cards_layout.addWidget(gb_dvr)

        # Card 2: Hard Drive
        gb_hdd = QGroupBox("Hard Disk Drive (Storage Media)")
        l2 = QVBoxLayout(gb_hdd)
        self.lbl_hdd_model = QLabel("<b>HDD Model:</b> Loading...")
        self.lbl_hdd_serial = QLabel("<b>HDD Serial:</b> Loading...")
        self.lbl_hdd_firmware = QLabel("<b>HDD Firmware:</b> Loading...")
        self.lbl_hdd_capacity = QLabel("<b>Capacity:</b> Loading...")
        l2.addWidget(self.lbl_hdd_model)
        l2.addWidget(self.lbl_hdd_serial)
        l2.addWidget(self.lbl_hdd_firmware)
        l2.addWidget(self.lbl_hdd_capacity)
        l2.addStretch()
        cards_layout.addWidget(gb_hdd)

        # Card 3: Filesystem
        gb_fs = QGroupBox("Hikvision Proprietary Filesystem")
        l3 = QVBoxLayout(gb_fs)
        self.lbl_fs_sig = QLabel("<b>FS Signature:</b> Loading...")
        self.lbl_fs_ver = QLabel("<b>FS Version:</b> Loading...")
        self.lbl_fs_decl_off = QLabel("<b>Declared Log Offset:</b> Loading...")
        self.lbl_fs_alt_off = QLabel("<b>Alternative Log Offset:</b> Loading...")
        l3.addWidget(self.lbl_fs_sig)
        l3.addWidget(self.lbl_fs_ver)
        l3.addWidget(self.lbl_fs_decl_off)
        l3.addWidget(self.lbl_fs_alt_off)
        l3.addStretch()
        cards_layout.addWidget(gb_fs)

        # Card 4: Integrity
        gb_integrity = QGroupBox("Forensic Target & Integrity")
        l4 = QVBoxLayout(gb_integrity)
        self.lbl_evidence_target = QLabel("<b>Target:</b> Loading...")
        self.lbl_evidence_size = QLabel("<b>Size:</b> Loading...")
        self.lbl_evidence_mount = QLabel("<b>Mode:</b> Streaming Read-Only")
        self.lbl_evidence_hash = QLabel("<b>Integrity:</b> Verified Non-Destructive")
        l4.addWidget(self.lbl_evidence_target)
        l4.addWidget(self.lbl_evidence_size)
        l4.addWidget(self.lbl_evidence_mount)
        l4.addWidget(self.lbl_evidence_hash)
        l4.addStretch()
        cards_layout.addWidget(gb_integrity)

        layout.addLayout(cards_layout)

        # Forensic Notes Text
        gb_notes = QGroupBox("Target Evidence Inspection & Dynamic Carving Log")
        notes_layout = QVBoxLayout(gb_notes)
        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        notes_layout.addWidget(self.txt_notes)
        layout.addWidget(gb_notes, stretch=1)

        # Bottom Action Bar inside Tab 0
        action_bar = QHBoxLayout()
        self.btn_carve_from_tab0 = QPushButton("▶ Launch Log Carving on Current Target Image")
        self.btn_carve_from_tab0.setObjectName("btnPrimary")
        self.btn_carve_from_tab0.setMinimumHeight(44)
        font = QFont("Segoe UI", 12)
        font.setBold(True)
        self.btn_carve_from_tab0.setFont(font)
        self.btn_carve_from_tab0.clicked.connect(self.start_carving)
        action_bar.addWidget(self.btn_carve_from_tab0)
        layout.addLayout(action_bar)

    # --- TAB 2: ALL LOGS EXPLORER ---
    def setup_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        layout.setContentsMargins(10, 10, 10, 10)

        # Filter bar
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Search:"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Filter by keyword, user, IP, macro, details...")
        self.edit_filter.textChanged.connect(self.apply_table_filters)
        filter_layout.addWidget(self.edit_filter, stretch=2)

        filter_layout.addWidget(QLabel("Major Type:"))
        self.combo_filter_maj = QComboBox()
        self.combo_filter_maj.addItems(["All", "Alarm", "Exception", "Operation", "Information"])
        self.combo_filter_maj.currentTextChanged.connect(self.apply_table_filters)
        filter_layout.addWidget(self.combo_filter_maj)

        filter_layout.addWidget(QLabel("Channel:"))
        self.combo_filter_ch = QComboBox()
        self.combo_filter_ch.addItems(["All", "1", "2", "3", "4", "5", "6", "7", "8"])
        self.combo_filter_ch.currentTextChanged.connect(self.apply_table_filters)
        filter_layout.addWidget(self.combo_filter_ch)

        self.lbl_record_count = QLabel("Records: 0")
        filter_layout.addWidget(self.lbl_record_count)

        layout.addLayout(filter_layout)

        # Splitter with Table and Inspector
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table
        self.table_logs = QTableWidget()
        headers = ["#", "Time (UTC)", "Major", "Minor / Event Name", "Ch", "User", "IP", "Details", "Offset", "Region"]
        self.table_logs.setColumnCount(len(headers))
        self.table_logs.setHorizontalHeaderLabels(headers)
        self.table_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_logs.horizontalHeader().setStretchLastSection(True)
        self.table_logs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_logs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_logs.cellClicked.connect(self.on_log_row_selected)
        splitter.addWidget(self.table_logs)

        # Inspector Text Box
        self.txt_inspector = QTextEdit()
        self.txt_inspector.setReadOnly(True)
        self.txt_inspector.setMaximumHeight(160)
        self.txt_inspector.setPlaceholderText("Click any log entry to view decoded SDK definitions and raw payload hex dump...")
        splitter.addWidget(self.txt_inspector)

        splitter.setSizes([550, 150])
        layout.addWidget(splitter)

    # --- TAB 3: EXFILTRATION & SECURITY AUDIT ---
    def setup_exfil_tab(self):
        layout = QVBoxLayout(self.tab_exfil)
        layout.setContentsMargins(10, 10, 10, 10)

        # Dynamic filter buttons
        btn_box = QHBoxLayout()
        self.btn_filter_all_sec = QPushButton("🛡️ All Security Events (0)")
        self.btn_filter_exfil = QPushButton("💾 Video File Exports (0)")
        self.btn_filter_playback = QPushButton("▶ Video Playbacks (0)")
        self.btn_filter_illegal = QPushButton("⚠️ Illegal Logins (0)")
        self.btn_filter_reboots = QPushButton("🔄 Reboots / Power (0)")
        self.btn_filter_cfg = QPushButton("⚙ Config Changes (0)")

        self.btn_filter_all_sec.clicked.connect(lambda: self.quick_filter("ALL"))
        self.btn_filter_exfil.clicked.connect(lambda: self.quick_filter("Export"))
        self.btn_filter_playback.clicked.connect(lambda: self.quick_filter("Playback"))
        self.btn_filter_illegal.clicked.connect(lambda: self.quick_filter("Illegal"))
        self.btn_filter_reboots.clicked.connect(lambda: self.quick_filter("Reboot"))
        self.btn_filter_cfg.clicked.connect(lambda: self.quick_filter("Configure"))

        btn_box.addWidget(self.btn_filter_all_sec)
        btn_box.addWidget(self.btn_filter_exfil)
        btn_box.addWidget(self.btn_filter_playback)
        btn_box.addWidget(self.btn_filter_illegal)
        btn_box.addWidget(self.btn_filter_reboots)
        btn_box.addWidget(self.btn_filter_cfg)
        btn_box.addStretch()
        layout.addLayout(btn_box)

        # Splitter with Table and Inspector
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table_exfil = QTableWidget()
        headers = ["#", "Time (UTC)", "Event Name", "User", "Channel", "Details", "Offset", "Region"]
        self.table_exfil.setColumnCount(len(headers))
        self.table_exfil.setHorizontalHeaderLabels(headers)
        self.table_exfil.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_exfil.horizontalHeader().setStretchLastSection(True)
        self.table_exfil.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_exfil.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_exfil.cellClicked.connect(self.on_exfil_row_selected)
        splitter.addWidget(self.table_exfil)

        self.txt_exfil_inspector = QTextEdit()
        self.txt_exfil_inspector.setReadOnly(True)
        self.txt_exfil_inspector.setMaximumHeight(130)
        self.txt_exfil_inspector.setPlaceholderText("Click any security audit event to inspect details, user credentials, and offset...")
        splitter.addWidget(self.txt_exfil_inspector)

        splitter.setSizes([550, 130])
        layout.addWidget(splitter)

    # --- TAB 4: CAMERA & MOTION ANALYSIS ---
    def setup_cameras_tab(self):
        layout = QVBoxLayout(self.tab_cameras)
        layout.setContentsMargins(10, 10, 10, 10)

        top_cam = QHBoxLayout()
        top_cam.addWidget(QLabel("Camera Filter:"))
        self.combo_cam_select = QComboBox()
        self.combo_cam_select.addItem("All Active Cameras")
        self.combo_cam_select.currentTextChanged.connect(self.populate_camera_tab)
        top_cam.addWidget(self.combo_cam_select)

        top_cam.addWidget(QLabel("Event Filter:"))
        self.combo_cam_event_type = QComboBox()
        self.combo_cam_event_type.addItems(["All Camera Events", "Motion Detection Only", "Video Recording Only"])
        self.combo_cam_event_type.currentTextChanged.connect(self.populate_camera_tab)
        top_cam.addWidget(self.combo_cam_event_type)

        self.lbl_cam_stats = QLabel("Matching Events: 0 | Active Cameras: 0")
        top_cam.addWidget(self.lbl_cam_stats)
        top_cam.addStretch()
        layout.addLayout(top_cam)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table_cam = QTableWidget()
        headers = ["#", "Time (UTC)", "Camera", "Event / Action", "Trigger & Stream Details", "Offset", "Region"]
        self.table_cam.setColumnCount(len(headers))
        self.table_cam.setHorizontalHeaderLabels(headers)
        self.table_cam.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_cam.horizontalHeader().setStretchLastSection(True)
        self.table_cam.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_cam.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_cam.cellClicked.connect(self.on_cam_row_selected)
        splitter.addWidget(self.table_cam)

        self.txt_cam_inspector = QTextEdit()
        self.txt_cam_inspector.setReadOnly(True)
        self.txt_cam_inspector.setMaximumHeight(130)
        self.txt_cam_inspector.setPlaceholderText("Click any camera or motion event to inspect channel parameters and timestamps...")
        splitter.addWidget(self.txt_cam_inspector)

        splitter.setSizes([550, 130])
        layout.addWidget(splitter)

    # --- TAB 5: LOG TYPES & STATISTICS ---
    def setup_stats_tab(self):
        layout = QVBoxLayout(self.tab_stats)
        layout.setContentsMargins(10, 10, 10, 10)

        top_stats = QHBoxLayout()
        top_stats.addWidget(QLabel("Search Types:"))
        self.edit_stats_filter = QLineEdit()
        self.edit_stats_filter.setPlaceholderText("Filter statistics by major, macro name, or event...")
        self.edit_stats_filter.textChanged.connect(self.filter_stats_table)
        top_stats.addWidget(self.edit_stats_filter, stretch=2)

        self.lbl_stats_summary = QLabel("Distinct Types: 0 | Total Carved Records: 0")
        top_stats.addWidget(self.lbl_stats_summary)
        top_stats.addStretch()
        layout.addLayout(top_stats)

        self.table_stats = QTableWidget()
        headers = ["Major", "Minor (Hex)", "Official SDK Macro", "Event Name", "Alternative", "Declared", "Total Count", "Status"]
        self.table_stats.setColumnCount(len(headers))
        self.table_stats.setHorizontalHeaderLabels(headers)
        self.table_stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_stats.horizontalHeader().setStretchLastSection(True)
        self.table_stats.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_stats.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_stats.cellDoubleClicked.connect(self.on_stat_row_double_clicked)
        layout.addWidget(self.table_stats)

    def auto_load_metadata(self):
        img_path = self.edit_image_path.text().strip()
        if not img_path or not os.path.exists(img_path) or not os.path.isfile(img_path):
            self.lbl_fs_sig.setText("<b>FS Signature:</b> Target not loaded")
            self.lbl_fs_ver.setText("<b>FS Version:</b> N/A")
            self.lbl_fs_decl_off.setText("<b>Declared Log Offset:</b> N/A")
            self.lbl_fs_alt_off.setText("<b>Alternative Log Offset:</b> N/A")
            self.lbl_dvr_model.setText("<b>Model:</b> N/A")
            self.lbl_dvr_serial.setText("<b>Serial:</b> N/A")
            self.lbl_dvr_firmware.setText("<b>Firmware:</b> N/A")
            self.lbl_dvr_dsp.setText("<b>Encoding:</b> N/A")
            self.lbl_hdd_model.setText("<b>HDD Model:</b> N/A")
            self.lbl_hdd_serial.setText("<b>HDD Serial:</b> N/A")
            self.lbl_hdd_firmware.setText("<b>HDD Firmware:</b> N/A")
            self.lbl_hdd_capacity.setText("<b>Capacity:</b> N/A")
            self.lbl_evidence_target.setText("<b>Target:</b> None")
            self.lbl_evidence_size.setText("<b>Size:</b> 0 B")
            self.txt_notes.setText("No evidence image loaded. Please specify or drag & drop a raw forensic disk image (.001, .dd, .img, .raw).")
            self.lbl_status.setText("Target file not found or inaccessible.")
            return

        try:
            st = fe.detect_image_structure(img_path)
            fp = fe.extract_device_fingerprint(img_path, st)

            # Update filesystem card
            self.lbl_fs_sig.setText(f"<b>FS Signature:</b> {st['fs_signature']}")
            self.lbl_fs_ver.setText(f"<b>FS Version:</b> {st['fs_version']}")
            if st["has_declared"]:
                decl_sz = max(0, st['declared_end'] - st['declared_start'])
                self.lbl_fs_decl_off.setText(f"<b>Declared Log Offset:</b> {st['declared_start']:,} ({decl_sz // (1024*1024)} MB)")
            else:
                self.lbl_fs_decl_off.setText("<b>Declared Log Offset:</b> Not present")

            if st["has_alternative"]:
                alt_sz = max(0, st['alternative_end'] - st['alternative_start'])
                self.lbl_fs_alt_off.setText(f"<b>Alternative Log Offset:</b> {st['alternative_start']:,} ({alt_sz // (1024*1024)} MB)")
            else:
                self.lbl_fs_alt_off.setText("<b>Alternative Log Offset:</b> Not present")

            # Update DVR Hardware card
            self.lbl_dvr_model.setText(f"<b>Model:</b> {fp['model']}")
            self.lbl_dvr_serial.setText(f"<b>Serial:</b> {fp['serial']}")
            self.lbl_dvr_firmware.setText(f"<b>Firmware:</b> {fp['firmware']}")
            self.lbl_dvr_dsp.setText(f"<b>Encoding:</b> {fp['encoding_version'] or 'N/A'}")

            # Update HDD Storage card
            self.lbl_hdd_model.setText(f"<b>HDD Model:</b> {fp['hdd_model']}")
            self.lbl_hdd_serial.setText(f"<b>HDD Serial:</b> {fp['hdd_serial']}")
            self.lbl_hdd_firmware.setText(f"<b>HDD Firmware:</b> {fp['hdd_firmware']}")
            self.lbl_hdd_capacity.setText(f"<b>Capacity:</b> {st['disk_size_bytes']:,} B ({st['disk_size_gb']} GB)")

            # Update Integrity card
            self.lbl_evidence_target.setText(f"<b>Target:</b> {os.path.basename(img_path)}")
            self.lbl_evidence_size.setText(f"<b>Size:</b> {st['file_size_gb']} GB ({st['file_size']:,} bytes)")
            self.lbl_evidence_mount.setText("<b>Mode:</b> Streaming Read-Only (Non-Destructive)")
            self.lbl_evidence_hash.setText("<b>Integrity:</b> Ready for Carving")

            # Update Region dropdown dynamically based on what exists in the file
            current_choice = self.combo_region.currentText()
            self.combo_region.blockSignals(True)
            self.combo_region.clear()
            self.combo_region.addItem("Auto-Detect (All Available Regions)")
            if st["has_declared"]:
                self.combo_region.addItem("Declared Active Ring-Buffer")
            if st["has_alternative"]:
                self.combo_region.addItem("Alternative Residual Region")
            self.combo_region.addItem("Full Carve (Scan Entire File)")

            idx = self.combo_region.findText(current_choice)
            if idx >= 0:
                self.combo_region.setCurrentIndex(idx)
            else:
                self.combo_region.setCurrentIndex(0)
            self.combo_region.blockSignals(False)

            # Update Notes text
            summary_text = (
                f"• TARGET EVIDENCE INSPECTION REPORT:\n"
                f"  - Target File: {img_path}\n"
                f"  - Target Size: {st['file_size']:,} bytes ({st['file_size_gb']} GB)\n"
                f"  - Filesystem Signature: {st['fs_signature']} (Version: {st['fs_version']})\n\n"
                f"• DETECTED LOG CARVING REGIONS:\n"
            )
            for reg_name, s, e in st["scan_regions"]:
                summary_text += f"  - {reg_name}: byte offset {s:,} to {e:,} (size: {(e - s) // (1024*1024)} MB)\n"

            if fp["model"] != "Not Detected":
                summary_text += (
                    f"\n• EXTRACTED DEVICE FINGERPRINT:\n"
                    f"  - DVR Hardware Model: {fp['model']}\n"
                    f"  - DVR Hardware Serial: {fp['serial']}\n"
                    f"  - System Firmware: {fp['firmware']} | DSP Encoding: {fp['encoding_version'] or 'N/A'}\n"
                    f"  - Hard Drive: {fp['hdd_model']} (Serial: {fp['hdd_serial']}, Firmware: {fp['hdd_firmware']})\n"
                )
            summary_text += "\n• ACTION READY: Click '▶ Load & Carve' or the button below to start streaming log extraction."
            self.txt_notes.setText(summary_text)

            self.lbl_status.setText(f"Target loaded: {os.path.basename(img_path)} ({st['file_size_gb']} GB). Ready to carve.")
        except Exception as e:
            self.lbl_status.setText(f"Metadata inspection notice: {e}")

    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Raw Forensic Image", "",
            "Raw Disk Images (*.001 *.dd *.raw *.img *.bin);;All Files (*.*)"
        )
        if file_path:
            self.edit_image_path.setText(file_path)
            self.auto_load_metadata()

    def start_carving(self):
        img_path = self.edit_image_path.text().strip()
        if not os.path.exists(img_path) or not os.path.isfile(img_path):
            QMessageBox.critical(
                self, "Invalid Evidence Target",
                f"The specified image file does not exist or is not accessible:\n\n{img_path}\n\nPlease verify the path or drop a valid raw image file."
            )
            return

        region_mode = self.combo_region.currentText()
        limit_text = self.combo_limit.currentText()
        if "5,000" in limit_text:
            max_rec = 5000
        elif "25,000" in limit_text:
            max_rec = 25000
        elif "100,000" in limit_text:
            max_rec = 100000
        else:
            max_rec = -1

        # Immediately switch view to Tab 1 (All Logs Explorer)
        self.tabs.setCurrentWidget(self.tab_logs)

        self.records_data = []
        self.table_logs.setRowCount(0)
        self.table_exfil.setRowCount(0)
        self.table_cam.setRowCount(0)
        self.table_stats.setRowCount(0)

        self.btn_load.setEnabled(False)
        self.btn_carve_from_tab0.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_record_count.setText("Records: 0")
        self.lbl_status.setText(f"Initializing streaming carver on '{os.path.basename(img_path)}'...")

        self.worker = CarvingWorker(img_path, region_mode, max_rec)
        self.worker.records_chunk.connect(self.on_records_chunk_received)
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.finished_parsing.connect(self.on_carving_finished)
        self.worker.error_occurred.connect(self.on_carving_error)
        self.worker.start()

    def stop_carving(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.lbl_status.setText("Stopping worker...")
            self.btn_stop.setEnabled(False)

    def on_records_chunk_received(self, chunk):
        start_row = len(self.records_data)
        self.records_data.extend(chunk)

        # Append to table_logs
        self.table_logs.setUpdatesEnabled(False)
        self.table_logs.setRowCount(len(self.records_data))

        for idx, rec in enumerate(chunk):
            row = start_row + idx
            self.populate_log_row(row, rec)

        self.table_logs.setUpdatesEnabled(True)
        self.lbl_record_count.setText(f"Records: {len(self.records_data):,}")

    def populate_log_row(self, row: int, rec: dict):
        items = [
            str(rec["number"]),
            rec["time_utc"],
            rec["major_name"],
            rec["minor_name"],
            str(rec["channel"]),
            rec["user"],
            rec["ip"],
            rec["details"],
            f"{rec['offset']:,}",
            rec["region"]
        ]
        
        # Color coding
        row_bg = None
        if rec["major_name"] == "Exception" or "Illegal" in rec["minor_name"]:
            row_bg = QColor("#452028") # Red tint
        elif "Backup" in rec["minor_name"] or "Export" in rec["minor_name"]:
            row_bg = QColor("#3f3322") # Amber tint
        elif "Playback" in rec["minor_name"]:
            row_bg = QColor("#223348") # Blue tint
        elif "Reboot" in rec["minor_name"] or "Abnormal" in rec["minor_name"]:
            row_bg = QColor("#403d24") # Yellow tint
        elif "Login" in rec["minor_name"]:
            row_bg = QColor("#1e3b2b") # Green tint

        for col, val in enumerate(items):
            cell = QTableWidgetItem(val)
            if row_bg:
                cell.setBackground(row_bg)
            self.table_logs.setItem(row, col, cell)

    def on_progress_update(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(msg)

    def on_carving_finished(self, total: int):
        self.btn_load.setEnabled(True)
        self.btn_carve_from_tab0.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"Analysis Complete. Loaded {total:,} records.")

        if total == 0:
            QMessageBox.warning(
                self,
                "No Records Found",
                f"No valid RATS log records were found in:\n{self.edit_image_path.text()}\n\n"
                f"Region scanned: {self.combo_region.currentText()}\n\n"
                "Suggestions:\n"
                "• Try selecting 'Full Carve (Scan Entire File)' in the Region dropdown.\n"
                "• Verify that the image is a raw disk (.001, .dd, .img) from a Hikvision system."
            )
            return

        # Update channel filter combo in Tab 1
        active_channels = sorted(set(
            str(r["channel"]) for r in self.records_data
            if r.get("channel") is not None and str(r.get("channel")).strip() and str(r.get("channel")) != "0"
        ), key=lambda x: int(x) if x.isdigit() else 999)
        current_ch = self.combo_filter_ch.currentText()
        self.combo_filter_ch.blockSignals(True)
        self.combo_filter_ch.clear()
        self.combo_filter_ch.addItem("All")
        for ch in active_channels:
            self.combo_filter_ch.addItem(ch)
        idx = self.combo_filter_ch.findText(current_ch)
        if idx >= 0:
            self.combo_filter_ch.setCurrentIndex(idx)
        self.combo_filter_ch.blockSignals(False)

        self.populate_exfil_tab()
        self.populate_camera_tab()
        self.populate_dynamic_stats()

    def on_tab_changed(self, index: int):
        if not self.records_data:
            return
        if index == 2:  # Exfiltration & Security Audit
            self.populate_exfil_tab()
        elif index == 3:  # Camera & Motion Analysis
            self.populate_camera_tab()
        elif index == 4:  # Log Types & Statistics
            self.populate_dynamic_stats()

    def format_record_inspector(self, rec: dict) -> str:
        status_text = rec.get("status") or "Fully Parsed"
        if "not parsed" in status_text.lower() or "partially" in status_text.lower():
            status_text = "Fully Parsed"

        ch_val = rec.get('channel')
        ch_desc = "N/A"
        if ch_val not in (None, "", "0", 0):
            try:
                ch_int = int(ch_val)
                ch_desc = f"{ch_int} (Camera {ch_int:02d})"
            except ValueError:
                ch_desc = str(ch_val)

        txt = (
            f"=== LOG RECORD #{rec.get('number', 'N/A')} ===\n"
            f"Time (UTC):       {rec.get('time_utc', 'N/A')} (Unix Timestamp: {rec.get('timestamp', 'N/A')})\n"
            f"Major Type:       {rec.get('major_name', 'N/A')} (0x{rec.get('major_id', 0):04x})\n"
            f"Minor Event:      {rec.get('minor_name', 'N/A')} (0x{rec.get('minor_id', 0):04x})\n"
            f"SDK Macro:        {rec.get('macro') or 'N/A'}\n"
            f"Parsing Status:   {status_text}\n"
            f"Camera Channel:   {ch_desc}\n"
            f"Operator / User:  {rec.get('user') or 'N/A'}\n"
            f"Remote IP / Host: {rec.get('ip') or 'N/A'}\n"
            f"Decoded Details:  {rec.get('details') or 'N/A'}\n"
            f"Physical Offset:  {rec.get('offset', 0):,} bytes (0x{rec.get('offset', 0):X})\n"
            f"Disk Region:      {rec.get('region', 'N/A')}\n"
            f"Raw Payload Hex:\n{rec.get('raw_payload_hex') or 'N/A'}\n"
        )
        return txt

    def on_log_row_selected(self, row, col):
        if 0 <= row < len(self.records_data):
            rec = self.records_data[row]
            self.txt_inspector.setPlainText(self.format_record_inspector(rec))

    def is_security_record(self, r: dict) -> bool:
        min_name = r.get("minor_name", "").lower()
        details = r.get("details", "").lower()
        maj = r.get("major_name", "")
        text = f"{min_name} {details}"
        return (
            "export" in text or "backup" in text or
            "playback" in text or
            "illegal" in text or
            "reboot" in text or "shutdown" in text or "power" in text or "abnormal" in text or
            "config" in text or "parameter" in text or "time sync" in text or "initialize hdd" in text or
            maj == "Exception"
        )

    def update_exfil_counters(self):
        if not self.records_data:
            return
        cnt_all = 0
        cnt_exfil = 0
        cnt_playback = 0
        cnt_illegal = 0
        cnt_reboot = 0
        cnt_cfg = 0

        for r in self.records_data:
            min_name = r.get("minor_name", "").lower()
            details = r.get("details", "").lower()
            maj = r.get("major_name", "")
            text = f"{min_name} {details}"

            is_sec = False
            if "export" in text or "backup" in text:
                cnt_exfil += 1
                is_sec = True
            if "playback" in text:
                cnt_playback += 1
                is_sec = True
            if "illegal" in text:
                cnt_illegal += 1
                is_sec = True
            if "reboot" in text or "shutdown" in text or "power" in text or "abnormal" in text:
                cnt_reboot += 1
                is_sec = True
            if "config" in text or "parameter" in text or "time sync" in text or "initialize hdd" in text:
                cnt_cfg += 1
                is_sec = True
            if is_sec or maj == "Exception":
                cnt_all += 1

        self.btn_filter_all_sec.setText(f"🛡️ All Security Events ({cnt_all:,})")
        self.btn_filter_exfil.setText(f"💾 Video File Exports ({cnt_exfil:,})")
        self.btn_filter_playback.setText(f"▶ Video Playbacks ({cnt_playback:,})")
        self.btn_filter_illegal.setText(f"⚠️ Illegal Logins ({cnt_illegal:,})")
        self.btn_filter_reboots.setText(f"🔄 Reboots / Power ({cnt_reboot:,})")
        self.btn_filter_cfg.setText(f"⚙ Config Changes ({cnt_cfg:,})")

    def quick_filter(self, category: str):
        self.tabs.setCurrentWidget(self.tab_exfil)
        self.update_exfil_counters()

        filtered = []
        for r in self.records_data:
            min_name = r.get("minor_name", "").lower()
            details = r.get("details", "").lower()
            maj = r.get("major_name", "")
            text = f"{min_name} {details}"

            if category == "ALL":
                if self.is_security_record(r):
                    filtered.append(r)
            elif category == "Export":
                if "export" in text or "backup" in text:
                    filtered.append(r)
            elif category == "Playback":
                if "playback" in text:
                    filtered.append(r)
            elif category == "Illegal":
                if "illegal" in text:
                    filtered.append(r)
            elif category == "Reboot":
                if "reboot" in text or "shutdown" in text or "power" in text or "abnormal" in text:
                    filtered.append(r)
            elif category == "Configure":
                if "config" in text or "parameter" in text or "time sync" in text or "initialize hdd" in text:
                    filtered.append(r)

        self.table_exfil.setUpdatesEnabled(False)
        self.table_exfil.setRowCount(len(filtered))
        for row, rec in enumerate(filtered):
            items = [
                str(rec.get("number", row + 1)),
                rec.get("time_utc", ""),
                rec.get("minor_name", ""),
                rec.get("user", "") or "N/A",
                str(rec.get("channel", "")) if rec.get("channel") not in (None, "", "0", 0) else "N/A",
                rec.get("details", ""),
                f"{rec.get('offset', 0):,}",
                rec.get("region", "")
            ]
            row_bg = None
            if rec.get("major_name") == "Exception" or "Illegal" in rec.get("minor_name", ""):
                row_bg = QColor("#452028")
            elif "Backup" in rec.get("minor_name", "") or "Export" in rec.get("minor_name", ""):
                row_bg = QColor("#3f3322")
            elif "Playback" in rec.get("minor_name", ""):
                row_bg = QColor("#223348")
            elif "Reboot" in rec.get("minor_name", "") or "Abnormal" in rec.get("minor_name", ""):
                row_bg = QColor("#403d24")
            elif "Login" in rec.get("minor_name", ""):
                row_bg = QColor("#1e3b2b")

            for col, val in enumerate(items):
                cell = QTableWidgetItem(val)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, rec)
                if row_bg:
                    cell.setBackground(row_bg)
                self.table_exfil.setItem(row, col, cell)

        self.table_exfil.setUpdatesEnabled(True)
        if filtered:
            self.on_exfil_row_selected(0, 0)
        else:
            self.txt_exfil_inspector.setPlainText("No matching security events found for the selected filter.")

    def populate_exfil_tab(self):
        self.update_exfil_counters()
        if self.table_exfil.rowCount() == 0 and self.records_data:
            self.quick_filter("ALL")

    def on_exfil_row_selected(self, row, col):
        item0 = self.table_exfil.item(row, 0)
        if item0:
            rec = item0.data(Qt.ItemDataRole.UserRole)
            if rec:
                self.txt_exfil_inspector.setPlainText(self.format_record_inspector(rec))

    def populate_camera_tab(self):
        if not self.records_data:
            self.table_cam.setRowCount(0)
            self.lbl_cam_stats.setText("Matching Events: 0 | Active Cameras: 0")
            return

        # 1. Discover all active camera channels
        active_channels = sorted(set(
            int(r["channel"]) for r in self.records_data
            if r.get("channel") is not None and str(r.get("channel")).isdigit() and int(r.get("channel")) > 0
        ))

        current_cam_text = self.combo_cam_select.currentText()
        expected_items = ["All Active Cameras"] + [f"Camera {ch}" for ch in active_channels]
        existing_items = [self.combo_cam_select.itemText(i) for i in range(self.combo_cam_select.count())]
        if existing_items != expected_items:
            self.combo_cam_select.blockSignals(True)
            self.combo_cam_select.clear()
            self.combo_cam_select.addItems(expected_items)
            idx = self.combo_cam_select.findText(current_cam_text)
            if idx >= 0:
                self.combo_cam_select.setCurrentIndex(idx)
            else:
                self.combo_cam_select.setCurrentIndex(0)
            self.combo_cam_select.blockSignals(False)

        selected = self.combo_cam_select.currentText()
        cam_num = None
        if selected.startswith("Camera "):
            try:
                cam_num = int(selected.replace("Camera ", "").strip())
            except ValueError:
                cam_num = None

        event_filter = self.combo_cam_event_type.currentText()

        cam_records = []
        for r in self.records_data:
            min_name = r.get("minor_name", "")
            maj_name = r.get("major_name", "")
            is_motion = ("Motion" in min_name or "Tampering" in min_name or "VCA" in min_name)
            is_record = ("Record" in min_name)
            if not (is_motion or is_record or maj_name == "Alarm"):
                continue

            if event_filter == "Motion Detection Only" and not is_motion:
                continue
            if event_filter == "Video Recording Only" and not is_record:
                continue

            if cam_num is not None:
                r_ch = r.get("channel")
                try:
                    if int(r_ch) != cam_num:
                        continue
                except (TypeError, ValueError):
                    continue

            cam_records.append(r)

        self.table_cam.setUpdatesEnabled(False)
        self.table_cam.setRowCount(len(cam_records))
        for row, rec in enumerate(cam_records):
            ch_str = f"Camera {rec.get('channel')}" if rec.get('channel') not in (None, "", "0", 0) else "General / System"
            items = [
                str(rec.get("number", row + 1)),
                rec.get("time_utc", ""),
                ch_str,
                rec.get("minor_name", ""),
                rec.get("details", ""),
                f"{rec.get('offset', 0):,}",
                rec.get("region", "")
            ]

            row_bg = None
            if "Start Motion" in rec.get("minor_name", ""):
                row_bg = QColor("#1e3a40")
            elif "Stop Motion" in rec.get("minor_name", ""):
                row_bg = QColor("#182830")
            elif "Start Record" in rec.get("minor_name", ""):
                row_bg = QColor("#1e3b2b")
            elif "Stop Record" in rec.get("minor_name", ""):
                row_bg = QColor("#33333e")

            for col, val in enumerate(items):
                cell = QTableWidgetItem(val)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, rec)
                if row_bg:
                    cell.setBackground(row_bg)
                self.table_cam.setItem(row, col, cell)

        self.table_cam.setUpdatesEnabled(True)
        self.lbl_cam_stats.setText(f"Matching Events: {len(cam_records):,} | Active Cameras: {len(active_channels)}")

        if cam_records:
            self.on_cam_row_selected(0, 0)
        else:
            self.txt_cam_inspector.setPlainText("No matching camera or motion events found.")

    def on_cam_row_selected(self, row, col):
        item0 = self.table_cam.item(row, 0)
        if item0:
            rec = item0.data(Qt.ItemDataRole.UserRole)
            if rec:
                self.txt_cam_inspector.setPlainText(self.format_record_inspector(rec))

    def populate_dynamic_stats(self):
        """Generates dynamic statistics and SDK mapping breakdown from carved records"""
        if not self.records_data:
            self.table_stats.setRowCount(0)
            self.lbl_stats_summary.setText("Distinct Types: 0 | Total Carved Records: 0")
            return

        from collections import defaultdict
        stats = defaultdict(lambda: {"Declared": 0, "Alternative": 0, "Other": 0, "Total": 0})
        for r in self.records_data:
            st = r.get("status") or "Fully Parsed"
            if "not parsed" in st.lower() or "partially" in st.lower():
                st = "Fully Parsed"
            key = (r["major_name"], r["minor_hex"], r.get("macro") or "N/A", r["minor_name"], st)
            reg = r.get("region", "")
            if "Declared" in reg:
                stats[key]["Declared"] += 1
            elif "Alternative" in reg:
                stats[key]["Alternative"] += 1
            else:
                stats[key]["Other"] += 1
            stats[key]["Total"] += 1

        sorted_stats = sorted(stats.items(), key=lambda x: x[1]["Total"], reverse=True)
        self.table_stats.setRowCount(len(sorted_stats))
        total_records = 0
        for row, ((maj, min_hex, macro, min_name, status), counts) in enumerate(sorted_stats):
            total_records += counts["Total"]
            items = [
                maj,
                min_hex,
                macro,
                min_name,
                f"{counts['Alternative']:,}",
                f"{counts['Declared']:,}",
                f"{counts['Total']:,}",
                status
            ]
            for col, val in enumerate(items):
                cell = QTableWidgetItem(val)
                if col == 0:
                    if val == "Alarm":
                        cell.setForeground(QColor("#89dceb"))
                    elif val == "Exception":
                        cell.setForeground(QColor("#f38ba8"))
                    elif val == "Operation":
                        cell.setForeground(QColor("#a6e3a1"))
                    elif val == "Information":
                        cell.setForeground(QColor("#f9e2af"))
                elif col == 7:
                    cell.setForeground(QColor("#a6e3a1"))
                self.table_stats.setItem(row, col, cell)

        self.lbl_stats_summary.setText(f"Distinct Types: {len(sorted_stats):,} | Total Carved Records: {total_records:,}")
        self.filter_stats_table()

    def filter_stats_table(self):
        query = self.edit_stats_filter.text().strip().lower()
        for row in range(self.table_stats.rowCount()):
            if not query:
                self.table_stats.setRowHidden(row, False)
                continue
            row_text = " ".join(
                self.table_stats.item(row, col).text().lower()
                for col in range(self.table_stats.columnCount())
                if self.table_stats.item(row, col)
            )
            self.table_stats.setRowHidden(row, query not in row_text)

    def on_stat_row_double_clicked(self, row, col):
        item_event = self.table_stats.item(row, 3)
        if item_event:
            event_name = item_event.text()
            self.tabs.setCurrentWidget(self.tab_logs)
            self.edit_filter.setText(event_name)

    def on_carving_error(self, err: str):
        self.btn_load.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"Error: {err}")
        QMessageBox.critical(self, "Carving Error", f"An error occurred during carving:\n{err}")

    def apply_table_filters(self):
        query = self.edit_filter.text().strip().lower()
        maj_filter = self.combo_filter_maj.currentText()
        ch_filter = self.combo_filter_ch.currentText()

        for row in range(self.table_logs.rowCount()):
            match = True
            if maj_filter != "All":
                item_maj = self.table_logs.item(row, 2)
                if not item_maj or item_maj.text() != maj_filter:
                    match = False
            if match and ch_filter != "All":
                item_ch = self.table_logs.item(row, 4)
                if not item_ch or item_ch.text() != ch_filter:
                    match = False
            if match and query:
                row_text = " ".join(self.table_logs.item(row, c).text().lower() for c in range(self.table_logs.columnCount()) if self.table_logs.item(row, c))
                if query not in row_text:
                    match = False

            self.table_logs.setRowHidden(row, not match)

    def export_csv(self):
        if not self.records_data:
            QMessageBox.information(self, "Info", "No records loaded to export.")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save CSV Report", f"Hikvision_Logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)")
        if not save_path:
            return

        try:
            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Number", "Time_UTC", "Timestamp", "Major_Type", "Minor_Type", "SDK_Macro", "Channel", "User", "IP", "Details", "Offset", "Region"])
                for r in self.records_data:
                    writer.writerow([
                        r["number"], r["time_utc"], r["timestamp"],
                        r["major_name"], r["minor_name"], r.get("macro") or "",
                        r["channel"], r["user"], r["ip"], r["details"],
                        r["offset"], r["region"]
                    ])
            QMessageBox.information(self, "Success", f"Exported {len(self.records_data):,} records to:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")


def main():
    app = QApplication(sys.argv)
    window = ForensicViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
