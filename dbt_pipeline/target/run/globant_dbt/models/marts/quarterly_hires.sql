
  
    

    create or replace table `globant-migration-1777674652`.`globant_migration_marts`.`quarterly_hires`
      
    
    

    
    OPTIONS()
    as (
      WITH quarterly_data AS (
    SELECT 
        d.department,
        j.job,
        EXTRACT(QUARTER FROM TIMESTAMP(e.datetime)) as quarter,
        COUNT(*) as hires
    FROM `globant-migration-1777674652`.`globant_migration_staging`.`employees` e
    JOIN `globant-migration-1777674652`.`globant_migration_staging`.`departments` d ON e.department_id = d.id
    JOIN `globant-migration-1777674652`.`globant_migration_staging`.`jobs` j ON e.job_id = j.id
    WHERE EXTRACT(YEAR FROM TIMESTAMP(e.datetime)) = 2021
    GROUP BY department, job, quarter
)
SELECT 
    department,
    job,
    COALESCE(MAX(IF(quarter = 1, hires, 0)), 0) as Q1,
    COALESCE(MAX(IF(quarter = 2, hires, 0)), 0) as Q2,
    COALESCE(MAX(IF(quarter = 3, hires, 0)), 0) as Q3,
    COALESCE(MAX(IF(quarter = 4, hires, 0)), 0) as Q4,
    SUM(hires) as total_hires
FROM quarterly_data
GROUP BY department, job
ORDER BY department, job
    );
  