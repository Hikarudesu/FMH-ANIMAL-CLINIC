# Database Backup & Recovery Guide

**Backup Created:** August 16, 2026 16:05:03  
**Database:** fmhclinic (PostgreSQL)  
**Location:** `backups/` directory in project root

---

## 📁 Backup Files Overview

Your database has been backed up in **3 different formats** for maximum flexibility:

### 1. **PostgreSQL Binary Dump** (Recommended for quick restore)
```
File: fmhclinic_backup_2026-08-16_160435.dump
Size: 300.84 KB
Format: Custom PostgreSQL binary format
Best For: Fast restoration, compression, exact database replica
```

### 2. **SQL Text Backup** (Recommended for inspection/migration)
```
File: fmhclinic_backup_2026-08-16_160453.sql
Size: 546.94 KB
Format: Plain SQL text (human-readable)
Best For: Viewing backup contents, manual edits, migration to other systems
```

### 3. **Django JSON Export** (Recommended for data portability)
```
File: fmhclinic_data_2026-08-16_160503.json
Size: 879.36 KB
Format: JSON with app/model structure
Best For: Loading data into another Django instance, data inspection
```

### 4. **Backup Manifest** (Reference document)
```
File: BACKUP_MANIFEST_2026-08-16_160503.txt
Size: 554 bytes
Format: Plain text summary
Best For: Quick reference of what's in the backup
```

---

## 📊 What Was Backed Up

| Data Type | Count |
|-----------|-------|
| **User Accounts** | 15 |
| **Pets/Patients** | 15 |
| **Appointments** | 4 |
| **Medical Records** | 14 |
| **Inventory Items** | 63 |
| **Sales/Transactions** | 33 |
| **Employees** | 13 |
| **Branches/Locations** | 3 |
| **Notifications** | 209 |

---

## 🔄 How to Restore From Backup

### **Option 1: Restore from PostgreSQL Binary Dump** (FASTEST)

**Windows PowerShell:**
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" `
  -U postgres `
  -h localhost `
  -d fmhclinic `
  --clean `
  --if-exists `
  "backups\fmhclinic_backup_2026-08-16_160435.dump"
```

**Linux/Mac:**
```bash
export PGPASSWORD='postgres'
pg_restore -U postgres -h localhost -d fmhclinic \
  --clean --if-exists \
  backups/fmhclinic_backup_2026-08-16_160435.dump
```

**What it does:**
- `--clean` : Drops existing objects before recreating
- `--if-exists` : Only drops if objects exist (no errors)
- Restores complete database structure and data

---

### **Option 2: Restore from SQL Text File** (MANUAL/EDITABLE)

**Windows PowerShell:**
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" `
  -U postgres `
  -h localhost `
  -d fmhclinic `
  -f "backups\fmhclinic_backup_2026-08-16_160453.sql"
```

**Linux/Mac:**
```bash
export PGPASSWORD='postgres'
psql -U postgres -h localhost -d fmhclinic \
  < backups/fmhclinic_backup_2026-08-16_160453.sql
```

**Advantages:**
- Human-readable SQL format
- Can edit before restoring
- Works with any PostgreSQL client
- Good for documentation

---

### **Option 3: Restore from Django JSON Export** (FOR DJANGO ONLY)

This restores data while preserving Django relationships.

**Step 1: Ensure database is empty**
```bash
python FMHANIMALCLINIC/manage.py migrate
```

**Step 2: Load the JSON data**
```bash
python FMHANIMALCLINIC/manage.py loaddata \
  "backups/fmhclinic_data_2026-08-16_160503.json"
```

**Advantages:**
- Preserves all Django models and relationships
- Can migrate to another Django project
- Automatically handles model dependencies
- Best for app-level backup/restore

---

## ⚠️ Before Restoring

### Safety Precautions:

1. **Backup your current database first** (create a backup of the current state)
   ```powershell
   $env:PGPASSWORD='postgres'
   & "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" `
     -U postgres -h localhost -d fmhclinic `
     --format=custom `
     --file="backups\fmhclinic_backup_PRE_RESTORE_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').dump"
   ```

2. **Close the Django application** (stop the web server)
   ```powershell
   # Stop any running Django servers
   # Ctrl+C in the terminal where runserver is running
   ```

3. **Verify database connectivity**
   ```powershell
   $env:PGPASSWORD='postgres'
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" `
     -U postgres -h localhost -d fmhclinic -c "SELECT 1"
   ```

---

## ✅ After Restoring

### Verification Steps:

1. **Check data was restored**
   ```powershell
   $env:PGPASSWORD='postgres'
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" `
     -U postgres -h localhost -d fmhclinic -At `
     -c "SELECT count(*) FROM accounts_user"
   ```

