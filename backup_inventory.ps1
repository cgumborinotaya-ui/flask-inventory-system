$SourceDb = "C:\Users\User\OneDrive\Desktop\New folder\instance\inventory.db"
$BackupRoot = "D:\ICTAssetBackups"
if (!(Test-Path -Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot | Out-Null
}
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupRoot ("inventory_backup_{0}.db" -f $timestamp)
Copy-Item -Path $SourceDb -Destination $BackupFile -Force
$maxBackups = 30
Get-ChildItem -Path $BackupRoot -Filter "inventory_backup_*.db" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $maxBackups |
    Remove-Item -Force

