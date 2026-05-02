# Validation Runbook

Operational playbooks for different scenarios with step-by-step validation procedures.

## Scenario 1: New CSV Files Arrive

**When:** Client sends updated CSV files

### Step 1: Upload to Cloud Storage
```bash
export PROJECT_ID="globant-migration-1777674652"

gcloud storage cp hired_employees.csv gs://${PROJECT_ID}-data-lake/raw/employees/
gcloud storage cp departments.csv gs://${PROJECT_ID}-data-lake/raw/departments/
gcloud storage cp jobs.csv gs://${PROJECT_ID}-data-lake/raw/jobs/
```

**Verify:**
```bash
gcloud storage ls gs://${PROJECT_ID}-data-lake/raw/*/
```

### Step 2: Update Pipeline
```bash
./infra/update_pipeline.sh
```

**Time:** 30-60 seconds

### Step 3: Verify Loaded
```bash
bq query --use_legacy_sql=false "
SELECT 'RAW' as layer, COUNT(*) as records FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
UNION ALL SELECT 'STAGING', COUNT(*) FROM \`${PROJECT_ID}.globant_migration_staging.employees\`
UNION ALL SELECT 'QUARANTINE', COUNT(*) FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
"
```

### Step 4: Check MARTS
```bash
bq query --use_legacy_sql=false "SELECT * FROM \`${PROJECT_ID}.globant_migration_marts.quarterly_hires\` LIMIT 5"
```

### Step 5: Refresh Looker Studio

Open dashboard and click refresh button.

---

## Scenario 2: Validate Complete System

**When:** Before demo or presentation

### Step 1: API Health
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

### Step 6: Verify All Datasets
```bash
bq ls ${PROJECT_ID}: | grep globant_migration
```

✅ Expected: 4 datasets

---

## Scenario 3: Disaster Recovery

**When:** Need to restore from backup

### Step 1: Create Backup
```bash
curl -X POST $SERVICE_URL/backup/employees
```

Save timestamp from response (e.g., 20240502_143022)

### Step 2: Simulate Data Loss
```bash
bq query --use_legacy_sql=false "DELETE FROM \`${PROJECT_ID}.globant_migration_raw.employees\` WHERE id > 4540"
```

### Step 3: Verify Deletion
```bash
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`"
```

### Step 4: Restore
```bash
curl -X POST "$SERVICE_URL/restore/employees?backup_timestamp=20240502_143022"
```

### Step 5: Verify Recovery
```bash
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`"
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
FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
"
```

### Step 2: Count by Reason
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
LEFT JOIN \`${PROJECT_ID}.globant_migration_staging.departments\` d ON e.department_id = d.id
WHERE d.id IS NULL
"
```

✅ Expected: 0

### Step 4: Quality Percentage
```bash
bq query --use_legacy_sql=false "
WITH m AS (
  SELECT 
    (SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_raw.employees\`) as raw,
    (SELECT COUNT(*) FROM \`${PROJECT_ID}.globant_migration_staging.employees\`) as valid
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
bq show ${PROJECT_ID}:globant_migration_raw.employees
bq show --schema ${PROJECT_ID}:globant_migration_raw.employees
```

### Pipeline Update Fails

Run steps individually:
```bash
bq load --replace ${PROJECT_ID}:globant_migration_raw.employees gs://${PROJECT_ID}-data-lake/raw/employees/*.csv
bq query "CREATE OR REPLACE TABLE staging.employees AS SELECT * FROM raw.employees WHERE ..."
```

---

## Quick Reference

### Update when CSV arrives
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
bq query "SELECT * FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`"
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

| Operation | Expected |
|-----------|----------|
| Health check | <100ms |
| Ingest 10 | <800ms |
| Ingest 1000 | <1500ms |
| Quarterly query | <500ms |
| Above mean | <500ms |
| Pipeline update | 30-60s |

---

## Emergency Procedures

### Rollback Cloud Run
```bash
gcloud run revisions list --service globant-api
gcloud run services update-traffic globant-api --to-revisions PREVIOUS=100
```

### Restore BigQuery
```bash
LATEST=$(gcloud storage ls gs://${PROJECT_ID}-backups/backups/employees/ | tail -1)
bq load --source_format=AVRO --replace ${PROJECT_ID}:globant_migration_raw.employees $LATEST
```

### Clear QUARANTINE
```bash
bq query "DELETE FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\` WHERE TRUE"
```
