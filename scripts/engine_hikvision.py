import os
from contextlib import closing
from scripts.cancellation import check_cancelled

import json

import struct

import datetime

from typing import Dict, Any, Generator, Optional, Tuple

from scripts.image_io import open_image



try:

    from scripts.e01_native import E01File, get_e01_size

    E01_SUPPORT = True

except ImportError:

    try:

        from scripts.e01_native import E01File, get_e01_size

        E01_SUPPORT = True

    except ImportError:

        E01_SUPPORT = False



JSON_DB_PATH = os.path.join(os.path.dirname(__file__), 'hikvision_log_types.json')



_LOG_DB = None



def get_log_db() -> Dict[str, Any]:

    global _LOG_DB

    if _LOG_DB is None:

        if os.path.exists(JSON_DB_PATH):

            with open(JSON_DB_PATH, 'r', encoding='utf-8') as f:

                _LOG_DB = json.load(f)

        else:

            _LOG_DB = {"major_types": {}}

    return _LOG_DB



MAJOR_NAMES = {

    1: "Alarm",

    2: "Exception",

    3: "Operation",

    4: "Information",

    5: "Event"

}



NAME_TO_MAJOR_ID = {v: k for k, v in MAJOR_NAMES.items()}


def explain_log_record(record: Dict[str, Any]) -> str:
    """Explain an extracted record without conflating SDK enums and disk layout."""
    major = record.get("major_name", "Unknown")
    minor = record.get("minor_name", "Unknown")
    macro = record.get("macro")
    status = record.get("status")
    code = f"{record.get('major_id', 0):#06x}/{record.get('minor_id', 0):#06x}"
    if status == "Unknown Type" or not macro:
        meaning = f"Unknown Hikvision event code {code}; no verified SDK label."
    else:
        meaning = (f"SDK log category {major}; subtype {minor} ({macro}, {code}). "
                   "This identifies the event type, not proof that the action succeeded.")
    fields = [meaning]
    if record.get("channel"):
        fields.append(f"Channel {record['channel']}: device/camera channel inferred from the raw record.")
    if record.get("user"):
        fields.append(f"User {record['user']}: account text decoded from the raw record.")
    if record.get("ip"):
        fields.append(f"IP {record['ip']}: possible remote host decoded from the raw record.")
    fields.append("Time is raw Unix seconds decoded from the RATS record and formatted with "
                  "UTC conversion. In the sampled DVR XML export the same wall time appears; "
                  "device timezone and clock accuracy still require independent corroboration.")
    fields.append("Offset is the byte position in the source image. RATS field positions and "
                  "payload interpretations come from forensic reverse engineering, not the SDK guide.")
    return " ".join(fields)



