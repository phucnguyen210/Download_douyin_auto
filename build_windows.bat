@echo off
REM Build a single-file GUI executable with PyInstaller (Windows)
REM Requires: pip install pyinstaller

pyinstaller --onefile --name douyin_downloader_gui run_gui.py --add-data "app;app" --noconsole

echo Build finished. See the `dist` directory.
pause