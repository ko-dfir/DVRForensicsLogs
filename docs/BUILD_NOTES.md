# Compiled build notes

## Startup crash in Nuitka builds

An earlier standalone build (Nuitka 4.3, PySide6 6.11.2/6.12.0) compiled
successfully but terminated with an access violation while the main window was
being constructed. The fault occurred in `ColumnFilterHeader.__init__` while
connecting a second lambda to a header signal. Running the same code from source
worked, and a minimal standalone header also worked, so the failure depended on
the compiled signal connections made by the full main window.

Qt recommends declaring QObject slots with
[`@Slot`](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html).
The Nuitka project has historical signal-connection/caching reports, including
[#3362](https://github.com/Nuitka/Nuitka/issues/3362); that issue is context, not
confirmation of the same bug.

## Changes

- All Qt-connected lambdas in the PySide6 UI were replaced with bound methods:
  header geometry/debounce, main table scrolling/row resizing, entropy and
  investigation pagination, report field presets and type checkboxes.
- The adapters declare concrete `@Slot` signatures. Header return/timeout events
  call an explicit emitter, which also stops a pending debounce timer.
- `tests/test_compiled_startup_safety.py` fails if a connected lambda is
  reintroduced.
- PySide6/shiboken6 are pinned to 6.11.2, the runtime dependency snapshot is
  locked, and Nuitka is pinned to 4.2.2.
- Native-fault traces are written to `%LOCALAPPDATA%\CCTVLogAnalyzer\logs\native-crash.log`
  through a persistent file descriptor. Native faults bypass Python exception
  handlers, so an empty `error.log` does not rule out a crash.
- The display version stays `1.01`; the explicit four-part `windows_version`
  (`1.1.0.0`) is passed to Nuitka and Inno Setup, because Windows numeric version
  fields cannot retain the leading zero in `01`.

With these changes, both the console (diagnostic) and windowed builds start and
open the main window.

## Building

Keep the source and the build virtual environment in short paths; PySide6
contains deep package paths that exceed the Windows 260-character limit inside
nested folders. The build venv defaults to `%LOCALAPPDATA%\CCTVBuild\venv`.

```powershell
$env:CCTV_BUILD_VENV = 'C:\cctvbuild\venv'  # optional override
$env:CCTV_BUILD_DIAGNOSTIC = '1'            # optional: visible console
.\build.bat --exe-only                     # executable only, no installer
```

`build.bat` without `--exe-only` also builds the installer and requires Inno
Setup. The executable is written to `dist/cctv_log_analyzer.dist/CCTVLogAnalyzer.exe`.

Compilation success alone is not runtime validation. Launch the newly generated
executable, confirm the main window opens, then exercise column resize/move/scroll,
filter debounce, report preset/type buttons and both pagination controls. Do not
mix Qt DLLs from an older build into a fresh standalone directory.

If a build fails at runtime, keep `app.log`, `error.log`, `native-crash.log`, the
timestamped build log, `build-logs/nuitka-report.xml` and the exact package
versions. To compare Nuitka versions, change only the Nuitka pin in a separate
short-path venv.
