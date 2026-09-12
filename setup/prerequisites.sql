-- ─────────────────────────────────────────────────────────────
-- Prerequisites for text-to-sql-agent bundle
-- Run once in SQL Editor BEFORE deploying the bundle.
-- ─────────────────────────────────────────────────────────────
-- This script checks/creates the UC catalog, schemas, and volume
-- required by the Supervisor Agent's Genie Space subagent.
--
-- NOTE: The Genie Space itself must be created separately via the
-- Databricks UI (Genie > Create Genie Space) and its ID passed as
-- the `genie_space_id` bundle variable.
--
-- CUSTOMIZATION: Change the SET variables below to match your
-- environment. All subsequent statements use these values.
-- ─────────────────────────────────────────────────────────────

-- >>> Change these values to match your environment <<<
SET VAR catalog_name = 'nse_stock_research';
SET VAR silver_schema = 'silver';
SET VAR gold_schema = 'gold';

-- 1. Catalog (skip if already created by the ingestion bundle)
CREATE CATALOG IF NOT EXISTS IDENTIFIER('${catalog_name}')
  COMMENT 'Stock market research: prices, fundamentals, and news';

-- 2. Schemas
CREATE SCHEMA IF NOT EXISTS IDENTIFIER('${catalog_name}.${silver_schema}');
CREATE SCHEMA IF NOT EXISTS IDENTIFIER('${catalog_name}.${gold_schema}');

-- 3. Verify key tables exist (informational — creates nothing)
--    These tables are populated by the data pipeline.
--    If they don't exist yet, the Genie Space will return empty results.
SELECT '${silver_schema}.companies' AS table_name, COUNT(*) AS row_count
FROM IDENTIFIER('${catalog_name}.${silver_schema}.companies')
UNION ALL
SELECT '${gold_schema}.gold_price_daily_agg', COUNT(*)
FROM IDENTIFIER('${catalog_name}.${gold_schema}.gold_price_daily_agg');

-- 4. Embedding model check (informational)
--    The Supervisor Agent's Examples feature requires qwen3-embedding-0-6b.
--    If this query returns no rows, ask your workspace admin to enable it
--    under Settings > AI/Model Serving, or via the Previews page.
SELECT model_name, model_provider
FROM system.information_schema.models
WHERE model_name ILIKE '%qwen3%embedding%'
LIMIT 5;
