"""Emit validated build.bat variables; does not compile or install anything."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.versioning import get_version, windows_version_tuple


def build_variables():
    version = get_version()
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,3}(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Application version is not safe for a build filename.')
    return {'APP_VERSION': version,
            'WINDOWS_VERSION': '.'.join(map(str, windows_version_tuple()))}


if __name__ == '__main__':
    for key, value in build_variables().items():
        print(f'{key}={value}')
