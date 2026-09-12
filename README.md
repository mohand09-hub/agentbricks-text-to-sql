# NSE Stock Research — Text-to-SQL Agent

Natural language interface to query NSE stock market data using a Databricks Supervisor Agent with a Genie Space subagent.

## Architecture

```
User Question
     │
     ▼
Supervisor Agent ("NSE Stock Research Assistant")
     │  routes query via description matching
     ▼
Genie Space (subagent / tool: "nse-stock-sql")
     │  translates NL → SQL
     ▼
Unity Catalog Tables (nse_stock_research.silver.*, nse_stock_research.gold.*)
     │
     ▼
Results + Citations → User
```

**Components:**

* **Supervisor Agent** — orchestrates queries, routes to the Genie Space subagent
* **Genie Space** (ID: `01f1ae96b6b21b658c75b4c44c6dae06`) — translates natural language to SQL over the NSE data
* **Unity Catalog** (`nse_stock_research`) — silver and gold tables populated by the ingestion pipeline

## Bundle Structure

```
text-to-sql-agent/
├── databricks.yml                    # DAB config: targets (dev/prod), variables
├── resources/
│   └── setup_job.job.yml              # Job definition: runs the setup script
├── scripts/
│   └── setup_supervisor_agent.py     # Parameterized setup script (REST API)
├── config/
│   └── agent_config.json              # Agent metadata, tool config, examples
├── setup/
│   └── prerequisites.sql              # Pre-deploy SQL: catalog/schema checks
├── setup_supervisor_agent.py          # Original standalone script (dev)
├── .gitignore
└── README.md
```

## Prerequisites

Before deploying this bundle, ensure the following are in place in the target workspace:

### 1. Unity Catalog

The `nse_stock_research` catalog and its silver/gold schemas must exist. If the ingestion bundle (`nse-stock-research`) has already been deployed, these already exist. If not, run:

```sql
-- Run in SQL Editor
CREATE CATALOG IF NOT EXISTS nse_stock_research
  COMMENT 'NSE Stock Market Research: prices, fundamentals, and news';

CREATE SCHEMA IF NOT EXISTS nse_stock_research.silver;
CREATE SCHEMA IF NOT EXISTS nse_stock_research.gold;
```

Or run the bundled prerequisites script:

```sql
-- Run setup/prerequisites.sql in SQL Editor
-- Change the SET VAR values at the top to match your environment
```

### 2. Genie Space

A Genie Space must be created in the target workspace. This is a workspace-specific resource that cannot be bundled — create it manually:

1. Go to **Genie** in the left navigation
2. Click **Create Genie Space**
3. Select the Unity Catalog tables:
   - `nse_stock_research.silver.companies`
   - `nse_stock_research.gold.gold_price_daily_agg`
4. Add table descriptions and column comments for better SQL generation
5. Publish the Genie Space
6. Copy the Genie Space ID from the URL (e.g., `01f1ae96b6b21b658c75b4c44c6dae06`)
7. Pass this ID as the `genie_space_id` bundle variable during deployment

### 3. Embedding Model (for Examples)

Quality examples require the `qwen3-embedding-0-6b` model. If it is not enabled in your workspace:

1. Go to **Settings** > **AI/Model Serving** (or the **Previews** page)
2. Enable the `qwen3-embedding-0-6b` model
3. If the model is unavailable, examples can be added later via the agent UI

To check if the model is available:

```sql
SELECT model_name, model_provider
FROM system.information_schema.models
WHERE model_name ILIKE '%qwen3%embedding%'
LIMIT 5;
```

### 4. Supervisor Agent Tier

The free tier allows **1 Supervisor Agent** per workspace. For production with multiple agents, ensure your workspace has the appropriate tier. To check existing agents:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
print(w.api_client.do("GET", "/api/2.1/supervisor-agents"))
```

## Deployment

### Install the Databricks CLI

```bash
# If not already installed
pip install databricks-sdk
# Download CLI from: https://docs.databricks.com/dev-tools/cli/databricks-cli.html
```

### Authenticate

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
```

### Deploy to Development

```bash
# From the text-to-sql-agent/ directory
databricks bundle deploy --target dev
```

This deploys using the default Genie Space ID (`01f1ae96b6b21b658c75b4c44c6dae06`) and agent display name (`NSE Stock Research Assistant`).

### Deploy to Production

```bash
# From the text-to-sql-agent/ directory

# Option 1: Use default prod config (update databricks.yml prod target first)
databricks bundle deploy --target prod

# Option 2: Override variables at deploy time
databricks bundle deploy --target prod \
  --var="genie_space_id=<prod-genie-space-id>" \
  --var="catalog=<prod-catalog>" \
  --var="silver_schema=<prod-silver-schema>" \
  --var="gold_schema=<prod-gold-schema>"
```

### Run the Setup Job

After deploying the bundle, run the setup job to create (or update) the Supervisor Agent:

```bash
# Run in dev
databricks bundle run setup_supervisor_agent --target dev

# Run in prod
databricks bundle run setup_supervisor_agent --target prod
```

The job is idempotent — it will find existing agents and tools and skip creation if they already exist.

## Configuration

### Bundle Variables (`databricks.yml`)

