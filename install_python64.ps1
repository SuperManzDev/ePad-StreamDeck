# Check if Chocolatey is installed
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "Chocolatey not found. Installing Chocolatey..." -ForegroundColor Cyan
    Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}

# Install Python 64-bit (Standard package is 64-bit)
Write-Host "Installing Python 64-bit..." -ForegroundColor Green
choco install python -y --force

# Install the required libraries for the Deck on the NEW Python
Write-Host "Installing libraries (hidapi, pillow) for 64-bit Python..." -ForegroundColor Cyan
# We use 'py -3.12' (or whatever version installed) to target the new one specifically
# If choco installed 3.13, this ensures we hit the new 64-bit one
& py -0  # Refreshes the launcher
$latest_py = (py --list | Select-String "64-bit" | Select-Object -First 1).ToString().Split(" ")[0].Trim()

if ($latest_py) {
    Write-Host "Found new 64-bit Python: $latest_py" -ForegroundColor Green
    & py $latest_py -m pip install hidapi pillow
    Write-Host "Done! You can now run the Deck app." -ForegroundColor Green
} else {
    Write-Host "Could not auto-detect the new Python. Please restart your terminal." -ForegroundColor Yellow
}

Write-Host "IMPORTANT: Close this window and open a new one for changes to take effect." -ForegroundColor Red