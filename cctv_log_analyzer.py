import sys
import os
import sqlite3
import csv
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal, Slot, QDate, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QFrame, QSizePolicy, QCheckBox,
    QDateEdit, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QPlainTextEdit, QInputDialog
)
from PySide6.QtGui import QColor, QFont, QIcon, QAction, QDesktopServices

# Ensure scripts dir is importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from scripts.dvr_extractor import detect_brand_details, export_to_html, export_to_csv
from scripts.display_values import display_value
from scripts.engine_hikvision import (
    HikvisionEngine, detect_image_structure, extract_device_fingerprint,
)
from scripts.engine_dahua import DahuaEngine
from scripts.dahua_analysis import build_analysis_database
from scripts.engine_tvt import TVTEngine
from scripts.engine_icatch import ICatchEngine
from scripts.versioning import get_version, resource_path, version_info
from scripts.app_settings import AppSettings, resolve_theme
from scripts.settings_dialog import SettingsDialog
from scripts.filter_header import ColumnFilterHeader
from scripts.sse_progress import encode_sse, decode_sse
from scripts.logging_config import configure_logging, install_exception_hook, log_dir
from scripts.device_metadata import (
    acquisition_metadata, dahua_database_metadata, tvt_filesystem_metadata,
    tvt_log_metadata, icatch_timeline_metadata,
)
from scripts import recents
from scripts.physical_drive import (
    is_physical_drive, list_physical_drives, drive_volume_letters,
    is_running_as_admin, relaunch_as_admin,
)
from scripts.image_io import open_image
from scripts.table_rows import CELL_ALIGNMENT, cell_summary, cell_tooltip, fit_rows
from scripts.entropy_dialog import EntropyDialog
from scripts.tvt_log_fields import ensure_tvt_mlogtype
from scripts.report_options import ReportOptionsDialog
from scripts.cancellation import check_cancelled, ExtractionCancelled
from scripts.hikvision_investigation import HikvisionInvestigation
from scripts.case_workspace import (
    initialize_case, create_workspace, audit, update_workspace, workspace_for_database,
)

APP_VERSION = get_version()
APP_NAME = version_info()['product_name']
LOGGER = configure_logging()
DAHUA_LOG_SCOPE_NOTICE = (
    "Some Dahua log types may exist only in the recorder's internal memory or "
    "its on-device GUI/export. Logs recovered from disk databases may therefore "
    "be incomplete; absence of an event here does not prove it did not occur."
)

DARK_THEME_QSS = """
* { font-family: "Segoe UI", sans-serif; font-size: 13px; color: #e6e9f0; }
QMainWindow, QWidget#Root { background-color: #101319; }
QWidget { background: transparent; }
QFrame#Header { background: #171b23; border: 1px solid #232935; border-radius: 12px; }
QFrame#Sidebar { background: #171b23; border-right: 1px solid #2c3340; }
QLabel#Title { font-size: 23px; font-weight: 700; color: #f4f6fb; }
QLabel#CompactTitle { font-size: 16px; font-weight: 700; color: #f4f6fb; }
QLabel#Subtitle { color: #8b94a8; }
QLabel#SectionTitle { font-size: 15px; font-weight: 650; color: #f4f6fb; }
QLabel#Badge, QPushButton#VersionBadge { background: #1c2942; color: #7aa4f5; border: 1px solid #314873; border-radius: 11px; padding: 4px 10px; font-weight: 600; }
QLabel#StatusGood { color: #3fc48a; font-weight: 600; }
QLabel#StatusMuted { color: #8b94a8; }
QLabel#CoverageWarning { color: #f0b35a; font-weight: 600; }
QGroupBox {
    background: #171b23; border: 1px solid #2c3340; border-radius: 10px;
    margin-top: 14px; padding-top: 8px; font-weight: 600; color: #f4f6fb;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; padding: 0 6px;
}
QLineEdit, QComboBox, QDateEdit, QSpinBox {
    background: #1f242e; color: #e6e9f0; border: 1px solid #2c3340;
    padding: 8px 10px; border-radius: 7px; min-height: 20px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus { border: 1px solid #5b8def; }
QComboBox QAbstractItemView {
    background: #1f242e; color: #e6e9f0; border: 1px solid #465168;
    selection-background-color: #263a60; selection-color: #ffffff;
    outline: none;
}
QComboBox QAbstractItemView::item { min-height: 25px; padding: 3px 7px; }
QComboBox::drop-down, QDateEdit::drop-down {
    background: #272d39; border-left: 1px solid #465168;
    width: 25px; border-top-right-radius: 6px; border-bottom-right-radius: 6px;
}
QCalendarWidget { background: #171b23; color: #e6e9f0; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #1f242e; }
QCalendarWidget QToolButton, QCalendarWidget QSpinBox {
    background: #272d39; color: #e6e9f0; border: 1px solid #465168;
}
QCalendarWidget QAbstractItemView {
    background: #171b23; color: #e6e9f0;
    selection-background-color: #263a60; selection-color: #ffffff;
}
QMenu { background: #1f242e; color: #e6e9f0; border: 1px solid #465168; }
QToolTip {
    background: #1f242e; color: #e6e9f0; border: 1px solid #465168;
    padding: 6px 8px; border-radius: 4px;
}
QMenu::item:selected { background: #263a60; color: #ffffff; }
QLineEdit#ColumnFilter { padding: 2px 5px; min-height: 17px; border-radius: 4px; font-size: 11px; }
QPushButton {
    background: #272d39; color: #e6e9f0; padding: 8px 15px;
    border: 1px solid #343c4b; border-radius: 7px; font-weight: 600;
}
QPushButton:hover { background: #303746; border-color: #465168; }
QPushButton:pressed { background: #202631; }
QPushButton:disabled { background: #1b1f27; color: #5d6577; border-color: #232935; }
QPushButton#Primary { background: #5b8def; color: white; border: none; }
QPushButton#Primary:hover { background: #7aa4f5; }
QPushButton#Success { background: #23865e; color: white; border: none; }
QPushButton#Success:hover { background: #2da873; }
QTabWidget::pane { background: #171b23; border: 1px solid #2c3340; border-radius: 9px; top: -1px; }
QTabBar::tab { background: #101319; color: #8b94a8; padding: 10px 18px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #e6e9f0; border-bottom: 2px solid #5b8def; background: #171b23; }
QTableWidget {
    background: #141820; alternate-background-color: #181d26; color: #dfe4ee;
    border: none; gridline-color: #232935; font-family: "Cascadia Mono", Consolas, monospace;
    selection-background-color: #263a60; selection-color: #ffffff;
}
QHeaderView::section {
    background: #1f242e; color: #aeb6c8; padding: 5px 8px 31px 8px; border: none;
    border-right: 1px solid #2c3340; border-bottom: 1px solid #2c3340; font-weight: 600;
}
QProgressBar {
    text-align: center; color: #e6e9f0; background: #1f242e;
    border: 1px solid #2c3340; border-radius: 6px; min-height: 12px;
}
QProgressBar#CompactProgress { min-height: 8px; max-height: 14px; border-radius: 4px; }
QProgressBar#CompactProgress::chunk { border-radius: 3px; }
QProgressBar::chunk { background: #5b8def; border-radius: 5px; }
QTextEdit, QPlainTextEdit {
    background: #0d1015; color: #a8d8b9; border: none;
    font-family: "Cascadia Mono", Consolas, monospace; padding: 10px;
}
QScrollBar:vertical { background: #141820; width: 11px; }
QScrollBar::handle:vertical { background: #343c4b; border-radius: 5px; min-height: 28px; }
QStatusBar { background: #171b23; color: #8b94a8; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 9px 7px; border-radius: 6px; }
QListWidget::item:hover { background: #272d39; }
QListWidget::item:selected { background: #263a60; color: #ffffff; }
QDialog, QMessageBox { background: #171b23; }
QMessageBox QLabel { color: #e6e9f0; }
QFrame#DateFilterBar { background: #171b23; border: 1px solid #2c3340; border-radius: 8px; }
QDateEdit#DateFilter { min-width: 150px; min-height: 28px; font-weight: 600; }
"""

LIGHT_REPLACEMENTS = {
    "#101319": "#f6f7fa", "#171b23": "#ffffff", "#232935": "#e8ebf1",
    "#e6e9f0": "#171a21", "#f4f6fb": "#171a21", "#8b94a8": "#666f80",
    "#1c2942": "#e6eefc", "#7aa4f5": "#1f5bc7", "#314873": "#b9cff6",
    "#3fc48a": "#1a9c60", "#2c3340": "#dde1e9", "#1f242e": "#f0f2f6",
    "#272d39": "#e8ebf1", "#343c4b": "#d2d7e0", "#303746": "#dde3ed",
    "#465168": "#b7c0ce", "#202631": "#d7dce5", "#1b1f27": "#eef0f4",
    "#5d6577": "#98a0b0", "#141820": "#ffffff", "#181d26": "#f7f8fa",
    "#dfe4ee": "#20242c", "#263a60": "#dce8fb", "#aeb6c8": "#596273",
    "#0d1015": "#f4f6f9", "#a8d8b9": "#246b45",
    "#f0b35a": "#9a5b09",
}


def application_stylesheet(theme, family, size):
    """Stylesheet for 'dark', 'light' or 'system' (resolved from Windows)."""
    theme = resolve_theme(theme)
    sheet = DARK_THEME_QSS.replace('"Segoe UI", sans-serif', f'"{family}", "Segoe UI", sans-serif')
    sheet = sheet.replace("font-size: 13px", f"font-size: {size}px", 1)
    if theme == "light":
        for dark, light in LIGHT_REPLACEMENTS.items():
            sheet = sheet.replace(dark, light)
        sheet += """
QComboBox QAbstractItemView, QCalendarWidget QAbstractItemView, QMenu {
    selection-color: #171a21;
}
QMenu::item:selected { color: #171a21; }
"""
    return sheet

