
  
    

    create or replace table `globant-migration-1777674652`.`globant_migration_staging`.`departments`
      
    
    

    
    OPTIONS()
    as (
      
SELECT id, department FROM `globant-migration-1777674652`.`globant_migration_raw`.`departments`
    );
  