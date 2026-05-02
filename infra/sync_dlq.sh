#!/bin/bash

export PROJECT_ID="globant-migration-1777674652"

echo "Syncing QUARANTINE to DLQ..."

bq query --use_legacy_sql=false --format=json "
SELECT 
  id, name, 
  CAST(datetime AS STRING) as datetime,
  department_id,
  CAST(job_id AS INT64) as job_id,
  rejection_reason,
  FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', quarantine_at) as quarantine_at
FROM \`${PROJECT_ID}.globant_migration_quarantine.employees\`
ORDER BY quarantine_at DESC
" > /tmp/quarantine.json

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
gcloud storage cp /tmp/quarantine.json \
  gs://${PROJECT_ID}-dlq/quarantine/employees/quarantine_${TIMESTAMP}.json

rm /tmp/quarantine.json

echo "✓ DLQ synced: quarantine_${TIMESTAMP}.json"
