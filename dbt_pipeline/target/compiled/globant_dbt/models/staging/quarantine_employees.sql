

SELECT 
    id,
    name,
    datetime as original_datetime_string,
    department_id,
    job_id,
    CASE 
        WHEN id IS NULL THEN 'Missing ID'
        WHEN name IS NULL OR TRIM(name) = '' THEN 'Missing or empty Name'
        WHEN SAFE_CAST(datetime AS TIMESTAMP) IS NULL THEN CONCAT('Invalid datetime format: ', COALESCE(datetime, 'NULL'))
        WHEN department_id IS NULL THEN 'Missing Department ID'
        WHEN job_id IS NULL THEN 'Missing Job ID'
    END as rejection_reason,
    CURRENT_TIMESTAMP() as quarantined_at
FROM `globant-migration-1777674652`.`globant_migration_raw`.`employees`
WHERE id IS NULL 
   OR name IS NULL OR TRIM(name) = ''
   OR SAFE_CAST(datetime AS TIMESTAMP) IS NULL
   OR department_id IS NULL 
   OR job_id IS NULL