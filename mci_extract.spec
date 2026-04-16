# mci_extract.spec
# Build with:
#   pyinstaller --clean mci_extract.spec

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

SRC = Path("src/mci")

# Collect all dynamic imports/data for Typer stack
typer_datas, typer_binaries, typer_hidden = collect_all("typer")
click_datas, click_binaries, click_hidden = collect_all("click")
rich_datas, rich_binaries, rich_hidden = collect_all("rich")

a = Analysis(
    [str(SRC / "cli.py")],
    pathex=["src"],  # ensures "mci" package is discoverable
    binaries=typer_binaries + click_binaries + rich_binaries,
    datas=[
        (str(SRC / "mideu.yml"), "mci"),
    ] + typer_datas + click_datas + rich_datas,
    hiddenimports=typer_hidden + click_hidden + rich_hidden + [
        "mci",
        "mci.cli",
        "mci.parser",
        "mci.export",
        "yaml",
        "difflib",
        "importlib",
        "importlib.metadata",
        "pkgutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
        "pydoc",
        "doctest",
        "ftplib",
        "getpass",
        "imaplib",
        "mailbox",
        "mimetypes",
        "smtplib",
        "poplib",
        "antigravity",
        "_bootsubprocess",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="extractmc",
    version="version.txt",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="mci-extract",
)