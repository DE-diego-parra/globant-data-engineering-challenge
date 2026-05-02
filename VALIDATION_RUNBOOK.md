#!/bin/bash

# Script to add VALIDATION_RUNBOOK.md to GitHub
# Copy and paste this entire script into Cloud Shell

set -e

export PROJECT_ID="globant-migration-1777674652"

echo "Adding VALIDATION_RUNBOOK.md to repository..."

cd ~/globant-challenge

# Create the validation runbook
cat > VALIDATION_RUNBOOK.md << 'ENDRUNBOOK'
# Validation Runbook

Complete validation procedures and operational playbooks for different scenarios.

## Table of Contents

- [Scenario 1: New CSV Files Arrive](#scenario-1-new-csv-files-arrive)
- [Scenario 2: Validate Entire System](#scenario-2-validate-entire-system)
- [Scenario 3: Restore from Backup](#scenario-3-restore-from-backup)
- [Scenario 4: Verify Data Quality](#scenario-4-verify-data-quality)
- [Scenario 5: Troubleshooting](#scenario-5-troubleshooting)
- [Quick Reference](#quick-reference)

---

## Scenario 1: New CSV Files Arrive

**When:** Client sends updated CSV files

**Roadmap:**

### Step 1: Upload to Cloud Storage

```bash
export PROJECT_ID="your-project-id"

gcloud storage cp hired_employees.csv gs://${PROJECT_ID}-data-lake/raw/employees/
gcloud storage cp departments.csv gs://${PROJECT_ID}-data-lake/raw/departments/
gcloud storage cp jobs.csv gs://${PROJECT_ID}-data-lake/raw/jobs/
```

**Verify:**
```bash
gcloud storage ls gs://${PROJECT_ID}-data-lake/raw/*/
```

### Step 2: Update Complete Pipeline

```bash
cd ~/globant-challenge
./infra/update_pipeline.sh
```

**This executes:**
1. Load CSV → RAW (30s)
2. Validate → STAGING (10s)
3. Update → MARTS (15s)
4. Sync → DLQ (5s)

**Total time:** ~60 seconds

### Step 3: Verify Data Loaded

```bash
bq query --use_legacy_sql=false "
SELECT 
  'RAW' as layer, COUNT(*) as records 
FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
UNION ALL
SELECT 'STAGING', COUNT(*) FROM \`${PROJECT_ID}.globant_migration_staging.employees\`
UNION ALL
SELECT 'QUARANTINE', COUNT(*) FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
"
```

### Step 4: Check MARTS Updated

```bash
bq query --use_legacy_sql=false "
SELECT * FROM \`${PROJECT_ID}.globant_migration_marts.quarterly_hires\`
LIMIT 5
"
```

### Step 5: Refresh Looker Studio

Open dashboard → Click refresh button

**Done.** New data is live.

---

## Scenario 2: Validate Entire System

**When:** Before presentation or after deployment

**Roadmap:**

### Step 1: Test API Health

```bash
export SERVICE_URL=$(gcloud run services describe globant-api \
  --region us-central1 --format 'value(status.url)')

curl $SERVICE_URL/health
```

✅ Expected: `{"status":"healthy"}`

### Step 2: Test Data Ingestion

```bash
curl -X POST $SERVICE_URL/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "table": "employees",
    "data": [
      {"id": 9999, "name": "Test", "datetime": "2021-01-15T10:00:00Z", "department_id": 1, "job_id": 1}
    ]
  }'
```

✅ Expected: `{"inserted":1,"rejected":0}`

### Step 3: Test Validation

```bash
curl -X POST $SERVICE_URL/ingest \
  -d '{"table": "employees", "data": [{"id": -1, "name": "", "datetime": "bad", "department_id": 1, "job_id": 1}]}'
```

✅ Expected: `{"inserted":0,"rejected":1}`

### Step 4: Test Analytics

```bash
curl $SERVICE_URL/metrics/quarterly-hires | jq
curl $SERVICE_URL/metrics/above-mean-hires | jq
```

✅ Expected: JSON arrays with data

### Step 5: Test Backup

```bash
curl -X POST $SERVICE_URL/backup/employees
```

✅ Expected: `{"status":"success",...}`

### Step 6: Verify All Datasets

```bash
bq ls ${PROJECT_ID}: | grep globant_migration
```

✅ Expected: 4 datasets (raw, staging, marts, quarantine)

---

## Scenario 3: Restore from Backup

**When:** Data corruption or accidental deletion

**Roadmap:**

### Step 1: Create Backup First

```bash
curl -X POST $SERVICE_URL/backup/employees
```

**Save timestamp** from response

### Step 2: Simulate Data Loss

```bash
bq query --use_legacy_sql=false "
DELETE FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
WHERE id > 4540
"
```

### Step 3: Verify Deletion

```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
"
```

### Step 4: Restore

```bash
curl -X POST "$SERVICE_URL/restore/employees?backup_timestamp=20240502_143022"
```

### Step 5: Verify Recovery

```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
"
```

✅ Expected: Original count restored

### Step 6: Update Downstream

```bash
./infra/update_pipeline.sh
```

---

## Scenario 4: Verify Data Quality

**When:** Audit rejected records

**Roadmap:**

### Step 1: Check QUARANTINE

```bash
bq query --use_legacy_sql=false "
SELECT id, name, job_id, rejection_reason 
FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
"
```

### Step 2: Count by Rejection Reason

```bash
bq query --use_legacy_sql=false "
SELECT rejection_reason, COUNT(*) as count
FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
GROUP BY rejection_reason
"
```

### Step 3: Check Referential Integrity

```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) as orphans
FROM \`${PROJECT_ID}.globant_migration_staging.employees\` e
LEFT JOIN \`${PROJECT_ID}.globant_migration_staging.departments\` d 
  ON e.department_id = d.id
WHERE d.id IS NULL
"
```

✅ Expected: 0

### Step 4: Quality Percentage

```bash
bq query --use_legacy_sql=false "
WITH metrics AS (
  SELECT 
    (SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`) as raw,
    (SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_staging.employees\`) as valid
)
SELECT raw, valid, ROUND(valid * 100.0 / raw, 2) as quality_pct FROM metrics
"
```

✅ Expected: >95% quality

---

## Scenario 5: Troubleshooting

**When:** Errors occur

### API Returns 500

```bash
# Check logs
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" --limit 20

# Check service status
gcloud run services describe globant-api --region us-central1
```

### BigQuery Query Fails

```bash
# Verify table exists
bq show ${PROJECT_ID}:globant_migration_raw.employees

# Check schema
bq show --schema ${PROJECT_ID}:globant_migration_raw.employees
```

### Pipeline Update Fails

```bash
# Run steps individually
bq load --replace ${PROJECT_ID}:globant_migration_raw.employees gs://...
bq query "CREATE OR REPLACE TABLE staging.employees AS ..."
bq query "CREATE OR REPLACE TABLE marts.quarterly_hires AS ..."
```

---

## Quick Reference

### Update data
```bash
gcloud storage cp new.csv gs://${PROJECT_ID}-data-lake/raw/employees/
./infra/update_pipeline.sh
```

### Backup
```bash
curl -X POST $SERVICE_URL/backup/employees
```

### Restore
```bash
curl -X POST "$SERVICE_URL/restore/employees?backup_timestamp=YYYYMMDD_HHMMSS"
```

### Check quality
```bash
bq query "SELECT * FROM quarantine.employees"
```

### View logs
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

### Sync DLQ
```bash
./infra/sync_dlq.sh
```
ENDRUNBOOK

# Add to git
git add VALIDATION_RUNBOOK.md

# Commit
git commit -m "docs: add comprehensive validation runbook

added operational playbook with step-by-step procedures for:
- updating data when new csv files arrive
- complete system validation before demos
- disaster recovery with backup/restore
- data quality verification and auditing
- troubleshooting common issues
- quick reference commands

this serves as operations manual for running the system"

# Push
git push

echo ""
echo "✓ VALIDATION_RUNBOOK.md added to GitHub"
echo ""
echo "View at:"
echo "https://github.com/DE-diego-parra/globant-data-engineering-challenge/blob/main/VALIDATION_RUNBOOK.md"
