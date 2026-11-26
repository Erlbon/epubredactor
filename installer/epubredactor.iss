#if 0
; The Windows installer of The ƎPUB Redactor (Inno Setup 6): the one-folder build (dist\epubredactor\, built with
; EPUBREDACTOR_BUILD=folder; it starts faster than the one-file exe, which unpacks itself at every start) into the
; user's own programs folder, with a Start menu entry. The one-file dist\epubredactor.exe stays the portable download.
;
; Build:   build_exe.bat (it builds both programs and passes /DUpdateContract), or by hand:
;          iscc /DAppBuild=2026-11-26#02 /DUpdateContract=<python -m redactor_common.release contract-path> installer\epubredactor.iss
; Output:  dist\epubredactor-setup.exe
;
; Per user, no administrator rights: %LOCALAPPDATA%\Programs\The EPUB Redactor. Updating goes through the family's
; update framework (redactor_common docs/update-framework.md): its installer contract, included at the END of this
; file, writes {app}\update-channel = windows-installer, so Help > Check for Updates runs the new
; epubredactor-setup.exe the release's update-manifest.json names, silently with /relaunch=yes, and the contract
; starts the program again. The settings, crash log and logs sit beside the exe (the Redactor apps' convention):
; an update leaves them, and so does the uninstall.
;
; These notes sit in "#if 0", as in the shared contract.
#endif

#ifndef AppBuild
  #define AppBuild "0000-00-00#00"
#endif
#ifndef UpdateContract
  #error Pass /DUpdateContract (build_exe.bat does: python -m redactor_common.release contract-path)
#endif

; For the installer contract included at the end. The program has no --quit: Windows' close request ends it.
#define UpdateExe "epubredactor.exe"

[Setup]
AppId={{892C52FC-3E80-4C27-ABED-606097F056EB}
AppName=The ƎPUB Redactor
AppVersion={#AppBuild}
AppVerName=The ƎPUB Redactor {#AppBuild}
AppPublisher=Erlbon
AppPublisherURL=https://github.com/Erlbon/epubredactor
AppSupportURL=https://github.com/Erlbon/epubredactor/issues
AppUpdatesURL=https://github.com/Erlbon/epubredactor/releases
VersionInfoVersion=0.0.0.0
VersionInfoProductTextVersion={#AppBuild}
PrivilegesRequired=lowest
DefaultDirName={autopf}\The EPUB Redactor
DefaultGroupName=The ƎPUB Redactor
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\epubredactor.exe
UninstallDisplayName=The ƎPUB Redactor
SetupIconFile=..\assets\icon.ico
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=epubredactor-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "A shortcut on the desktop"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\epubredactor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\The ƎPUB Redactor"; Filename: "{app}\epubredactor.exe"
Name: "{autodesktop}\The ƎPUB Redactor"; Filename: "{app}\epubredactor.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\epubredactor.exe"; Description: "Start The ƎPUB Redactor"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; what Help > Check for Updates may leave beside the exe: the old exe after a swap, and a download that did not finish
Type: files; Name: "{app}\epubredactor.exe.old"
Type: files; Name: "{app}\epubredactor.exe.new"
Type: files; Name: "{app}\epubredactor.exe.new.part"

#include UpdateContract
