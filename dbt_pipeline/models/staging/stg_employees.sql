{{ config(alias='employees') }}

SELECT 
    id, 
    TRIM(name) as name, 
    FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', SAFE_CAST(datetime AS TIMESTAMP)) as datetime, 
    department_id, 
    CAST(job_id AS INT64) as job_id,
    CURRENT_TIMESTAMP() as processed_at
FROM {{ source('raw_data', 'employees') }}
WHERE id IS NOT NULL 
  AND name IS NOT NULL 
  AND SAFE_CAST(datetime AS TIMESTAMP) IS NOT NULL
  AND department_id IS NOT NULL 
  AND job_id IS NOT NULL
