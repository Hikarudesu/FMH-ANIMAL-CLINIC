# Quick Database Backup Script
# For FMH Animal Clinic - PostgreSQL Database
# Usage: Run this script anytime you want to create a backup

param(
    [Parameter(Mandatory = $false)]
    [string]$BackupType = "all"  # all, dump, sql, json
)

# Configuration
$ProjectRoot = "C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC"
$BackupDir = Join-Path $ProjectRoot "backups"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"

# PostgreSQL Configuration
$PGPath = "C:\Program Files\PostgreSQL\17\bin"
$PGUser = "postgres"
$PGHost = "localhost"
$PGDatabase = "fmhclinic"
$PGPassword = "postgres"

# Setup
Write-Host "=== FMH ANIMAL CLINIC DATABASE BACKUP ===" -ForegroundColor Green
Write-Host "Timestamp: $Timestamp" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Write-Host "✓ Created backup directory: $BackupDir" -ForegroundColor Yellow
}

$env:PGPASSWORD = $PGPassword

# Function to create binary dump
function Create-BinaryDump {
    param([string]$OutputFile)
    Write-Host "Creating PostgreSQL binary dump..." -ForegroundColor Cyan
    try {
        & "$PGPath\pg_dump.exe" -U $PGUser -h $PGHost -d $PGDatabase --format=custom --file=$OutputFile 2>&1 | Where-Object { $_ }
        if ($LASTEXITCODE -eq 0) {
            $Size = (Get-Item $OutputFile).Length / 1MB
            Write-Host "✓ Binary Dump: $(Split-Path $OutputFile -Leaf)" -ForegroundColor Green
            Write-Host "  Size: $([Math]::Round($Size, 2)) MB" -ForegroundColor DarkGray
            return $true
        }
        else {
            Write-Host "✗ Failed to create binary dump" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "✗ Error: $_" -ForegroundColor Red
        return $false
    }
}

# Function to create SQL dump
function Create-SQLDump {
    param([string]$OutputFile)
    Write-Host "Creating SQL text backup..." -ForegroundColor Cyan
    try {
        & "$PGPath\pg_dump.exe" -U $PGUser -h $PGHost -d $PGDatabase --format=plain 2>&1 | Out-File -Encoding utf8 $OutputFile
        if ($LASTEXITCODE -eq 0) {
            $Size = (Get-Item $OutputFile).Length / 1MB
            Write-Host "✓ SQL Dump: $(Split-Path $OutputFile -Leaf)" -ForegroundColor Green
            Write-Host "  Size: $([Math]::Round($Size, 2)) MB" -ForegroundColor DarkGray
            return $true
        }
        else {
            Write-Host "✗ Failed to create SQL dump" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "✗ Error: $_" -ForegroundColor Red
        return $false
    }
}

# Function to create Django JSON export
function Create-JSONExport {
    param([string]$OutputFile)
    Write-Host "Creating Django JSON export..." -ForegroundColor Cyan
    try {
        Push-Location $ProjectRoot
        & ".\venv\Scripts\python.exe" FMHANIMALCLINIC/manage.py dumpdata --all --indent=2 --format=json 2>&1 | Out-File -Encoding utf8 $OutputFile
        Pop-Location
        if ($LASTEXITCODE -eq 0) {
            $Size = (Get-Item $OutputFile).Length / 1MB
            Write-Host "✓ JSON Export: $(Split-Path $OutputFile -Leaf)" -ForegroundColor Green
            Write-Host "  Size: $([Math]::Round($Size, 2)) MB" -ForegroundColor DarkGray
            return $true
        }
        else {
            Write-Host "✗ Failed to create JSON export" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "✗ Error: $_" -ForegroundColor Red
        return $false
    }
}

# Function to create manifest
function Create-Manifest {
    param([string]$OutputFile)
    Write-Host "Creating backup manifest..." -ForegroundColor Cyan
    try {
        $Manifest = @()
        $Manifest += "=== FMH ANIMAL CLINIC DATABASE BACKUP ==="
        $Manifest += "Backup Date: $(Get-Date -Format 'MMMM dd, yyyy HH:mm:ss')"
        $Manifest += ""
        $Manifest += "Database: $PGDatabase"
        $Manifest += "Host: $PGHost"
        $Manifest += ""
        $Manifest += "DATABASE CONTENTS:"
        
        $queries = @(
            "SELECT 'Accounts: ' || count(*) FROM accounts_user",
            "SELECT 'Pets/Patients: ' || count(*) FROM patients_pet",
            "SELECT 'Appointments: ' || count(*) FROM appointments_appointment",
            "SELECT 'Medical Records: ' || count(*) FROM records_medicalrecord",
            "SELECT 'Inventory Items: ' || count(*) FROM inventory_product",
            "SELECT 'Sales/Transactions: ' || count(*) FROM pos_sale",
            "SELECT 'Employees: ' || count(*) FROM employees_staffmember",
            "SELECT 'Branches: ' || count(*) FROM branches_branch",
            "SELECT 'Notifications: ' || count(*) FROM notifications_notification"
        )
        
        foreach ($query in $queries) {
            $result = & "$PGPath\psql.exe" -U $PGUser -h $PGHost -d $PGDatabase -At -c $query 2>&1
            $Manifest += "  $result"
        }
        
        $Manifest | Out-File -Encoding utf8 $OutputFile
        Write-Host "✓ Manifest: $(Split-Path $OutputFile -Leaf)" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "✗ Error: $_" -ForegroundColor Red
        return $false
    }
}

# Main execution
$SuccessCount = 0

Write-Host "Creating backups..." -ForegroundColor Cyan
Write-Host ""

if ($BackupType -eq "all" -or $BackupType -eq "dump") {
    if (Create-BinaryDump "$BackupDir\fmhclinic_backup_$Timestamp.dump") {
        $SuccessCount++
    }
}

if ($BackupType -eq "all" -or $BackupType -eq "sql") {
    if (Create-SQLDump "$BackupDir\fmhclinic_backup_$Timestamp.sql") {
        $SuccessCount++
    }
}

if ($BackupType -eq "all" -or $BackupType -eq "json") {
    if (Create-JSONExport "$BackupDir\fmhclinic_data_$Timestamp.json") {
        $SuccessCount++
    }
}

if ($BackupType -eq "all") {
    if (Create-Manifest "$BackupDir\BACKUP_MANIFEST_$Timestamp.txt") {
        $SuccessCount++
    }
}

Write-Host ""
Write-Host "=== BACKUP SUMMARY ===" -ForegroundColor Green
Write-Host "Backup Location: $BackupDir" -ForegroundColor Cyan
Write-Host "Successful: $SuccessCount file(s)" -ForegroundColor Green

# List all backups
Write-Host ""
Write-Host "Recent backups:" -ForegroundColor Cyan
Get-ChildItem $BackupDir -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object {
    $Size = $_.Length / 1MB
    Write-Host "  - $($_.Name) ($([Math]::Round($Size, 2)) MB)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "✓ Backup complete! See README.md for restoration instructions." -ForegroundColor Green