2. **Run Django migrations to ensure schema is correct**
   ```bash
   python FMHANIMALCLINIC/manage.py migrate --check
   ```

3. **Run system checks**
   ```bash
   python FMHANIMALCLINIC/manage.py check
   ```

4. **Restart the application**
   ```bash
   python FMHANIMALCLINIC/manage.py runserver 0.0.0.0:8000
   ```

---

## 📋 Backup Schedule Recommendation

To maintain regular backups:

### **Automated Backup Script** (Windows)
Create a file: `backup_database.ps1`

```powershell
# Set this to run daily via Windows Task Scheduler
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupDir = "C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\backups"
$env:PGPASSWORD='postgres'

Write-Host "Backing up database at $timestamp..."

# Create binary dump
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" `
  -U postgres -h localhost -d fmhclinic `
  --format=custom `
  --file="$backupDir\fmhclinic_backup_$timestamp.dump"

# Create SQL backup
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" `
  -U postgres -h localhost -d fmhclinic `
  --format=plain `
  --file="$backupDir\fmhclinic_backup_$timestamp.sql"

Write-Host "✓ Backup completed: $timestamp"
```

### **Setup Windows Task Scheduler**
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2 AM
4. Action: Run PowerShell script
5. Add script: `backup_database.ps1`

### **Linux Cron Job**
Add to `crontab -e`:
```bash
# Daily backup at 2 AM
0 2 * * * /home/user/backup_database.sh
```

---

## 🚨 Disaster Recovery Procedure

### If database corruption occurs:

**Step 1: Stop the application**
```bash
Ctrl+C in terminal running Django
```

**Step 2: Drop corrupted database**
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\dropdb.exe" `
  -U postgres -h localhost fmhclinic
```

**Step 3: Create new database**
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\createdb.exe" `
  -U postgres -h localhost fmhclinic
```

**Step 4: Restore from backup (use Option 1)**
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" `
  -U postgres -h localhost -d fmhclinic `
  --clean --if-exists `
  "backups\fmhclinic_backup_2026-08-16_160435.dump"
```

**Step 5: Verify and restart**
```bash
python FMHANIMALCLINIC/manage.py check
python FMHANIMALCLINIC/manage.py runserver 0.0.0.0:8000
```

---

## 📚 Reference Information

### PostgreSQL Commands

| Command | Purpose |
|---------|---------|
| `pg_dump` | Export database to file |
| `pg_restore` | Restore from binary dump |
| `psql` | Execute SQL commands/files |
| `createdb` | Create new database |
| `dropdb` | Delete database |

### Connection Parameters

```
Host: localhost
Port: 5432 (default)
Username: postgres
Password: postgres
Database: fmhclinic
```

### Files Location

```
Project Root: C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\
Backups: C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\backups\
Django: C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\FMHANIMALCLINIC\
```

---

## 💡 Best Practices

1. ✅ **Keep multiple backups** - Store on different drives/cloud
2. ✅ **Test restores periodically** - Ensure backups actually work
3. ✅ **Document restoration process** - Keep this guide accessible
4. ✅ **Backup before major changes** - Schema updates, deployments
5. ✅ **Monitor backup sizes** - Watch for unexpected growth
6. ✅ **Archive old backups** - Keep for compliance/audit trail
7. ✅ **Encrypt sensitive backups** - Especially for production

---

## 🔐 Security Notes

- **Database password:** Currently stored in environment/code
- **Backup files:** Contains all data (keep secure)
- **Access control:** Backup directory should have restricted permissions
- **Encryption:** Consider encrypting backups for production use

---

## 📞 Troubleshooting

### "Connection refused"
- Check PostgreSQL is running: `Get-Service postgresql-x64-17`
- Check connection parameters in .env file

### "role 'postgres' does not exist"
- Create user: `createuser postgres` (if needed)

### "database 'fmhclinic' does not exist"
- Create database: `createdb fmhclinic` before restore

### "permission denied"
- Check file permissions on backup files
- Ensure PostgreSQL service is running as correct user

### "Invalid backup file format"
- Verify file wasn't corrupted during download/transfer
- Ensure correct PostgreSQL version (17 for binary dump)

---

## 📝 Backup Log

| Date | Backup Type | Records | Status |
|------|-------------|---------|--------|
| 2026-08-16 | Full Database | All | ✅ Complete |
| Timestamp | fmhclinic_backup_2026-08-16_160435.dump | | Created |
| Timestamp | fmhclinic_backup_2026-08-16_160453.sql | | Created |
| Timestamp | fmhclinic_data_2026-08-16_160503.json | | Created |

---

**Last Updated:** August 16, 2026  
**Created By:** Automated Backup System  
**Next Review:** Recommend monthly backup verification
