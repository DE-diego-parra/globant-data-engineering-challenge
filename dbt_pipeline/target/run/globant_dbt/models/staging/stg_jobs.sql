
  
    

    create or replace table `globant-migration-1777674652`.`globant_migration_staging_staging`.`stg_jobs`
      
    
    

    
    OPTIONS()
    as (
      SELECT id, job 
FROM `globant-migration-1777674652`.`globant_migration_raw`.`jobs`
    );
  