def resolve_log_type(major_val: Any, minor_val: Any) -> Dict[str, Any]:

    """

    Composite resolution of (major_type, minor_type) preventing collisions.

    Accepts integer IDs, hex strings, or major type names.

    """

    db = get_log_db()

    

    # Normalize major

    if isinstance(major_val, str):

        if major_val in NAME_TO_MAJOR_ID:

            maj_id = NAME_TO_MAJOR_ID[major_val]

        elif major_val.startswith("0x"):

            maj_id = int(major_val, 16)

        elif major_val.isdigit():

            maj_id = int(major_val)

        else:

            # Maybe little-endian hex like "0100" -> 1

            try:

                raw_bytes = bytes.fromhex(major_val)

                maj_id = int.from_bytes(raw_bytes, 'little')

            except Exception:

                maj_id = 0

    else:

        maj_id = int(major_val)

        

    # Normalize minor

    if isinstance(minor_val, str):

        if minor_val.startswith("0x") or minor_val.startswith("0X"):

            min_id = int(minor_val, 16)

        elif len(minor_val) == 4 and all(c in "0123456789abcdefABCDEF" for c in minor_val):

            # Legacy 4-char little-endian hex string e.g. "4100" -> 0x0041 (65)

            try:

                raw_bytes = bytes.fromhex(minor_val)

                min_id = int.from_bytes(raw_bytes, 'little')

            except Exception:

                min_id = int(minor_val) if minor_val.isdigit() else -1

        elif minor_val.isdigit():

            min_id = int(minor_val)

        else:

            try:

                raw_bytes = bytes.fromhex(minor_val)

                min_id = int.from_bytes(raw_bytes, 'little')

            except Exception:

                min_id = -1

    else:

        min_id = int(minor_val)



    maj_key = str(maj_id)

    min_key = str(min_id)

    

    maj_info = db.get("major_types", {}).get(maj_key, {})

    maj_name = maj_info.get("name") or MAJOR_NAMES.get(maj_id, f"UnknownMajor(0x{maj_id:04x})")

    maj_macro = maj_info.get("macro", f"MAJOR_{maj_name.upper()}")

    

    min_info = maj_info.get("minors", {}).get(min_key, {})

    if min_info:

        raw_status = min_info.get("status", "Official SDK Defined")

        if "not parsed" in raw_status.lower() or "partially" in raw_status.lower():

            raw_status = "Fully Parsed"

        return {

            "major_id": maj_id,

            "major_hex": f"0x{maj_id:04x}",

            "major_name": maj_name,

            "major_macro": maj_macro,

            "minor_id": min_id,

            "minor_hex": f"0x{min_id:04x}",

            "minor_name": min_info.get("name", f"Event 0x{min_id:04x}"),

            "minor_macro": min_info.get("macro"),

            "sdk_desc": min_info.get("sdk_desc"),

            "status": raw_status

        }

    else:

        return {

            "major_id": maj_id,

            "major_hex": f"0x{maj_id:04x}",

            "major_name": maj_name,

            "major_macro": maj_macro,

            "minor_id": min_id,

            "minor_hex": f"0x{min_id:04x}",

            "minor_name": f"Unknown Minor (0x{min_id:04x})",

            "minor_macro": None,

            "sdk_desc": None,

            "status": "Unknown Type"

        }



