
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select department_id
from `globant-migration-1777674652`.`globant_migration_staging_staging`.`stg_employees`
where department_id is null



  
  
      
    ) dbt_internal_test