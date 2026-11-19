; Guided NSIS pages for the AxizPOS installer.
; Included by Tauri before its own pages, so this radio page is shown first.
;
; An existing register is detected from HKCU\Software\QuantumPOS, from Tauri's
; uninstall key, or from the register files themselves. Recovery is the default.
; Reset is explicit and asks for confirmation before anything is deleted.
;
; The register keeps its database, activation, printer settings, and offline
; sales in %APPDATA%\com.aipos.desktop (the Tauri identifier). Reset also removes
; %APPDATA%\quantum-pos when that folder exists.

!include LogicLib.nsh
!include WinVer.nsh

; Windows 11 uses the Windows 10 supported-OS GUID.
ManifestSupportedOS {8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}

!define POS_REG_KEY "Software\QuantumPOS"
!define POS_BUNDLE_ID "com.aipos.desktop"
!define POS_UNINST_CURRENT "Software\Microsoft\Windows\CurrentVersion\Uninstall\AxizPOS"
!define POS_UNINST_REGISTER "Software\Microsoft\Windows\CurrentVersion\Uninstall\AxizPOS POS Register"
!define POS_UNINST_PREVIOUS "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI POS"

Var PosInstallChoice
Var PosResetRadio
Var PosRecoverRadio
Var PosSavedUninstallDefault
Var PosSavedUninstallString
Var PosHidUninstallKey
Var PosUninstKey

!define MUI_CUSTOMFUNCTION_GUIINIT PosGuiInit
Function PosGuiInit
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "AxizPOS supports Windows 10 and Windows 11."
    Quit
  ${EndIf}
FunctionEnd

Function PosExistingInstallPage
  ${If} ${Silent}
    ; An update keeps the register database. Only the interactive Reset choice deletes it.
    StrCpy $PosInstallChoice "recovery"
    Abort
  ${EndIf}

  StrCpy $0 ""
  ReadRegStr $1 HKCU "${POS_REG_KEY}" "InstallLocation"
  ${If} $1 != ""
    StrCpy $0 "1"
  ${EndIf}
  ReadRegStr $1 SHCTX "${POS_UNINST_CURRENT}" "UninstallString"
  ${If} $1 != ""
    StrCpy $0 "1"
  ${EndIf}
  ReadRegStr $1 SHCTX "${POS_UNINST_REGISTER}" "UninstallString"
  ${If} $1 != ""
    StrCpy $0 "1"
  ${EndIf}
  ReadRegStr $1 SHCTX "${POS_UNINST_PREVIOUS}" "UninstallString"
  ${If} $1 != ""
    StrCpy $0 "1"
  ${EndIf}
  ${If} ${FileExists} "$APPDATA\${POS_BUNDLE_ID}\*.*"
    StrCpy $0 "1"
  ${EndIf}
  ${If} ${FileExists} "$INSTDIR\ai-pos-desktop.exe"
    StrCpy $0 "1"
  ${EndIf}
  ${If} $0 != "1"
    Abort
  ${EndIf}

  !insertmacro MUI_HEADER_TEXT "AxizPOS is already installed" "Reset the register, or keep its files"

  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${If} $(^RTL) = 1
    nsDialogs::SetRTL $(^RTL)
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 48u "Reset removes the program and the register files in %APPDATA%\${POS_BUNDLE_ID}: the local database, printer settings, and sales that have not synced.$\r$\n$\r$\nRecovery replaces the program and keeps those files."
  Pop $1

  ${NSD_CreateRadioButton} 0 58u 100% 12u "Reset all and re-install"
  Pop $PosResetRadio

  ${NSD_CreateRadioButton} 0 76u 100% 12u "Recovery (keep user data)"
  Pop $PosRecoverRadio
  ${NSD_SetState} $PosRecoverRadio ${BST_CHECKED}
  ${NSD_SetFocus} $PosRecoverRadio

  nsDialogs::Show
FunctionEnd