| Variable | Description | Default | Required |
| --- | --- | --- | --- |
| `catalog` | UC catalog for data tables | `nse_stock_research` | No |
| `silver_schema` | Schema name for silver tables | `silver` | No |
| `gold_schema` | Schema name for gold tables | `gold` | No |
| `genie_space_id` | Genie Space ID (workspace-specific) | `01f1ae96b6b21b658c75b4c44c6dae06` | Yes |
| `agent_display_name` | Supervisor Agent display name | `NSE Stock Research Assistant` | No |

Override at deploy time:

```bash
databricks bundle deploy --target prod \
  --var="catalog=stock_research_prod" \
  --var="silver_schema=silver" \
  --var="gold_schema=gold" \
  --var="genie_space_id=<prod-genie-space-id>"
```

### Agent Config (`config/agent_config.json`)

| Field | Description |
| --- | --- |
| `display_name` | Agent display name (overridden by bundle variable) |
| `description` | Short description shown in the workspace |
| `instructions` | System instructions for the Supervisor Agent |
| `tool.tool_id` | Unique identifier for the Genie Space tool |
| `tool.description` | Description used by the supervisor for routing |
| `tool.genie_space_id` | Genie Space ID (overridden by CLI argument) |
| `examples` | Quality examples (question + guidelines) |

**Template placeholders:** The config file supports `{{catalog}}`, `{{silver_schema}}`, and `{{gold_schema}}` placeholders in any string field. These are replaced at runtime with the values passed via `--catalog`, `--silver-schema`, and `--gold-schema` CLI arguments. For example:

```json
"guidelines": ["Query {{catalog}}.{{silver_schema}}.companies, order by market_cap DESC"]
```

expands to `Query nse_stock_research.silver.companies, order by market_cap DESC` when using the defaults.

## Data Available

| Table (default) | Schema variable | Description |
| --- | --- | --- |
| `{{catalog}}.{{silver_schema}}.companies` | `silver_schema` | Company profiles + fundamentals (market_cap, trailing_pe, sector) |
| `{{catalog}}.{{silver_schema}}.price_snapshots` | `silver_schema` | Daily OHLCV prices |
| `{{catalog}}.{{gold_schema}}.gold_price_daily_agg` | `gold_schema` | Daily aggregates with % changes |
| `{{catalog}}.{{silver_schema}}.news_articles` | `silver_schema` | News with sentiment |

Table names are parameterized via `{{catalog}}`, `{{silver_schema}}`, and `{{gold_schema}}` placeholders in `config/agent_config.json`. Change the bundle variables to point to different catalogs or schemas without editing the config file.

## Running Standalone (Without DAB)

If you prefer to run the setup script directly without deploying a bundle:

```bash
# Install the SDK
pip install databricks-sdk

# Run with arguments
python scripts/setup_supervisor_agent.py \
  --config config/agent_config.json \
  --genie-space-id 01f1ae96b6b21b658c75b4c44c6dae06 \
  --agent-display-name "NSE Stock Research Assistant" \
  --catalog nse_stock_research \
  --silver-schema silver \
  --gold-schema gold
```

Or use the original standalone script (hardcoded values, for quick dev testing):

```bash
python setup_supervisor_agent.py
```

## Troubleshooting

### ModuleNotFoundError: No module named 'databricks.sdk.service.supervisoragents'

The installed SDK version (0.67.0 on serverless) does not include the `supervisoragents` module. The production script uses `w.api_client.do()` REST calls instead, so this error should not occur. If you see it, ensure you are running `scripts/setup_supervisor_agent.py` (not the old standalone version).

### PermissionDenied: Model qwen3-embedding-0-6b is unavailable

The embedding model is not enabled in your workspace. See **Prerequisites > 3. Embedding Model** above. Examples can be added later via the agent UI.

### BadRequest: You've reached your limit of 1 Supervisor Agent

The free tier allows only 1 Supervisor Agent. Delete the existing agent before creating a new one, or upgrade your workspace tier:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
w.api_client.do("DELETE", "/api/2.1/supervisor-agents/<agent-id>")
```

### subprocess pip install hangs on serverless

Do not use `subprocess.check_call([sys.executable, "-m", "pip", "install", ...])` on serverless compute. It runs outside the notebook's managed virtualenv and will not affect the notebook's Python environment. Use `%pip install` for non-core packages instead.

## Rollback

To remove the Supervisor Agent and all its resources:

```bash
# 1. Delete the agent via REST API
python -c "
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
agents = w.api_client.do('GET', '/api/2.1/supervisor-agents')
for a in agents.get('supervisor_agents', []):
    if 'NSE Stock Research' in a.get('display_name', ''):
        w.api_client.do('DELETE', f'/api/2.1/supervisor-agents/{a[\"supervisor_agent_id\"]}')
        print(f'Deleted: {a[\"display_name\"]}')
"

# 2. Destroy the bundle deployment
databricks bundle destroy --target prod
```

## Dependencies

* **Data pipeline**: This agent depends on the `nse-stock-research` bundle for data ingestion and pipeline processing. Ensure that bundle is deployed and running before deploying this agent.
* **Genie Space**: Must be created manually in each workspace — the Genie Space ID is workspace-specific and cannot be shared across environments.
* **Databricks SDK**: Version 0.67.0+ (pre-installed on serverless). The script uses `w.api_client.do()` REST calls and does not require the `supervisoragents` typed module.

---

Created: 2026-09-12

