# Dahua Digital Video Recorder (DVR) Forensic Findings

## File System Architecture
- **Standard Partitioning:** Dahua Generation A DVRs utilize a standard GUID Partition Table (GPT), recognizable by the `EFI PART` magic signature at Sector 1 (LBA 1).
- **Log Storage Location:** The system logs are not mixed with the raw video streams. Instead, they are stored inside a dedicated Linux partition, typically named `msftdata` or `Linux`, located at the end of the disk. This partition is generally 10GB in size.
- **File System:** The 10GB log partition is formatted using the **XFS** File System (`XFSB` magic signature).

## System Logs Architecture
- **Database Format:** Dahua stores its system logs in standard **SQLite 3** databases (e.g., `syslog.db`, `log.db`, `IoTDataBase.db`).
- **Payload Format:** Within the SQLite B-Tree tables, the actual log events are stored as serialized **JSON Strings**.
  - Example payload: `{"EventAction":"Log_EventStart","Log_Code":"PowerOn", ... }`

## Implemented Database and Log Interpretation

### Official NetSDK provenance and limits

Dahua's [official download center](https://www.dahuasecurity.com/download-center/softwares?menu_id=472)
routes its SDK category to the Partner Alliances knowledge base; access may
require an account or partner entitlement. An [official Dahua release note](https://materialfile.dahuasecurity.com/uploads/cpq/SWR/2802098/DH_Faraday_V3.146.0000000.32.R.240824_Release_Notes.pdf)
identifies `General_NetSDK_Eng_Win64_IS_V3.058.0000000.0.R.240325.7z`, but
does not supply a direct archive URL or checksum. No internal SQLite field
meaning is claimed to be verified by the SDK. NetSDK describes the live device interface; the disk databases and
their schema require separate validation. The interpretations below derive
from the cited forensic research and observed database contents.

The [452/dahua-sdk mirror](https://github.com/452/dahua-sdk)
was inspected at commit `4f162bd10b526045a51b80ff2277dead05cef9ab`
(2019-07-07). It contains a
Java/JNA `NetSDKLib.java` binding, demos, and native libraries. Its README
claims origin in Dahua's official download center, but the repository is not
an official Dahua publication and supplies no provenance hash. The binding
does not contain `CLIENT_QueryLog`, `NET_LOG_INFO`, `Log_Code`, or the SQLite
`log`/`operate`/`mode`/`user` schema. Consequently it does not validate the
meaning of fields in the offline DVR database. Its `nEventAction` fields refer
to live SDK alarm events and should not be equated with SQLite `EventAction`.

### Exported database cross-check (2026-10-04)

A separately exported `<serial>_log.db`
passed SQLite `integrity_check` and contains 10,596 `log` rows. Its lookup
tables contain 10 operations, three modes (`Log_Config`, `Log_Ugm`,
`Log_Event`), and six users. All observed operations have decoder mappings.
The dominant operations are `Log_SaveConfig` (6,137), `Log_NetLogin` (2,178),
and `Log_Logout` (2,154). The 106 alarm rows contain only video-loss and
video-blind codes in this particular export.

This cross-check corrected three assumptions: `Log_Index` also appears in
configuration records and is labelled as a camera channel only for `Log_Event`
(its meaning in a configuration record is not assumed);
`Log_NetLogin` does not by itself establish an external/remote actor (the
observed source address is `127.0.0.1`); and the `com.EndTime` in 13
`LossEnd` rows trails the authoritative `timep` by about one minute, so this
discrepancy must not be reported as a timezone offset. The original payload
time is preserved separately. Logout `Log_Time` is now retained as a device
timestamp. These observations apply to this export and are not a universal
Dahua schema guarantee.

#### Meaning of fields observed in the export

| Field | Interpretation for this export | Caution |
| --- | --- | --- |
| `log.timep` | Unix timestamp for the log row; primary timeline value | Compare with payload time; do not silently replace it. |
| `log.oid`, `log.mid`, `log.uid` | Keys into `operate`, `mode`, and `user` | `uid` can resolve to an empty name or a device/default identity. |
| `Log_Code` | Alarm code, e.g. `appEventVideoLoss` or `appEventVideoBlind` | Observed only on 106 event rows here. |
| `EventAction` | `Log_EventStart` / `Log_EventEnd` indicates event transition | Not a separate event type. |
| `Log_Index` | Camera channel on `Log_Event` rows | Also present on configuration rows; there its meaning is not established. |
| `Log_LinkRec` | Array of linked recording indexes | `[2]` accompanies `Log_Index=3` in examples; zero-based numbering is plausible, not proved. |
| `Log_LinkRecTime` | Device-provided time associated with linked recording | May refer to an earlier event, not the row's own timestamp. |
| `sys.StartTime`, `com.EndTime` | Device-provided event start/end strings | Some `LossEnd` end strings lag `timep`; preserve both. |
| `ReserveType` | Numeric event discriminator | `771/772` accompany loss start/end; `780/781` blind start/end in this export. No universal enum is asserted. |
| `Log_UserName`, `LoginUser` | Account recorded for login or as the acting account | `User` on `Log_ModUser` is the *target* account, not necessarily the actor. |
| `Log_IP_Address`, `LoginIPAddr` | Recorded login address | `127.0.0.1` indicates loopback, not a remote host. |
| `Log_FailReason` | Device-provided authentication failure reason | Preserve original language/text. |
| `Name`, `Log_Name` | Names of the setting and log group in configuration rows | Interpret the exact setting through its `Detail` entries. |
| `Detail[].ID`, `Detail[].Value` | Setting identifier and ordered list of stored values | A two-item `Value` list resembles old/new but direction is not verified. |
| `Authority` | Permission changes on `Log_ModUser` | Entries explicitly contain `Old` and `New`; these can be described as enabled/disabled. |
| `Group`, `User`, `IP` on `Log_SaveConfig` | Recorded group, user, and source fields | `IP` may be symbolic (`sys.UserStLoginLocal`), not an IP address; `User=default` does not prove a human user. |
| `Log_Time` | Device-provided timestamp in logout and failed-login rows | Compare with `timep` before inferring a timezone. |

The normalized `explanation` column now includes the relevant field values
for each row, while `raw_json` retains the complete original payload. In
particular, `Log_SaveConfig` means a save was logged; it does not prove every
repeated row represents a distinct manual configuration change.

The extractor recursively walks the XFS hierarchy and preserves every SQLite
database (`.db`, `.sqlite`, `.sqlite3`, `.db3`) under `Dahua_Databases`, rather
than selecting only the root serial-number log. This includes the root log,
IoT, POS, SMD, face recognition/detection, and IVS databases when present.

`Dahua_Analysis.db` contains two analysis tables:

- `dahua_databases`: source path, size, readable/partial status, table list,
  and per-table row counts for every extracted database.
- `dahua_logs`: normalized log timeline with Unix time converted to explicit
  UTC, the recorder-provided timestamp retained separately, any inferred UTC
  offset, resolved mode/operation/user lookups, channel, decoded action and a
  plain-language forensic explanation. Original JSON is always preserved.

The event interpretations implement Appendix A of Evangelos Dragonas' thesis
and the corresponding peer-reviewed study, including login/logout, illegal
login, account changes, video loss/tampering, network camera disconnects,
configuration changes, recording modes and intelligent alarms:

- E. Dragonas et al., “IoT forensics: Exploiting log records from the DAHUA
  technology CCTV systems,” *Journal of Forensic Sciences*, 2024,
  https://doi.org/10.1111/1556-4029.15401
- E. Dragonas, thesis Appendix A, University of Piraeus,
  https://dione.lib.unipi.gr/xmlui/handle/unipi/15806

The paper also establishes an important scope limitation: some Dahua log types
exist only in recorder internal memory/exported GUI text and cannot be recovered
from the disk databases alone. The program reports extracted disk evidence and
does not imply that it represents every log held by the original recorder.

## DMSS Mobile-App Correlation

Dragonas, Lambrinoudakis, and Kotsis also examined the Dahua DMSS companion
application on Android and iOS (“IoT Forensics: Investigating the Mobile App of
Dahua Technology,” IEEE CSR 2023, DOI: 10.1109/CSR57506.2023.10224982). These
artifacts are a separate evidence source and must not be labelled as originating
from the DVR disk, but they can corroborate and enrich the recorder timeline.

Useful Android artifacts include:

- `shared_prefs/dh_data.xml`: last DMSS account email and `{userName}` identifier.
- `databases/devicechannel.db`: recorder-friendly names and channel names.
- `databases/.db` and `databases/{userName}.db`: devices, sharing state,
  settings, cloud alarm notifications and notification channels.
- `Download/snapshot` and `Download/snapshot/video`: user-created snapshots,
  MP4 recordings and DAV playback exports whose filenames encode creation time.

Useful iOS artifacts include:

- `Library/Support/config.plist`: last account and account identifiers.
- `Library/Support/Devices.sqlite3`: recorder and channel names.
- `Library/Support/{userID}/DMSSCloud.sqlite`: devices, settings and cached
  alarm notifications for each historically used account.
- `Documents/Captures` and `Documents/Videos`: saved visual evidence.

Future mobile-evidence ingestion should correlate on device serial number,
channel identity, account, event type and timestamp while retaining provenance
columns (`DVR/XFS`, `Android DMSS`, `iOS DMSS`, or `cloud cache`). Cloud alarm
caches can be incomplete, so absence from the mobile database is not evidence
that the recorder event did not occur.

## XFS and Forensic Extraction
- **XFS Sub-Block Allocation:** While the partition is valid XFS, Dahua employs proprietary modifications to the file system allocation mechanics (such as tail-packing or sub-block alignment). SQLite database headers (e.g., `SQLite format 3`) are frequently found at non-standard block offsets (e.g., byte 1540 of a physical block). 
- **Tool Compatibility:** Sleuth Kit-based workflows may fail on these images, but `dissect.xfs` successfully resolves the tested filesystems when given a correct partition-relative seekable stream.
- **Forensic Extraction Methodology:** 
  1. **Commercial:** Tools like UFS Explorer have reverse-engineered the proprietary Dahua XFS containers and can extract the SQLite databases cleanly.
  2. **Implemented Open-Source Path:** Parse GPT, verify `XFSB`, expose a partition-relative stream to `dissect.xfs`, and extract the original SQLite databases without modifying the evidence.
  3. **Fallback:** Raw JSON carving remains useful when the filesystem metadata is damaged.

## Implementation and Validation

| Image | XFS start LBA | Main log database | Log rows |
|---|---:|---|---:|
| DAHUA1.E01 | 3,886,063,616 | `<serial>_log.db` | 30,000 |
| DAHUA2.E01 | 1,932,558,336 | `<serial>_log.db` | 1,080 |

The main log, IoT, SMD, and POS databases extracted from both images passed
SQLite `integrity_check`. The partition wrapper maintains correct relative
`read`, `seek`, and `tell` positions for raw and E01 evidence. Directories are
skipped rather than treated as byte streams, and extraction errors are surfaced
to the caller.
