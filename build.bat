@echo off

echo Cleaning old builds...
rmdir /s /q build
rmdir /s /q dist

echo Building EXE...
py -m PyInstaller --clean mci_extract.spec

echo Done!
pause