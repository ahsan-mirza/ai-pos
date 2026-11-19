param(
  [int]$ProcessId,
  [Int64]$Hwnd,
  [string]$Output
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class CapWin3 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$process = Get-Process -Id $ProcessId -ErrorAction Stop
if ($process.Path -ne 'D:\Work\ai-pos\apps\desktop\src-tauri\target\release\ai-pos-desktop.exe') { throw "unexpected executable" }
if ($process.MainWindowTitle -ne 'AxizPOS Pharmacy Acceptance') { throw "unexpected title $($process.MainWindowTitle)" }
$handle = [IntPtr]$Hwnd
$rect = New-Object CapWin3+RECT
[CapWin3]::GetWindowRect($handle, [ref]$rect) | Out-Null
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
[CapWin3]::PrintWindow($handle, $hdc, 2) | Out-Null
$graphics.ReleaseHdc($hdc)
$graphics.Dispose()
$bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
$bitmap.Dispose()
Write-Output "saved $width x $height"
