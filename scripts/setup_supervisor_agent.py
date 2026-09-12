"""Setup script for NSE Stock Research Text-to-SQL Agent (Production)

Reads configuration from a JSON config file and accepts CLI arguments
for environment-specific values (Genie Space ID, agent display name).

Uses the Databricks REST API directly (w.api_client.do) instead of
the databricks.sdk.service.supervisoragents typed module, which is
not available in the SDK version pre-installed on serverless compute.

Idempotent: detects existing agents/tools and skips creation if found.

Template substitution:
    The config file supports {{catalog}}, {{silver_schema}}, {{gold_schema}}
    placeholders in any string field (examples, descriptions, instructions).
    These are replaced at runtime with the CLI argument values.

Usage (standalone):
    python setup_supervisor_agent.py \
        --config config/agent_config.json \
        --genie-space-id 01f1ae96b6b21b658c75b4c44c6dae06 \
        --agent-display-name "NSE Stock Research Assistant" \
        --catalog nse_stock_research \
        --silver-schema silver \
        --gold-schema gold

Usage (via DAB):
    databricks bundle run setup_supervisor_agent --target prod
"""

import argparse
import json
import os
import sys
from databricks.sdk import WorkspaceClient

SA_API = "/api/2.1/supervisor-agents"


def load_config(config_path: str) -> dict:
    """Load agent configuration from JSON file."""
    with open(config_path, "r") as f:
        return json.load(f)


def substitute_templates(config: dict, catalog: str, silver_schema: str, gold_schema: str) -> dict:
    """Replace {{catalog}}, {{silver_schema}}, {{gold_schema}} placeholders
    in all string values within the config (recursively)."""
    replacements = {
        "{{catalog}}": catalog,
        "{{silver_schema}}": silver_schema,
        "{{gold_schema}}": gold_schema,
    }
    raw = json.dumps(config)
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    return json.loads(raw)


def find_or_create_agent(w, display_name: str, config: dict) -> str:
    """Find an existing agent by display name, or create a new one.
    Returns the agent_id."""
    existing = w.api_client.do("GET", SA_API)
    for agent in existing.get("supervisor_agents", []):
        if agent.get("display_name") == display_name:
            agent_id = agent["supervisor_agent_id"]
            print(f"[1/3] Found existing agent: {display_name} (ID: {agent_id})")
            return agent_id

    print(f"[1/3] Creating new Supervisor Agent: {display_name}")
    payload = {
        "display_name": display_name,
        "description": config["description"],
        "instructions": config["instructions"],
    }
    created = w.api_client.do("POST", SA_API, body=payload)
    agent_id = created["name"].split("/")[-1]
    print(f"      Created agent ID: {agent_id}")
    return agent_id


def find_or_add_tool(w, agent_id: str, tool_config: dict, genie_space_id: str) -> bool:
    """Find an existing tool by tool_id, or add a new one.
    Returns True if the tool was added (False if it already existed)."""
    tool_id = tool_config["tool_id"]
    tools_resp = w.api_client.do("GET", f"{SA_API}/{agent_id}/tools")
    for tool in tools_resp.get("tools", []):
        if tool.get("tool_id") == tool_id:
            print(f"[2/3] Tool already exists: {tool_id}")
            return False

    print(f"[2/3] Adding Genie Space tool: {tool_id}")
    payload = {
        "tool_type": "genie_space",
        "description": tool_config["description"],
        "genie_space": {"id": genie_space_id},
    }
    w.api_client.do(
        "POST",
        f"{SA_API}/{agent_id}/tools",
        body=payload,
        query={"tool_id": tool_id},
    )
    print(f"      Added tool: {tool_id}")
    return True


def add_examples(w, agent_id: str, examples: list) -> int:
    """Add quality examples to the agent. Returns count of successful additions."""
    added = 0
    for i, example in enumerate(examples, 1):
        try:
            w.api_client.do(
                "POST",
                f"{SA_API}/{agent_id}/examples",
                body=example,
            )
            added += 1
            print(f"[3/3] Example {i}/{len(examples)}: {example['question']}")
        except Exception as e:
            print(f"[3/3] Example {i}/{len(examples)} FAILED: {example['question']}")
            print(f"      Error: {e}")
    return added


def main():
    parser = argparse.ArgumentParser(description="Setup Supervisor Agent")
    parser.add_argument("--config", required=True, help="Path to agent_config.json")
    parser.add_argument("--genie-space-id", required=True, help="Genie Space ID")
    parser.add_argument("--agent-display-name", required=True, help="Agent display name")
    parser.add_argument("--catalog", required=False, default="nse_stock_research",
                        help="Unity Catalog name (default: nse_stock_research)")
    parser.add_argument("--silver-schema", required=False, default="silver",
                        help="Silver schema name (default: silver)")
    parser.add_argument("--gold-schema", required=False, default="gold",
                        help="Gold schema name (default: gold)")
    args = parser.parse_args()

    config = load_config(args.config)
    config = substitute_templates(config, args.catalog, args.silver_schema, args.gold_schema)

    print("Initializing Databricks SDK...")
    w = WorkspaceClient()

    print("\n" + "=" * 80)
    print(f"Setting up Supervisor Agent: {args.agent_display_name}")
    print("=" * 80)

    # Step 1: Find or create agent
    agent_id = find_or_create_agent(w, args.agent_display_name, config)

    # Step 2: Find or add Genie Space tool
    find_or_add_tool(w, agent_id, config["tool"], args.genie_space_id)

    # Step 3: Add examples
    examples_added = add_examples(w, agent_id, config.get("examples", []))

    # Summary
    print("\n" + "=" * 80)
    print("Setup Complete!")
    print("=" * 80)
    print(f"\nAgent ID: {agent_id}")
    print(f"Genie Space: {args.genie_space_id}")
    print(f"Catalog: {args.catalog}")
    print(f"Schemas: {args.silver_schema}, {args.gold_schema}")
    print(f"Examples added: {examples_added}/{len(config.get('examples', []))}")

    if examples_added < len(config.get("examples", [])):
        print("\nNote: Some examples failed. Enable the qwen3-embedding-0-6b")
        print("model in workspace AI settings, then re-run this job.")

    host = os.environ.get("DATABRICKS_HOST", "")
    print(f"\nAgent URL: {host}/agents/{agent_id}")


if __name__ == "__main__":
    main()
