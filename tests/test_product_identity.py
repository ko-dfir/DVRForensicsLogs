import re
import subprocess
from pathlib import Path

import scripts.logging_config as logging_config
import scripts.recents as recents
from scripts.versioning import version_info

ROOT = Path(__file__).resolve().parent.parent
OLD_NAMES = re.compile(r'Universal ?DVR|DVR ?Forensics ?Logs|DVRForensic(?:Viewer|sLogs)|dvr_forensics|dvr-forensics|DVR_BUILD|DVRBuild', re.IGNORECASE)


def test_product_name_and_per_user_folders():
    assert version_info()['product_name'] == 'CCTV Log Analyzer'
    assert logging_config.APP_NAME == 'CCTVLogAnalyzer'
    assert recents.APP_DIR_NAME == 'CCTVLogAnalyzer'


def test_installer_and_build_use_the_product_name():
    script = (ROOT / 'installer' / 'CCTVLogAnalyzer.iss').read_text(encoding='utf-8')
    assert '#define MyAppExeName "CCTVLogAnalyzer.exe"' in script
    assert 'OutputBaseFilename=CCTVLogAnalyzer-{#MyAppVersion}-Setup' in script
    assert 'Source: "..\\dist\\cctv_log_analyzer.dist\\*"' in script
    assert '{localappdata}\\CCTVLogAnalyzer' in script
    build = (ROOT / 'build.bat').read_text(encoding='utf-8')
    assert '--output-filename=CCTVLogAnalyzer.exe' in build
    assert 'installer\\CCTVLogAnalyzer.iss' in build


def test_no_earlier_product_names_remain_in_tracked_files():
    files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()
    offenders = []
    for name in files:
        path = ROOT / name
        if path.suffix.lower() in ('.png', '.ico', '.dll') or not path.is_file():
            continue
        if name == 'tests/test_product_identity.py':
            continue
        if OLD_NAMES.search(name) or OLD_NAMES.search(path.read_text(encoding='utf-8', errors='ignore')):
            offenders.append(name)
    assert offenders == []
