SELECT id, job 
FROM {{ source('raw_data', 'jobs') }}
