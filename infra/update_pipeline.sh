#!/bin/bash

export PROJECT_ID="globant-migration-1777674652"

echo "Updating complete pipeline..."

echo "[1/5] Loading to RAW..."
bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.employees \
  gs://globant-migration-1777674652-data-lake/raw/employees/*.csv

bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.departments \
  gs://globant-migration-1777674652-data-lake/raw/departments/*.csv

bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.jobs \
  gs://globant-migration-1777674652-data-lake/raw/jobs/*.csv

echo "[2/5] Updating STAGING..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_staging.employees\` AS
SELECT 
  id,
  TRIM(name) as name,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', datetime) as datetime,
  department_id,
  CAST(job_id AS INT64) as job_id,
  CURRENT_TIMESTAMP() as processed_at
FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
WHERE id IS NOT NULL
  AND name IS NOT NULL AND name != ''
  AND datetime IS NOT NULL
  AND department_id IS NOT NULL
  AND job_id IS NOT NULL
" > /dev/null

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_staging.departments\` AS
SELECT * FROM \`globant-migration-1777674652.globant_migration_raw.departments\`
WHERE id IS NOT NULL AND department IS NOT NULL
" > /dev/null

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_staging.jobs\` AS
SELECT * FROM \`globant-migration-1777674652.globant_migration_raw.jobs\`
WHERE id IS NOT NULL AND job IS NOT NULL
" > /dev/null

echo "[3/5] Updating QUARANTINE..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_quarantine.employees\` AS
SELECT 
  id,
  name,
  datetime,
  department_id,
  job_id,
  CASE 
    WHEN id IS NULL THEN 'Missing id'
    WHEN name IS NULL OR name = '' THEN 'Missing name'
    WHEN datetime IS NULL THEN 'Missing datetime'
    WHEN department_id IS NULL THEN 'Missing department_id'
    WHEN job_id IS NULL THEN 'Missing job_id'
    ELSE 'Multiple issues'
  END as rejection_reason,
  CURRENT_TIMESTAMP() as quarantine_at
FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
WHERE id IS NULL
   OR name IS NULL OR name = ''
   OR datetime IS NULL
   OR department_id IS NULL
   OR job_id IS NULL
" > /dev/null

echo "[4/5] Refreshing MARTS..."
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_marts.quarterly_hires\` AS
WITH qd AS (
  SELECT d.department, j.job, EXTRACT(QUARTER FROM TIMESTAMP(e.datetime)) as q, COUNT(*) as h
  FROM \`globant-migration-1777674652.globant_migration_staging.employees\` e
  JOIN \`globant-migration-1777674652.globant_migration_staging.departments\` d ON e.department_id = d.id
  JOIN \`globant-migration-1777674652.globant_migration_staging.jobs\` j ON e.job_id = j.id
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

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`globant-migration-1777674652.globant_migration_marts.dept_performance\` AS
WITH dh AS (
  SELECT d.id, d.department, COUNT(*) as hired
  FROM \`globant-migration-1777674652.globant_migration_staging.employees\` e
  JOIN \`globant-migration-1777674652.globant_migration_staging.departments\` d ON e.department_id = d.id
  WHERE EXTRACT(YEAR FROM TIMESTAMP(e.datetime)) = 2021
  GROUP BY d.id, d.department
),
mc AS (SELECT AVG(hired) as mean_hired FROM dh)
SELECT dh.id, dh.department, dh.hired, ROUND(mc.mean_hired,2) as mean_hired, ROUND(dh.hired - mc.mean_hired,2) as diff
FROM dh CROSS JOIN mc WHERE dh.hired > mc.mean_hired ORDER BY dh.hired DESC
" > /dev/null

echo "[5/5] Syncing DLQ..."
./infra/sync_dlq.sh > /dev/null

echo ""
echo "✓ Pipeline updated"
echo ""
bq query --use_legacy_sql=false "
SELECT 'RAW' as capa, COUNT(*) as total FROM \`globant-migration-1777674652.globant_migration_raw.employees\`
UNION ALL SELECT 'STAGING', COUNT(*) FROM \`globant-migration-1777674652.globant_migration_staging.employees\`
UNION ALL SELECT 'QUARANTINE', COUNT(*) FROM \`globant-migration-1777674652.globant_migration_quarantine.employees\`
UNION ALL SELECT 'MARTS/quarterly', COUNT(*) FROM \`globant-migration-1777674652.globant_migration_marts.quarterly_hires\`
"
