# Hikvision Digital Video Recorder (DVR) Forensic Findings

## File System Architecture
- **Proprietary Structure:** Hikvision DVRs do not use standard file systems like FAT, NTFS, or Ext4. Instead, they format the disk using a proprietary structure commonly referred to as **HIKFAT** or **HIKVISION@HANGZHOU**.
- **Data Layout:** The disk is divided into a Master Sector, index blocks, and video/log data blocks. 

## System Logs Architecture
- **Log Signature:** The system logs are stored sequentially in fixed-length proprietary C-Structures. Every valid system log starts with the magic byte signature `RATS` (0x52 0x41 0x54 0x53).
- **Structure Size:** Each `RATS` log record is exactly **136 bytes** long.
- **Timestamp Format:** The timestamp is stored as a 4-byte Little-Endian unsigned integer representing a standard Unix Epoch (Seconds since 1970-01-01), typically found immediately following the event type metadata.
- **Data Fields:** The 136-byte structure typically includes:
  - Magic Signature (`RATS`)
  - Event Type / Action Code
  - Unix Epoch Timestamp
  - Channel / Camera ID
  - Fixed-length strings (e.g., IPv4 addresses, usernames)

## Forensic Extraction Methodology
Standard file system parsing tools will fail. The most reliable forensic extraction method is **Raw File Carving**. By scanning the raw disk (or `.E01` image) for the 136-byte blocks beginning with `RATS` and decoding the contained Little-Endian timestamps, investigators can recover both live and deleted/orphaned system logs.

## Implementation and Validation

- The engine first reads `HIKVISION@HANGZHOU`, then scans only the declared active ring-buffer and any validated residual region.
- `HIKVISION1.E01` produced 12,361 declared and 44,585 residual records (56,946 unique records).
- `HIKVISION2.E01` produced 86 declared records.
- SQLite output is deduplicated by physical offset and cleared before a repeated run, preventing duplicate evidence rows.
- Native E01 access is provided by `libewf-python`; no mounted intermediary image is required.

## Published research

The HIKFAT log-region analysis and `RATS` record decoding implemented here
originate in HikvisionLogAnalyzer and the accompanying study:

- E. Dragonas, C. Lambrinoudakis and M. Kotsis, "IoT forensics: Exploiting
  unexplored log records from the HIKVISION file system," *Journal of Forensic
  Sciences*, vol. 68, no. 6, pp. 2002–2011, 2023.
  https://doi.org/10.1111/1556-4029.15349

## Log interpretation and evidence provenance

The extracted `hikvision_logs` table now retains `major_code`, `minor_code`,
`sdk_macro`, `interpretation_source`, and a human-readable `explanation`.
Hikvision's *Device Network SDK (General) Developer Guide*, especially its
"HCNetSDK Log Types" appendix, documents the major/minor event taxonomy:
alarm, exception, operation, information, and event. The SDK label identifies
the event category and subtype; it does **not** establish whether an action
succeeded, who performed it, or whether the device clock was accurate.

The offline `RATS` byte layout, payload-derived channel/user/IP, and Unix
timestamp decoding remain forensic reverse-engineering findings, not claims
made by the SDK guide. Unknown codes retain their numeric values and are
explicitly marked as unverified. The SDK guide describes network API log
structures, not the proprietary disk record format.

### Cross-check against device exports (2026-10-04)

Read-only parsing of the device's exported `logCurFile.bin` and `logMainFile.bin`
yielded 12,361 and 44,585 records respectively (56,946 total), with no
unmapped major/minor combinations in this sample. The 2,000 entries in the
first exported XML log report matched raw records by timestamp and event label;
all 11 entries in the second report matched by timestamp and event label. This validates the
observed code-to-label mapping for these samples, not every SDK subtype.

The two `Local: Playback by Time` entries in the second report have
`Channel No.=0`. Their 60-byte raw payloads have no validated camera field;
the old parser nevertheless defaulted to Camera 1. That default was removed.
An empty extracted channel now means unknown/not available, **not** camera 1.
The raw timestamp strings match the wall-time strings in the device XML for
these samples. Neither source alone proves the device's timezone or clock
accuracy. The first report covers mostly server-status and S.M.A.R.T. events;
therefore its agreement does not validate all user-action payload fields.

