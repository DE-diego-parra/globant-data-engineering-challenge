#!/bin/bash

export PROJECT_ID="globant-migration-1777674652"

echo "Updating complete pipeline..."

echo "[1/5] Loading to RAW..."
bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  ${PROJECT_ID}:globant_migration_raw.employees \
  gs://${PROJECT_ID}-data-lake/raw/employees/*.csv

bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  ${PROJECT_ID}:globant_migration_raw.departments \
  gs://${PROJECT_ID}-data-lake/raw/departments/*.csv

bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  ${PROJECT_ID}:globant_migration_raw.jobs \
  gs://${PROJECT_ID}-data-lake/raw/jobs/*.csv

echo "[2/5] Updating STAGING..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.globant_migration_staging.employees\` AS
SELECT id, TRIM(name) as name, FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', datetime) as datetime,
       department_id, CAST(job_id AS INT64) as job_id
FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
WHERE id IS NOT NULL AND name IS NOT NULL AND name != ''
  AND datetime IS NOT NULL AND department_id IS NOT NULL AND job_id IS NOT NULL
" > /dev/null

echo "[3/5] Updating QUARANTINE..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.globant_migration_quarantine.employees\` AS
SELECT *, CASE 
    WHEN job_id IS NULL THEN 'Missing job_id'
    WHEN name IS NULL THEN 'Missing name'
    ELSE 'Multiple issues'
  END as rejection_reason, CURRENT_TIMESTAMP() as quarantine_at
FROM \`${PROJECT_ID}.globant_migration_raw.employees\`
WHERE job_id IS NULL OR name IS NULL OR name = ''
" > /dev/null

echo "[4/5] Refreshing MARTS..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.globant_migration_marts.quarterly_hires\` AS
WITH qd AS (
  SELECT d.department, j.job, EXTRACT(QUARTER FROM TIMESTAMP(e.datetime)) as q, COUNT(*) as h
  FROM \`${PROJECT_ID}.globant_migration_staging.employees\` e
  JOIN \`${PROJECT_ID}.globant_migration_staging.departments\` d ON e.department_id = d.id
  JOIN \`${PROJECT_ID}.globant_migration_staging.jobs\` j ON e.job_id = j.id
  WHERE EXTRACT(YEAR FROM TIMESTAMP(e.datetime)) = 2021
  GROUP BY d.department, j.job, q
)
SELECT department, job,
  COALESCE(MAX(IF(q=1,h,0)),0) as Q1,
  COALESCE(MAX(IF(q=2,h,0)),0) as Q2,
  COALESCE(MAX(IF(q=3,h,0)),0) as Q3,
  COALESCE(MAX(IF(q=4,h,0)),0) as Q4,
  SUM(h) as total_hires
FROM qd GROUP BY department, job ORDER BY department, job
" > /dev/null

echo "[5/5] Syncing DLQ..."
./infra/sync_dlq.sh > /dev/null

echo "✓ Pipeline updated successfully"
