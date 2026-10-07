Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!ifndef VERSION
!define VERSION "1.1.1"
!endif
!ifndef PAYLOAD
!define PAYLOAD "build/windows"
!endif
Name "CometForge ${VERSION}"
Icon "assets/CometForge.ico"
UninstallIcon "assets/CometForge.ico"
OutFile "dist/CometForge-${VERSION}-Windows-x64-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\CometForge"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\CometForge.exe"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchCometForge
!define MUI_FINISHPAGE_RUN_TEXT "Open CometForge"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "THIRD_PARTY_NOTICES.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function LaunchCometForge
  Exec '"$INSTDIR\CometForge.exe"'
FunctionEnd

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "CometForge requires 64-bit Windows 10 or later."
    Abort
  ${EndIf}
FunctionEnd

Section "CometForge and required Python/PDF dependencies" Core
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}/app/*"
  SetOutPath "$INSTDIR\runtime"
  File /r "${PAYLOAD}/runtime/*"
  SetOutPath "$INSTDIR"
  File "THIRD_PARTY_NOTICES.txt"
  CreateDirectory "$LOCALAPPDATA\CometForge\data"
  ; Preserve the saved port and existing preferences during upgrades.
  IfFileExists "$LOCALAPPDATA\CometForge\data\settings.json" preserve_settings
    ExecWait '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\launcher.py" --configure-install --ghostscript disabled' $1
  preserve_settings:
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\CometForge"
  CreateShortcut "$SMPROGRAMS\CometForge\CometForge.lnk" "$INSTDIR\CometForge.exe" "" "$INSTDIR\CometForge.exe" 0
  CreateShortcut "$DESKTOP\CometForge.lnk" "$INSTDIR\CometForge.exe" "" "$INSTDIR\CometForge.exe" 0
  ExecWait '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\launcher.py" --register-shortcuts "$SMPROGRAMS\CometForge\CometForge.lnk" "$DESKTOP\CometForge.lnk"' $1
  ${If} $1 != 0
    MessageBox MB_ICONEXCLAMATION "CometForge shortcuts were created, but Windows could not register their taskbar identity ($1). Re-run setup to repair the shortcuts."
  ${EndIf}
  CreateShortcut "$SMPROGRAMS\CometForge\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\CometForge" "DisplayName" "CometForge ${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\CometForge" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\CometForge" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\CometForge" "DisplayIcon" "$INSTDIR\CometForge.exe,0"
SectionEnd

Section "Microsoft Visual C++ runtime (required for PDF engines)" VisualCpp
  SectionIn RO
  SetOutPath "$TEMP\CometForge-Setup"
  File "${PAYLOAD}/ghostscript/vcredist_x64.exe"
  SetRegView 64
  ReadRegDWORD $0 HKLM "Software\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  SetRegView 32
  ${If} $0 != 1
    ExecShellWait "runas" "$TEMP\CometForge-Setup\vcredist_x64.exe" "/install /quiet /norestart" SW_SHOWNORMAL $1
    ${If} $1 != 0
    ${AndIf} $1 != 3010
    ${AndIf} $1 != 1638
      MessageBox MB_ICONEXCLAMATION "Visual C++ runtime setup returned $1. Run the bundled vcredist_x64.exe as administrator before opening CometForge."
    ${EndIf}
  ${EndIf}
SectionEnd

Section "Install Ghostscript (recommended for target-fit compression)" Ghostscript
  SetOutPath "$INSTDIR\ghostscript"
  File /r "${PAYLOAD}/ghostscript/*"
  CreateDirectory "$LOCALAPPDATA\CometForge\data"
  ExecWait '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\launcher.py" --configure-install --ghostscript enabled' $1
SectionEnd

Section "Microsoft WebView2 runtime (required if missing; Internet needed)" WebView
  SectionIn RO
  ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKLM "Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
    SetOutPath "$TEMP\CometForge-Setup"
    File "${PAYLOAD}/MicrosoftEdgeWebview2Setup.exe"
    ExecWait '"$TEMP\CometForge-Setup\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    ${If} $1 != 0
      MessageBox MB_ICONEXCLAMATION "WebView2 setup failed ($1). Connect to the Internet and run the bundled WebView2 installer before opening CometForge."
    ${EndIf}
  ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
!insertmacro MUI_DESCRIPTION_TEXT ${Core} "Offline Python runtime and all PDF dependencies. No system Python required."
!insertmacro MUI_DESCRIPTION_TEXT ${VisualCpp} "Bundled Microsoft C++ runtime required by PikePDF and Ghostscript. Windows may ask for administrator approval."
!insertmacro MUI_DESCRIPTION_TEXT ${Ghostscript} "Checked by default. Installs the bundled AGPL Ghostscript engine for compression to a target size."
!insertmacro MUI_DESCRIPTION_TEXT ${WebView} "Uses Microsoft Edge WebView2 for a native app window. Downloads the runtime only if absent."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$DESKTOP\CometForge.lnk"
  RMDir /r "$SMPROGRAMS\CometForge"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\CometForge"
  RMDir /r "$INSTDIR"
  ; Keep user outputs/settings in LOCALAPPDATA\CometForge\data.
SectionEnd
