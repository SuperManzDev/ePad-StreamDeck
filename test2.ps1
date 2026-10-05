$pgPath = "C:\Program Files\PostgreSQL\17\bin"

if (Test-Path $pgPath) {
    # Get current User Path
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    # Check if it's already there to avoid duplicates
    if ($currentPath -notlike "*$pgPath*") {
        # Add it permanently
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$pgPath", "User")
        Write-Host "SUCCESS: PostgreSQL added to your Path!" -ForegroundColor Green
        Write-Host "PLEASE RESTART YOUR TERMINAL NOW." -ForegroundColor Yellow
    } else {
        Write-Host "INFO: It was already in your Path." -ForegroundColor Cyan
    }
} else {
    Write-Host "ERROR: Could not find folder at: $pgPath" -ForegroundColor Red
    Write-Host "Check if you installed a different version."
}