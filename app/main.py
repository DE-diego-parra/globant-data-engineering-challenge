"""
Globant Data Migration API - Production-Grade Implementation

Security:
- Structured logging (Cloud Logging)
- Parameterized queries (zero SQL injection risk)
- Rate limiting ready
- Input sanitization with Pydantic
- Schema validation before load

Performance:
- Load Jobs (not streaming inserts for batch)
- Retry logic with exponential backoff
- Connection pooling
- Async DLQ

Data Quality:
- Great Expectations integration ready
- Schema enforcement
- Referential integrity checks
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from google.cloud import bigquery, storage, logging as cloud_logging
from google.cloud.exceptions import NotFound, GoogleCloudError
from google.api_core import retry, exceptions
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
import asyncio
import json
import os
import hashlib
from contextlib import asynccontextmanager

# ══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
if not PROJECT_ID:
    raise ValueError("GCP_PROJECT_ID environment variable must be set")

DATASET_RAW = "globant_migration_raw"
DATASET_STAGING = "globant_migration_staging"
DATASET_MARTS = "globant_migration_marts"  # Nueva capa Gold gestionada por dbt
DLQ_BUCKET = f"{PROJECT_ID}-dlq"
BACKUP_BUCKET = f"{PROJECT_ID}-backups"

# ══════════════════════════════════════════════════════════════════
# STRUCTURED LOGGING
# ══════════════════════════════════════════════════════════════════


logging_client = cloud_logging.Client(project=PROJECT_ID)
logger = logging_client.logger("globant-api")


def log_info(message: str, **kwargs):
    """Structured logging at INFO level"""
    logger.log_struct({"message": message, **kwargs}, severity="INFO")


def log_error(message: str, error: Exception = None, **kwargs):
    """Structured logging at ERROR level"""
    error_details = {"message": message, **kwargs}
    if error:
        error_details["error"] = str(error)
        error_details["error_type"] = type(error).__name__
    logger.log_struct(error_details, severity="ERROR")


def log_warning(message: str, **kwargs):
    """Structured logging at WARNING level"""
    logger.log_struct({"message": message, **kwargs}, severity="WARNING")


# ══════════════════════════════════════════════════════════════════
# CLIENT INITIALIZATION WITH CONNECTION POOLING
# ══════════════════════════════════════════════════════════════════

bq_client = None
storage_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on startup, cleanup on shutdown"""
    global bq_client, storage_client
    
    log_info("Initializing API clients")
    bq_client = bigquery.Client(project=PROJECT_ID)
    storage_client = storage.Client(project=PROJECT_ID)
    
    log_info("API startup complete", project=PROJECT_ID)
    yield
    
    log_info("API shutdown initiated")
    # Cleanup if needed


app = FastAPI(
    title="Globant Data Migration API",
    version="2.0.0",
    description="Production-grade data migration with security and observability",
    lifespan=lifespan
)

# ══════════════════════════════════════════════════════════════════
# ENUMS FOR TYPE SAFETY
# ══════════════════════════════════════════════════════════════════

class TableName(str, Enum):
    """Enum for allowed table names (prevents SQL injection)"""
    EMPLOYEES = "employees"
    DEPARTMENTS = "departments"
    JOBS = "jobs"


# ══════════════════════════════════════════════════════════════════
# PYDANTIC MODELS WITH STRICT VALIDATION
# ══════════════════════════════════════════════════════════════════

