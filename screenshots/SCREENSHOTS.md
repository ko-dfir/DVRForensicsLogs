# CCTV Log Analyzer 1.01 — screenshot set

Ten screenshots of the running application, captured on 2026-10-17.
All source images, records, users and recorder identifiers are synthetic DEMO data.

All ten PNGs were captured using the application's native QWidget.grab export.
They contain only the client area of the main window or active dialog, without
the mouse cursor, window decorations or desktop. Image dimensions vary to fit
each view.

1. `01-tvt-dark-overview.png` — TVT parsed records, case workspace, column filters and pagination.
2. `02-tvt-config-filter.png` — original TVT mlogtype filter restricted to configuration events.
3. `03-tvt-record-hex.png` — double-click inspector with recovered record bytes and logical offsets.
4. `04-report-config-selection.png` — report record selection with only config events checked and exact count.
5. `05-report-column-selection.png` — report column selection and investigation-summary preset.
6. `06-hikvision-log-explanation.png` — Hikvision record, SDK identifiers, interpretation and source offset.
7. `07-dahua-source-database-filter.png` — normalized Dahua records filtered to a single demo source database.
8. `08-settings-appearance-reports.png` — appearance, fonts, recent history and report defaults.
9. `09-tvt-light-theme.png` — parsed TVT records with the light theme.
10. `10-full-image-entropy-survey.png` — complete scan of a small demo image and interpreted entropy results.

TVT and Hikvision fixtures were parsed by the production engines. The Dahua
sample demonstrates normalization of synthetic exported SQLite databases; its
image is a detection-signature fixture, not a functional XFS filesystem. These
screenshots illustrate the UI, not validation against real recorder evidence.
The screenshots were taken with an isolated settings/history profile.
