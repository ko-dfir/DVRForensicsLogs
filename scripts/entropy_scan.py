"""Bounded entropy profiling for locating structured DVR metadata regions."""

from collections import Counter
from math import log2


def shannon_entropy(data):
    if not data:
        return 0.0
    size = len(data)
    return -sum((count / size) * log2(count / size)
                for count in Counter(data).values())


def entropy_profile(handle, start, length, window_size=1024 * 1024,
                    progress_callback=None, cancelled=None):
    """Profile the requested range with optional progress and cancellation."""
    return list(iter_entropy_profile(handle, start, length, window_size,
                                     progress_callback, cancelled))


def iter_entropy_profile(handle, start, length, window_size=1024 * 1024,
                         progress_callback=None, cancelled=None):
    """Yield one window at a time so whole-image scans have bounded memory."""
    if start < 0 or length < 0 or window_size <= 0:
        raise ValueError('Invalid entropy scan range or window size')
    end = start + length
    offset = start
    while offset < end:
        if cancelled and cancelled():
            break
        handle.seek(offset)
        data = handle.read(min(window_size, end - offset))
        if not data:
            break
        counts = Counter(data)
        size = len(data)
        yield {
            "offset": offset,
            "size": len(data),
            "entropy": -sum((count / size) * log2(count / size) for count in counts.values()),
            "printable_ratio": sum(count for byte, count in counts.items()
                                   if 32 <= byte < 127 or byte in (9, 10, 13)) / size,
            "zero_ratio": counts.get(0, 0) / size,
        }
        offset += len(data)
        if progress_callback:
            progress_callback(offset - start, length)


def interpret_window(item):
    """Descriptive heuristics, not an identification of logs or encryption."""
    if item['zero_ratio'] >= 0.98:
        return 'Mostly zero bytes — little content in this window', False
    if item['printable_ratio'] >= 0.75:
        return 'Mostly readable text — inspect for configuration or metadata', True
    if item['entropy'] < 6.5:
        return 'Repetitive / structured bytes — candidate for manual inspection', True
    if item['entropy'] >= 7.5:
        return 'High byte diversity — possibly compressed video or encrypted data', False
    return 'Mixed binary content — entropy does not identify its purpose', False

