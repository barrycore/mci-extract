[Setup]
AppName=MCI Extract
AppVersion=1.0.0
DefaultDirName={pf}\MCIExtract
DefaultGroupName=MCI Extract
OutputDir=output
OutputBaseFilename=extractmc-setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\mci-extract\*"; DestDir: "{app}"; Flags: recursesubdirs
Source: "..\config.json"; DestDir: "{app}"

[Icons]
Name: "{group}\MCI Extract"; Filename: "{app}\extractmc.exe"

[Run]
Filename: "{app}\extractmc.exe"; Description: "Launch MCI Extract"; Flags: nowait postinstall skipifsilent