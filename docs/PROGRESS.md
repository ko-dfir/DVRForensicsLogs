# Development Progress

Last validated: 2026-10-15

## Compiled startup fix and installer options

- Fixed an access violation at startup of Nuitka builds by replacing Qt-connected
  lambdas across the PySide6 UI with bound `@Slot` methods: header
  geometry/debounce, main table scrollbar/row resize, entropy/investigation paging
  and report buttons. Regression tests cover their signal behavior and fail if a
  connected lambda is reintroduced.
- Build dependencies are pinned (PySide6 6.11.2, Nuitka 4.2.2) and synchronized on
  every build. A short external venv is configurable, Inno Setup is checked before
  normal compilation, and `--exe-only` / console diagnostic builds are available.
- Native fault diagnostics go to AppData `native-crash.log`; version.json separates
  display `1.01` from the explicit numeric Windows resource version `1.1.0.0`.
- The installer asks whether to install for the current user only (no
  Administrator rights, `%LOCALAPPDATA%\Programs`) or for all users
  (`Program Files`, Administrator rights required).
- Physical Drive checks for Administrator rights before reading and offers
  "Restart as Administrator" through the Windows UAC prompt; a header badge shows
  when the app is elevated.
- Validation: 147 regression tests pass. The console and windowed executables
  start and open the main window, and the installer builds. See
  `docs/BUILD_NOTES.md`.

## CCTV Log Analyzer 1.01

- Updated product name, canonical version, executable and installer output names.
- Result rows show a short explanation summary; the full text is in the record
  details window (double-click), including a scrollable Full text tab.
- Dahua source database selector filters the complete dataset and CSV/HTML exports.
- Hikvision and TVT extraction databases now retain recovered record hex. Absolute
  logical evidence offsets are exposed in columns and in the double-click hex view.
  Existing extracted databases need re-extraction for stored hex.
- Unrecognized images offer an asynchronous, cancellable, read-only entropy survey.
  The default reads every byte of the whole logical image. Alternatively users
  choose a range without a 4 GiB cap. Results stream to temporary SQLite and
  are paged, with a global candidate filter and plain-language interpretations.
  Byte progress, throughput and ETA show the cost of complete coverage. Small
  regions can be masked by large windows; no log presence/absence is inferred.
- TVT now stores original `mlogtype` values with an independent global selector
  in the UI and HTML report. Filtering applies to exports and all pages. Older
  derived extraction databases are backfilled from `raw_payload` automatically.
- HTML reports offer per-export column selection and presets, record scope
  (filtered, selected rows, current page or all), title, logo, metadata and page
  size. Excluded fields are omitted from HTML and its global search index.
  Selected rows use stored row identities so UI sorting preserves selection.
- The report Records / log types tab now checks individual original types or
  categories (e.g. TVT config only, Dahua category or Hikvision minor type).
  Per-type counts and the exact export total update with scope and checkboxes.
  Unchecked types are excluded before files and search index are generated.
- Case folder selection now creates a unique per-run workspace per image, with
  databases/reports subfolders, provenance/status manifest and UTC audit log.
  Report choices, extraction progress/counts/errors and entropy outputs are
  retained there. Recents restores the original workspace; prior output folders
  remain in place. Physical-disk destinations are verified before creation.
- Validation: 92 tests passed, including synthetic binary record byte/offset
  comparisons, global database filtering, inspector hex, entropy bounds and cancellation.

## Current State

The project is a multi-vendor CCTV recorder forensic workbench supporting Hikvision,
Dahua, and TVT images. The primary desktop entry point is
`cctv_log_analyzer.py`, including the Hikvision investigation tabs. The older
Hikvision-specific viewer is retained only as a legacy entry point.

## Recent Milestones

### PySide6 Desktop Interface

- Migrated the primary GUI from PyQt6 to PySide6.
- Added a modern dark visual system, application header, evidence/brand badges,
  sortable alternating-row tables, terminal output, progress and status bars.
- Updated `run_dev.bat`, `build.bat`, and `requirements.txt` for PySide6,
  `dissect.xfs`, and `libewf-python`.
