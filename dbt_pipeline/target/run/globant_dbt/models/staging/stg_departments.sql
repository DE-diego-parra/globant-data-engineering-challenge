
  
    

    create or replace table `globant-migration-1777674652`.`globant_migration_staging_staging`.`stg_departments`
      
    
    

    
    OPTIONS()
    as (
      SELECT id, department 
FROM `globant-migration-1777674652`.`globant_migration_raw`.`departments`
    );
  