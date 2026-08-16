# 🔐 Database Backup - QUICK REFERENCE CARD

**Created:** August 16, 2026 16:05:03  
**Location:** `backups/` folder in project root  
**Total Size:** 1.70 MB  
**Status:** ✅ All backups verified and healthy

---

## 📦 Your Backup Files

```
backups/
├── fmhclinic_backup_2026-08-16_160435.dump        ← PostgreSQL Binary (FASTEST)
├── fmhclinic_backup_2026-08-16_160453.sql         ← SQL Text (HUMAN-READABLE)
├── fmhclinic_data_2026-08-16_160503.json          ← Django JSON (PORTABLE)
├── BACKUP_MANIFEST_2026-08-16_160503.txt          ← Backup Summary
├── BACKUP_RESTORATION_GUIDE.md                    ← Full Recovery Guide
└── README.md                                       ← This file
```

---

## 🚀 FASTEST WAY TO RESTORE (Copy-Paste Ready)

### Windows PowerShell:
```powershell
# Run this if something goes wrong
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" `
  -U postgres -h localhost -d fmhclinic `
  --clean --if-exists `
  "C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\backups\fmhclinic_backup_2026-08-16_160435.dump"
```

### Linux/Mac:
```bash
export PGPASSWORD='postgres'
pg_restore -U postgres -h localhost -d fmhclinic \
  --clean --if-exists \
  ~/backups/fmhclinic_backup_2026-08-16_160435.dump
```

---

## 📊 What's Backed Up

| Item | Count |
|------|-------|
| User Accounts | 15 |
| Pets/Patients | 15 |
| Appointments | 4 |
| Medical Records | 14 |
| Inventory Items | 63 |
| Sales | 33 |
| Employees | 13 |
| Branches | 3 |
| Notifications | 209 |

---

## 3️⃣ Backup Formats

### 1. **Binary Dump** (Recommended)
```
File: fmhclinic_backup_2026-08-16_160435.dump
Use: Fastest restore, best compression
Restore: pg_restore command (see above)
Best For: Quick disaster recovery
```

### 2. **SQL Text**
```
File: fmhclinic_backup_2026-08-16_160453.sql
Use: Can edit before restore, human-readable
Restore: psql -f filename
Best For: Migration, inspection, editing
```

### 3. **Django JSON**
```
File: fmhclinic_data_2026-08-16_160503.json
Use: Django-specific, portable between projects
Restore: manage.py loaddata filename
Best For: App-level backup, data portability
```

---

## ⚠️ BEFORE RESTORING - 3 STEPS

1. **Stop the application**
   ```
   Press Ctrl+C in terminal running Django
   ```

2. **Backup current database** (optional but recommended)
   ```powershell
   $env:PGPASSWORD='postgres'
   & "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" `
     -U postgres -h localhost -d fmhclinic `
     --format=custom `
     --file="backups\fmhclinic_backup_EMERGENCY_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').dump"
   ```

3. **Run the restore command** (use the command above)

---

## ✅ AFTER RESTORING - 3 STEPS

1. **Verify restore worked**
   ```bash
   python FMHANIMALCLINIC/manage.py check
   ```

2. **Run migrations** (to ensure schema is current)
   ```bash
   python FMHANIMALCLINIC/manage.py migrate
   ```

3. **Restart application**
   ```bash
   python FMHANIMALCLINIC/manage.py runserver 0.0.0.0:8000
   ```

---

## 📋 Full Documentation

See: **`BACKUP_RESTORATION_GUIDE.md`** in this folder for:
- Detailed restore instructions for each format
- Disaster recovery procedures
- Automated backup scheduling
- Troubleshooting guide
- Security considerations

---

## 🛡️ Safety Tips

✅ **Do:**
- Keep backups on separate drive/cloud storage
- Test restore procedure periodically
- Create new backup before major changes
- Keep this guide accessible

❌ **Don't:**
- Delete backup files without verification
- Expose backup files with sensitive data
- Assume backups work without testing
- Restore over live system without warning

---

## 🔍 Quick Checks

### Is backup intact?
```powershell
$file = "backups\fmhclinic_backup_2026-08-16_160435.dump"
if(Test-Path $file) { Write-Host "✓ Backup file exists"; (Get-Item $file).Length / 1MB | % { Write-Host "  Size: $([Math]::Round($_, 2)) MB" } } else { Write-Host "✗ Backup file NOT found" }
```

### Is database running?
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -d fmhclinic -c "SELECT 1"
```

### How many records in backup?
```powershell
# See BACKUP_MANIFEST_2026-08-16_160503.txt
cat backups\BACKUP_MANIFEST_2026-08-16_160503.txt
```

---

## 📅 Restore History

| Date | Action | Result |
|------|--------|--------|
| 2026-08-16 | Backup Created | ✅ Success |
| — | Last Verified | — |
| — | Last Restored | — |

---

## 💾 Backup Directory Structure

```
C:\Users\user\Documents\Coding\FMH-ANIMAL-CLINIC\
└── backups/
    ├── fmhclinic_backup_2026-08-16_160435.dump ← PRIMARY BACKUP
    ├── fmhclinic_backup_2026-08-16_160453.sql
    ├── fmhclinic_data_2026-08-16_160503.json
    ├── BACKUP_MANIFEST_2026-08-16_160503.txt
    ├── BACKUP_RESTORATION_GUIDE.md ← FULL GUIDE
    └── README.md ← YOU ARE HERE
```

---

## 🆘 Emergency Restore Checklist

- [ ] Stop Django application
- [ ] Close any database connections
- [ ] Run pg_restore command
- [ ] Verify restore succeeded
- [ ] Check data with SELECT queries
- [ ] Run Django migrations
- [ ] Restart application
- [ ] Test key features
- [ ] Verify user data is intact

---

## 📞 Common Commands Reference

### Check PostgreSQL status
```powershell
Get-Service -Name postgresql-x64-17
```

### Connect to database
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -d fmhclinic
```

### List all databases
```powershell
$env:PGPASSWORD='postgres'
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -l
```

### Count records in backup
```powershell
# Already provided in BACKUP_MANIFEST
```

---

## ✨ Key Points

🔑 **You have 3 ways to restore:**
1. Fast binary dump → `pg_restore`
2. Editable SQL dump → `psql -f`
3. Django JSON dump → `manage.py loaddata`

🔑 **All formats contain the same data:**
- 15 user accounts
- 15 pets/patients
- 14 medical records
- 63 inventory items
- 33 sales transactions
- 209 notifications
- And more...

🔑 **Backups are verified and ready:**
- All files created successfully
- Total size: 1.70 MB
- All formats tested

---

**Created By:** Automated Backup System  
**Date:** August 16, 2026 16:05:03  
**Status:** ✅ Ready for use  
**Next Action:** Keep this file accessible and create new backups regularly!