- Unknown images no longer enable carving automatically.
- Added a custom DVR/forensic application icon in PNG and Windows ICO formats.
- Introduced canonical `version.json` metadata; the UI and Windows executable
  metadata now read the same version. The initial application version is `0.1`.
- Added persistent dark/light theme and font family/size settings.
- Added SQLite recent-evidence history under `%LOCALAPPDATA%` and moved recent
  evidence plus settings into a permanent left navigation rail.
- Added global search, filters embedded directly in every column header,
  optional date-range filtering, and SQL-backed pagination with configurable
  page size.
- Replaced synthetic progress stages with byte-accurate callbacks from all
  three vendor engines. Worker progress is serialized as SSE event frames and
  rendered with byte totals, phase/region/file context, and timestamps.
- Made the version badge clickable; its dialog renders the release notes held
  in the canonical `version.json`. Removed the blocking success dialog.
- The image picker now persists and reopens the last evidence directory.
- Added transparent `.001/.002/...` split-raw reading across segment boundaries.
  Large monolithic E01 acquisitions get a fast, on-media Dahua preflight that
  validates the decoded GPT layout without waiting for a full libewf index.
- Reduced Dahua resource pressure: GPT and XFS now share one EWF handle,
  partition reads are bounded, and extraction is restricted to database/log
  artefacts instead of copying every regular file from the XFS root.
- Dahua XFS collection now recursively preserves every SQLite database,
  inventories its tables, builds a normalized UTC/device-time timeline, and
  explains known events using the published Dragonas mapping. The UI dataset
  selector exposes both normalized logs and the complete database inventory.
- Added a provenance-aware Device Metadata UI tab. Hikvision supplies recorder
  and disk fingerprints plus filesystem details from its on-disk records;
  Dahua derives recorder serials from `{serial}_log.db`; TVT reports its raw
  SHFL layout and the metadata actually recoverable from `mlogtype` records.
- Added an Inno Setup 7 installer pipeline; the build now produces both the
  application directory and a versioned Setup executable.

### Evidence-Based Brand Detection

- Replaced the former `anything else is TVT` fallback with positive on-media
  identification in `scripts/dvr_extractor.py`.
- Dahua requires GPT plus an `XFSB` superblock at a partition boundary.
- Hikvision requires `HIKVISION@HANGZHOU` or multiple `RATS` records.
- TVT requires an `mlogtype:` payload in the known log region or input chunk.
- Detection returns brand, confidence, physical evidence, offsets, and scores.
- Validated correctly against two Dahua E01 images, two Hikvision E01 images,
  one TVT raw image, and a standalone Hikvision log file.

### Native E01 Repair

- Fixed the `E01File` wrapper to use the supported pyewf
  `read_buffer_at_offset()` API instead of the nonexistent `read_random()`.
- Synchronized wrapper and libewf seek positions.
- Raw and E01 inputs now share a seek/read interface across all engines.

### Hikvision Engine

- Consolidated the implementation in `scripts/engine_hikvision.py`; the new
  `scripts/forensic_engine.py` is a compatibility facade for older imports.
- Carving now uses detected declared/residual log regions rather than scanning
  an arbitrary multi-gigabyte prefix.
- Added offset deduplication and idempotent SQLite output.
- Retained invalid timestamp handling, SDK mapping, channel correction, and
  aggressive context inference.

Validated results:

| Image | Region | Records |
|---|---|---:|
| HIKVISION1.E01 | Declared active ring-buffer | 12,361 |
| HIKVISION1.E01 | Alternative residual region | 44,585 |
| HIKVISION1.E01 | Total unique | 56,946 |
| HIKVISION2.E01 | Declared active ring-buffer | 86 |

### Dahua Engine

- Corrected partition-relative `read`, `seek`, and `tell` behavior for both raw
  and E01 images.
- XFS extraction now skips directories and surfaces failures instead of
  returning a misleading partial success.
- The GUI selects the forensic `log` table instead of the first SQLite table.
- Every extracted SQLite database passed `PRAGMA integrity_check`.

Validated results:

| Image | XFS start LBA | Main log rows |
|---|---:|---:|
| DAHUA1.E01 | 3,886,063,616 | 30,000 |
| DAHUA2.E01 | 1,932,558,336 | 1,080 |

