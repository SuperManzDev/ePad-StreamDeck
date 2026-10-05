# 1. Delete the potentially wrong 64-bit files from the 32-bit folder
Remove-Item "C:\Windows\SysWOW64\msvcr80.dll" -ErrorAction SilentlyContinue
Remove-Item "C:\Windows\SysWOW64\msvcr90.dll" -ErrorAction SilentlyContinue

# 2. Find the REAL 32-bit versions installed by Chocolatey in WinSxS
# We look for folders starting with x86_microsoft.vc80 (2005) and vc90 (2008)
$dll80 = Get-ChildItem -Path "C:\Windows\WinSxS\x86_microsoft.vc80.crt_*" -Recurse -Filter "msvcr80.dll" | Select-Object -Last 1
$dll90 = Get-ChildItem -Path "C:\Windows\WinSxS\x86_microsoft.vc90.crt_*" -Recurse -Filter "msvcr90.dll" | Select-Object -Last 1

# 3. Copy the correct 32-bit files to SysWOW64
if ($dll80) {
    Copy-Item $dll80.FullName "C:\Windows\SysWOW64\msvcr80.dll" -Force
    Write-Host "FIXED: Copied 32-bit msvcr80.dll to SysWOW64" -ForegroundColor Green
} else {
    Write-Host "ERROR: Could not find msvcr80.dll in WinSxS. Did the install finish?" -ForegroundColor Red
}

if ($dll90) {
    Copy-Item $dll90.FullName "C:\Windows\SysWOW64\msvcr90.dll" -Force
    Write-Host "FIXED: Copied 32-bit msvcr90.dll to SysWOW64" -ForegroundColor Green
}