
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select job_id
from `globant-migration-1777674652`.`globant_migration_staging`.`employees`
where job_id is null



  
  
      
    ) dbt_internal_test