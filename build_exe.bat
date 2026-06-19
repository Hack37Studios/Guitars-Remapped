@echo off
REM Build the Python app into a Windows executable using PyInstaller
python -m pip install -r requirements.txt
python -m pip install -r dev-requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name GuitarMapper main.py
if %ERRORLEVEL% equ 0 (
    echo Build complete.
    echo The executable is in the dist folder.
) else (
    echo Build failed with exit code %ERRORLEVEL%.
)
