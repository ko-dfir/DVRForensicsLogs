# TVT (Shenzhen TVT) Digital Video Recorder (DVR) Forensic Findings

## File System Architecture
- **Headless/Raw Disk:** TVT DVRs use a completely raw, "headless" disk architecture. There is no Master Boot Record (MBR), no GUID Partition Table (GPT), and no traditional file system (no FAT, Ext4, XFS, etc.).
- **Video Ring Buffer:** The majority of the disk acts as a gigantic video ring buffer. The video streams are interspersed with proprietary index chunks, recognizable by the magic signature `SHFL` (occurring roughly every 300GB). 
- **Log Sequestration:** Despite the lack of partitions, system logs are mathematically sequestered to a specific physical region near the beginning of the disk. In 1TB/2TB drives, logs are typically found exclusively at the **~1GB mark** (physical offsets ranging between ~939 MB and 1.036 GB).

## System Logs Architecture
- **Format:** TVT does not use fixed-length C-Structs (like Hikvision) or SQLite databases (like Dahua). Logs are stored in a **Proprietary Variable-Length Key-Value String** format.
- **Payload Signature:** The core of the log is a plaintext key-value string, typically starting with `mlogtype:`.
  - Example: `mlogtype:operation;action:28;ip:192.0.2.10;`
- **Measured Record Layout:**
  1. The surrounding binary record begins with marker `AA AB`.
  2. The 4-byte Little-Endian Unix epoch is located at `marker + 16`.
  3. Operation/configuration records may contain a one-byte username length followed by the username (for example `admin`).
  4. The two bytes immediately before `mlogtype:` contain the exact payload length.
- **Termination:** A NUL terminator is not guaranteed. The declared two-byte payload length is authoritative.

## Forensic Extraction Methodology
Because there is no file system, file-based extraction tools are blind to TVT logs. The implementation scans the validated 850-1100 MiB physical region, locates `mlogtype:`, resolves the preceding `AA AB` record marker, reads the fixed timestamp and optional length-prefixed username, and consumes exactly the declared payload length.

A 1.86 TiB raw validation image was identified from an on-media
`mlogtype:` signature near 980 MiB. A bounded read-only scan recovered 446,339
records, including 446,324 with valid UTC timestamps. Sector inspection found
no MBR/GPT and bounded disk sampling found
the expected `SHFL` video-ring signature in all five samples.

## Implementation and Validation

`TVT1.001` produced 439,930 valid records at 439,930 unique physical offsets:

| Category | Records |
|---|---:|
| Alarm | 426,223 |
| Operation | 13,134 |
| Configuration | 315 |
| Exception | 258 |

Eight damaged records have no recoverable timestamp. Structural parsing removed
14 malformed false positives from the previous heuristic result and corrected
shifted timestamps, contaminated usernames such as `adminG`/`adminI`, and
payloads that previously crossed into the next record. SQLite output includes
the physical `source_offset` and is idempotent across repeated runs.

## Device Metadata Scope

Bounded sampling of `TVT1.001` confirms an empty sector-zero partition table
(no MBR/GPT) and finds the proprietary `SHFL` video-ring signature throughout
the disk. The `mlogtype` payloads expose timestamps, usernames, source IPs,
channel UUIDs, NAT/P2P information, categories and action codes. No validated
recorder model or recorder serial field was found in either the raw header area
or the recovered log payloads, so the UI does not invent these values.

Disk model, disk serial, interface, geometry and acquisition hashes are shown
when present in the forensic acquisition sidecar and are explicitly labelled
as acquisition metadata. After carving, the UI adds the recovered log range,
record count, distinct users/IPs/channels, categories and action codes.
