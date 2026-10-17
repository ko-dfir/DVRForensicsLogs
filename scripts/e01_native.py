import os

try:
    import pyewf
    E01_SUPPORT = True
except ImportError:
    E01_SUPPORT = False
    pyewf = None

class E01File:
    _CACHE_BLOCK = 64 * 1024
    _CACHE_READ_LIMIT = 16 * 1024

    def __init__(self, filename):
        # QFileDialog returns forward slashes on Windows. libewf may prepend
        # the extended-path prefix to that value, producing invalid \\?\Z:/...
        # paths for mapped drives. Normalize before handing paths to libewf.
        filename = os.path.normpath(os.path.abspath(os.fspath(filename)))
        self.filename = filename
        if not E01_SUPPORT:
            raise ImportError("pyewf is missing from this environment. Cannot open E01 files.")
        self.handle = pyewf.handle()
        
        # Check if file exists
        if not os.path.exists(filename):
            raise FileNotFoundError(f"File not found: {filename}")
            
        # Try to open the file and any segments automatically
        base, ext = os.path.splitext(filename)
        segment_files = []
        
        # We assume standard E01, E02, E03 naming convention
        # Check up to E99 just in case
        for i in range(1, 100):
            seg_ext = f".E{i:02d}"
            seg_file = base + seg_ext
            if os.path.exists(seg_file):
                segment_files.append(seg_file)
            else:
                break
                
        if not segment_files:
            # Maybe the extension is exactly .e01 or .E01
            segment_files = [filename]
            
        self.handle.open(segment_files)
        self.size = self.handle.get_media_size()
        self.pos = 0
        self._cache_offset = -1
        self._cache_data = b""

    def read(self, size=-1):
        if size == -1:
            size = self.size - self.pos
        size = min(max(0, int(size)), self.size - self.pos)
        if not size:
            return b""
        # XFS parsers issue many small, nearby random reads. Reuse one aligned
        # libewf block instead of crossing the Python/native boundary for each.
        if size <= self._CACHE_READ_LIMIT:
            parts = []
            remaining = size
            while remaining:
                block_offset = self.pos // self._CACHE_BLOCK * self._CACHE_BLOCK
                if block_offset != self._cache_offset:
                    block_size = min(self._CACHE_BLOCK, self.size - block_offset)
                    self._cache_data = self.handle.read_buffer_at_offset(
                        block_size, block_offset)
                    self._cache_offset = block_offset
                inside = self.pos - block_offset
                part = self._cache_data[inside:inside + remaining]
                if not part:
                    break
                parts.append(part)
                self.pos += len(part)
                remaining -= len(part)
            return b"".join(parts)
        # Large sequential scans bypass the cache to avoid unnecessary copies.
        data = self.handle.read_buffer_at_offset(size, self.pos)
        if data:
            self.pos += len(data)
        return data

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        
        if self.pos < 0:
            self.pos = 0
        elif self.pos > self.size:
            self.pos = self.size
        # read_buffer_at_offset is position-independent; no native seek needed.
        return self.pos

    def tell(self):
        return self.pos

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def get_e01_size(filename):
    if not E01_SUPPORT:
        return os.path.getsize(filename)
    with E01File(filename) as f:
        return f.size
