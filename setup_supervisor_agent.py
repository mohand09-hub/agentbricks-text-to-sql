"""Setup script for NSE Stock Research Text-to-SQL Agent

Uses the Databricks REST API directly (w.api_client.do) instead of
the databricks.sdk.service.supervisoragents typed module, which is
not available in the SDK version pre-installed on serverless compute.

Idempotent: detects existing agents/tools and skips creation if found.
"""

from databricks.sdk import WorkspaceClient

print("Initializing Databricks SDK...")
w = WorkspaceClient()

GENIE_SPACE_ID = "01f1ae96b6b21b658c75b4c44c6dae06"
AGENT_DISPLAY_NAME = "NSE Stock Research Assistant"
TOOL_ID = "nse-stock-sql"

# Base path for the Supervisor Agent REST API
SA_API = "/api/2.1/supervisor-agents"

print("\n" + "="*80)
print("Setting up Supervisor Agent for Text-to-SQL...")
print("="*80)

# Step 1: Find or create Supervisor Agent
print("\n[1/3] Checking for existing Supervisor Agent...")

agent_id = None
existing = w.api_client.do("GET", SA_API)
for agent in existing.get("supervisor_agents", []):
    if agent.get("display_name") == AGENT_DISPLAY_NAME:
        agent_id = agent["supervisor_agent_id"]
        print(f"Found existing: {agent['display_name']}")
        print(f"   Agent ID: {agent_id}")
        break

if not agent_id:
    print("Creating new Supervisor Agent...")
    agent_payload = {
        "display_name": AGENT_DISPLAY_NAME,
        "description": "Natural language interface to query NSE stock market data.",
        "instructions": (
            "You are a stock market analyst for NSE data.\n\n"
            "Query company profiles, prices, fundamentals, news, and sector analysis.\n"
            "Use clear SQL patterns, meaningful filters, and cite data sources."
        ),
    }
    created_agent = w.api_client.do("POST", SA_API, body=agent_payload)
    agent_id = created_agent["name"].split("/")[-1]
    print(f"Created: {created_agent.get('display_name', AGENT_DISPLAY_NAME)}")
    print(f"   Agent ID: {agent_id}")

# Step 2: Find or add Genie Space tool
print("\n[2/3] Checking for Genie Space tool...")

tool_exists = False
tools_resp = w.api_client.do("GET", f"{SA_API}/{agent_id}/tools")
for tool in tools_resp.get("tools", []):
    if tool.get("tool_id") == TOOL_ID:
        tool_exists = True
        print(f"Tool already exists: {TOOL_ID}")
        break

if not tool_exists:
    tool_payload = {
        "tool_type": "genie_space",
        "description": "Query NSE stock data: companies, prices, fundamentals, news.",
        "genie_space": {"id": GENIE_SPACE_ID},
    }
    w.api_client.do(
        "POST",
        f"{SA_API}/{agent_id}/tools",
        body=tool_payload,
        query={"tool_id": TOOL_ID},
    )
    print(f"Added Genie Space tool: {TOOL_ID}")
else:
    print("Skipping tool creation (already exists)")

# Step 3: Add example queries via REST API
print("\n[3/3] Adding example queries...")

examples = [
    {
        "question": "Show me the top 10 companies by market cap",
        "guidelines": [
            "Query silver.companies, order by market_cap DESC, limit 10",
            "Include ticker, company_name, sector, market_cap",
        ],
    },
    {
        "question": "Which stocks moved more than 5% today?",
        "guidelines": [
            "Query gold.gold_price_daily_agg",
            "Filter ABS(day_over_day_pct) > 5.0",
        ],
    },
    {
        "question": "What's the average PE ratio by sector?",
        "guidelines": [
            "Query silver.companies",
            "Group by sector, calculate AVG(trailing_pe)",
        ],
    },
]

examples_added = 0
for i, example in enumerate(examples, 1):
    try:
        w.api_client.do(
            "POST",
            f"{SA_API}/{agent_id}/examples",
            body=example,
        )
        examples_added += 1
        print(f"Example {i}/3: {example['question']}")
    except Exception as e:
        print(f"Example {i}/3 FAILED: {example['question']}")
        print(f"   Error: {e}")
        print("   You can add examples later via the UI once the embedding model is enabled.")

print("\n" + "="*80)
print("Setup Complete!")
print("="*80)
print(f"\nAgent ID: {agent_id}")
print(f"Tools added: 1 (Genie Space: {GENIE_SPACE_ID})")
print(f"Examples added: {examples_added}/3")
if examples_added < 3:
    print("\nNote: Some examples failed. Enable the qwen3-embedding-0-6b model")
    print("in your workspace AI settings, then add examples via the agent UI.")
print(f"\nAccess at:")
print(f"   https://dbc-97d2bf38-c66c.cloud.databricks.com/agents/{agent_id}")
print(f"\nTry: 'Show me the top gainers today'")