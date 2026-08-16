#!/bin/bash
# Quick Database Backup Script
# For FMH Animal Clinic - PostgreSQL Database (Linux/Mac)
# Usage: chmod +x backup_database.sh && ./backup_database.sh

# Configuration
PROJECT_ROOT="$HOME/fmh-animal-clinic"  # Update this path
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

# PostgreSQL Configuration
PG_USER="postgres"
PG_HOST="localhost"
PG_PORT="5432"
PG_DATABASE="fmhclinic"
PG_PASSWORD="postgres"  # Set via environment or prompt

# Setup
echo "=== FMH ANIMAL CLINIC DATABASE BACKUP ==="
echo "Timestamp: $TIMESTAMP"
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"
if [ $? -eq 0 ]; then
    echo "✓ Backup directory: $BACKUP_DIR"
else
    echo "✗ Failed to create backup directory"
    exit 1
fi

# Export PostgreSQL password
export PGPASSWORD="$PG_PASSWORD"

# Function to create binary dump
create_binary_dump() {
    local output_file="$1"
    echo "Creating PostgreSQL binary dump..."
    pg_dump -U "$PG_USER" -h "$PG_HOST" -p "$PG_PORT" -d "$PG_DATABASE" \
            --format=custom --file="$output_file" 2>&1
    
    if [ $? -eq 0 ]; then
        local size=$(du -h "$output_file" | cut -f1)
        echo "✓ Binary Dump: $(basename $output_file)"
        echo "  Size: $size"
        return 0
    else
        echo "✗ Failed to create binary dump"
        return 1
    fi
}

# Function to create SQL dump
create_sql_dump() {
    local output_file="$1"
    echo "Creating SQL text backup..."
    pg_dump -U "$PG_USER" -h "$PG_HOST" -p "$PG_PORT" -d "$PG_DATABASE" \
            --format=plain > "$output_file" 2>&1
    
    if [ $? -eq 0 ]; then
        local size=$(du -h "$output_file" | cut -f1)
        echo "✓ SQL Dump: $(basename $output_file)"
        echo "  Size: $size"
        return 0
    else
        echo "✗ Failed to create SQL dump"
        return 1
    fi
}

# Function to create Django JSON export
create_json_export() {
    local output_file="$1"
    echo "Creating Django JSON export..."
    
    cd "$PROJECT_ROOT"
    python manage.py dumpdata --all --indent=2 --format=json > "$output_file" 2>&1
    
    if [ $? -eq 0 ]; then
        local size=$(du -h "$output_file" | cut -f1)
        echo "✓ JSON Export: $(basename $output_file)"
        echo "  Size: $size"
        return 0
    else
        echo "✗ Failed to create JSON export"
        return 1
    fi
}

# Function to create manifest
create_manifest() {
    local output_file="$1"
    echo "Creating backup manifest..."
    
    {
        echo "=== FMH ANIMAL CLINIC DATABASE BACKUP ==="
        echo "Backup Date: $(date '+%B %d, %Y %H:%M:%S')"
        echo ""
        echo "Database: $PG_DATABASE"
        echo "Host: $PG_HOST"
        echo ""
        echo "DATABASE CONTENTS:"
        
        psql -U "$PG_USER" -h "$PG_HOST" -p "$PG_PORT" -d "$PG_DATABASE" -At <<EOF
SELECT 'Accounts: ' || count(*) FROM accounts_user;
SELECT 'Pets/Patients: ' || count(*) FROM patients_pet;
SELECT 'Appointments: ' || count(*) FROM appointments_appointment;
SELECT 'Medical Records: ' || count(*) FROM records_medicalrecord;
SELECT 'Inventory Items: ' || count(*) FROM inventory_product;
SELECT 'Sales/Transactions: ' || count(*) FROM pos_sale;
SELECT 'Employees: ' || count(*) FROM employees_staffmember;
SELECT 'Branches: ' || count(*) FROM branches_branch;
SELECT 'Notifications: ' || count(*) FROM notifications_notification;
EOF
    } > "$output_file"
    
    if [ $? -eq 0 ]; then
        echo "✓ Manifest: $(basename $output_file)"
        return 0
    else
        echo "✗ Failed to create manifest"
        return 1
    fi
}

# Main execution
success_count=0

echo "Creating backups..."
echo ""

# Create all backup types
if create_binary_dump "$BACKUP_DIR/fmhclinic_backup_${TIMESTAMP}.dump"; then
    ((success_count++))
fi

if create_sql_dump "$BACKUP_DIR/fmhclinic_backup_${TIMESTAMP}.sql"; then
    ((success_count++))
fi

if create_json_export "$BACKUP_DIR/fmhclinic_data_${TIMESTAMP}.json"; then
    ((success_count++))
fi

if create_manifest "$BACKUP_DIR/BACKUP_MANIFEST_${TIMESTAMP}.txt"; then
    ((success_count++))
fi

# Summary
echo ""
echo "=== BACKUP SUMMARY ==="
echo "Backup Location: $BACKUP_DIR"
echo "Successful: $success_count file(s)"
echo ""
echo "Recent backups:"
ls -lhS "$BACKUP_DIR" | grep -v "^total" | head -5 | awk '{print "  " $9 " (" $5 ")"}'

echo ""
echo "✓ Backup complete! See README.md for restoration instructions."

# Clean up environment
unset PGPASSWORD
