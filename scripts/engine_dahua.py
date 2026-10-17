import struct
import re
import os
import json
import traceback
from contextlib import closing
from scripts.cancellation import check_cancelled, ExtractionCancelled
from scripts.image_io import open_image

# Optionally import dissect.xfs. If not available, fallback is graceful.
try:
    from dissect.xfs import xfs
    DISSECT_XFS_AVAILABLE = True
except ImportError:
    DISSECT_XFS_AVAILABLE = False

class OffsetFile:
    """Wrapper to map an E01 file to a specific partition offset for dissect.xfs"""
    def __init__(self, fh, offset):
        self.fh = fh
        self.offset = offset
        media_size = getattr(fh, "size", None)
        if media_size is None:
            here = fh.tell()
            fh.seek(0, os.SEEK_END)
            media_size = fh.tell()
            fh.seek(here)
        self.size = media_size - offset
        self.pos = 0
        self.fh.seek(self.offset)
    def read(self, size=-1):
        if size < 0:
            # A filesystem parser should use bounded random reads. Never let
            # an accidental read() allocate the remaining multi-GB partition.
            size = min(16 * 1024 * 1024, self.size - self.pos)
        else:
            size = min(size, 16 * 1024 * 1024)
        size = min(size, self.size - self.pos)
        data = self.fh.read(size)
        self.pos += len(data)
        return data
    def seek(self, offset, whence=0):
        if whence == 0: self.pos = offset
        elif whence == 1: self.pos += offset
        elif whence == 2: self.pos = self.size + offset
        self.pos = max(0, min(self.pos, self.size))
        self.fh.seek(self.offset + self.pos)
        return self.pos
    def tell(self): 
        return self.pos

class DahuaEngine:
    def __init__(self, image_path):
        self.image_path = image_path
        self.is_e01 = image_path.lower().endswith('.e01')

    def _open_image(self):
        return open_image(self.image_path)

    @staticmethod
    def _walk_regular_files(root, max_entries=50000, max_depth=16, cancelled=None):
        """Yield every regular XFS file recursively with bounded traversal."""
        stack = [("", root, 0)]
        visited = 0
        while stack:
            check_cancelled(cancelled)
            parent, directory, depth = stack.pop()
            if depth > max_depth:
                continue
            try:
                children = directory.dirlist().items()
            except Exception:
                continue
            for name, inode in children:
                check_cancelled(cancelled)
                if name in ('.', '..'):
                    continue
                visited += 1
                if visited > max_entries:
                    raise RuntimeError(
                        f"Dahua XFS traversal exceeded {max_entries:,} entries.")
                relative = os.path.join(parent, str(name)) if parent else str(name)
                if inode.filetype == 0x8000:
                    yield relative, inode
                elif inode.filetype == 0x4000:
                    stack.append((relative, inode, depth + 1))

    def detect_partitions(self, image_handle=None, cancelled=None):
        f = image_handle or self._open_image()
        owns_handle = image_handle is None
        partitions = []
        try:
            check_cancelled(cancelled)
            f.seek(512)
            gpt_header = f.read(512)
            if gpt_header[:8] != b'EFI PART':
                return partitions

            part_entry_lba = struct.unpack('<Q', gpt_header[72:80])[0]
            num_entries = struct.unpack('<I', gpt_header[80:84])[0]
            entry_size = struct.unpack('<I', gpt_header[84:88])[0]

            f.seek(part_entry_lba * 512)
            entries_data = f.read(num_entries * entry_size)

            for i in range(num_entries):
                check_cancelled(cancelled)
                entry = entries_data[i*entry_size : (i+1)*entry_size]
                if entry[0:16] == b'\x00'*16: continue

                first_lba = struct.unpack('<Q', entry[32:40])[0]
                last_lba = struct.unpack('<Q', entry[40:48])[0]
                name = entry[56:].decode('utf-16le', 'ignore').rstrip('\x00')
                size_bytes = (last_lba - first_lba + 1) * 512
                
                part_info = {
                    "name": name,
                    "start_lba": first_lba,
                    "size_bytes": size_bytes,
                    "is_target": ('msft' in name.lower() or 'linux' in name.lower())
                }
                
                if part_info['is_target']:
                    f.seek(first_lba * 512)
                    if f.read(4) == b'XFSB':
                        part_info['fs'] = 'XFS'
                    else:
                        part_info['fs'] = 'Unknown'
                        
                partitions.append(part_info)
        finally:
            if owns_handle:
                f.close()
        return partitions

    def extract_xfs_native(self, start_offset, out_dir, progress_callback=None,
                           image_handle=None, status_callback=None, cancelled=None):
        """Uses dissect.xfs to extract the original physical files directly from the XFS partition"""
        if not DISSECT_XFS_AVAILABLE:
            raise Exception("dissect.xfs library is required for physical extraction. Install it via 'pip install dissect.xfs'")
            
        print(f"[*] Mounting XFS Partition at offset {start_offset}...")
        f = image_handle or self._open_image()
        owns_handle = image_handle is None
        extracted_files = []
        try:
            check_cancelled(cancelled)
            if status_callback:
                status_callback("Mounting the Dahua XFS filesystem", True)
            xfs_fh = OffsetFile(f, start_offset)
            fs = xfs.XFS(xfs_fh)
            root = fs.get('/')
            
            os.makedirs(out_dir, exist_ok=True)
            if status_callback:
                status_callback("Indexing the XFS directory tree", True)
            regular_entries = list(self._walk_regular_files(root, cancelled=cancelled))
            # Only database/log artefacts belong in a log carving operation.
            # Extracting every XFS root file can copy video/media data and
            # saturate a VM's RAM, disk and network-backed evidence storage.
            database_extensions = ('.db', '.sqlite', '.sqlite3', '.db3')
            entries = [
                (name, inode) for name, inode in regular_entries
                if name.lower().endswith(database_extensions)
            ]
            if not entries:
                raise RuntimeError(
                    "No Dahua database/log files were found in the XFS root.")
            total_bytes = max(1, sum(inode.size for _, inode in entries))
            if status_callback:
                status_callback(
                    f"Found {len(entries)} database files; starting byte-level extraction", False)
            completed_bytes = 0
            for entry_name, inode in entries:
                check_cancelled(cancelled)
                safe_parts = [part for part in entry_name.replace('\\', '/').split('/')
                              if part not in ('', '.', '..')]
                out_path = os.path.join(out_dir, "Dahua_Databases", *safe_parts)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                print(f"[*] Extracting: {entry_name} (Size: {inode.size} bytes)")
                
                with closing(inode.open()) as source, open(out_path + '.partial', 'wb') as out_f:
                    while True:
                        check_cancelled(cancelled)
                        block = source.read(4 * 1024 * 1024)
                        if not block:
                            break
                        out_f.write(block)
                        completed_bytes += len(block)
                        if progress_callback:
                            progress_callback(
                                completed_bytes, total_bytes, entry_name)
                
                check_cancelled(cancelled)
                os.replace(out_path + '.partial', out_path)
                extracted_files.append(out_path)
        except ExtractionCancelled:
            raise
        except Exception as e:
            traceback.print_exc()
            raise RuntimeError(f"Error parsing Dahua XFS: {e}") from e
        finally:
            if owns_handle:
                f.close()
            
        return extracted_files
