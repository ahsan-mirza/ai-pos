Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FrontKey {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@
$front = [FrontKey]::GetForegroundWindow()
$proc = [uint32]0
[FrontKey]::GetWindowThreadProcessId($front, [ref]$proc) | Out-Null
$process = Get-Process -Id $proc
if ($process.Path -ne 'D:\Work\ai-pos\apps\desktop\src-tauri\target\release\ai-pos-desktop.exe') { throw "foreground is not the acceptance register" }
if ($process.MainWindowTitle -ne 'AxizPOS Pharmacy Acceptance') { throw "unexpected title" }
$envFile = 'D:\Work\ai-pos\acceptance\pharmacy\.env.acceptance.runtime'
$line = Get-Content $envFile | Where-Object { $_ -like 'GROCERY_ACTIVATION_KEY=*' } | Select-Object -First 1
if (-not $line) { throw "grocery key missing" }
$value = $line.Substring('GROCERY_ACTIVATION_KEY='.Length).Trim()
if ($value.Length -lt 8) { throw "grocery key too short" }
$escaped = $value -replace '([+^%~(){}\[\]])', '{$1}'
$shell = New-Object -ComObject WScript.Shell
$shell.SendKeys($escaped) | Out-Null
Write-Output "typed length=$($value.Length) pid=$proc"
