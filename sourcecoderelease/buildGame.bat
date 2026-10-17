@echo off
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Dodge The Blocks" --icon "C:\path\to\icon" --distpath "C:\path\to\output\folder" dodgetheblocks.py
pause
