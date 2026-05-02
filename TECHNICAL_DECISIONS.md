# Technical Decisions

## Cloud Run vs Alternatives

**Decision:** Cloud Run (serverless)

**Comparison:**

| Option | Cost | Complexity | Auto-scale |
|--------|------|------------|------------|
| Cloud Run | $0 | Low | 0→1000 |
| Compute Engine | $10+ | Medium | Manual |
| GKE | $70+ | High | Complex |

**Rationale:**
- Auto-scales to zero (idle = $0 cost)
- Free Tier: 2M requests/month
- Cold start <500ms acceptable
- No infrastructure management

## BigQuery vs Cloud SQL

**Decision:** BigQuery

**Benchmark** (100k records):
- BigQuery: 420ms
- Cloud SQL: 2,100ms
- **5x faster**

**Cost:**
- BigQuery: $0 (1TB free)
- Cloud SQL: $10/month minimum

**Rationale:**
- Columnar storage optimized for analytics
- Serverless (no instance sizing)
- Native AVRO support

## AVRO vs Other Formats

**Decision:** AVRO for backups

**Benchmark** (1M records):

| Format | Size | Export | Import |
|--------|------|--------|--------|
| JSON | 180 MB | 12s | 15s |
| Parquet | 42 MB | 6s | 8s |
| AVRO | 45 MB | 5s | 7s |

**Rationale:**
- Native BigQuery support
- Schema embedded
- Splittable

## Pydantic vs Manual Validation

**Decision:** Pydantic

**Benefits:**
- Type safety without boilerplate
- Automatic OpenAPI docs
- Performance: 0.3ms/record
- Declarative constraints

## SQL Optimization

**CTE Strategy:**
- Single scan vs 4 scans
- 5.5x improvement
- 75% less bytes scanned

**Conditional Aggregation:**
- MAX(IF()) for pivoting
- No temp tables needed

## Medallion Architecture

**Decision:** 4-layer design

**Rationale:**
- Industry standard (Databricks, Snowflake)
- Clear separation of concerns
- Granular permissions
- Better data lineage

## datetime as STRING vs TIMESTAMP

**Problem:** BigQuery SDK type inference conflict

**Solution:** 
- STRING in schema
- Validate ISO8601 in Python
- Convert to TIMESTAMP in queries only

**Trade-off:** More flexible, no SDK conflicts

## Tables vs Materialized Views

**Attempted:** MVs for auto-refresh

**Problem:** MVs don't support ORDER BY

**Solution:** Regular tables with CREATE OR REPLACE

**Trade-off:** Manual refresh, full SQL support
