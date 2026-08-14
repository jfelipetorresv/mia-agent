; Mia compacta usa el WebView2 Evergreen que Windows ya distribuye.
; Si falta, se detiene ANTES de copiar archivos: nunca queda una app rota ni
; se inicia una descarga silenciosa. Para esos equipos existe el instalador
; Offline, que conserva el redistribuible completo.

!macro NSIS_HOOK_PREINSTALL
  ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" mia_check_webview_hklm_native
  StrCmp $0 "0.0.0.0" mia_check_webview_hklm_native mia_webview_ready

  mia_check_webview_hklm_native:
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" mia_check_webview_hkcu
  StrCmp $0 "0.0.0.0" mia_check_webview_hkcu mia_webview_ready

  mia_check_webview_hkcu:
  ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" mia_webview_missing
  StrCmp $0 "0.0.0.0" mia_webview_missing mia_webview_ready

  mia_webview_missing:
  MessageBox MB_ICONSTOP|MB_OK "Este equipo no tiene Microsoft Edge WebView2 Runtime. Mia no instalara una aplicacion incompleta ni descargara componentes sin aviso. Use el instalador 'Mia Offline', que incluye WebView2."
  Abort

  mia_webview_ready:
!macroend
