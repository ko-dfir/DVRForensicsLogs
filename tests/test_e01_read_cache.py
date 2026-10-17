import os
from types import SimpleNamespace

from scripts import e01_native


def test_small_e01_reads_reuse_native_block_and_preserve_seek_semantics(tmp_path, monkeypatch):
    payload = bytes(range(256)) * 512
    image = tmp_path / "sample.E01"
    image.write_bytes(b"placeholder")
    handles = []

    class FakeHandle:
        def __init__(self):
            self.calls = []
            handles.append(self)

        def open(self, paths):
            assert paths == [str(image)]

        def get_media_size(self):
            return len(payload)

        def read_buffer_at_offset(self, size, offset):
            self.calls.append((size, offset))
            return payload[offset:offset + size]

        def close(self):
            pass

    monkeypatch.setattr(e01_native, "pyewf", SimpleNamespace(handle=FakeHandle))
    monkeypatch.setattr(e01_native, "E01_SUPPORT", True)
    with e01_native.E01File(str(image)) as stream:
        assert stream.read(4096) == payload[:4096]
        stream.seek(1024)
        assert stream.read(4096) == payload[1024:5120]
        assert handles[0].calls == [(65536, 0)]
        stream.seek(65520)
        assert stream.read(64) == payload[65520:65584]
        assert handles[0].calls[-1] == (65536, 65536)
        stream.seek(-16, os.SEEK_END)
        assert stream.read(100) == payload[-16:]
        stream.seek(100)
        assert stream.read(32768) == payload[100:32868]
        assert handles[0].calls[-1] == (32768, 100)
