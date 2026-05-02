#!/bin/bash

# Salir inmediatamente si algún comando falla
set -e 

echo "========================================================"
echo "🚀 INICIANDO PIPELINE DE DATOS (MEDALLION ARCHITECTURE)"
echo "========================================================"

echo ""
echo "=== [1/4] CARGANDO CSV A CAPA RAW (BRONZE) ==="
# Carga de Employees
bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.employees \
  gs://globant-migration-1777674652-data-lake/raw/employees/*.csv

# (Si en tu script original cargabas departments y jobs aquí, los mantienes igual)
bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.departments \
  gs://globant-migration-1777674652-data-lake/raw/departments/*.csv

bq load --source_format=CSV --skip_leading_rows=1 --autodetect --replace \
  globant-migration-1777674652:globant_migration_raw.jobs \
  gs://globant-migration-1777674652-data-lake/raw/jobs/*.csv

echo ""
echo "=== [2/4] EJECUTANDO DBT: TRANSFORMACIONES (SILVER & GOLD) ==="
# Entramos a la carpeta de dbt para ejecutar los modelos
cd dbt_pipeline
dbt run

echo ""
echo "=== [3/4] EJECUTANDO DBT: TESTS DE CALIDAD DE DATOS ==="
dbt test

# Volvemos a la raíz del proyecto
cd ..

echo ""
echo "=== [4/4] SINCRONIZANDO CUARENTENA CON DLQ (CLOUD STORAGE) ==="
# Tu script original para el backup JSON de la cuarentena
./infra/sync_dlq.sh

echo ""
echo "✅ PIPELINE COMPLETADO EXITOSAMENTE"
echo "========================================================"
