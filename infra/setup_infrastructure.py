#!/usr/bin/env python3

import subprocess
import sys
import time

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else None
if not PROJECT_ID:
    print("Usage: python setup_infrastructure.py <project-id>")
    sys.exit(1)

APIS = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com"
]

DATASET_ID = "globant_migration"
REGION = "us-central1"

def run_command(cmd, check=True):
    print(f"\n→ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

print(f"Setting up infrastructure for project: {PROJECT_ID}")

print("\n=== Setting default project ===")
run_command(["gcloud", "config", "set", "project", PROJECT_ID])

print("\n=== Enabling required APIs ===")
for api in APIS:
    print(f"Enabling {api}...")
    run_command(["gcloud", "services", "enable", api])

time.sleep(10)

print("\n=== Creating BigQuery dataset ===")
run_command([
    "bq", "mk", "--dataset",
    f"{PROJECT_ID}:{DATASET_ID}"
], check=False)

print("\n=== Creating BigQuery tables ===")

employees_schema = "id:INTEGER,name:STRING,datetime:STRING,department_id:INTEGER,job_id:INTEGER"
run_command([
    "bq", "mk", "--table",
    f"{PROJECT_ID}:{DATASET_ID}.employees",
    employees_schema
])

departments_schema = "id:INTEGER,department:STRING"
run_command([
    "bq", "mk", "--table",
    f"{PROJECT_ID}:{DATASET_ID}.departments",
    departments_schema
])

jobs_schema = "id:INTEGER,job:STRING"
run_command([
    "bq", "mk", "--table",
    f"{PROJECT_ID}:{DATASET_ID}.jobs",
    jobs_schema
])

print("\n=== Creating Cloud Storage buckets ===")

run_command([
    "gcloud", "storage", "buckets", "create",
    f"gs://{PROJECT_ID}-dlq",
    f"--location={REGION}"
], check=False)

run_command([
    "gcloud", "storage", "buckets", "create",
    f"gs://{PROJECT_ID}-backups",
    f"--location={REGION}"
], check=False)

print("\n=== Infrastructure setup complete ===")
print(f"\nDataset: {PROJECT_ID}:{DATASET_ID}")
print(f"DLQ Bucket: gs://{PROJECT_ID}-dlq")
print(f"Backup Bucket: gs://{PROJECT_ID}-backups")
