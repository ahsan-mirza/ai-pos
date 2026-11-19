param([int]$ProcessId = 48672, [int]$Hwnd = 9310454)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FocusWin {
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@
$handle = [IntPtr]$Hwnd
[FocusWin]::ShowWindow($handle, 9) | Out-Null
[FocusWin]::SetWindowPos($handle, [IntPtr](-1), 40, 40, 1500, 980, 0x0040) | Out-Null
[FocusWin]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[FocusWin]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
[FocusWin]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Milliseconds 200
$front = [FocusWin]::GetForegroundWindow()
$proc = [uint32]0
[FocusWin]::GetWindowThreadProcessId($front, [ref]$proc) | Out-Null
if ([int]$proc -ne $ProcessId) {
  Write-Output "STOP front_pid=$proc front_hwnd=$front"
  exit 2
}
Write-Output "ready pid=$proc hwnd=$front"
