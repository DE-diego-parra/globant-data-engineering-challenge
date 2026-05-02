{{ config(alias='jobs') }}
SELECT id, job FROM {{ source('raw_data', 'jobs') }}