Function PosExistingInstallLeave
  ${NSD_GetState} $PosResetRadio $0
  ${If} $0 == ${BST_CHECKED}
    MessageBox MB_ICONEXCLAMATION|MB_YESNO "Reset deletes the local database, printer settings, and any sales that have not synced. This cannot be undone. Continue?" IDYES pos_reset_yes
    Abort
    pos_reset_yes:
    StrCpy $PosInstallChoice "reset"
  ${Else}
    StrCpy $PosInstallChoice "recover"
  ${EndIf}

  ; Tauri also asks whether to uninstall. Hiding its uninstall entry skips that
  ; page; .onInit has already pointed $INSTDIR at the existing folder.
  StrCpy $PosUninstKey "${POS_UNINST_CURRENT}"
  ReadRegStr $PosSavedUninstallString SHCTX "${POS_UNINST_CURRENT}" "UninstallString"
  ${If} $PosSavedUninstallString == ""
    StrCpy $PosUninstKey "${POS_UNINST_REGISTER}"
    ReadRegStr $PosSavedUninstallString SHCTX "${POS_UNINST_REGISTER}" "UninstallString"
  ${EndIf}
  ${If} $PosSavedUninstallString == ""
    StrCpy $PosUninstKey "${POS_UNINST_PREVIOUS}"
    ReadRegStr $PosSavedUninstallString SHCTX "${POS_UNINST_PREVIOUS}" "UninstallString"
  ${EndIf}
  ReadRegStr $PosSavedUninstallDefault SHCTX "$PosUninstKey" ""
  ${If} $PosSavedUninstallString != ""
    DeleteRegValue SHCTX "$PosUninstKey" ""
    DeleteRegValue SHCTX "$PosUninstKey" "UninstallString"
    StrCpy $PosHidUninstallKey "1"
  ${EndIf}
FunctionEnd

Page custom PosExistingInstallPage PosExistingInstallLeave

!define MUI_CUSTOMFUNCTION_ABORT PosUserAbort
Function PosUserAbort
  ${If} $PosHidUninstallKey == "1"
    WriteRegStr SHCTX "$PosUninstKey" "" $PosSavedUninstallDefault
    WriteRegStr SHCTX "$PosUninstKey" "UninstallString" $PosSavedUninstallString
    StrCpy $PosHidUninstallKey "0"
  ${EndIf}
FunctionEnd

!macro NSIS_HOOK_PREINSTALL
  !insertmacro CheckIfAppIsRunning "$INSTDIR\${MAINBINARYNAME}.exe" "${PRODUCTNAME}"
  ${If} $PosInstallChoice == "reset"
    ; Only the product folder. Never remove a parent such as the user profile.
    StrCpy $1 $INSTDIR "" -6
    StrCpy $2 $INSTDIR "" -20
    StrCpy $3 $INSTDIR "" -7
    ${If} $1 == "AI POS"
    ${OrIf} $2 == "AxizPOS POS Register"
    ${OrIf} $3 == "AxizPOS"
      RMDir /r "$INSTDIR"
      CreateDirectory "$INSTDIR"
    ${Else}
      Delete "$INSTDIR\${MAINBINARYNAME}.exe"
      Delete "$INSTDIR\uninstall.exe"
    ${EndIf}
    RMDir /r "$APPDATA\${BUNDLEID}"
    RMDir /r "$LOCALAPPDATA\${BUNDLEID}"
    RMDir /r "$APPDATA\quantum-pos"
    RMDir /r "$LOCALAPPDATA\quantum-pos"
    DeleteRegKey HKCU "${POS_REG_KEY}"
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ${If} ${Silent}
    Exec '"$INSTDIR\${MAINBINARYNAME}.exe"'
  ${EndIf}
  StrCpy $PosHidUninstallKey "0"
  WriteRegStr HKCU "${POS_REG_KEY}" "" "$INSTDIR"
  WriteRegStr HKCU "${POS_REG_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${POS_REG_KEY}" "UserData" "$APPDATA\${BUNDLEID}"
  WriteRegStr HKCU "${POS_REG_KEY}" "InstallChoice" "$PosInstallChoice"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegKey HKCU "${POS_REG_KEY}"
!macroend
