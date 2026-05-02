# Scripts Documentation

## setup_infrastructure.py

```bash
python infra/setup_infrastructure.py <project-id>
```

Automated GCP setup:
- Enable APIs
- Create BigQuery datasets
- Create Cloud Storage buckets
- Time: 2-3 minutes

## update_pipeline.sh

```bash
./infra/update_pipeline.sh
```

Complete pipeline refresh:
1. Load CSV to RAW
2. Validate to STAGING
3. Refresh MARTS
4. Sync QUARANTINE to DLQ

Time: 30-60 seconds  
Idempotent: Safe to run multiple times

## sync_dlq.sh

```bash
./infra/sync_dlq.sh
```

Export QUARANTINE to Cloud Storage as JSON.

Output: `gs://project-dlq/quarantine/employees/quarantine_TIMESTAMP.json`

## load_historical_data.py

```bash
python infra/load_historical_data.py <project> <csv> <table>
```

Batch load single CSV file to BigQuery.