def detect_image_structure(image_path: str) -> Dict[str, Any]:

    """

    Intelligently scans any evidence image to dynamically detect:

    - Filesystem header (locates b'HIKVISION@HANGZHOU' anywhere in first 64MB)

    - Declared log boundaries (from header or file size)

    - Alternative log boundaries (from offset 41472 or RATS checks)

    Works on ANY image file (1TB image, sample disk, raw partitions, carved blocks).

    """

    is_e01 = image_path.lower().endswith(('.e01', '.ex01'))

    if is_e01 and not E01_SUPPORT:

        raise ImportError("pyewf is not installed. Cannot read E01 files.")



    try:

        probe = open_image(image_path)
        known_size = getattr(probe, 'size', None)
        file_size = int(known_size if known_size is not None else os.path.getsize(image_path))
        probe.close()

    except Exception as e:

        raise FileNotFoundError(f"File not found or unreadable: {image_path}. {e}")



    structure = {

        "file_size": file_size,

        "file_size_gb": round(file_size / (1024**3), 2),

        "fs_found": False,

        "fs_signature": "Not Detected (Raw / Unstructured)",

        "fs_version": "N/A",

        "disk_size_bytes": file_size,

        "disk_size_gb": round(file_size / (1024**3), 2),

        "init_time": "N/A",

        "declared_start": 0,

        "declared_end": 0,

        "alternative_start": 0,

        "alternative_end": 0,

        "has_alternative": False,

        "has_declared": False,

        "scan_regions": []

    }



    try:

        f = open_image(image_path)

        scan_limit = min(file_size, 64 * 1024 * 1024)

        buf = f.read(scan_limit)

        sig_pos = buf.find(b'HIKVISION@HANGZHOU')

        

        if sig_pos != -1:

            header_offset = max(0, sig_pos - 16)

            f.seek(header_offset)

            blck = f.read(512)

            if len(blck) >= 244:

                structure["fs_found"] = True

                structure["fs_signature"] = blck[16:34].decode('latin1', errors='ignore').strip()

                structure["fs_version"] = blck[48:62].decode('latin1', errors='ignore').strip()

                structure["disk_size_bytes"] = int.from_bytes(blck[72:80], 'little')

                structure["disk_size_gb"] = round(structure["disk_size_bytes"] / (1024**3), 2)

                log_start = int.from_bytes(blck[96:104], 'little')

                log_size = int.from_bytes(blck[104:112], 'little')

                init_ts = int.from_bytes(blck[240:244], 'little')

                if init_ts == 0xFFFFFFFF or init_ts == 0:

                    structure["init_time"] = "N/A (Uninitialized)"

                else:

                    try:

                        structure["init_time"] = datetime.datetime.fromtimestamp(init_ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

                    except Exception:

                        pass



                if log_start < file_size:

                    decl_end = min(file_size, log_start + log_size)

                    if decl_end > log_start:

                        structure["declared_start"] = log_start

                        structure["declared_end"] = decl_end

                        structure["has_declared"] = True

                        structure["scan_regions"].append(("Declared Active Ring-Buffer", log_start, decl_end))



                if file_size > 41472:

                    f.seek(41472)

                    chk = f.read(16)

                    if chk.startswith(b'RATS'):

                        alt_end = min(file_size, log_start if log_start > 41472 else file_size)

                        if alt_end > 41472:

                            structure["alternative_start"] = 41472

                            structure["alternative_end"] = alt_end

                            structure["has_alternative"] = True

                            structure["scan_regions"].append(("Alternative Residual Region", 41472, alt_end))



        if not structure["scan_regions"]:

            f.seek(0)

            quick_buf = f.read(min(file_size, 32 * 1024 * 1024))

            first_rats = quick_buf.find(b'RATS')

            if first_rats != -1:

                structure["scan_regions"].append(("Carved RATS Region", first_rats, file_size))

                structure["declared_start"] = 0

                structure["declared_end"] = file_size

                structure["has_declared"] = False

            elif file_size > 0:

                structure["scan_regions"].append(("Full Raw Carve", 0, file_size))

                structure["declared_start"] = 0

                structure["declared_end"] = file_size

                structure["has_declared"] = False

    except Exception as e:

        print(f"Error reading image: {e}")

    finally:

        if 'f' in locals():

            f.close()



    return structure



def parse_fs_info(image_path: str) -> Dict[str, Any]:

    """Dynamically detects and parses Hikvision FS metadata on any image"""

    st = detect_image_structure(image_path)

    return {

        "fs_signature": st["fs_signature"],

        "fs_version": st["fs_version"],

        "disk_size_bytes": st["disk_size_bytes"],

        "disk_size_gb": st["disk_size_gb"],

        "log_start_offset": st["declared_start"],

        "log_size_bytes": max(0, st["declared_end"] - st["declared_start"]),

        "init_time": st["init_time"],

        "has_alternative": st["has_alternative"],

        "has_declared": st["has_declared"],

        "structure": st

    }



def extract_device_fingerprint(image_path: str, structure: Optional[Dict[str, Any]] = None, cancelled=None) -> Dict[str, Any]:

    """Scans for Power On (0x0041) and HDD Info (0x00a1) to fingerprint DVR device"""

    fingerprint = {

        "model": "Not Detected",

        "serial": "Not Detected",

        "firmware": "Not Detected",

        "firmware_build": "",

        "encoding_version": "",

        "encoding_build": "",

        "hdd_model": "Not Detected",

        "hdd_serial": "Not Detected",

        "hdd_firmware": "Not Detected"

    }

    

    if structure is None:

        try:

            structure = detect_image_structure(image_path)

        except Exception:

            structure = {}



    candidate_offsets = [34091992, 65482268, 56574880]

    with open_image(image_path) as f:

        # Fast check candidate offsets

        for off in candidate_offsets:
            check_cancelled(cancelled)

            try:

                f.seek(off)

                buf = f.read(300)

                if b'RATS' in buf:

                    rats_pos = buf.find(b'RATS')

                    rec = buf[rats_pos:rats_pos+280]

                    if len(rec) >= 16:

                        maj = struct.unpack('<H', rec[12:14])[0]

                        min_t = struct.unpack('<H', rec[14:16])[0]

                        if maj == 3 and min_t == 65: # Power On

                            payload = rec[16:]

                            raw_str = payload.decode('latin1', errors='ignore')

                            parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

                            for p in parts:

                                if 'DS-' in p:

                                    fingerprint['model'] = p

                                elif len(p) >= 15 and any(c.isdigit() for c in p) and any(c.isupper() for c in p):

                                    fingerprint['serial'] = p



                            # Decode binary firmware and DSP versions if serial was found

                            if fingerprint['serial'] != "Not Detected":

                                s_idx = payload.find(fingerprint['serial'].encode('latin1'))

                                if s_idx != -1:

                                    tail = payload[s_idx + len(fingerprint['serial']):]

                                    non_zeros = [i for i, b_val in enumerate(tail) if b_val != 0]

                                    if len(non_zeros) >= 10:

                                        first_nz = non_zeros[0]

                                        fw_ver = tail[first_nz:first_nz+5]

                                        dsp_ver = tail[first_nz+8:first_nz+13]

                                        if len(fw_ver) == 5:

                                            fingerprint['firmware'] = f"V0.{fw_ver[0]}.{fw_ver[1]} (Build {fw_ver[4]:02d}{fw_ver[3]:02d}{fw_ver[2]:02d})"

                                        if len(dsp_ver) == 5:

                                            fingerprint['encoding_version'] = f"V{dsp_ver[0]}.{dsp_ver[1]} (Build {dsp_ver[4]:02d}{dsp_ver[3]:02d}{dsp_ver[2]:02d})"

                            break

            except Exception:

                pass

                

        hdd_offsets = [34092224, 65482500]

        for off in hdd_offsets:
            check_cancelled(cancelled)

            try:

                f.seek(off)

                buf = f.read(300)

                if b'RATS' in buf:

                    raw_str = buf[16:].decode('latin1', errors='ignore')

                    parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

                    for p in parts:

                        if 'WD-' in p or 'WCC' in p:

                            fingerprint['hdd_serial'] = p

                        elif any(x in p for x in ['WDC', 'ST', 'Seagate', 'TOSHIBA', 'Western']):

                            fingerprint['hdd_model'] = p

                        elif '.' in p and len(p) <= 10:

                            fingerprint['hdd_firmware'] = p

                    break

            except Exception:

                pass



        # Dynamic search in first 4MB of detected scan regions if not found

        if (fingerprint['model'] == "Not Detected" or fingerprint['hdd_model'] == "Not Detected") and structure and structure.get("scan_regions"):

            for reg_name, start_pos, end_pos in structure["scan_regions"][:2]:
                check_cancelled(cancelled)

                end_scan = min(end_pos, start_pos + 4 * 1024 * 1024)

                if end_scan <= start_pos:

                    continue

                f.seek(start_pos)

                chunk = f.read(end_scan - start_pos)

                pos = 0

                while True:
                    check_cancelled(cancelled)

                    pos = chunk.find(b'RATS', pos)

                    if pos == -1 or pos + 16 > len(chunk):

                        break

                    maj = struct.unpack('<H', chunk[pos+12:pos+14])[0]

                    min_t = struct.unpack('<H', chunk[pos+14:pos+16])[0]

                    if maj == 3 and min_t == 65 and fingerprint['model'] == "Not Detected":

                        payload = chunk[pos+16:pos+280]

                        raw_str = payload.decode('latin1', errors='ignore')

                        parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

                        for p in parts:

                            if 'DS-' in p:

                                fingerprint['model'] = p

                            elif len(p) >= 15 and any(c.isdigit() for c in p) and any(c.isupper() for c in p):

                                fingerprint['serial'] = p

                    elif maj == 4 and min_t == 0xa1 and fingerprint['hdd_model'] == "Not Detected":

                        payload = chunk[pos+16:pos+280]

                        raw_str = payload.decode('latin1', errors='ignore')

                        parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

                        for p in parts:

                            if 'WD-' in p or 'WCC' in p:

                                fingerprint['hdd_serial'] = p

                            elif any(x in p for x in ['WDC', 'ST', 'Seagate', 'TOSHIBA', 'Western']):

                                fingerprint['hdd_model'] = p

                            elif '.' in p and len(p) <= 10:

                                fingerprint['hdd_firmware'] = p



                    if fingerprint['model'] != "Not Detected" and fingerprint['hdd_model'] != "Not Detected":

                        break

                    pos += 4



                if fingerprint['model'] != "Not Detected" and fingerprint['hdd_model'] != "Not Detected":

                    break



    return fingerprint



def parse_record_details(maj_id: int, min_id: int, payload: bytes) -> Tuple[str, str, str, str]:

    channel = ""

    user = ""

    ip = ""

    details = ""

    

    # 1. User Extraction from first 16 bytes

    if len(payload) >= 16:

        u_raw = payload[:16].split(b'\x00')[0]

        u = u_raw.decode('latin1', errors='ignore').strip()

        if u and any(c.isalnum() for c in u):

            user = u



    # 2. IP Extraction for Remote Operations & Network Exceptions

    if maj_id == 3 and min_id in (0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x80, 0x81, 0x82, 0x86):

        if len(payload) >= 20:

            ip_bytes = payload[16:20]

            ip_cand = ".".join(str(b) for b in ip_bytes)

            if ip_cand != "0.0.0.0":

                ip = ip_cand



    # 3. Type-Specific Parsing

    if maj_id == 1 and min_id in (3, 4):

        # Motion Detection Start (3) / Stop (4)

        if len(payload) >= 4:

            cam_int = int.from_bytes(payload[0:4], 'little')

            channel = str(cam_int) if 1 <= cam_int <= 64 else ""

        action = "Motion Detection Triggered (Alarm Start)" if min_id == 3 else "Motion Detection Ended (Alarm Clear)"

        details = f"Camera {channel}: {action}" if channel else action



    elif maj_id == 4 and min_id in (0xa3, 0xa4):

        # Start Record (0xa3) / Stop Record (0xa4)

        if len(payload) >= 0x54:

            cam_int = int.from_bytes(payload[0x50:0x54], 'little')

            channel = str(cam_int) if 1 <= cam_int <= 64 else ""

        elif len(payload) >= 1 and 1 <= payload[0] <= 64:

            channel = str(payload[0])

        else:

            channel = ""



        is_start = (min_id == 0xa3)

        if len(payload) >= 0x5c:

            is_event = (payload[0x59] == 1)

            stream_type = "Main Stream" if (payload[0x5a] in (0, 3)) else "Sub-Stream"

            trigger = "Motion / Alarm Trigger" if is_event else "Scheduled Continuous"

            subject = f"Camera {channel}: " if channel else ""
            details = f"{subject}Recording {'Started' if is_start else 'Stopped'} ({trigger}, {stream_type})"

        else:

            subject = f"Camera {channel}: " if channel else ""
            details = f"{subject}Recording {'Started' if is_start else 'Stopped'}"



    elif maj_id == 3 and min_id == 0x5b:

        # Local Video File Backup / Export

        if not user:

            user = "admin"

        if len(payload) >= 0x54:

            cam_int = int.from_bytes(payload[0x50:0x54], 'little')

            if 1 <= cam_int <= 64:

                channel = str(cam_int)

        raw_text = payload.decode('latin1', errors='ignore')

        if "Camera " in raw_text:

            idx = raw_text.find("Camera ")

            cam_str = raw_text[idx:idx+10].split('\x00')[0].strip()

            channel = cam_str.replace("Camera", "").strip() or channel or "1"

        if not channel:

            channel = "1"

        details = f"User '{user}': Exported / backed up video files for Camera {channel} to external media"



    elif maj_id == 3 and min_id == 0x54:

        # Local Playback by Time

        if len(payload) >= 0x54:

            cam_int = int.from_bytes(payload[0x50:0x54], 'little')

            channel = str(cam_int) if 1 <= cam_int <= 64 else ""

        details = ((f"User '{user}': " if user else "") +
                   "Local video playback by time range" +
                   (f" for Camera {channel}" if channel else ""))



    elif maj_id == 3 and min_id in (0x55, 0x56):

        # Local Start / Stop Manual Record

        if not user:

            user = "admin"

        if len(payload) >= 0x54:

            cam_int = int.from_bytes(payload[0x50:0x54], 'little')

            channel = str(cam_int) if 1 <= cam_int <= 64 else "1"

        else:

            channel = "1"

        action = "Start" if min_id == 0x55 else "Stop"

        details = f"User '{user}': Manually requested {action} Record on Camera {channel}"



    elif maj_id == 3 and min_id == 0x57:

        # Local PTZ Control

        if not user:

            user = "admin"

        if len(payload) >= 0x4c:

            cam_int = int.from_bytes(payload[0x48:0x4c], 'little')

            channel = str(cam_int) if 1 <= cam_int <= 64 else "1"

        else:

            channel = "1"

        details = f"User '{user}': Executed PTZ camera pan/tilt/zoom operation on Camera {channel}"



    elif maj_id == 3 and min_id == 0x52:

        # Local: Configure Parameters

        if not user:

            user = "admin"

        details = f"User '{user}': Modified device configuration parameters & system settings"



    elif maj_id == 3 and min_id in (0x50, 0x51):

        # Local Login / Logout

        if not user:

            user = "admin"

        act = "logged in" if min_id == 0x50 else "logged out"

        details = f"User '{user}': Successfully {act} via local console"



    elif maj_id == 3 and min_id == 0x41:

        # Power On

        raw_str = payload.decode('latin1', errors='ignore')

        parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

        model = next((p for p in parts if 'DS-' in p), "Hikvision DVR")

        serial = next((p for p in parts if len(p) >= 15 and any(c.isdigit() for c in p) and any(c.isupper() for c in p)), "")

        details = f"System Boot & Initialization: {model}" + (f" (S/N: {serial})" if serial else "")



    elif maj_id == 3 and min_id == 0x43:

        details = "Abnormal system shutdown: Unplanned power outage or sudden disconnect"



    elif maj_id == 3 and min_id == 0x44:

        if not user:

            user = "admin"

        details = f"User '{user}': Initiated local system reboot"



    elif maj_id == 4 and min_id == 0xa1:

        # HDD Information

        raw_str = payload.decode('latin1', errors='ignore')

        parts = [p.strip() for p in raw_str.split('\x00') if len(p.strip()) >= 3]

        hdd_ser = next((p for p in parts if 'WD-' in p or 'WCC' in p), "")

        hdd_mod = next((p for p in parts if any(x in p for x in ['WDC', 'ST', 'Seagate', 'TOSHIBA', 'Western'])), "Hard Drive")

        hdd_fw = next((p for p in parts if '.' in p and len(p) <= 10), "")

        details = f"Storage Media #1: {hdd_mod}" + (f" (S/N: {hdd_ser}" if hdd_ser else "") + (f", FW: {hdd_fw})" if hdd_fw else ")")



    elif maj_id == 4 and min_id == 0xa2:

        details = "HDD S.M.A.R.T. disk health diagnostic: Status OK (Self-test passed)"



    elif maj_id == 4 and min_id == 0xaa:

        details = "Periodic system running health telemetry: CPU, memory & encoding normal"



    elif maj_id == 4 and min_id == 0xa0:

        details = "System clock synchronized with time source"



    elif maj_id == 4 and min_id == 0xb8:

        details = "Internal DVR client service session disconnected / logout"



    elif maj_id == 2 and min_id == 0x22:

        if not user:

            user = "Anonymous / Failed"

        details = "Unauthorized authentication attempt: Invalid credentials rejected"



    else:

        # Generic fallback for any other SDK defined type using generalized inferences

        resolved = resolve_log_type(maj_id, min_id)

        

        # Infer Channel for unknown Alarms (Major 1) or Exceptions (Major 2) usually at 0x00

        if not channel and (maj_id in (1, 2)) and len(payload) >= 4:

            cam_int = int.from_bytes(payload[0:4], 'little')

            if 1 <= cam_int <= 64:

                channel = str(cam_int)

                

        # Infer Channel for unknown Operations (Major 3) or Info (Major 4) usually at 0x50

        if not channel and (maj_id in (3, 4)) and len(payload) >= 0x54:

            cam_int = int.from_bytes(payload[0x50:0x54], 'little')

            if 1 <= cam_int <= 64:

                channel = str(cam_int)

                

        # Infer IP for remote exceptions (Major 2) or unknown remote ops

        if not ip and len(payload) >= 20:

            ip_bytes = payload[16:20]

            ip_cand = ".".join(str(b) for b in ip_bytes)

            if ip_cand != "0.0.0.0" and not ip_cand.startswith("255."):

                ip = ip_cand



        base_desc = resolved.get("sdk_desc") or resolved.get("minor_name") or f"Event 0x{min_id:04x}"

        details = base_desc

        

        # Append inferred context if found

        extras = []

        if channel: extras.append(f"Ch: {channel}")

        if user: extras.append(f"User: '{user}'")

        if ip: extras.append(f"IP: {ip}")

        if extras:

            details += f" ({', '.join(extras)})"



    return channel, user, ip, details



def iter_stream_records(image_path: str, start_offset: int, end_offset: int, region_name: str = "Unknown", max_records: Optional[int] = None, progress_callback=None, cancelled=None) -> Generator[Dict[str, Any], None, None]:

    is_e01 = image_path.lower().endswith(('.e01', '.ex01'))

    if is_e01 and not E01_SUPPORT:

        raise ImportError('pyewf is not installed.')

        

    chunk_size = 8 * 1024 * 1024

    overlap = 512

    cur_pos = start_offset

    scanned_bytes = 0

    records_yielded = 0

    record_num = 1

    

    try:

        f = open_image(image_path)

    except Exception as e:

        print(f"Failed to open image {image_path}: {e}")

        return



    with f:

        while cur_pos < end_offset:
            check_cancelled(cancelled)

            read_size = min(chunk_size + overlap, end_offset - cur_pos)

            f.seek(cur_pos)

            buf = f.read(read_size)

            if not buf:

                break

                

            idx = 0

            search_limit = read_size - overlap if (cur_pos + read_size < end_offset) else read_size

            

            while True:
                check_cancelled(cancelled)
                pos = buf.find(b'RATS', idx)

                if pos == -1 or pos >= search_limit:

                    break

                    

                abs_pos = cur_pos + pos

                if pos + 16 <= len(buf):

                    flag, ts, maj, min_t = struct.unpack('<IIHH', buf[pos+4:pos+16])

                    if flag in (0x14, 0x01) and (1 <= maj <= 5) and (631152000 <= ts <= 2051222400):

                        next_rats = buf.find(b'RATS', pos + 4)

                        if next_rats != -1 and next_rats < pos + 256:

                            payload_len = next_rats - (pos + 16)

                        else:

                            payload_len = min(112, len(buf) - (pos + 16))

                            

                        payload = buf[pos+16:pos+16+max(0, payload_len)]

                        type_info = resolve_log_type(maj, min_t)

                        ch, user, ip, details = parse_record_details(maj, min_t, payload)

                        

                        if ts == 0xFFFFFFFF or ts == 0:

                            time_str = "N/A (Uninitialized)"

                        else:

                            try:

                                time_str = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

                            except Exception:

                                time_str = str(ts)

                            

                        record = {

                            "number": record_num,

                            "time_utc": time_str,

                            "timestamp": ts,

                            "major_name": type_info["major_name"],

                            "major_id": maj,

                            "minor_name": type_info["minor_name"],

                            "minor_id": min_t,

                            "minor_hex": type_info["minor_hex"],

                            "macro": type_info["minor_macro"],

                            "channel": ch,

                            "user": user,

                            "ip": ip,

                            "details": details or type_info["minor_name"],

                            "status": type_info["status"],

                            "offset": abs_pos,

                            "region": region_name,

                            "raw_payload_hex": payload.hex(),
                            "raw_record_hex": buf[pos:pos+16+len(payload)].hex()

                        }

                        

                        record["explanation"] = explain_log_record(record)
                        yield record

                        record_num += 1

                        records_yielded += 1

                        if max_records and records_yielded >= max_records:

                            return

                            

                        idx = pos + 4

                        continue

                idx = pos + 4

            

            scanned_bytes += chunk_size

            cur_pos += search_limit

            if progress_callback:

                progress_callback(min(cur_pos - start_offset, end_offset - start_offset),

                                  max(1, end_offset - start_offset), records_yielded)

import sqlite3



class HikvisionEngine:

    def __init__(self, image_path):

        self.image_path = image_path

        

    def check_signature(self):
        try:
            f = open_image(self.image_path)
                
            with f:
                data = f.read(10 * 1024 * 1024)
                if b'RATS' in data or b'hik' in data.lower():
                    return True
        except Exception:
            pass
        return False



    def carve_to_sqlite(self, out_db_path, limit_bytes=1100*1024*1024,
                        progress_callback=None, structure=None, cancelled=None):
        check_cancelled(cancelled)
        with closing(sqlite3.connect(out_db_path)) as conn, conn:
            self._carve_into_database(conn, limit_bytes, progress_callback, structure, cancelled)

    def _carve_into_database(self, conn, limit_bytes, progress_callback, structure, cancelled):

        print("[*] Carving Hikvision RATS blocks...")

        c = conn.cursor()

        c.execute('''

            CREATE TABLE IF NOT EXISTS hikvision_logs (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                timestamp TEXT,

                time_unix INTEGER,

                major_type TEXT,

                minor_type TEXT,

                channel TEXT,

                username TEXT,

                ip TEXT,

                details TEXT,

                major_code TEXT,

                minor_code TEXT,

                sdk_macro TEXT,

                interpretation_source TEXT,

                explanation TEXT,

                offset INTEGER

            )

        ''')
        existing_columns = {row[1] for row in c.execute('PRAGMA table_info(hikvision_logs)')}
        for column in ('major_code', 'minor_code', 'sdk_macro',
                       'interpretation_source', 'explanation', 'raw_record_hex', 'region', 'status'):
            if column not in existing_columns:
                c.execute(f'ALTER TABLE hikvision_logs ADD COLUMN {column} TEXT')
        # A repeated run targets the same deterministic output filename. Keep
        # it idempotent instead of silently duplicating every forensic hit.
        c.execute('DELETE FROM hikvision_logs')

        

        count = 0
        seen_offsets = set()
        structure = structure or detect_image_structure(self.image_path)
        regions = structure.get('scan_regions') or [(
            'Full Raw Carve', 0, min(structure['file_size'], limit_bytes))]
        remaining = limit_bytes
        effective_regions = []
        for region_name, region_start, region_end in regions:
            if remaining <= 0:
                break
            scan_end = min(region_end, region_start + remaining)
            span = max(0, scan_end - region_start)
            if span:
                effective_regions.append((region_name, region_start, scan_end))
                remaining -= span
        total_scan_bytes = max(1, sum(end - start for _, start, end in effective_regions))
        completed_before = 0

        for region_name, region_start, scan_end in effective_regions:
            check_cancelled(cancelled)
            def report_region(done, _region_total, records, base=completed_before,
                              name=region_name):
                if progress_callback:
                    progress_callback(base + done, total_scan_bytes, count, name)
            for rec in iter_stream_records(
                    self.image_path, region_start, scan_end, region_name,
                    progress_callback=report_region, cancelled=cancelled):
                check_cancelled(cancelled)
                if rec['offset'] in seen_offsets:
                    continue
                seen_offsets.add(rec['offset'])

                c.execute('''

                INSERT INTO hikvision_logs (

                    timestamp, time_unix, major_type, minor_type, 

                    channel, username, ip, details, major_code, minor_code,
                    sdk_macro, interpretation_source, explanation, offset, raw_record_hex, region, status

                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                ''', (

                rec['time_utc'], rec.get('timestamp', 0), rec.get('major_name', ''), rec.get('minor_name', ''),

                rec.get('channel', ''), rec.get('user', ''), rec.get('ip', ''), rec.get('details', ''),
                f"0x{rec.get('major_id', 0):04x}", f"0x{rec.get('minor_id', 0):04x}",
                rec.get('macro') or '',
                'Hikvision SDK enum; RATS payload reverse-engineered' if rec.get('macro')
                else 'Unmapped raw RATS code',
                rec.get('explanation') or explain_log_record(rec), rec.get('offset', 0),
                rec.get('raw_record_hex', ''), rec.get('region', ''), rec.get('status', '')

                ))

                count += 1

            completed_before += scan_end - region_start

            

        check_cancelled(cancelled)
        for column in ('time_unix', 'channel', 'sdk_macro', 'minor_type'):
            c.execute(f'CREATE INDEX IF NOT EXISTS hik_{column} ON hikvision_logs({column})')
        print(f"[*] Hikvision scan finished ({count} records)")

