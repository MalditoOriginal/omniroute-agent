Write-Host "Starting OmniRoute sync to GitHub..." -ForegroundColor Cyan

 $projectPath = "D:\OmniRoute-Agent"
 $backupPath = "$projectPath\omniroute-backup"
 $sourcePath = "$env:APPDATA\omniroute"

# 1. Clean old backup
if (Test-Path $backupPath) {
    Remove-Item -Path $backupPath -Recurse -Force
}

# 2. Copy fresh settings
if (Test-Path $sourcePath) {
    Copy-Item -Path $sourcePath -Destination $backupPath -Recurse -Force
    Write-Host "[OK] Settings copied." -ForegroundColor Green
} else {
    Write-Host "[ERROR] OmniRoute settings folder not found!" -ForegroundColor Red
    exit
}

# 3. Push to GitHub
Set-Location $projectPath
git add -f omniroute-backup/
git commit -m "Auto-Sync: OmniRoute settings update $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push

Write-Host "Sync complete! Backup pushed to GitHub." -ForegroundColor Green	