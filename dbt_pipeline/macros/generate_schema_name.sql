{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        globant_migration_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