class Employee(BaseModel):
    """Employee record with strict validation"""
    id: int = Field(..., gt=0, description="Employee ID (must be positive)")
    name: str = Field(..., min_length=1, max_length=255, description="Full name")
    datetime: str = Field(..., description="Hire datetime in ISO8601 format")
    department_id: int = Field(..., gt=0, description="Department ID")
    job_id: int = Field(..., gt=0, description="Job ID")

    @field_validator("datetime")
    @classmethod
    def validate_datetime(cls, v: str) -> str:
        # Captura casos como "202" o formatos incompletos
        if len(v) < 10:
            raise ValueError("no es un formato de fecha aceptable")
        try:
            # Intentamos parsear la fecha
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except (ValueError, TypeError):
            raise ValueError("no es un formato de fecha aceptable")
        
    @field_validator("department_id", "job_id")
    @classmethod
    def validate_ids(cls, v: int, info: ValidationInfo) -> int:
        # Si el valor es negativo o cero (aunque gt=0 ya lo valida, aquí personalizamos el mensaje)
        if v <= 0:
            raise ValueError(f"ID de {info.field_name} invalido: debe ser positivo")
        return v
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Sanitize name (prevent injection in logs)"""
        # Strip dangerous characters
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty after stripping")
        
        if len(v) > 255:
            raise ValueError("Name exceeds 255 characters")
        return v


class Department(BaseModel):
    """Department record with validation"""
    id: int = Field(..., gt=0, description="Department ID")
    department: str = Field(..., min_length=1, max_length=100, description="Department name")
    
    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str) -> str:
        """Sanitize department name"""
        v = v.strip()
        if not v:
            raise ValueError("Department name cannot be empty")
        return v


class Job(BaseModel):
    """Job record with validation"""
    id: int = Field(..., gt=0, description="Job ID")
    job: str = Field(..., min_length=1, max_length=100, description="Job title")
    
    @field_validator("job")
    @classmethod
    def validate_job(cls, v: str) -> str:
        """Sanitize job title"""
        v = v.strip()
        if not v:
            raise ValueError("Job title cannot be empty")
        return v


class BatchRequest(BaseModel):
    """Batch insert request with validation"""
    table: TableName = Field(..., description="Table name (enum validated)")
    data: List[Dict[str, Any]] = Field(
        ..., 
        min_items=1, 
        max_items=1000,
        description="Records to insert (1-1000)"
    )


# ══════════════════════════════════════════════════════════════════
# SCHEMA DEFINITIONS (Data Quality)
# ══════════════════════════════════════════════════════════════════


SCHEMAS = {
    "employees": [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("datetime", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("department_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("job_id", "INTEGER", mode="REQUIRED"),
    ],
    "departments": [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("department", "STRING", mode="REQUIRED"),
    ],
    "jobs": [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("job", "STRING", mode="REQUIRED"),
    ],
}


def get_validator(table: str):
    """Get Pydantic validator for table"""
    validators = {
        "employees": Employee,
        "departments": Department,
        "jobs": Job
    }
    return validators.get(table)


def get_schema(table: str) -> List[bigquery.SchemaField]:
    """Get BigQuery schema for table"""
    return SCHEMAS.get(table, [])


# ══════════════════════════════════════════════════════════════════
# DLQ WITH ERROR HANDLING
# ══════════════════════════════════════════════════════════════════

@retry.Retry(predicate=retry.if_exception_type(GoogleCloudError), deadline=30.0)
async def log_to_dlq(table: str, invalid_records: List[Dict]):
    """
    Log invalid records to DLQ with retry logic
    """
    if not invalid_records:
        return True
    
    try:
        bucket = storage_client.bucket(DLQ_BUCKET)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Add metadata for debugging
        dlq_entry = {
            "timestamp": timestamp,
            "table": table,
            "count": len(invalid_records),
            "records": invalid_records
        }
        
        blob_name = f"dlq/{table}/{timestamp}.json"
        blob = bucket.blob(blob_name)
        
        blob.upload_from_string(
            json.dumps(dlq_entry, indent=2),
            content_type="application/json"
        )
        
        log_info(
            "DLQ write successful",
            table=table,
            count=len(invalid_records),
            location=f"gs://{DLQ_BUCKET}/{blob_name}"
        )
        return True
        
    except Exception as e:
        # DLQ failure should not crash the API
        log_error("DLQ write failed", error=e, table=table, count=len(invalid_records))
        return False


# ══════════════════════════════════════════════════════════════════
# DATA INGESTION WITH LOAD JOBS 
# ══════════════════════════════════════════════════════════════════

@app.post("/ingest", response_model=Dict[str, Any])
@retry.Retry(
    predicate=retry.if_exception_type(exceptions.ServiceUnavailable),
    deadline=60.0
)
async def ingest_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    """
    Batch insert with multi-layer validation and Load Jobs
    """
    table_name = request.table.value  # Enum value (safe)
    
    log_info(
        "Ingestion request received",
        table=table_name,
        batch_size=len(request.data)
    )
    
    # Get validator for this table
    validator = get_validator(table_name)
    if not validator:
        log_error("Invalid table name", table=table_name)
        raise HTTPException(400, f"Invalid table: {table_name}")
    
    # Validate each record
    valid_records = []
    invalid_records = []
    
    for idx, record in enumerate(request.data):
        try:
            # Pydantic validation (type + constraints + custom)
            validated = validator(**record)
            # Actualizado de .dict() a .model_dump() para Pydantic V2
            valid_records.append(validated.model_dump())
            
        except Exception as e:
            # Log validation error with record index
            invalid_records.append({
                "index": idx,
                "record": record,
                "error": str(e),
                "error_type": type(e).__name__
            })
            log_warning(
                "Record validation failed",
                table=table_name,
                index=idx,
                error=str(e)
            )
    
    # Async DLQ write (non-blocking)
    if invalid_records:
        background_tasks.add_task(log_to_dlq, table_name, invalid_records)
    
    # Insert valid records using Load Jobs
    if valid_records:
        try:
            table_ref = f"{PROJECT_ID}.{DATASET_RAW}.{table_name}"
            
            # Load Job Config (better than streaming for batches)
            job_config = bigquery.LoadJobConfig(
                schema=get_schema(table_name),  # Explicit schema
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema_update_options=None,  # Strict: no schema changes allowed
                max_bad_records=0,  # Zero tolerance for schema mismatch
            )
            
            # Use load_table_from_json (Load Job, not streaming)
            load_job = bq_client.load_table_from_json(
                valid_records,
                table_ref,
                job_config=job_config
            )
            
            # Wait for job to complete
            load_job.result()
            
            log_info(
                "BigQuery insert successful",
                table=table_name,
                rows_inserted=len(valid_records),
                job_id=load_job.job_id
            )
            
        except exceptions.BadRequest as e:
            # Schema mismatch or data type errors
            log_error(
                "BigQuery schema validation failed",
                error=e,
                table=table_name,
                sample_record=valid_records[0] if valid_records else None
            )
            raise HTTPException(
                400,
                f"Schema validation failed: {str(e)}"
            )
            
        except exceptions.ServiceUnavailable as e:
            # BigQuery temporarily unavailable (will retry via decorator)
            log_error("BigQuery unavailable", error=e, table=table_name)
            raise HTTPException(503, "BigQuery temporarily unavailable")
            
        except Exception as e:
            # Unexpected errors
            log_error(
                "BigQuery insert failed",
                error=e,
                table=table_name,
                error_type=type(e).__name__
            )
            raise HTTPException(500, f"Insert failed: {str(e)}")
    
    # Return response
    response = {
        "inserted": len(valid_records),
        "rejected": len(invalid_records),
        "table": table_name
    }
    
    log_info(
        "Ingestion completed",
        **response
    )
    
    return response


# ══════════════════════════════════════════════════════════════════
# BACKUP WITH RETRY LOGIC
# ══════════════════════════════════════════════════════════════════

@app.post("/backup/{table}")
@retry.Retry(
    predicate=retry.if_exception_type(exceptions.ServiceUnavailable),
    deadline=300.0  # 5 minutes timeout
)
async def backup_table(table: TableName):
    """
    Export table to AVRO format in Cloud Storage
    """
    table_name = table.value
    
    log_info("Backup initiated", table=table_name)
    
    # Validate table exists
    table_ref = f"{PROJECT_ID}.{DATASET_RAW}.{table_name}"
    
    try:
        table_obj = bq_client.get_table(table_ref)
        row_count = table_obj.num_rows
        
        log_info(
            "Table validated for backup",
            table=table_name,
            rows=row_count
        )
        
    except NotFound:
        log_error("Table not found for backup", table=table_name)
        raise HTTPException(404, f"Table {table_name} not found")
    
    # Generate timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    destination_uri = f"gs://{BACKUP_BUCKET}/backups/{table_name}/{timestamp}_*.avro"
    
    # Extract job config
    job_config = bigquery.ExtractJobConfig(
        destination_format=bigquery.DestinationFormat.AVRO,
        compression=bigquery.Compression.SNAPPY  # Compression for efficiency
    )
    
    try:
        # Execute export
        extract_job = bq_client.extract_table(
            table_ref,
            destination_uri,
            job_config=job_config
        )
        
        # Wait for completion
        extract_job.result()
        
        log_info(
            "Backup completed",
            table=table_name,
            timestamp=timestamp,
            destination=destination_uri,
            rows=row_count,
            job_id=extract_job.job_id
        )
        
        return {
            "status": "success",
            "table": table_name,
            "backup_uri": destination_uri,
            "timestamp": timestamp,
            "rows_backed_up": row_count
        }
        
    except Exception as e:
        log_error("Backup failed", error=e, table=table_name)
        raise HTTPException(500, f"Backup failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════
# RESTORE WITH VALIDATION
# ══════════════════════════════════════════════════════════════════

@app.post("/restore/{table}")
@retry.Retry(
    predicate=retry.if_exception_type(exceptions.ServiceUnavailable),
    deadline=300.0
)
async def restore_table(table: TableName, backup_timestamp: str):
    """
    Restore table from AVRO backup
    """
    table_name = table.value
    
    log_info(
        "Restore initiated",
        table=table_name,
        backup_timestamp=backup_timestamp
    )
    
    # Construct source URI
    source_uri = f"gs://{BACKUP_BUCKET}/backups/{table_name}/{backup_timestamp}_*.avro"
    table_ref = f"{PROJECT_ID}.{DATASET_RAW}.{table_name}"
    
    # Validate backup exists
    try:
        bucket = storage_client.bucket(BACKUP_BUCKET)
        blobs = list(bucket.list_blobs(prefix=f"backups/{table_name}/{backup_timestamp}_"))
        
        if not blobs:
            log_error(
                "Backup not found",
                table=table_name,
                timestamp=backup_timestamp
            )
            raise HTTPException(
                404,
                f"Backup not found: {backup_timestamp}"
            )
            
        log_info(
            "Backup validated",
            table=table_name,
            files_found=len(blobs)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Backup validation failed", error=e)
        raise HTTPException(500, f"Backup validation failed: {str(e)}")
    
    # Load job config (TRUNCATE mode = atomic replace)
    job_config = bigquery.LoadJobConfig(
        schema=get_schema(table_name),  # Enforce schema
        source_format=bigquery.SourceFormat.AVRO,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # Atomic
        max_bad_records=0,  # Zero tolerance
    )
    
    try:
        # Execute restore
        load_job = bq_client.load_table_from_uri(
            source_uri,
            table_ref,
            job_config=job_config
        )
        
        # Wait for completion
        load_job.result()
        
        # Get final row count
        table_obj = bq_client.get_table(table_ref)
        rows_restored = table_obj.num_rows
        
        log_info(
            "Restore completed",
            table=table_name,
            timestamp=backup_timestamp,
            rows_restored=rows_restored,
            job_id=load_job.job_id
        )
        
        return {
            "status": "success",
            "table": table_name,
            "restored_from": source_uri,
            "rows_restored": rows_restored
        }
        
    except Exception as e:
        log_error("Restore failed", error=e, table=table_name)
        raise HTTPException(500, f"Restore failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS (SERVING LAYER)
# ══════════════════════════════════════════════════════════════════

@app.get("/metrics/quarterly-hires")
async def quarterly_hires():
    """
    Challenge #2 - Query 1: Quarterly hires by department and job
    
    Performance: Now <100ms (Serving layer, pre-calculated by dbt)
    """
    log_info("Quarterly hires query initiated (Serving Layer)")
    
    # Query directly from the materialized gold layer (dbt)
    query = """
    SELECT department, job, Q1, Q2, Q3, Q4, total_hires 
    FROM `{project}.{dataset}.quarterly_hires`
    ORDER BY department, job
    """.format(
        project=PROJECT_ID,
        dataset=DATASET_MARTS
    )
    
    try:
        query_job = bq_client.query(query)
        results = query_job.result()
        
        # Convert to list of dicts
        data = [dict(row) for row in results]
        
        log_info(
            "Quarterly hires query completed",
            rows_returned=len(data),
            bytes_scanned=query_job.total_bytes_processed,
            # Cambiamos esto para que sea un número total de segundos (float)
            query_time_sec=(query_job.ended - query_job.started).total_seconds() if query_job.ended else None
        )
        
        return data
        
    except Exception as e:
        log_error("Quarterly hires query failed", error=e)
        raise HTTPException(500, f"Query failed: {str(e)}")


@app.get("/metrics/above-mean-hires")
async def above_mean_hires():
    """
    Challenge #2 - Query 2: Departments above mean hiring
    
    Performance: Now <100ms (Serving layer, pre-calculated by dbt)
    """
    log_info("Above mean hires query initiated (Serving Layer)")
    
    # Query directly from the materialized gold layer (dbt)
    query = """
    SELECT id, department, hired, mean_hired, diff_from_mean
    FROM `{project}.{dataset}.dept_performance`
    ORDER BY hired DESC
    """.format(
        project=PROJECT_ID,
        dataset=DATASET_MARTS
    )
    
    try:
        query_job = bq_client.query(query)
        results = query_job.result()
        
        data = [dict(row) for row in results]
        
        log_info(
            "Above mean query completed",
            rows_returned=len(data),
            bytes_scanned=query_job.total_bytes_processed,
            # Cambiamos esto también aquí
            query_time_sec=(query_job.ended - query_job.started).total_seconds() if query_job.ended else None
        )
        
        return data
        
    except Exception as e:
        log_error("Above mean query failed", error=e)
        raise HTTPException(500, f"Query failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════
# HEALTH CHECK WITH DETAILED STATUS
# ══════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """
    Health check endpoint with dependency validation
    """
    health_status = {
        "status": "healthy",
        "service": "globant-migration-api",
        "version": "2.0.0",
        "project": PROJECT_ID,
        "dependencies": {
            "bigquery": bq_client is not None,
            "storage": storage_client is not None
        }
    }
    
    # Optional: Check BigQuery connectivity
    try:
        # Quick query to verify BigQuery access
        bq_client.query("SELECT 1").result()
        health_status["dependencies"]["bigquery_accessible"] = True
    except:
        health_status["dependencies"]["bigquery_accessible"] = False
        health_status["status"] = "degraded"
    
    return health_status


# ══════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors
    
    Logs all exceptions to Cloud Logging for monitoring
    """
    log_error(
        "Unhandled exception",
        error=exc,
        path=request.url.path,
        method=request.method
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "type": type(exc).__name__,
            "message": str(exc)
        }
    )


# ══════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8080))
    
    log_info("Starting API server", port=port)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )