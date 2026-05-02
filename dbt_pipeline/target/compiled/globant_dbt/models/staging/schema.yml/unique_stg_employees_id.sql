
    
    

with dbt_test__target as (

  select id as unique_field
  from `globant-migration-1777674652`.`globant_migration_staging_staging`.`stg_employees`
  where id is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1


