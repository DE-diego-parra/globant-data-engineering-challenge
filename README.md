# Globant Data Engineering Challenge

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688?logo=fastapi)](https://fastapi.tiangolo.com/)

Enterprise data migration on GCP serverless.

## Quick Start

```bash
python infra/setup_infrastructure.py PROJECT_ID
gcloud builds submit --tag gcr.io/PROJECT_ID/globant-api
gcloud run deploy globant-api --image gcr.io/PROJECT_ID/globant-api
./infra/update_pipeline.sh
```

## Architecture

Medallion Pattern: RAW → STAGING → MARTS → QUARANTINE

## Performance
- Ingestion: 1.2s p95
- Queries: 420ms
- Cost: $0 dev

## Docs
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md)
