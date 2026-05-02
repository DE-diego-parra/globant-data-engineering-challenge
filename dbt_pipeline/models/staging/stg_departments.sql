{{ config(alias='departments') }}
SELECT id, department FROM {{ source('raw_data', 'departments') }}
