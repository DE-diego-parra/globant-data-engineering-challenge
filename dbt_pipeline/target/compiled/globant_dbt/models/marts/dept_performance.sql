WITH dept_hires AS (
    SELECT 
        d.id,
        d.department,
        COUNT(*) as hired
    FROM `globant-migration-1777674652`.`globant_migration_staging`.`employees` e
    JOIN `globant-migration-1777674652`.`globant_migration_staging`.`departments` d ON e.department_id = d.id
    WHERE EXTRACT(YEAR FROM TIMESTAMP(e.datetime)) = 2021
    GROUP BY d.id, d.department
),
mean_calc AS (
    SELECT AVG(hired) as mean_hired
    FROM dept_hires
)
SELECT 
    dh.id,
    dh.department,
    dh.hired,
    ROUND(mc.mean_hired, 2) as mean_hired,
    ROUND(dh.hired - mc.mean_hired, 2) as diff_from_mean
FROM dept_hires dh
CROSS JOIN mean_calc mc
WHERE dh.hired > mc.mean_hired
ORDER BY dh.hired DESC