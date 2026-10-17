# Changelog

## 1.01 — 2026-10-15

- Fixed a startup crash in compiled (Nuitka) builds: Qt-connected lambdas were
  replaced with bound slots, build dependencies pinned, a native crash log added,
  plus a short-path build venv and executable-only/diagnostic build options.
- The installer asks whether to install for the current user only (no
  Administrator rights) or for all users (Program Files).
- Physical Drive checks for Administrator rights and offers Restart as
  Administrator; a header badge shows when the app is elevated.
- Fixed result rows growing taller than the window for very long values (e.g.
  Dahua configuration explanations): result rows now show a short summary
  (about 150 characters), capped at three lines; the full text is shown in the
  record details window (double-click), which now scrolls by pixel. Values
  that cannot wrap (e.g. raw payloads) are cut with "…" instead of painting
  over the neighbouring column.
- Tooltips have explicit colours in both themes, so they stay readable with the
  Windows light theme; long tooltips are shortened.
- New System theme (the default) follows the Windows light/dark app setting and
  switches live when it changes; Dark and Light remain available.
- Licensed under GPL-3.0.

- Added cooperative extraction cancellation, explicit cancelled workspace/SSE
  status, transaction rollback and `.partial` names for interrupted XFS copies.
- Integrated SQL-paginated Hikvision Security Audit, Camera/Motion and Log
  Statistics into the main PySide6 app, with shared filters and record drilldown.
- Added TVT SDK type/named-operation interpretation with namespace provenance,
  and expanded Dahua JSON field explanations and actor/source/config columns.
- Added `.gitignore` and a source packaging script.

- Added an explicit case folder with a unique workspace per analysis run,
  separate databases/reports directories, a workspace manifest and UTC audit log.
  Recent evidence restores its workspace and entropy results are preserved there.

- Report log-type selection chooses the actual records (e.g. TVT config only),
  independently of visible columns, with per-type counts and an exact export total.

- HTML export now offers per-report field selection, a summary preset and record
  scope (filtered, selected, current page or entire dataset), plus presentation
  options. Excluded fields are also omitted from the companion search index.

- TVT exposes original mlogtype values as a column and independent global filter
  in the UI and HTML report. Older extracted TVT databases are upgraded from
  their raw payloads without re-reading the evidence image.

- Entropy UI explains the method and interpretations, defaults to full-image
  byte coverage, and supports selected ranges without a 4 GiB cap. Results are
  stored on disk with pagination, candidate filtering, throughput, ETA and cancellation.

- Named CCTV Log Analyzer, the successor of HikvisionLogAnalyzer.
- Full-text tab in the record details window.
- Dahua source database filter applies globally and to CSV/HTML exports.
- Hikvision and TVT store recovered record hex and logical image offsets.
- Unknown images offer a read-only entropy survey with configurable range, progress and cancellation.

## 0.3 — 2026-10-05

- Version metadata updated to 0.3; no additional functional changes in this bump.

## 0.2 — 2026-10-05

- Faster E01 reads with a bounded random-read cache and larger sequential scan blocks.
- HTML reports now include category filtering, search, pagination and configurable presentation.
- Improved evidence navigation, date filters and log category views across supported brands.
- Dahua source database names omit computer paths; report pages are separate, linked HTML files with readable columns.
- A shared local search index makes report text and category filters work across all HTML pages.
- The image picker remembers the last folder; successful extraction shows a completion dialog with Open Folder.

## 0.1 — 2026-09-21

- Modern PySide6 interface with dark/light themes and configurable fonts.
- Recent evidence database in `%LOCALAPPDATA%\CCTVLogAnalyzer`, exposed through a left sidebar.
- Global search, date filters, per-column header filters and SQL pagination.
- Real byte-based TVT, Hikvision and Dahua progress encoded as SSE events.
- Detailed timestamped terminal activity and non-blocking completion feedback.
- Improved multi-signal brand detection and validation against the available forensic images.
- Application icon, `version.json` metadata and an Inno Setup installer build.