class ExtractionThread(QThread):
    log_signal = Signal(str)
    sse_signal = Signal(str)
    metadata_signal = Signal(dict)
    artifacts_signal = Signal(list)
    cancelled_signal = Signal(str)
    finished_signal = Signal(bool, str, str, str) # success, msg, db_path, table_name

    def __init__(self, image_path, out_dir, brand, workspace=None):
        super().__init__()
        self.image_path = image_path
        self.out_dir = out_dir
        self.brand = brand
        self.workspace = workspace

    def run(self):
        try:
            self._check_cancelled()
            update_workspace(self.workspace, status='running')
            LOGGER.info("Extraction started | brand=%s | image=%s | output=%s",
                        self.brand, self.image_path, self.out_dir)
            self._event("started", phase="prepare", brand=self.brand,
                        image=self.image_path, output=self.out_dir)
            
            os.makedirs(self.out_dir, exist_ok=True)

            db_out_path = os.path.join(self.out_dir, f"Extracted_Logs_{self.brand}.db")
            table_name = ""
            generated_files = []

            if self.brand == 'TVT':
                self._event("phase", phase="scan", detail="Initializing TVT engine")
                engine = TVTEngine(self.image_path)
                records = engine.extract_logs(
                    start_offset=850*1024*1024,
                    limit_bytes=1100*1024*1024,
                    progress_callback=lambda done, total, records: self._progress(
                        done, total, "TVT raw scan", records=records),
                    cancelled=self.isInterruptionRequested,
                )
                self._event("phase", phase="database", detail=f"Writing {len(records):,} records")
                engine.save_to_sqlite(records, db_out_path, cancelled=self.isInterruptionRequested)
                table_name = "tvt_logs"
                self.metadata_signal.emit(tvt_log_metadata(records))
                
            elif self.brand == 'DAHUA':
                self._event("phase", phase="evidence", detail="Opening and indexing EWF evidence",
                            indeterminate=True)
                engine = DahuaEngine(self.image_path)
                # Keep one libewf handle for partition detection and XFS
                # extraction. Re-opening a monolithic multi-TB E01 rebuilds
                # its index and can overwhelm a VM.
                with engine._open_image() as evidence:
                    partitions = engine.detect_partitions(evidence, cancelled=self.isInterruptionRequested)
                    xfs_part = next((p for p in partitions if p['is_target']), None)
                    if xfs_part:
                        extracted = engine.extract_xfs_native(
                            xfs_part['start_lba'] * 512, self.out_dir,
                            progress_callback=lambda done, total, name: self._progress(
                                done, total, "Dahua XFS extraction", file=name),
                            image_handle=evidence,
                            cancelled=self.isInterruptionRequested,
                            status_callback=lambda detail, indeterminate: self._event(
                                "phase", phase="Dahua XFS", detail=detail,
                                indeterminate=indeterminate),
                        )
                    else:
                        extracted = []
                if xfs_part:
                    if extracted:
                        generated_files.extend(extracted)
                        db_out_path = os.path.join(self.out_dir, "Dahua_Analysis.db")
                        self._event(
                            "phase", phase="database",
                            detail=f"Normalizing {len(extracted)} Dahua databases")
                        summary = build_analysis_database(
                            extracted, db_out_path,
                            progress_callback=lambda done, total, name, records:
                                self._item_progress(done, total, "Dahua database analysis",
                                                    file=name, records=records),
                            cancelled=self.isInterruptionRequested,
                        )
                        table_name = "dahua_logs"
                        self.metadata_signal.emit(dahua_database_metadata(extracted))
                        self._event(
                            "phase", phase="database",
                            detail=(f"Inventoried {summary['databases']} databases; "
                                    f"normalized {summary['logs']:,} logs"))
                    if not extracted:
                        raise RuntimeError("No Dahua SQLite databases were extracted.")
                else:
                    raise RuntimeError("No Dahua XFS partition found.")
                    
            elif self.brand == 'HIKVISION':
                self._event("phase", phase="scan", detail="Initializing Hikvision RATS scanner")
                engine = HikvisionEngine(self.image_path)
                structure = detect_image_structure(self.image_path)
                self._check_cancelled()
                fingerprint = extract_device_fingerprint(self.image_path, structure, cancelled=self.isInterruptionRequested)
                self._check_cancelled()
                hik_metadata = {
                    "Recorder model": (fingerprint.get("model", "Not Detected"), "Hikvision Power On record"),
                    "Recorder serial": (fingerprint.get("serial", "Not Detected"), "Hikvision Power On record"),
                    "Recorder firmware": (fingerprint.get("firmware", "Not Detected"), "Hikvision Power On record"),
                    "Disk model": (fingerprint.get("hdd_model", "Not Detected"), "Hikvision HDD Info record"),
                    "Disk serial": (fingerprint.get("hdd_serial", "Not Detected"), "Hikvision HDD Info record"),
                    "Disk firmware": (fingerprint.get("hdd_firmware", "Not Detected"), "Hikvision HDD Info record"),
                    "Filesystem": (structure.get("fs_signature", "Not Detected"), "Hikvision filesystem header"),
                    "Filesystem version": (structure.get("fs_version", "N/A"), "Hikvision filesystem header"),
                    "Filesystem initialized": (structure.get("init_time", "N/A"), "Hikvision filesystem header"),
                }
                self.metadata_signal.emit(hik_metadata)
                engine.carve_to_sqlite(
                    db_out_path, limit_bytes=5*1024*1024*1024,
                    progress_callback=lambda done, total, records, region: self._progress(
                        done, total, "Hikvision raw scan", records=records, region=region),
                    structure=structure,
                    cancelled=self.isInterruptionRequested,
                )
                table_name = "hikvision_logs"
            elif self.brand == 'ICATCH':
                self._event(
                    "phase", phase="entropy",
                    detail="Profiling the bounded metadata region and validating HOUR records")
                engine = ICatchEngine(self.image_path)
                records = engine.extract_timeline(
                    progress_callback=lambda done, total, records: self._progress(
                        done, total, "iCatch metadata scan", records=records),
                )
                db_out_path = os.path.join(self.out_dir, "Extracted_Logs_ICATCH.db")
                self._event(
                    "phase", phase="database",
                    detail=f"Writing {len(records):,} validated hourly index records")
                engine.save_to_sqlite(records, db_out_path)
                table_name = "icatch_timeline"
                self.metadata_signal.emit(icatch_timeline_metadata(records))
            else:
                raise RuntimeError(f"Unsupported or unknown DVR brand: {self.brand}")
            
            self._check_cancelled()
            connection = sqlite3.connect(db_out_path)
            try:
                record_count = connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            finally:
                connection.close()
            self._event("completed", phase="complete", progress=100,
                        database=db_out_path, table=table_name, records=record_count)
            self.artifacts_signal.emit(list(dict.fromkeys([*generated_files, db_out_path])))
            update_workspace(self.workspace, status='completed', database=db_out_path,
                             table=table_name, record_count=record_count,
                             artifacts=[*generated_files, db_out_path])
            LOGGER.info("Extraction completed | brand=%s | database=%s | table=%s",
                        self.brand, db_out_path, table_name)
            self.finished_signal.emit(True, "Extraction Complete!", db_out_path, table_name)
            
        except ExtractionCancelled as exc:
            artifacts = [os.path.join(root, name) for root, _, names in os.walk(self.out_dir)
                         for name in names]
            try:
                update_workspace(self.workspace, status='cancelled', artifacts=artifacts,
                                 partial_results=True)
                self._event('cancelled', phase='cancelled', detail=str(exc),
                            partial_results=True)
            except Exception:
                LOGGER.exception('Could not write workspace cancellation audit')
            self.artifacts_signal.emit(artifacts)
            LOGGER.info('Extraction cancelled | brand=%s | image=%s', self.brand, self.image_path)
            self.cancelled_signal.emit(str(exc))
        except Exception as e:
            LOGGER.exception("Extraction failed | brand=%s | image=%s",
                             self.brand, self.image_path)
            import traceback
            try:
                self._event("error", phase="failed", detail=str(e))
                update_workspace(self.workspace, status='failed', error=str(e))
                audit(self.workspace, 'traceback', detail=traceback.format_exc())
            except Exception:
                LOGGER.exception('Could not write workspace failure audit')
            self.log_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, str(e), "", "")

    def _event(self, event, **data):
        if event not in ('cancelled', 'error'):
            self._check_cancelled()
        audit(self.workspace, event, **data)
        self.sse_signal.emit(encode_sse(event, **data))

    def _check_cancelled(self):
        check_cancelled(self.isInterruptionRequested)

    def _progress(self, done, total, phase, **details):
        percent = min(100, max(0, round(done * 100 / max(1, total))))
        self._event("progress", phase=phase, progress=percent,
                    bytes_done=done, bytes_total=total, **details)

    def _item_progress(self, done, total, phase, **details):
        percent = min(100, max(0, round(done * 100 / max(1, total))))
        self._event("progress", phase=phase, progress=percent,
                    items_done=done, items_total=total, **details)

class CCTVLogAnalyzerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        application = QApplication.instance()
        if application is not None:
            application.setApplicationName(APP_NAME)
            application.setApplicationVersion(APP_VERSION)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        icon_path = resource_path("assets", "cctv-log-analyzer.ico")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.settings = AppSettings()
        recents.initialize()
        
        self.current_db = ""
        self.current_table = ""
        self.image_path = ""
        self.selected_drive_info = None
        self.detected_brand = ""
        self.case_folder = str(self.settings.get('case_folder') or '')
        self.workspace_dir = ''
        self.extraction_thread = None
        saved_output = str(self.settings.get("last_output_dir") or "")
        self.out_dir = (saved_output if os.path.isdir(saved_output)
                        else os.path.join(os.getcwd(), "output"))
        self.columns = []
        self.date_column = None
        self.category_column = None
        self.current_page = 1
        self.total_rows = 0
        self.metadata = {}

        self.init_ui()
        self.apply_settings()
        if application is not None:
            # Follow Windows light/dark changes while the app is running.
            application.styleHints().colorSchemeChanged.connect(
                self._system_colour_scheme_changed)

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("Root")
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(10, 12, 10, 10)
        side_title = QLabel("CCTV LOG ANALYZER")
        side_title.setObjectName("SectionTitle")
        side_layout.addWidget(side_title)
        self.case_label = QLabel('Case: ' + (os.path.basename(self.case_folder) if self.case_folder else 'Not selected'))
        self.case_label.setWordWrap(True)
        self.case_label.setToolTip(self.case_folder)
        side_layout.addWidget(self.case_label)
        case_button = QPushButton('Select Case Folder')
        case_button.clicked.connect(self.action_select_case)
        side_layout.addWidget(case_button)
        self.workspace_button = QPushButton('Open Workspace')
        self.workspace_button.setEnabled(False)
        self.workspace_button.clicked.connect(self.open_workspace_folder)
        side_layout.addWidget(self.workspace_button)
        side_layout.addSpacing(8)
        recent_title = QLabel("RECENT EVIDENCE")
        recent_title.setObjectName("StatusMuted")
        side_layout.addWidget(recent_title)
        self.recent_list = QListWidget()
        self.recent_list.setToolTip("Double-click to reopen evidence")
        self.recent_list.itemDoubleClicked.connect(self.open_recent_item)
        side_layout.addWidget(self.recent_list, 1)
        clear_recent_button = QPushButton("Clear Recent")
        clear_recent_button.setToolTip("Clear the recent-evidence list only; extracted files are kept")
        clear_recent_button.clicked.connect(self.clear_recent_history)
        side_layout.addWidget(clear_recent_button)
        settings_button = QPushButton("⚙  Settings")
        settings_button.clicked.connect(self.open_settings)
        side_layout.addWidget(settings_button)
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)
        root_layout.addWidget(content, 1)

        # One compact evidence toolbar replaces the former large title card and
        # separate target group, preserving vertical space for result rows.
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)
        self.sidebar_toggle = QPushButton("☰")
        self.sidebar_toggle.setFixedWidth(38)
        self.sidebar_toggle.setToolTip("Show/hide recent evidence sidebar")
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        title = QLabel(APP_NAME)
        title.setObjectName("CompactTitle")
        edition = QPushButton(f"v{APP_VERSION}")
        edition.setObjectName("VersionBadge")
        edition.setToolTip("View version history")
        edition.clicked.connect(self.show_version_dialog)
        self.admin_lbl = QLabel("Administrator")
        self.admin_lbl.setObjectName("Badge")
        self.admin_lbl.setToolTip("Running with Administrator rights; physical drives can be read")
        self.admin_lbl.setVisible(is_running_as_admin())

        self.img_lbl = QLabel("No Image Loaded")
        self.img_lbl.setObjectName("StatusMuted")
        self.img_lbl.setMinimumWidth(100)
        self.img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self.brand_lbl = QLabel("Brand: N/A")
        self.brand_lbl.setObjectName("Badge")
        self.log_availability_lbl = QLabel("")
        self.log_availability_lbl.setObjectName("StatusMuted")
        
        btn_load = QPushButton("Load Image")
        btn_load.setObjectName("Primary")
        btn_load.clicked.connect(self.action_load_image)
        btn_drive = QPushButton("Physical Drive")
        btn_drive.setToolTip("Analyze a Windows physical disk directly (read-only; may require Administrator)")
        btn_drive.clicked.connect(self.action_load_drive)
        
        self.btn_carve = QPushButton("Carve Data")
        self.btn_carve.setEnabled(False)
        self.btn_carve.setObjectName("Success")
        self.btn_carve.clicked.connect(self.action_carve_data)
        self.btn_cancel = QPushButton('Cancel extraction')
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.action_cancel_extraction)
        self.btn_entropy = QPushButton('Entropy test')
        self.btn_entropy.setToolTip('Survey an unrecognized image for potentially structured regions')
        self.btn_entropy.setVisible(False)
        self.btn_entropy.clicked.connect(self.action_entropy_test)

        header_layout.addWidget(self.sidebar_toggle)
        header_layout.addWidget(title)
        header_layout.addWidget(edition)
        header_layout.addWidget(self.admin_lbl)
        header_layout.addSpacing(6)
        header_layout.addWidget(btn_load)
        header_layout.addWidget(btn_drive)
        header_layout.addWidget(self.img_lbl, 1)
        header_layout.addWidget(self.brand_lbl)
        header_layout.addWidget(self.log_availability_lbl)
        header_layout.addWidget(self.btn_carve)
        header_layout.addWidget(self.btn_cancel)
        header_layout.addWidget(self.btn_entropy)
        self.refresh_recent_list()
        main_layout.addWidget(header)
        
        # --- Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("CompactProgress")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0% · Waiting")
        main_layout.addWidget(self.progress_bar)
        
        # --- Tabs (Search & Terminal) ---
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        
        # Tab 1: Database Search View
        self.tab_search = QWidget()
        search_layout = QVBoxLayout(self.tab_search)
        search_layout.setContentsMargins(8, 6, 8, 6)
        search_layout.setSpacing(6)
        
        filter_layout = QHBoxLayout()
        self.table_selector = QComboBox()
        self.table_selector.setMinimumWidth(170)
        self.table_selector.setToolTip("Select an extracted dataset/table")
        self.table_selector.currentTextChanged.connect(self.table_changed)
        self.filter_text = QLineEdit()
        self.filter_text.setPlaceholderText("Global search across all columns...")
        self.filter_text.returnPressed.connect(self.reset_and_populate)
        self.category_selector = QComboBox()
        self.category_selector.setMinimumWidth(150)
        self.category_selector.setToolTip("Filter records by log category")
        self.category_selector.addItem("All categories", None)
        self.category_selector.setEnabled(False)
        self.category_selector.currentIndexChanged.connect(self.reset_and_populate)
        
        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self.reset_and_populate)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_filters)
        
        btn_export_csv = QPushButton("Export to Excel/CSV")
        btn_export_csv.clicked.connect(self.action_export_csv)
        btn_export_html = QPushButton("Export to HTML")
        btn_export_html.clicked.connect(self.action_export_html)
        
        filter_layout.addWidget(QLabel("Dataset:"))
        filter_layout.addWidget(self.table_selector)
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.filter_text, 1)
        filter_layout.addWidget(QLabel("Category:"))
        filter_layout.addWidget(self.category_selector)
        filter_layout.addWidget(btn_search)
        filter_layout.addWidget(btn_clear)
        filter_layout.addWidget(btn_export_csv)
        filter_layout.addWidget(btn_export_html)

        date_bar = QFrame()
        date_bar.setObjectName("DateFilterBar")
        date_layout = QHBoxLayout(date_bar)
        date_layout.setContentsMargins(8, 4, 8, 4)
        date_layout.setSpacing(7)
        date_title = QLabel("DATE FILTER")
        date_title.setObjectName("SectionTitle")
        self.date_enabled = QCheckBox("Filter dates")
        self.date_enabled.toggled.connect(self._date_controls_enabled)
        self.date_from = QDateEdit(QDate.currentDate().addYears(-1))
        self.date_to = QDateEdit(QDate.currentDate())
        for control in (self.date_from, self.date_to):
            control.setObjectName("DateFilter")
            control.setCalendarPopup(True)
            control.setDisplayFormat("yyyy-MM-dd")
            control.setEnabled(False)
            control.setMinimumWidth(165)
            control.setMinimumHeight(28)
            control.dateChanged.connect(self._date_value_changed)
        apply_date = QPushButton("Apply date range")
        apply_date.clicked.connect(self.reset_and_populate)
        date_layout.addWidget(date_title)
        date_layout.addWidget(self.date_enabled)
        date_layout.addWidget(QLabel("From"))
        date_layout.addWidget(self.date_from)
        date_layout.addWidget(QLabel("To"))
        date_layout.addWidget(self.date_to)
        date_layout.addWidget(apply_date)
        self.database_selector = QComboBox()
        self.database_selector.addItem('All source databases', None)
        self.database_selector.setMinimumWidth(220)
        self.database_selector.setToolTip('Filter Dahua logs by the extracted source database')
        self.database_selector.setVisible(False)
        self.database_selector.currentIndexChanged.connect(self.reset_and_populate)
        date_layout.addWidget(self.database_selector)
        self.mlogtype_selector = QComboBox()
        self.mlogtype_selector.addItem('All mlogtypes', None)
        self.mlogtype_selector.setMinimumWidth(180)
        self.mlogtype_selector.setToolTip('TVT: original mlogtype field, independently of translated category')
        self.mlogtype_selector.setVisible(False)
        self.mlogtype_selector.currentIndexChanged.connect(self.reset_and_populate)
        date_layout.addWidget(self.mlogtype_selector)
        date_layout.addStretch(1)
        
        self.table = QTableWidget()
        self.filter_header = ColumnFilterHeader(Qt.Horizontal, self.table)
        self.filter_header.filtersChanged.connect(self.reset_and_populate)
        self.table.setHorizontalHeader(self.filter_header)
        self.table.horizontalScrollBar().valueChanged.connect(
            self._table_scrolled)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self.open_record_details)
        self.filter_header.setStretchLastSection(False)
        self.filter_header.setMinimumSectionSize(130)
        self.filter_header.setDefaultSectionSize(190)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(True)
        # Cells hold summaries; elide values that cannot wrap (e.g. raw payloads)
        # so they never paint over the neighbouring column.
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.horizontalHeader().sectionResized.connect(
            self._table_section_resized)
        
        search_layout.addLayout(filter_layout)
        search_layout.addWidget(date_bar)
        search_layout.addWidget(self.table)

        pager = QHBoxLayout()
        self.prev_page = QPushButton("Previous")
        self.next_page = QPushButton("Next")
        self.page_label = QLabel("Page 0 of 0")
        self.page_size = QComboBox()
        for size in (50, 100, 250, 500):
            self.page_size.addItem(f"{size} rows", size)
        index = self.page_size.findData(int(self.settings.get("page_size")))
        self.page_size.setCurrentIndex(index if index >= 0 else 1)
        self.prev_page.clicked.connect(self.go_previous_page)
        self.next_page.clicked.connect(self.go_next_page)
        self.page_size.currentIndexChanged.connect(self.page_size_changed)
        pager.addWidget(self.prev_page)
        pager.addWidget(self.next_page)
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(QLabel("Page size"))
        pager.addWidget(self.page_size)
        search_layout.addLayout(pager)
        
        # Tab 2: Terminal Logs
        self.tab_terminal = QWidget()
        terminal_layout = QVBoxLayout(self.tab_terminal)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        terminal_layout.addWidget(self.log_text)

        self.tab_metadata = QWidget()
        metadata_layout = QVBoxLayout(self.tab_metadata)
        metadata_intro = QLabel(
            "Device, disk and filesystem facts. The Source column records provenance.")
        metadata_intro.setObjectName("StatusMuted")
        self.metadata_table = QTableWidget(0, 3)
        self.metadata_table.setHorizontalHeaderLabels(["Field", "Value", "Source"])
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
        self.metadata_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.metadata_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.metadata_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metadata_table.setAlternatingRowColors(True)
        self.metadata_table.verticalHeader().setVisible(False)
        metadata_layout.addWidget(metadata_intro)
        metadata_layout.addWidget(self.metadata_table, 1)
        
        self.tabs.addTab(self.tab_search, "Log Database")
        self.tabs.addTab(self.tab_terminal, "Terminal Output")
        self.tabs.addTab(self.tab_metadata, "Device Metadata")
        self.hik_views = []
        for mode, title in (('audit', 'Security Audit'), ('camera', 'Camera / Motion'),
                            ('stats', 'Log Statistics')):
            view = HikvisionInvestigation(self, mode)
            self.tabs.addTab(view, title)
            self.tabs.setTabEnabled(self.tabs.indexOf(view), False)
            self.hik_views.append(view)
        self.tabs.currentChanged.connect(self._investigation_tab_changed)
        
        main_layout.addWidget(self.tabs, 1)
        self.statusBar().showMessage("Ready — load a forensic image to begin")
        LOGGER.info("UI initialized | version=%s | log_dir=%s", APP_VERSION, log_dir())

    @Slot(int)
    def _table_scrolled(self, _value):
        self.filter_header._position_editors()

    @Slot(int, int, int)
    def _table_section_resized(self, _logical, _old_size, _new_size):
        fit_rows(self.table)

    def apply_settings(self):
        family, size = self.settings.font()
        self.setStyleSheet(application_stylesheet(self.settings.get("theme"), family, size))

    def _system_colour_scheme_changed(self, _scheme):
        if self.settings.get("theme") not in ("dark", "light"):
            LOGGER.info("Windows colour scheme changed; reapplying system theme")
            self.apply_settings()

    def _investigation_tab_changed(self, _index):
        current = self.tabs.currentWidget()
        if current in self.hik_views:
            current.refresh()

    def _sync_investigation_views(self):
        available = bool(self.current_db and self.current_table == 'hikvision_logs')
        for view in self.hik_views:
            self.tabs.setTabEnabled(self.tabs.indexOf(view), available)
            if not available:
                view.clear()
            elif self.tabs.currentWidget() is view:
                view.reset()

    def toggle_sidebar(self):
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.sidebar_toggle.setText("☰" if visible else "☷")
        self.sidebar_toggle.setToolTip(
            "Hide recent evidence sidebar" if visible
            else "Show recent evidence sidebar")

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.apply_settings()
            self.refresh_recent_list()

    def clear_recent_history(self):
        exports = recents.registered_exports()
        delete_exports = self._choose_recent_cleanup(exports)
        if delete_exports is None:
            return
        removed_files = 0
        if delete_exports:
            try:
                removed_files = recents.delete_registered_exports()
            except (OSError, ValueError) as exc:
                LOGGER.exception("Registered export deletion stopped")
                QMessageBox.warning(self, "Export deletion stopped", str(exc))
                return
            deleted_paths = {os.path.normcase(os.path.abspath(item.path)) for item in exports}
            if self.current_db and os.path.normcase(os.path.abspath(self.current_db)) in deleted_paths:
                self.current_db = ""
                self.current_table = ""
                self.columns = []
                self.table.clear()
                self.table.setRowCount(0)
                self.table.setColumnCount(0)
                self.table_selector.clear()
        removed = recents.clear()
        self.refresh_recent_list()
        self.statusBar().showMessage(
            f"Cleared {removed} recent entries and {removed_files} registered export files")
        LOGGER.info("Recent evidence cleared | entries=%d | export_files=%d",
                    removed, removed_files)

    def _choose_recent_cleanup(self, exports):
        """Return None to cancel, False for history only, True for files too."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Clear recent evidence")
        dialog.setText("What should be removed?")
        dialog.setInformativeText(
            f"{len(exports)} registered export file(s). Source images are never deleted. "
            "Older exports not registered by this version are not included.")
        if exports:
            dialog.setDetailedText("Registered files:\n" + "\n".join(
                f"{item.kind}: {item.path}" for item in exports))
        history_button = dialog.addButton("History only", QMessageBox.ButtonRole.AcceptRole)
        exports_button = dialog.addButton(
            "History + registered exports", QMessageBox.ButtonRole.DestructiveRole)
        exports_button.setEnabled(bool(exports))
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        choice = dialog.clickedButton()
        if choice not in (history_button, exports_button):
            return None
        if choice == history_button:
            return False
        paths = "\n".join(item.path for item in exports)
        confirm = QMessageBox.question(
            self, "Confirm export deletion",
            f"Permanently delete these {len(exports)} registered files?\n\n{paths}\n\n"
            "The source images and other files will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return True if confirm == QMessageBox.StandardButton.Yes else None

    def refresh_recent_list(self):
        self.recent_list.clear()
        items = recents.recent(int(self.settings.get("recent_limit")))
        if not items:
            empty = QListWidgetItem("No recent evidence")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(empty)
        for item in items:
            widget_item = QListWidgetItem(
                f"{os.path.basename(item.image_path)}\n{item.brand}")
            widget_item.setToolTip(item.image_path)
            widget_item.setData(Qt.ItemDataRole.UserRole, item)
            if not item.exists:
                widget_item.setFlags(widget_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.recent_list.addItem(widget_item)

    def open_recent_item(self, list_item):
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if item is not None:
            self.open_recent(item)

    def show_version_dialog(self):
        metadata = version_info()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Version {metadata['version']}")
        dialog.resize(540, 390)
        layout = QVBoxLayout(dialog)
        heading = QLabel(f"{metadata.get('product_name', APP_NAME)} v{metadata['version']}")
        heading.setObjectName("Title")
        layout.addWidget(heading)
        layout.addWidget(QLabel(metadata.get("description", "")))
        changes = metadata.get("changes") or []
        history = QPlainTextEdit()
        history.setReadOnly(True)
        history.setPlainText("\n".join(f"• {change}" for change in changes)
                             or "No release notes are available.")
        layout.addWidget(history, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def open_recent(self, item):
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            QMessageBox.information(self, 'Extraction running', 'Wait for extraction before reopening evidence.')
            return
        self.load_image_path(item.image_path)
        if (self.detected_brand != "ICATCH"
                and item.database_path and item.table_name
                and os.path.isfile(item.database_path)):
            self.current_db = item.database_path
            self.out_dir = os.path.dirname(os.path.abspath(item.database_path))
            try:
                root = workspace_for_database(item.database_path)
            except (OSError, ValueError) as exc:
                LOGGER.warning('Workspace descriptor could not be read: %s', exc)
                root = None
            self.workspace_dir = str(root) if root else ''
            self.workspace_button.setEnabled(bool(root))
            if root and root.parent.name == 'workspaces':
                self.case_folder = str(root.parent.parent)
                self.settings.set('case_folder', self.case_folder)
                self.case_label.setText(f'Case: {root.parent.parent.name}')
                self.case_label.setToolTip(self.case_folder)
            audit(self.workspace_dir, 'reopened', database=item.database_path)
            self.current_table = item.table_name
            self.setup_table_columns()
            self.reset_and_populate()
            self.tabs.setCurrentIndex(0)
            self.statusBar().showMessage(
                f"Reopened {os.path.basename(item.database_path)}")

    def _validate_case_location(self, folder):
        if is_physical_drive(self.image_path):
            source_letters = drive_volume_letters(self.image_path)
            output_letter = os.path.splitdrive(os.path.realpath(folder))[0][:1].upper()
            if output_letter in source_letters:
                raise ValueError('The case folder is on the evidence disk. Choose a different physical disk or network location.')

    def action_select_case(self):
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            QMessageBox.information(self, 'Extraction running', 'Wait for extraction before changing the case folder.')
            return False
        folder = QFileDialog.getExistingDirectory(self, 'Select or create case folder', self.case_folder)
        if not folder:
            return False
        try:
            self._validate_case_location(folder)
            root = initialize_case(folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Case folder', str(exc))
            return False
        if os.path.normcase(str(root)) != os.path.normcase(self.case_folder):
            self.workspace_dir = ''
            self.workspace_button.setEnabled(False)
            self.current_db = self.current_table = ''
            self.columns = []
            self._sync_investigation_views()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
        self.case_folder = str(root)
        self.settings.set('case_folder', self.case_folder)
        self.case_label.setText(f'Case: {root.name}')
        self.case_label.setToolTip(str(root))
        return True

    def _prepare_workspace(self):
        if not self.case_folder or not os.path.isdir(self.case_folder):
            if not self.action_select_case():
                return False
        try:
            self._validate_case_location(self.case_folder)
            self._validate_case_location(os.path.join(self.case_folder, 'workspaces'))
            root = create_workspace(self.case_folder, self.image_path, self.detected_brand,
                                    APP_VERSION, self.metadata)
            self.workspace_dir = str(root)
            self.out_dir = str(root / 'databases')
            self.workspace_button.setEnabled(True)
            self.settings.set('last_output_dir', self.out_dir)
            audit(root, 'detection_context', terminal=self.log_text.toPlainText())
            self.current_db = self.current_table = ''
            self.columns = []
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.append_log(f'[WORKSPACE] {root}')
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot create workspace', str(exc))
            return False

    def open_workspace_folder(self):
        if self.workspace_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.workspace_dir))

    def closeEvent(self, event):
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            QMessageBox.information(self, 'Extraction running', 'Use Cancel extraction and wait for the current read to finish before closing.')
            event.ignore()
            return
        super().closeEvent(event)

    def _report_destination(self, extension):
        folder = os.path.join(self.workspace_dir, 'reports') if self.workspace_dir else self.out_dir
        os.makedirs(folder, exist_ok=True)
        name = 'Report-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.' + extension
        return os.path.join(folder, name)

    def action_load_image(self):
        initial_dir = self._preferred_image_directory()
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select DVR Image", initial_dir,
            "Disk Images (*.e01 *.E01 *.ex01 *.Ex01 *.001 *.dd *.img *.bin);;All Files (*.*)"
        )
        if filename:
            self.settings.set("last_open_dir", os.path.dirname(filename))
            self.load_image_path(filename)

    def _preferred_image_directory(self):
        """Use the last chosen folder, with recent evidence as a fallback."""
        saved = str(self.settings.get("last_open_dir") or "")
        if os.path.isdir(saved):
            return saved
        for item in recents.recent(int(self.settings.get("recent_limit"))):
            if item.exists and not is_physical_drive(item.image_path):
                directory = os.path.dirname(item.image_path)
                if os.path.isdir(directory):
                    return directory
        if self.image_path and not is_physical_drive(self.image_path):
            directory = os.path.dirname(self.image_path)
            if os.path.isdir(directory):
                return directory
        return ""

    def _offer_admin_restart(self, title, message, allow_continue):
        """Offer an elevated restart; returns 'continue', 'restarted' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        restart = box.addButton("Restart as Administrator", QMessageBox.ButtonRole.AcceptRole)
        proceed = (box.addButton("Continue anyway", QMessageBox.ButtonRole.DestructiveRole)
                   if allow_continue else None)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(restart)
        box.exec()
        clicked = box.clickedButton()
        if proceed is not None and clicked is proceed:
            return 'continue'
        if clicked is not restart:
            return 'cancel'
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            QMessageBox.information(self, 'Extraction running',
                                    'Wait for the current extraction to finish before restarting.')
            return 'cancel'
        try:
            started = relaunch_as_admin()
        except OSError as exc:
            LOGGER.exception("Administrator restart failed")
            QMessageBox.warning(self, "Restart failed",
                                f"Could not start the app as Administrator:\n{exc}")
            return 'cancel'
        if not started:
            LOGGER.info("Administrator restart declined at the UAC prompt")
            QMessageBox.information(self, "Restart cancelled",
                                    "The Administrator prompt was declined. The app keeps running "
                                    "without Administrator rights.")
            return 'cancel'
        LOGGER.info("Restarting as Administrator; closing this instance")
        self.close()
        return 'restarted'

    def action_load_drive(self):
        if not is_running_as_admin():
            choice = self._offer_admin_restart(
                "Administrator rights needed",
                "Reading a physical drive usually requires Administrator rights, and this app "
                "is not running as Administrator.\n\nRestart the app as Administrator now? "
                "Windows will ask for confirmation. Evidence is still opened read-only.",
                allow_continue=True)
            if choice != 'continue':
                return
        try:
            drives = list_physical_drives()
        except Exception as exc:
            LOGGER.exception("Physical drive enumeration failed")
            QMessageBox.warning(self, "Physical drives", f"Could not list drives:\n{exc}")
            return
        if not drives:
            QMessageBox.information(self, "Physical drives", "No physical drives were found.")
            return
        labels = [drive.label for drive in drives]
        selection, accepted = QInputDialog.getItem(
            self, "Select physical drive", "Read-only evidence source:", labels, 0, False)
        if not accepted:
            return
        drive = drives[labels.index(selection)]
        try:
            source_letters = drive_volume_letters(drive.path)
        except Exception as exc:
            QMessageBox.warning(self, "Drive verification failed",
                                f"Could not verify mounted volumes:\n{exc}")
            return
        appdata_letter = os.path.splitdrive(os.path.abspath(str(recents.app_data_dir())))[0][:1].upper()
        if appdata_letter in source_letters:
            QMessageBox.warning(
                self, "System/AppData disk cannot be evidence",
                "This disk contains the app's AppData logs/settings. Windows and the app "
                "may write to it during analysis. Use a static image or attach the evidence "
                "drive to a different workstation.")
            return
        warning = (f"Analyze {drive.label}?\n\n"
                   "The drive will be opened for reading only. A mounted/live disk may change "
                   "during analysis, so results are not a forensic snapshot. Run as Administrator "
                   "if Windows denies access. Save all output to a different physical disk.")
        if QMessageBox.question(self, "Confirm physical drive", warning) != QMessageBox.StandardButton.Yes:
            return
        try:
            with open_image(drive.path) as source:
                source.read(512)
        except PermissionError:
            if is_running_as_admin():
                QMessageBox.warning(
                    self, "Drive access denied",
                    "Windows denied read access to this physical drive even with Administrator "
                    "rights. It may be locked by another program or blocked by policy. "
                    "No evidence was modified.")
            else:
                self._offer_admin_restart(
                    "Drive access denied",
                    "Windows denied read access to this physical drive. Restart the app as "
                    "Administrator and try again. No evidence was modified.",
                    allow_continue=False)
            return
        except OSError as exc:
            QMessageBox.warning(self, "Drive access failed", f"Cannot read {drive.path}:\n{exc}")
            return
        self.load_image_path(drive.path, drive_info=drive)

    def load_image_path(self, filename, drive_info=None):
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            QMessageBox.information(self, 'Extraction running', 'Wait for the current extraction before changing evidence.')
            return
        if filename:
            self.workspace_dir = ''
            self.workspace_button.setEnabled(False)
            self.log_text.clear()
            self.current_db = ""
            self.current_table = ""
            self.columns = []
            self.date_column = None
            self.category_column = None
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table_selector.clear()
            self.category_selector.blockSignals(True)
            self.category_selector.clear()
            self.category_selector.addItem("All categories", None)
            self.category_selector.setEnabled(False)
            self.category_selector.blockSignals(False)
            self.database_selector.blockSignals(True)
            self.database_selector.clear()
            self.database_selector.addItem('All source databases', None)
            self.database_selector.setVisible(False)
            self.database_selector.blockSignals(False)
            self.mlogtype_selector.blockSignals(True)
            self.mlogtype_selector.clear()
            self.mlogtype_selector.addItem('All mlogtypes', None)
            self.mlogtype_selector.setVisible(False)
            self.mlogtype_selector.blockSignals(False)
            physical = is_physical_drive(filename)
            if not physical:
                filename = os.path.normpath(os.path.abspath(filename))
                self.settings.set("last_open_dir", os.path.dirname(filename))
            self.image_path = filename
            self.selected_drive_info = drive_info if physical else None
            self.metadata = {
                "Evidence path": (filename, "Selected evidence"),
                **({} if physical else acquisition_metadata(filename)),
            }
            if physical:
                if drive_info is None:
                    drive_info = next((drive for drive in list_physical_drives()
                                       if drive.path.lower() == filename.lower()), None)
                self.selected_drive_info = drive_info
                self.metadata["Evidence type"] = ("Live physical drive (read-only)",
                                                   "Not a static forensic image")
                if drive_info:
                    self.metadata["Disk model"] = (drive_info.model, "Windows disk inventory")
                    self.metadata["Disk serial"] = (drive_info.serial or "N/A", "Windows disk inventory")
                    self.metadata["Source size"] = (str(drive_info.size), "Windows disk inventory, bytes")
            self.update_metadata({})
            self.img_lbl.setText(f"Loaded: {filename if physical else os.path.basename(filename)}")
            self.img_lbl.setObjectName("StatusGood")
            self.img_lbl.style().unpolish(self.img_lbl)
            self.img_lbl.style().polish(self.img_lbl)
            
            self.append_log(f"[INFO] Analyzing {'physical drive' if physical else 'image'}: {filename}")
            LOGGER.info("Evidence opened | path=%s", filename)
            try:
                detection = detect_brand_details(filename)
                self.detected_brand = detection["brand"]
                self.btn_entropy.setVisible(self.detected_brand not in ('DAHUA', 'HIKVISION', 'TVT'))
                self.metadata["Detected vendor"] = (
                    self.detected_brand,
                    detection["reason"])
                if self.detected_brand == "TVT":
                    try:
                        self.metadata.update(tvt_filesystem_metadata(filename))
                    except Exception as exc:
                        LOGGER.warning("TVT filesystem metadata failed: %s", exc)
                self.update_metadata({})
                self.brand_lbl.setText(f"Brand: {self.detected_brand}")
                self.log_availability_lbl.setObjectName("StatusMuted")
                self.log_availability_lbl.setToolTip("")
                has_user_logs = self.detected_brand in ("DAHUA", "HIKVISION", "TVT")
                self.btn_carve.setEnabled(has_user_logs)
                self.btn_carve.setToolTip(
                    "Extract user logs" if has_user_logs
                    else "No verified user-log extractor is available for this image")
                if self.detected_brand == "ICATCH":
                    message = "No user logs found in the analyzed ICATCH image"
                    self.log_availability_lbl.setText("No user logs found")
                    self.log_availability_lbl.setToolTip(message)
                    self.metadata["User logs"] = (
                        "Not found in analyzed image",
                        "Bounded media survey; hourly recording index is not a user log")
                    self.update_metadata({})
                    self.append_log(f"[INFO] {message}. Recording index only.")
                    self.statusBar().showMessage(message)
                elif self.detected_brand == "DAHUA":
                    self.log_availability_lbl.setObjectName("CoverageWarning")
                    self.log_availability_lbl.setText("⚠ Disk logs may be incomplete")
                    self.log_availability_lbl.setToolTip(DAHUA_LOG_SCOPE_NOTICE)
                    self.metadata["Log coverage"] = (
                        DAHUA_LOG_SCOPE_NOTICE, "Dahua forensic literature; disk-only scope")
                    self.update_metadata({})
                    self.append_log(f"[SCOPE] {DAHUA_LOG_SCOPE_NOTICE}")
                    self.statusBar().showMessage("Dahua detected · disk logs may be incomplete")
                else:
                    self.log_availability_lbl.setText("")
                    self.log_availability_lbl.setToolTip("")
                    self.statusBar().showMessage(f"Brand detected: {self.detected_brand}")
                self.log_availability_lbl.style().unpolish(self.log_availability_lbl)
                self.log_availability_lbl.style().polish(self.log_availability_lbl)
                self.append_log(f"[DETECT] Brand: {self.detected_brand}")
                self.append_log(f"[DETECT] Evidence: {detection['reason']}")
                LOGGER.info("Brand detection | brand=%s | confidence=%s | reason=%s",
                            self.detected_brand, detection['confidence'], detection['reason'])
                if not physical:
                    recents.remember(filename, self.detected_brand)
                    self.refresh_recent_list()
            except Exception as e:
                LOGGER.exception("Brand detection failed | image=%s", filename)
                self.append_log(f"[ERROR] Brand detection failed: {e}")
                self.brand_lbl.setText("Brand: UNKNOWN")
                self.detected_brand = 'UNKNOWN'
                self.btn_entropy.setVisible(True)
                self.log_availability_lbl.setText("")
                self.log_availability_lbl.setToolTip("")
                self.log_availability_lbl.setObjectName("StatusMuted")
                self.btn_carve.setEnabled(False)

    def action_entropy_test(self):
        if self.image_path:
            if not self._prepare_workspace():
                return
            update_workspace(self.workspace_dir, status='running', operation='entropy')
            dialog = EntropyDialog(self.image_path, self.append_log, self,
                                   results_dir=self.out_dir)
            dialog.exec()
            update_workspace(self.workspace_dir, status=dialog.outcome,
                             entropy_summary=dialog.last_summary, artifacts=dialog.saved_results)
            self.register_generated_exports(dialog.saved_results)

    def action_carve_data(self):
        if self.extraction_thread is not None and self.extraction_thread.isRunning():
            return
        if not self.image_path or self.detected_brand not in ("DAHUA", "HIKVISION", "TVT"):
            return
        if is_physical_drive(self.image_path):
            try:
                current_drive = next((drive for drive in list_physical_drives()
                                      if drive.path.lower() == self.image_path.lower()), None)
            except Exception as exc:
                QMessageBox.warning(self, "Drive verification failed", str(exc))
                return
            if (current_drive is None or self.selected_drive_info is None
                    or (current_drive.serial, current_drive.model, current_drive.size) !=
                    (self.selected_drive_info.serial, self.selected_drive_info.model,
                     self.selected_drive_info.size)):
                QMessageBox.warning(self, "Evidence drive changed",
                                    "The selected physical drive is missing or its identity changed. "
                                    "Select the drive again before extraction.")
                return
        if not self._prepare_workspace():
            return
            
        self.btn_carve.setEnabled(False)
        self.tabs.setCurrentIndex(1) # Switch to terminal
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0% · Preparing")
        
        self.extraction_thread = ExtractionThread(self.image_path, self.out_dir, self.detected_brand, self.workspace_dir)
        self.extraction_thread.log_signal.connect(self.append_log)
        self.extraction_thread.sse_signal.connect(self.handle_sse_event)
        self.extraction_thread.metadata_signal.connect(self.update_metadata)
        self.extraction_thread.artifacts_signal.connect(self.register_generated_exports)
        self.extraction_thread.finished_signal.connect(self.extraction_finished)
        self.extraction_thread.cancelled_signal.connect(self.extraction_cancelled)
        self.extraction_thread.finished.connect(self._extraction_thread_stopped)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText('Cancel extraction')
        self.extraction_thread.start()

    def action_cancel_extraction(self):
        if self.extraction_thread and self.extraction_thread.isRunning():
            self.extraction_thread.requestInterruption()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText('Cancelling…')
            self.append_log('[CANCEL REQUESTED] Waiting for the current read/native call to return. Incomplete results will not be shown as complete.')

    def _extraction_thread_stopped(self):
        self.btn_cancel.setVisible(False)
        self.btn_carve.setEnabled(self.detected_brand in ('TVT', 'DAHUA', 'HIKVISION'))

    def extraction_cancelled(self, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFormat('Cancelled · incomplete results')
        self.statusBar().showMessage('Extraction cancelled — workspace retained; results are incomplete')
        self.append_log('[CANCELLED] ' + message)

    @Slot(str)
    def append_log(self, text):
        try:
            audit(self.workspace_dir, 'terminal', message=str(text))
        except OSError:
            LOGGER.exception('Workspace terminal log write failed')
        LOGGER.debug("Terminal | %s", str(text).replace("\n", " | "))
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for line in str(text).rstrip().splitlines() or [""]:
            self.log_text.appendPlainText(f"[{timestamp}] {line}")
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(list)
    def register_generated_exports(self, paths):
        for path in paths:
            try:
                recents.remember_export(self.image_path, path, "Extracted database")
            except (OSError, ValueError) as exc:
                LOGGER.warning("Could not register generated export %s: %s", path, exc)

    @Slot(dict)
    def update_metadata(self, values):
        self.metadata.update(values or {})
        if values and self.workspace_dir:
            update_workspace(self.workspace_dir, metadata=self.metadata)
        self.metadata_table.setRowCount(len(self.metadata))
        for row, (field, item) in enumerate(self.metadata.items()):
            value, source = item if isinstance(item, (tuple, list)) else (item, "Derived")
            self.metadata_table.setItem(row, 0, QTableWidgetItem(str(field)))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))
            self.metadata_table.setItem(row, 2, QTableWidgetItem(str(source)))

    @staticmethod
    def _human_bytes(value):
        size = float(value)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024 or unit == "TiB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024

    @Slot(str)
    def handle_sse_event(self, frame):
        try:
            event, data = decode_sse(frame)
        except (ValueError, TypeError) as exc:
            self.append_log(f"[SSE ERROR] Invalid progress event: {exc}")
            return
        phase = data.get("phase", event)
        if event == "progress":
            self.progress_bar.setRange(0, 100)
            percent = int(data.get("progress", 0))
            if "bytes_total" in data:
                done = self._human_bytes(data.get("bytes_done", 0))
                total = self._human_bytes(data.get("bytes_total", 0))
            else:
                done = f"{data.get('items_done', 0)} DB"
                total = f"{data.get('items_total', 0)} DB"
            self.progress_bar.setValue(percent)
            self.progress_bar.setFormat(f"{percent}% · {done} / {total}")
            extras = []
            for key in ("region", "file", "records"):
                if key in data:
                    extras.append(f"{key}={data[key]}")
            self.append_log(f"[PROGRESS] {phase}: {done} / {total} ({percent}%)"
                            + (" · " + ", ".join(extras) if extras else ""))
        elif event == "started":
            self.append_log(f"[START] Brand={data.get('brand')} · image={data.get('image')}")
            self.append_log(f"[START] Output directory: {data.get('output')}")
        elif event == "phase":
            detail = data.get('detail', '')
            if data.get("indeterminate"):
                self.progress_bar.setRange(0, 0)
                self.progress_bar.setFormat(f"Working · {detail}")
            else:
                self.progress_bar.setRange(0, 100)
            self.append_log(f"[PHASE] {phase}: {data.get('detail', '')}")
        elif event == "completed":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100% · Complete")
            self.append_log(f"[COMPLETE] Database={data.get('database')} · table={data.get('table')}")
        elif event == 'cancelled':
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat('Cancelled · incomplete results')
            self.append_log('[CANCELLED] ' + data.get('detail', ''))
        elif event == "error":
            self.progress_bar.setRange(0, 100)
            self.append_log(f"[ERROR] {phase}: {data.get('detail', '')}")

    @Slot(bool, str, str, str)
    def extraction_finished(self, success, message, db_path, table_name):
        self.btn_carve.setEnabled(True)
        if success:
            self.current_db = db_path
            self.current_table = table_name
            if not is_physical_drive(self.image_path):
                recents.remember(self.image_path, self.detected_brand, db_path, table_name)
                self.refresh_recent_list()
            self.setup_table_columns()
            self.populate_table()
            self.tabs.setCurrentIndex(0) # Switch to db view
            self.statusBar().showMessage(f"Extraction complete — {os.path.basename(db_path)}")
            self.settings.set("last_output_dir", os.path.dirname(os.path.abspath(db_path)))
            self._show_extraction_complete(db_path)
        else:
            LOGGER.error("Extraction UI failure | image=%s | error=%s",
                         self.image_path, message)
            QMessageBox.critical(self, "Error", f"Carving failed:\n{message}")

    def _show_extraction_complete(self, db_path):
        folder = self.workspace_dir or os.path.dirname(os.path.abspath(db_path))
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle("Extraction complete")
        dialog.setText("Log extraction finished successfully.")
        dialog.setInformativeText(f"Results saved in:\n{folder}")
        open_button = dialog.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        close_button = dialog.addButton("Close", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(close_button)
        dialog.exec()
        if dialog.clickedButton() == open_button:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
                QMessageBox.warning(self, "Open Folder", f"Could not open:\n{folder}")
            
    def setup_table_columns(self):
        if not self.current_db or not self.current_table:
            return
            
        conn = sqlite3.connect(self.current_db)
        if self.current_table == 'tvt_logs':
            ensure_tvt_mlogtype(conn)
        c = conn.cursor()
        tables = [row[0] for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        self.table_selector.blockSignals(True)
        self.table_selector.clear()
        self.table_selector.addItems(tables)
        if self.current_table in tables:
            self.table_selector.setCurrentText(self.current_table)
        self.table_selector.blockSignals(False)
        c.execute(f"PRAGMA table_info({self._identifier(self.current_table)})")
        column_info = c.fetchall()
        cols = [row[1] for row in column_info]
        self.columns = cols
        lowered = {column.lower(): column for column in cols}
        self.date_column = next((lowered[name] for name in (
            "timestamp", "time_utc", "timep", "time_unix", "datetime",
            "event_time", "event_date", "date_time", "created_at")
            if name in lowered), None)
        if self.date_column is None:
            self.date_column = next((column for column in cols
                if any(token in column.lower() for token in ("timestamp", "datetime", "event_time"))
                and "timezone" not in column.lower()), None)
        self.category_column = next((lowered[name] for name in (
            "category", "event_category", "major_type") if name in lowered), None)
        self.category_selector.blockSignals(True)
        self.category_selector.clear()
        self.category_selector.addItem("All categories", None)
        if self.category_column:
            category = self._identifier(self.category_column)
            table = self._identifier(self.current_table)
            values = c.execute(
                f"SELECT DISTINCT {category} FROM {table} "
                f"WHERE {category} IS NOT NULL AND TRIM(CAST({category} AS TEXT)) != '' "
                f"ORDER BY {category} COLLATE NOCASE").fetchall()
            for (value,) in values:
                self.category_selector.addItem(str(value), str(value))
        self.category_selector.setEnabled(self.category_column is not None)
        self.category_selector.blockSignals(False)
        self.database_selector.blockSignals(True)
        self.database_selector.clear()
        self.database_selector.addItem('All source databases', None)
        self.source_database_column = lowered.get('source_database')
        if self.source_database_column:
            column = self._identifier(self.source_database_column)
            for (value,) in c.execute(
                    f'SELECT DISTINCT {column} FROM {self._identifier(self.current_table)} '
                    f'WHERE {column} IS NOT NULL ORDER BY {column}').fetchall():
                self.database_selector.addItem(display_value('source_database', value), value)
        self.database_selector.setVisible(bool(self.source_database_column))
        self.database_selector.blockSignals(False)
        self.mlogtype_selector.blockSignals(True)
        self.mlogtype_selector.clear()
        self.mlogtype_selector.addItem('All mlogtypes', None)
        if 'mlogtype' in cols:
            for (value,) in c.execute(
                    f'SELECT DISTINCT mlogtype FROM {self._identifier(self.current_table)} '
                    "WHERE mlogtype IS NOT NULL AND mlogtype != '' ORDER BY mlogtype").fetchall():
                self.mlogtype_selector.addItem(str(value), value)
        self.mlogtype_selector.setVisible('mlogtype' in cols)
        self.mlogtype_selector.blockSignals(False)
        
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        for index, column in enumerate(cols):
            if column in ('offset', 'source_offset', 'raw_record_offset'):
                self.table.horizontalHeaderItem(index).setToolTip(
                    'Absolute byte offset in the logical evidence stream. '
                    + ('TVT mlogtype payload start.' if column == 'source_offset'
                       else 'Recovered record start.'))
            # Keep full headings and useful values accessible via horizontal
            # scrolling instead of squeezing every field into the viewport.
            self.table.setColumnWidth(index, min(420, max(150, len(column) * 9 + 50)))
            if column in ('explanation', 'event_description', 'details'):
                self.table.setColumnWidth(index, 500)
            if column == 'raw_record_hex':
                self.table.setColumnHidden(index, True)
            else:
                self.table.setColumnHidden(index, False)
        self.filter_header.set_columns(cols)
        has_dates = self.date_column is not None
        self.date_enabled.setEnabled(has_dates)
        self.date_from.setEnabled(has_dates)
        self.date_to.setEnabled(has_dates)
        if not has_dates:
            self.date_enabled.setChecked(False)
            self.date_enabled.setToolTip("This dataset has no recognized date/time column")
        else:
            self.date_enabled.setToolTip(f"Apply range to {self.date_column}")
            self._set_available_date_range(c)
        conn.close()

    def table_changed(self, table_name):
        if not table_name or not self.current_db or table_name == self.current_table:
            return
        self.current_table = table_name
        self.setup_table_columns()
        self.reset_and_populate()

    @staticmethod
    def _identifier(name):
        return '"' + name.replace('"', '""') + '"'

    def _where_clause(self):
        clauses = []
        params = []
        keyword = self.filter_text.text().strip()
        if keyword and self.columns:
            clauses.append("(" + " OR ".join(
                f"CAST({self._identifier(column)} AS TEXT) LIKE ?" for column in self.columns
            ) + ")")
            params.extend([f"%{keyword}%"] * len(self.columns))

        for selected, column_value in self.filter_header.filters().items():
            if selected in self.columns and column_value:
                clauses.append(f"CAST({self._identifier(selected)} AS TEXT) LIKE ?")
                params.append(f"%{column_value}%")

        category = self.category_selector.currentData()
        if self.category_column and category is not None:
            clauses.append(f"{self._identifier(self.category_column)} = ?")
            params.append(category)
        source_database = self.database_selector.currentData()
        mlogtype = self.mlogtype_selector.currentData()
        if 'mlogtype' in self.columns and mlogtype is not None:
            clauses.append('"mlogtype" = ?')
            params.append(mlogtype)
        if 'source_database' in self.columns and source_database is not None:
            clauses.append(f'{self._identifier("source_database")} = ?')
            params.append(source_database)

        if self.date_enabled.isChecked() and self.date_column:
            start = self.date_from.date().toString("yyyy-MM-dd")
            end = self.date_to.date().addDays(1).toString("yyyy-MM-dd")
            if self.date_column.lower() in ("timep", "time_unix"):
                start_epoch = int(datetime.strptime(start, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc).timestamp())
                end_epoch = int(datetime.strptime(end, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc).timestamp())
                clauses.append(f"{self._identifier(self.date_column)} >= ? AND {self._identifier(self.date_column)} < ?")
                params.extend([start_epoch, end_epoch])
            else:
                clauses.append(f"{self._identifier(self.date_column)} >= ? AND {self._identifier(self.date_column)} < ?")
                params.extend([start, end])
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def reset_and_populate(self):
        self.current_page = 1
        self.populate_table()

    def populate_table(self):
        if not self.current_db or not self.current_table:
            return
            
        conn = sqlite3.connect(self.current_db)
        c = conn.cursor()
        where, params = self._where_clause()
        table = self._identifier(self.current_table)
        page_size = int(self.page_size.currentData())
        offset = (self.current_page - 1) * page_size
        query = f"SELECT _rowid_, * FROM {table}{where} LIMIT ? OFFSET ?"
                
        try:
            self.total_rows = c.execute(
                f"SELECT count(*) FROM {table}{where}", params).fetchone()[0]
            pages = max(1, (self.total_rows + page_size - 1) // page_size)
            self.current_page = min(self.current_page, pages)
            offset = (self.current_page - 1) * page_size
            try:
                c.execute(query, [*params, page_size, offset])
            except sqlite3.OperationalError as exc:
                if '_rowid_' not in str(exc):
                    raise
                c.execute(f'SELECT NULL, * FROM {table}{where} LIMIT ? OFFSET ?',
                          [*params, page_size, offset])
            rows = c.fetchall()
            
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, val in enumerate(row[1:]):
                    value = display_value(self.columns[j], val)
                    # The cell shows a summary; record details read UserRole.
                    item = QTableWidgetItem(cell_summary(value))
                    item.setData(Qt.ItemDataRole.UserRole, val)
                    item.setData(Qt.ItemDataRole.UserRole + 1, row[0])
                    item.setToolTip(cell_tooltip(value))
                    item.setTextAlignment(CELL_ALIGNMENT)
                    self.table.setItem(i, j, item)
            self.table.setSortingEnabled(True)
            fit_rows(self.table)
            first = offset + 1 if self.total_rows else 0
            last = offset + len(rows)
            self.page_label.setText(f"Page {self.current_page:,} of {pages:,}")
            self.prev_page.setEnabled(self.current_page > 1)
            self.next_page.setEnabled(self.current_page < pages)
            self.statusBar().showMessage(
                f"Showing {first:,}-{last:,} of {self.total_rows:,} records")
        except Exception as e:
            QMessageBox.warning(self, "Query Error", str(e))
        finally:
            conn.close()

        self._sync_investigation_views()

    def _date_controls_enabled(self, enabled):
        # Calendar controls remain clickable whenever the dataset has a date
        # column. The checkbox controls application of the range, not editing.
        available = self.date_column is not None
        self.date_from.setEnabled(available)
        self.date_to.setEnabled(available)

    def _date_value_changed(self, _date):
        if self.date_column and not self.date_enabled.isChecked():
            self.date_enabled.setChecked(True)

    def _set_available_date_range(self, cursor):
        """Initialize the controls from actual evidence dates where possible."""
        column = self._identifier(self.date_column)
        table = self._identifier(self.current_table)
        try:
            minimum, maximum = cursor.execute(
                f"SELECT MIN({column}), MAX({column}) FROM {table} "
                f"WHERE {column} IS NOT NULL").fetchone()
            if minimum is None or maximum is None:
                return
            if self.date_column.lower() in ("timep", "time_unix"):
                first = QDate.fromString(
                    datetime.fromtimestamp(int(minimum), timezone.utc).strftime("%Y-%m-%d"),
                    "yyyy-MM-dd")
                last = QDate.fromString(
                    datetime.fromtimestamp(int(maximum), timezone.utc).strftime("%Y-%m-%d"),
                    "yyyy-MM-dd")
            else:
                first = QDate.fromString(str(minimum)[:10], "yyyy-MM-dd")
                last = QDate.fromString(str(maximum)[:10], "yyyy-MM-dd")
            if first.isValid() and last.isValid():
                self.date_from.blockSignals(True)
                self.date_to.blockSignals(True)
                self.date_from.setDate(first)
                self.date_to.setDate(last)
                self.date_from.blockSignals(False)
                self.date_to.blockSignals(False)
        except (sqlite3.Error, TypeError, ValueError, OSError) as exc:
            LOGGER.warning("Could not derive dataset date range | table=%s | error=%s",
                           self.current_table, exc)

    def clear_filters(self):
        self.filter_text.clear()
        self.filter_header.clear_filters()
        self.category_selector.setCurrentIndex(0)
        self.database_selector.setCurrentIndex(0)
        self.mlogtype_selector.setCurrentIndex(0)
        self.date_enabled.setChecked(False)
        self.reset_and_populate()

    def go_previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.populate_table()

    def go_next_page(self):
        page_size = int(self.page_size.currentData())
        if self.current_page * page_size < self.total_rows:
            self.current_page += 1
            self.populate_table()

    def page_size_changed(self):
        if self.page_size.currentData() is None:
            return
        self.settings.set("page_size", int(self.page_size.currentData()))
        if self.current_db:
            self.reset_and_populate()

    def open_record_details(self, row, _column):
        """Open every field of the selected result without truncating table cells."""
        if row < 0 or not self.columns:
            return
        values = {field: self.table.item(row, index).data(Qt.ItemDataRole.UserRole)
                  for index, field in enumerate(self.columns) if self.table.item(row, index)}
        number = (self.current_page - 1) * int(self.page_size.currentData()) + row + 1
        self.show_record_values(values, self.current_table, f'Record {number:,}')

    def show_record_values(self, values, table_name, label):
        fields = list(values)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Record details · {table_name}")
        dialog.resize(860, 600)
        layout = QVBoxLayout(dialog)
        heading = QLabel(f"{table_name} · {label}")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        tabs = QTabWidget()
        details = QTableWidget(len(fields), 2)
        details.setHorizontalHeaderLabels(["Field", "Value"])
        details.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        details.setWordWrap(True)
        details.setTextElideMode(Qt.TextElideMode.ElideNone)
        # Field values keep their full height here; scroll by pixel so a value
        # taller than the dialog can still be read from top to bottom.
        details.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        details.verticalHeader().setVisible(False)
        details.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        details.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index, field in enumerate(fields):
            details.setItem(index, 0, QTableWidgetItem(field))
            details.setItem(index, 1, QTableWidgetItem(display_value(field, values[field])))
        details.resizeRowsToContents()
        tabs.addTab(details, 'Fields and explanations')
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText('\n\n'.join(
            f'{field}\n{display_value(field, values[field])}'
            for field in fields if field != 'raw_record_hex'))
        tabs.addTab(text, 'Full text')
        if table_name in ('hikvision_logs', 'tvt_logs'):
            raw_hex = values.get('raw_record_hex')
            hex_view = QPlainTextEdit()
            hex_view.setReadOnly(True)
            hex_view.setFont(QFont('Consolas', 10))
            if raw_hex:
                raw = bytes.fromhex(raw_hex)
                start = next((int(values[key]) for key in
                              ('raw_record_offset', 'offset', 'source_offset')
                              if values.get(key) is not None), 0)
                lines = ['Logical evidence offsets — recovered record bytes\n']
                for pos in range(0, len(raw), 16):
                    block = raw[pos:pos+16]
                    ascii_text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in block)
                    lines.append(f'{start + pos:016X}  {block.hex(" "):<47}  {ascii_text}')
                hex_view.setPlainText('\n'.join(lines))
            else:
                hex_view.setPlainText('No raw bytes stored in this older extraction. Re-extract the image to include record hex.')
            tabs.addTab(hex_view, 'Record hex')
        layout.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _export_context(self):
        filters = []
        if self.mlogtype_selector.currentData() is not None:
            filters.append(f'mlogtype: {self.mlogtype_selector.currentText()}')
        if self.database_selector.currentData() is not None:
            filters.append(f'Source database: {self.database_selector.currentText()}')
        if self.filter_text.text().strip():
            filters.append(f"Global search: {self.filter_text.text().strip()}")
        filters.extend(f"{key}: {value}" for key, value in self.filter_header.filters().items()
                       if value)
        if self.category_column and self.category_selector.currentData() is not None:
            filters.append(f"{self.category_column}: {self.category_selector.currentData()}")
        if self.date_enabled.isChecked() and self.date_column:
            filters.append(
                f"{self.date_column}: {self.date_from.date().toString('yyyy-MM-dd')} through "
                f"{self.date_to.date().toString('yyyy-MM-dd')}")
        return {
            "subtitle": f"Evidence report for {os.path.basename(self.image_path) or self.current_table}",
            "title": str(self.settings.get("report_title") or "CCTV Log Analyzer Report"),
            "page_size": int(self.settings.get("report_page_size")),
            "show_metadata": bool(self.settings.get("report_show_metadata")),
            "category_column": self.category_column,
            "metadata": {
                "Evidence": os.path.basename(self.image_path.replace("\\", "/"))
                if self.image_path else "Previously extracted database",
                "Vendor": self.detected_brand or "Not recorded",
                "Active filters": "; ".join(filters) if filters else "None (all records)",
            },
        }

    def action_export_csv(self):
        if not self.current_db: return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save CSV / Excel", self._report_destination('csv'), "CSV Files (*.csv)")
        if out_path:
            where, params = self._where_clause()
            audit(self.workspace_dir, 'report_requested', kind='CSV', path=out_path,
                  context=self._export_context())
            try:
                export_to_csv(self.current_db, self.current_table, out_path, where, params)
            except Exception as exc:
                audit(self.workspace_dir, 'report_failed', path=out_path, error=str(exc))
                QMessageBox.warning(self, 'Export failed', str(exc))
                return
            self._register_report_export(out_path, "CSV report")
            QMessageBox.information(self, "Success", f"Exported successfully to:\n{out_path}")

    def action_export_html(self):
        if not self.current_db: return
        where, params = self._where_clause()
        with sqlite3.connect(self.current_db) as connection:
            table = self._identifier(self.current_table)
            filtered_count = connection.execute(f'SELECT COUNT(*) FROM {table}{where}', params).fetchone()[0]
            all_count = connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        selected = self._report_rowids(selected=True)
        page = self._report_rowids(selected=False)
        options = ReportOptionsDialog(self.columns, self.settings,
                                      {'filtered': filtered_count, 'all': all_count,
                                       'selected': len(selected), 'page': len(page)}, self,
                                      log_type_columns=[name for name in (
                                          'mlogtype', 'category', 'event_category', 'major_type', 'minor_type', 'event')
                                          if name in self.columns],
                                      type_provider=lambda scope, column: self._report_type_counts(scope, selected, page, column),
                                      count_provider=lambda scope, column, values: self._report_record_count(
                                          scope, selected, page, column, values))
        if options.exec() != QDialog.DialogCode.Accepted:
            return
        scope = options.scope.currentData()
        type_column, types = options.type_column.currentText(), options.selected_log_types()
        where, params = self._report_scope(scope, selected, page, type_column, types)
        context = self._export_context()
        context.update(options.report_context())
        if scope == 'all':
            context['metadata']['Active filters'] = 'None (entire dataset)'
        context['metadata']['Report scope'] = options.scope.currentText()
        if types is not None:
            context['metadata']['Report log types'] = f'{type_column}: ' + ', '.join(str(value) for value in types)
        context['metadata']['Report record count'] = str(options.export_count)
        out_path, _ = QFileDialog.getSaveFileName(self, "Save HTML", self._report_destination('html'), "HTML Files (*.html)")
        if out_path:
            audit(self.workspace_dir, 'report_requested', kind='HTML', path=out_path, context=context)
            try:
                report_files = export_to_html(
                    self.current_db, self.current_table, out_path, where, params,
                    logo_path=options.logo.text().strip(), report_context=context)
            except Exception as exc:
                audit(self.workspace_dir, 'report_failed', path=out_path, error=str(exc))
                QMessageBox.warning(self, 'Export failed', str(exc))
                return
            for report_file in report_files:
                self._register_report_export(report_file, "HTML report")
            QMessageBox.information(
                self, "Success",
                f"Exported {len(report_files) - 1} HTML page(s). Open:\n{out_path}\n\n"
                "Keep all HTML pages and the search index.js file together.")

    def _report_rowids(self, selected):
        rows = ([index.row() for index in self.table.selectionModel().selectedRows()]
                if selected else range(self.table.rowCount()))
        return [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
                for row in rows if self.table.item(row, 0) is not None
                and self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) is not None]

    def _report_scope(self, scope, selected, page, type_column='', types=None):
        where, params = ('', []) if scope == 'all' else self._where_clause()
        if scope in ('selected', 'page'):
            ids = selected if scope == 'selected' else page
            if not ids:
                return ' WHERE 0', []
            where += (' AND ' if where else ' WHERE ') + '_rowid_ IN (' + ','.join('?' for _ in ids) + ')'
            params.extend(ids)
        if types is not None and type_column in self.columns:
            values = [value for value in types if value is not None]
            conditions = []
            if values:
                conditions.append(self._identifier(type_column) + ' IN (' + ','.join('?' for _ in values) + ')')
                params.extend(values)
            if None in types:
                conditions.append(self._identifier(type_column) + ' IS NULL')
            where += (' AND ' if where else ' WHERE ') + '(' + (' OR '.join(conditions) or '0') + ')'
        return where, params

    def _report_type_counts(self, scope, selected, page, column):
        where, params = self._report_scope(scope, selected, page)
        with sqlite3.connect(self.current_db) as connection:
            field, table = self._identifier(column), self._identifier(self.current_table)
            return connection.execute(f'SELECT {field}, COUNT(*) FROM {table}{where} '
                                      f'GROUP BY {field} ORDER BY {field}', params).fetchall()

    def _report_record_count(self, scope, selected, page, column, values):
        where, params = self._report_scope(scope, selected, page, column, values)
        with sqlite3.connect(self.current_db) as connection:
            return connection.execute(f'SELECT COUNT(*) FROM {self._identifier(self.current_table)}{where}',
                                      params).fetchone()[0]

    def _register_report_export(self, path, kind):
        audit(self.workspace_dir, 'report_exported', path=path, kind=kind,
              filters=self._export_context()['metadata'].get('Active filters'))
        if not self.image_path:
            return
        try:
            recents.remember_export(self.image_path, path, kind)
        except (OSError, ValueError) as exc:
            LOGGER.warning("Could not register report export %s: %s", path, exc)

if __name__ == '__main__':
    install_exception_hook(LOGGER)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app_icon = resource_path("assets", "cctv-log-analyzer.ico")
    if app_icon.is_file():
        app.setWindowIcon(QIcon(str(app_icon)))
    
    gui = CCTVLogAnalyzerWindow()
    gui.show()
    sys.exit(app.exec())