### TVT Engine

- Replaced heuristic backward timestamp hunting with the measured binary
  record structure: `AA AB` marker, epoch at marker+16, two-byte payload length
  immediately before `mlogtype:`, and an optional length-prefixed username.
- Payloads are read by their declared length rather than an assumed NUL byte.
- Fixed corrupted usernames such as `adminG`/`adminI`, cross-record payloads,
  overlap duplicates, and shifted false timestamps.
- Added physical `source_offset` and idempotent SQLite output.
- The GUI scans the validated 850-1100 MiB log area instead of 10 GiB.

Validated TVT result: 439,930 unique records at 439,930 unique offsets; 426,223
alarms, 13,134 operations, 315 configuration events, and 258 exceptions. Eight
damaged records have no recoverable timestamp.

## Automated Verification

- 147 unit/regression tests pass under headless Qt (2026-10-15 update), including
  live worker cancellation and rendering all three investigation tabs in both themes.
- Real-image end-to-end SQLite creation passed integrity checks for all three
  vendors.
- Synthetic tests cover brand detection, Hikvision parsing, TVT field layout,
  Dahua partition views, UI filtering, and forensic inspectors.

## Cancellation and vendor field updates — 2026-10-15

- Cooperative extraction cancellation now covers TVT scanning/writing, Hikvision
  scanning/fingerprint reads/writing, and Dahua GPT/XFS traversal, file copying
  and SQLite normalization. The main UI offers Cancel extraction. Cancellation
  emits its own SSE event and workspace/audit status, never success or failure.
  SQL write transactions roll back; copied but unfinished XFS files retain a
  `.partial` suffix. The workspace is kept and is explicitly incomplete.
  A blocking native EWF open/read must return before cancellation can take effect;
  no unsafe thread termination is used.
- TVT interpretation now supports 38 N9000 SDK types plus 24 named DD_LOG_INFO
  operations, with separate action code, SDK macro, interpretation provenance
  and a lossless parsed-payload field column. Numeric raw `action` values are
  deliberately not equated with the SDK type enum. The existing seven raw-action
  mappings remain; unmapped raw action numbers remain visible as original codes.
- Dahua normalized records expose actor account, source IP, configuration target
  and per-field JSON explanations. Every key/value, including unknown/nested
  fields, remains available with context-specific Log_Index interpretation.
  Camera index zero is no longer lost. Raw JSON and its source database/row remain.
- The primary PySide6 app now includes Security Audit, Camera / Motion and Log
  Statistics. These are SQL-backed, paginated views sharing the main global,
  column, category and date scope. They include event/channel selectors, full
  record/hex inspection, type-count drilldown and declared/residual/other counts.
  New Hikvision extractions retain region/status; old databases explicitly show
  missing provenance as not stored rather than inventing it.
- `.gitignore` excludes environments, caches, evidence, derived databases, build
  outputs and local research data.

### Ongoing format-validation limits

- New undocumented numeric TVT actions and undocumented Dahua fields require
  further source/fixture validation; unknown values are retained, not guessed.
- Regression coverage uses synthetic fixtures. Earlier real-image validation
  results above are historical; the new changes have not been rerun over every
  original evidence image.

### Filtered reports and Dahua XFS progress

- Table rows now open in a full record inspector on double-click.
- CSV and HTML exports use the active global, column and date filters; pagination does not limit the export.
- HTML reports use a blue forensic theme and can embed a user-selected logo as a standalone data URI.
- Dahua EWF opening and XFS traversal report an indeterminate activity phase, followed by byte-accurate progress once database files are indexed.
- Detection confidence and internal scores remain diagnostic log data and are no longer presented in the UI/footer.

### Log category filters

- The workbench reads the available categories directly from each extracted database:
  Dahua `category`, Hikvision `major_type`, and TVT `event_category`.
- Selecting a category filters the paginated search results and both CSV and HTML
  exports together with the existing global, column, and date filters.
- Standalone HTML reports use linked page files plus a companion JavaScript
  search index. Category and text filters query all exported records and link
  directly to matching rows on any page. Keep all generated files together;
  the selected UI category is recorded in report metadata.
