"""Compatibility facade for the consolidated Hikvision forensic engine.

Older viewers and tests import ``scripts.forensic_engine``.  The maintained
implementation now lives in ``engine_hikvision``; re-exporting it here keeps a
single implementation while preserving those public imports.
"""

from .engine_hikvision import *  # noqa: F401,F403
