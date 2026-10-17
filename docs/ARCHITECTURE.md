# CCTV Log Analyzer - Architecture

## 1. Overview

The application performs dead-box analysis of raw and E01 DVR/NVR images. It
uses a shared desktop workflow while preserving a vendor-specific acquisition
strategy:

- Hikvision: proprietary HIKFAT metadata and fixed-size `RATS` records.
- Dahua: GPT/XFS discovery and native extraction of SQLite databases.
- TVT: filesystem-independent carving of variable-length `mlogtype:` records.
- iCatch: identified from its hourly recording index only; no usable logs were
  found, so carving is disabled.

## 2. Primary Components

### Desktop Application

`cctv_log_analyzer.py` is the primary PySide6 entry point. It provides image
selection, evidence-based vendor detection, threaded extraction, searchable
SQLite results, CSV/HTML export, terminal output, and job status.

`hikvision_forensic_viewer.py` is the legacy PyQt6 specialist interface. It
contains the detailed Hikvision overview, exfiltration, camera intelligence,
statistics, and raw-payload inspector tabs. It is retained as a legacy entry
point; its investigation views are now part of the main PySide6 app.

The shell uses a fixed left rail for recent evidence and settings. Database
filters live inside a custom `QHeaderView`, so each filter is visually bound to
its column while the separate search box remains global. Extraction workers
emit standards-shaped SSE frames (`event:` plus JSON `data:`); the GUI decodes
these queued events and updates a byte-accurate progress bar without blocking
the Qt event loop.

Application diagnostics use rotating UTF-8 logs under
`%LOCALAPPDATA%\CCTVLogAnalyzer\logs`. `app.log` records lifecycle,
detection, extraction, progress, and UI terminal activity; `error.log` receives
errors and uncaught exceptions. Each log rotates at 5 MiB with five backups.

### Detection

`scripts/dvr_extractor.py` contains `detect_brand_details()` and the CLI. Brand
selection is based only on media structures:

1. Dahua: GPT entry whose partition begins with `XFSB`.
2. Hikvision: `HIKVISION@HANGZHOU` or a repeated `RATS` structure.
3. TVT: `mlogtype:` in the measured log region near 1 GiB.
4. iCatch: fixed-cadence `HOUR_` recording-index records in the first 16 MiB.
5. No unique signature: `UNKNOWN`; carving remains disabled.

### Image Access

`scripts/e01_native.py` adapts `libewf-python` to the same `read`, `seek`,
`tell`, and context-manager behavior as a raw Python file. Engines therefore do
not need separate carving logic for raw and E01 evidence.

### Vendor Engines

- `scripts/engine_hikvision.py`: HIKFAT structure detection, log-region
  selection, `RATS` carving, SDK resolution, payload parsing, SQLite output.
- `scripts/engine_dahua.py`: GPT partition parsing, partition-relative stream,
  `dissect.xfs` traversal, original database extraction.
- `scripts/engine_tvt.py`: targeted `mlogtype:` carving, binary-prefix parsing,
  action/category translation, SQLite output.
- `scripts/forensic_engine.py`: compatibility re-export of the Hikvision engine
  for older tests and viewers.

### Mapping and Reporting

- `scripts/hikvision_log_types.json`: Hikvision SDK major/minor mappings.
- `scripts/carving_utils.py`: legacy parsing/report compatibility helpers.
- `scripts/csv_reporting.py`, `scripts/html_report_files.py`, and
  `scripts/intel_methods.py`: legacy Hikvision reporting.
- `export_to_csv()` and `export_to_html()` in `scripts/dvr_extractor.py`:
  vendor-neutral exports of the selected SQLite result table.

## 3. Processing Flow

1. The user selects `.E01`, `.001`, `.dd`, `.img`, or `.bin` evidence.
2. `detect_brand_details()` reads bounded physical regions and returns brand,
   confidence, evidence, offsets, and vendor scores.
3. A `QThread` runs the selected vendor engine.
4. The engine writes or extracts a SQLite database in the output directory.
5. The GUI chooses the forensic table (`log`, `hikvision_logs`, or `tvt_logs`),
   then provides filtering and export.
6. Re-running an image is idempotent for carved Hikvision/TVT tables.

## 4. Vendor Data Paths

```text
Raw / E01 evidence
        |
        +-- GPT + XFSB -----------------> Dahua XFS -> original SQLite DB
        |
        +-- HIKVISION@HANGZHOU / RATS ---> Hikvision region carve -> SQLite
        |
        +-- mlogtype near 1 GiB ---------> TVT structured carve -> SQLite
        |
        +-- no validated signature ------> UNKNOWN (no automatic carve)
```

## 5. Verification

The automated suite currently contains 149 tests. Real-image validation uses
a controlled set of evidence images; diagnostic outputs are
written only to temporary directories and the evidence is opened read-only.

## 6. Per-User State and Packaging

- Appearance preferences are stored through `QSettings` and include the theme
  (system, dark or light; system follows the Windows colour scheme through
  `QStyleHints.colorScheme()` and its change signal), font family, font size,
  recent-list size, and result page size.
- Recent evidence is stored in
  `%LOCALAPPDATA%\CCTVLogAnalyzer\recents.db`. The SQLite database is
  created on first run; the installer creates its parent directory and marks it
  `uninsneveruninstall`, preserving history across upgrades and uninstall.
- `build.bat` reads `version.json`, builds the Nuitka standalone application, and
  invokes the Inno Setup compiler using
  `installer/CCTVLogAnalyzer.iss`.
