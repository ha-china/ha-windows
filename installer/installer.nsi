; Home Assistant Windows Installer Script
; Supports auto-startup and clean uninstall

!define PRODUCT_NAME "Home Assistant Windows"
; Version can be overridden at build time: makensis -DPRODUCT_VERSION=x.y.z
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "0.9.0"
!endif
!define PRODUCT_PUBLISHER "HA-China"
!define PRODUCT_WEB_SITE "https://github.com/ha-china/ha-windows"
!define PRODUCT_EXE "HomeAssistantWindows.exe"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\HomeAssistantWindows.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"
; Autostart Run value name - must match src/autostart.py AUTOSTART_NAME
!define AUTOSTART_VALUE_NAME "HomeAssistantWindows"

; Modern UI
!include "MUI2.nsh"

; General
Name "${PRODUCT_NAME}"
OutFile "..\dist\HomeAssistantWindows_Setup.exe"
InstallDir "$PROGRAMFILES64\HomeAssistantWindows"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
SetCompressor lzma

; Variables
Var StartMenuFolder

; Interface Settings
!define MUI_ABORTWARNING
!define MUI_ICON "..\src\logo.ico"
!define MUI_UNICON "..\src\logo.ico"
; Note: Header and welcome images are optional
; Uncomment and create these files if you want custom images
; !define MUI_HEADERIMAGE
; !define MUI_HEADERIMAGE_BITMAP "header.bmp"
; !define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"

; Installer Sections
Section "Main Program" SEC01
  SectionIn RO
  ; Stop a running instance so file replacement cannot fail mid-upgrade
  nsExec::ExecToLog 'taskkill /F /IM ${PRODUCT_EXE}'
  Sleep 2000

  SetOutPath "$INSTDIR"
  File /r "..\dist\HomeAssistantWindows\*"
  
  ; Create shortcuts
  CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\${PRODUCT_NAME}.lnk" "$INSTDIR\HomeAssistantWindows.exe" "" "$INSTDIR\HomeAssistantWindows.exe" 0
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\HomeAssistantWindows.exe" "" "$INSTDIR\HomeAssistantWindows.exe" 0
  
  ; Register application
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\HomeAssistantWindows.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\HomeAssistantWindows.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "NoModify" 1
  WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "NoRepair" 1
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninst.exe"
SectionEnd

Section "Auto Start on Boot" SEC02
  ; Add to Windows startup registry (same value name the app itself uses)
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${AUTOSTART_VALUE_NAME}" '"$INSTDIR\${PRODUCT_EXE}"'
SectionEnd

Section "Start Menu Shortcuts" SEC03
  CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall ${PRODUCT_NAME}.lnk" "$INSTDIR\uninst.exe"
SectionEnd

; Section Descriptions
LangString DESC_SEC01 ${LANG_ENGLISH} "Install main program files"
LangString DESC_SEC01 ${LANG_SIMPCHINESE} "Install main program files"
LangString DESC_SEC02 ${LANG_ENGLISH} "Start application automatically when Windows boots"
LangString DESC_SEC02 ${LANG_SIMPCHINESE} "Start application automatically when Windows boots"
LangString DESC_SEC03 ${LANG_ENGLISH} "Create Start Menu shortcuts"
LangString DESC_SEC03 ${LANG_SIMPCHINESE} "Create Start Menu shortcuts"

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} $(DESC_SEC01)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC02} $(DESC_SEC02)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC03} $(DESC_SEC03)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; Uninstaller Section
Section Uninstall
  ; Stop running application
  nsExec::ExecToLog 'taskkill /F /IM ${PRODUCT_EXE}'
  Sleep 2000
  
  ; Remove application files (PyInstaller onedir layout: payload in _internal).
  ; Only app-owned paths are removed recursively; $INSTDIR itself is only
  ; deleted when empty, so a user-chosen directory with foreign files survives.
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${PRODUCT_EXE}"
  Delete "$INSTDIR\uninst.exe"
  RMDir "$INSTDIR"
  
  ; Remove shortcuts
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\$StartMenuFolder\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\$StartMenuFolder"
  
  ; Remove registry entries
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  ; Autostart entries: current name plus the legacy installer name
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${AUTOSTART_VALUE_NAME}"
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  
  ; Remove application data directory (optional, keep user data)
  ; RMDir /r "$APPDATA\HomeAssistantWindows"
SectionEnd