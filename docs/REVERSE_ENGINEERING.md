# Reverse Engineering HIKFAT & Hikvision Logs

## 1. The Hikvision Filesystem (HIKFAT)
Hikvision devices do not use standard FAT/NTFS filesystems. They write data directly to physical sectors using a proprietary scheme.
*   **Master Sector:** Located near the beginning of the disk. Identified by the `HIKVISION@HANGZHOU` signature.
*   **Log Partitions:** The Master Sector defines where logs are stored:
    *   **logCurFile (Active Logs):** `Declared Active Ring-Buffer` (Usually 16MB). Found at offsets defined by bytes 96:104.
    *   **logMainFile (Archive Logs):** `Alternative Residual Region` (Usually 64MB).
*   **UFS Explorer vs Raw Carving:** Tools like UFS Explorer Pro extract logical files from the filesystem index. The engine carves both declared and residual physical regions directly, allowing recovery of active and orphaned records.

## 2. Log Structure (RATS)
Each log entry is a fixed-size block, starting with:
*   `0x52 0x41 0x54 0x53` (`RATS` magic signature)

### Header
*   Contains standard metadata: Event Timestamp (32-bit LE Unix Epoch), Major Type (32-bit), Minor Type (32-bit).
*   **Invalid Timestamps:** Uninitialized or corrupted logs often have timestamps of `0x00000000` or `0xFFFFFFFF`. These are explicitly caught and labeled as "N/A (Uninitialized)" to prevent parsing dates in 1970 or 2106.

### The 136-byte Payload
The context of the event is stored in a proprietary 136-byte C-struct. Through forensic diffing and pattern analysis, we have mapped the following offsets:

*   **Users:** Almost exclusively located in the first 16 bytes: `payload[0:16]` (Null-terminated Latin-1 string).
*   **IP Addresses (Network/Remote Events):** Always located at `payload[16:20]` as a 4-byte sequence.
*   **Camera/Alarm Channels (Major 1 - Alarms / Major 2 - Exceptions):** Mapped at the very beginning of the payload: `payload[0:4]` (32-bit LE int).
*   **Camera Channels (Major 3 - Operations / Major 4 - Info):** Mapped deeper in the payload: `payload[0x50:0x54]` (Byte 80). E.g., Video Exports, Playbacks, and Recordings.

## 3. Generic Aggressive Inference
Because the SDK defines over 2,100 events, it is impossible to manually map every single one. Our engine uses an **Aggressive Inference** algorithm:
For any unknown SDK event, the parser automatically checks `0x10` for a valid IP, and `0x00`/`0x50` for a valid channel (1-64). If found, it automatically decodes and appends them to the log entry, providing context for previously "opaque" events.

## 4. E01 vs UFS Explorer Validation
In our validation tests against a 465GB EnCase (`.E01`) image, we confirmed that our direct-offset carving is surgically accurate:
*   Reading bytes from `64,041,472` to `80,043,520` directly via `libewf` on the E01 image yielded a **100% byte-for-byte match** against `logCurFile.bin` (which was logically extracted by UFS Explorer Pro).
*   Both the UFS extract and our native raw read produced exactly **12,361 records**.
*   The current real-image validation recovered 12,361 records from the declared region and 44,585 additional records from the residual region (56,946 unique records total).
*   `HIKVISION2.E01` independently validated the same filesystem/version parser and produced 86 records from its declared ring-buffer.

## 5. Current Implementation

The maintained implementation is `scripts/engine_hikvision.py`.
`scripts/forensic_engine.py` exists only as a compatibility facade for older
imports. SQLite carving follows the regions returned by
`detect_image_structure()` and deduplicates records by physical offset.
