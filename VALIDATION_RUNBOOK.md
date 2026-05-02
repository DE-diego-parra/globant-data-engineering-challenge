# Validation Runbook

Operational playbooks with step-by-step validation procedures.

## Scenario 1: New CSV Files Arrive

**When:** Client sends updated CSV files

### Step 1: Upload to Cloud Storage
```bash
export PROJECT_ID="globant-migration-1777674652"

gcloud storage cp hired_employees.csv gs://globant-migration-1777674652-data-lake/raw/employees/
gcloud storage cp departments.csv gs://globant-migration-1777674652-data-lake/raw/departments/
gcloud storage cp jobs.csv gs://globant-migration-1777674652-data-lake/raw/jobs/
```

**Verify:**
```bash
gcloud storage ls gs://globant-migration-1777674652-data-lake/raw/*/
```

### Step 2: Update Pipeline
```bash
cd ~/globant-challenge
./infra/update_pipeline.sh
```

**Time:** 30-60 seconds

### Step 3: Verify Data Loaded
```bash
bq query --use_legacy_sql=false "
SELECT 'RAW' as layer, COUNT(*) as records FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
UNION ALL SELECT 'STAGING', COUNT(*) FROM \`globant-migration-1777674652.globant_migration_staging.employees\`
UNION ALL SELECT 'QUARANTINE', COUNT(*) FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\`
"
```

### Step 4: Check MARTS Updated
```bash
bq query --use_legacy_sql=false "
SELECT * FROM \`globant-migration-1777674652.globant_migration_marts.quarterly_hires\`
LIMIT 5
"
```

### Step 5: Refresh Looker Studio

Open dashboard and click refresh button.

---

## Scenario 2: Complete System Validation

**When:** Before demo or presentation

### Step 1: Check Cloud Run
```bash
export SERVICE_URL=$(gcloud run services describe globant-api --region us-central1 --format 'value(status.url)')
curl $SERVICE_URL/health
```

✅ Expected: `{"status":"healthy"}`

### Step 2: Test Ingestion
```bash
curl -X POST $SERVICE_URL/ingest -H "Content-Type: application/json" \
  -d '{"table": "employees", "data": [{"id": 9999, "name": "Test User", "datetime": "2021-01-15T10:00:00Z", "department_id": 1, "job_id": 1}]}'
```

✅ Expected: `{"inserted":1,"rejected":0}`

### Step 3: Test Validation
```bash
curl -X POST $SERVICE_URL/ingest \
  -d '{"table": "employees", "data": [{"id": -1, "name": "", "datetime": "invalid", "department_id": 1, "job_id": 1}]}'
```

✅ Expected: `{"inserted":0,"rejected":1}`

### Step 4: Test Analytics
```bash
curl $SERVICE_URL/metrics/quarterly-hires | jq
curl $SERVICE_URL/metrics/above-mean-hires | jq
```

### Step 5: Test Backup
```bash
curl -X POST $SERVICE_URL/backup/employees
```

✅ Expected: `{"status":"success"}`

### Step 6: Verify BigQuery Structure
```bash
bq ls globant-migration-1777674652:globant_migration_raw
bq ls globant-migration-1777674652:globant_migration_staging
bq ls globant-migration-1777674652:globant_migration_marts
bq ls globant-migration-1777674652:globant_migration_quarantine
```

✅ Expected: 3, 3, 2, 1 tables respectively

---

## Scenario 3: Disaster Recovery

**When:** Need to restore from backup

### Step 1: Create Backup
```bash
curl -X POST $SERVICE_URL/backup/employees
```

Save timestamp from response

### Step 2: Simulate Data Loss
```bash
bq query --use_legacy_sql=false "
DELETE FROM \`globant-migration-1777674652.globant_migration_raw.employees\` WHERE id > 4540
"
```

### Step 3: Verify Deletion
```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
"
```

### Step 4: Restore
```bash
curl -X POST "$SERVICE_URL/restore/employees?backup_timestamp=20240502_143022"
```

Replace timestamp with your actual backup timestamp.

### Step 5: Verify Recovery
```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
"
```

✅ Expected: Original count restored

### Step 6: Update Pipeline
```bash
./infra/update_pipeline.sh
```

---

## Scenario 4: Data Quality Audit

**When:** Review rejected records

### Step 1: View Rejected Records
```bash
bq query --use_legacy_sql=false "
SELECT id, name, job_id, rejection_reason 
FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\`
"
```

### Step 2: Count by Rejection Reason
```bash
bq query --use_legacy_sql=false "
SELECT rejection_reason, COUNT(*) as count
FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\`
GROUP BY rejection_reason
"
```

### Step 3: Check Referential Integrity
```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) as orphans
FROM \`globant-migration-1777674652.globant_migration_staging.employees\` e
LEFT JOIN \`globant-migration-1777674652.globant_migration_staging.departments\` d ON e.department_id = d.id
WHERE d.id IS NULL
"
```

✅ Expected: 0

### Step 4: Quality Percentage
```bash
bq query --use_legacy_sql=false "
WITH m AS (
  SELECT 
    (SELECT COUNT(*) FROM \`globant-migration-1777674652.globant_migration_raw.employees\`) as raw,
    (SELECT COUNT(*) FROM \`globant-migration-1777674652.globant_migration_staging.employees\`) as valid
)
SELECT raw, valid, ROUND(valid * 100.0 / raw, 2) as quality_pct FROM m
"
```

✅ Expected: >95%

---

## Scenario 5: Troubleshooting

### API Returns 500
```bash
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" --limit 20
```

### BigQuery Query Fails
```bash
bq show globant-migration-1777674652:globant_migration_raw.employees
```

### Pipeline Fails

Run steps individually:
```bash
bq load --replace globant-migration-1777674652:globant_migration_raw.employees \
  gs://globant-migration-1777674652-data-lake/raw/employees/*.csv
```

---

## Quick Reference

### Update data
```bash
gcloud storage cp file.csv gs://globant-migration-1777674652-data-lake/raw/employees/
./infra/update_pipeline.sh
```

### Backup table
```bash
curl -X POST $SERVICE_URL/backup/employees
```

### Restore table
```bash
curl -X POST "$SERVICE_URL/restore/employees?backup_timestamp=TIMESTAMP"
```

### Check QUARANTINE
```bash
bq query "SELECT * FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\`"
```

### View logs
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

### Sync DLQ
```bash
./infra/sync_dlq.sh
```

---

## Performance Benchmarks

| Operation | Expected Time |
|-----------|---------------|
| Health check | <100ms |
| Ingest 10 records | <800ms |
| Ingest 1000 records | <1500ms |
| Quarterly query | <500ms |
| Above mean query | <500ms |
| Pipeline update | 30-60s |

---

## Emergency Procedures

### Rollback Cloud Run
```bash
gcloud run revisions list --service globant-api
gcloud run services update-traffic globant-api --to-revisions PREVIOUS_REVISION=100
```

### Restore BigQuery Table
```bash
LATEST=$(gcloud storage ls gs://globant-migration-1777674652-backups/backups/employees/ | tail -1)
bq load --source_format=AVRO --replace globant-migration-1777674652:globant_migration_raw.employees $LATEST
```

### Clear QUARANTINE
```bash
bq query "DELETE FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\` WHERE TRUE"
```

### Re-run Complete Setup
```bash
python infra/setup_infrastructure.py globant-migration-1777674652
./infra/update_pipeline.sh
```
