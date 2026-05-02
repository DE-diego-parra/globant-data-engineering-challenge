# Deployment Guide

## Prerequisites

- GCP account with billing enabled
- gcloud CLI authenticated
- Python 3.11+

## Infrastructure Setup

```bash
python infra/setup_infrastructure.py <project-id>
```

Automated setup:
- Enables BigQuery, Cloud Run, Cloud Storage, Cloud Build APIs
- Creates 4 BigQuery datasets
- Creates 3 Cloud Storage buckets
- Time: 2-3 minutes

## Deploy API

```bash
# Build image
gcloud builds submit --tag gcr.io/<project-id>/globant-api

# Deploy to Cloud Run
gcloud run deploy globant-api \
  --image gcr.io/<project-id>/globant-api \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=<project-id> \
  --memory 512Mi \
  --max-instances 5
```

## Load Data

```bash
./infra/update_pipeline.sh
```

Loads CSV → RAW → STAGING → MARTS → DLQ sync

## Verify

```bash
export SERVICE_URL=$(gcloud run services describe globant-api \
  --region us-central1 --format 'value(status.url)')

curl $SERVICE_URL/health
curl $SERVICE_URL/metrics/quarterly-hires
```

## Troubleshooting

### API 500 errors
```bash
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" --limit 20
```

### BigQuery issues
```bash
bq show <project>:globant_migration_raw.employees
```

## Rollback

```bash
gcloud run revisions list --service globant-api
gcloud run services update-traffic globant-api --to-revisions REVISION=100
```
