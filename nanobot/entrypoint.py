#!/usr/bin/env python3
"""Entrypoint for nanobot gateway in Docker.

Resolves environment variables into config.json at runtime, then launches nanobot gateway.
"""

import json
import os
import sys
from pathlib import Path


def main():
    # Paths
    config_dir = Path(__file__).parent
    config_path = config_dir / "config.json"
    resolved_path = config_dir / "config.resolved.json"
    workspace_dir = config_dir / "workspace"
    
    # Global config path for Docker
    global_config_dir = Path("/root/.nanobot")
    global_config_dir.mkdir(parents=True, exist_ok=True)
    global_config_path = global_config_dir / "config.json"

    # Load base config
    with open(config_path) as f:
        config = json.load(f)

    # Resolve LLM provider config from env vars
    provider = config["agents"]["defaults"]["provider"]
    llm_api_key = os.environ.get("LLM_API_KEY", "")
    llm_api_base = os.environ.get("LLM_API_BASE_URL", "")
    
    # Update both agents.* and providers.* sections
    if provider in config["agents"]:
        config["agents"][provider]["apiKey"] = llm_api_key
        config["agents"][provider]["apiBase"] = llm_api_base
    
    if "providers" not in config:
        config["providers"] = {}
    if provider not in config["providers"]:
        config["providers"][provider] = {}
    config["providers"][provider]["apiKey"] = llm_api_key
    config["providers"][provider]["apiBase"] = llm_api_base

    # Resolve gateway host/port from env vars
    gateway_host = os.environ.get("NANOBOT_GATEWAY_CONTAINER_ADDRESS", "0.0.0.0")
    gateway_port = os.environ.get("NANOBOT_GATEWAY_CONTAINER_PORT", "18790")
    
    # Resolve webchat host/port from env vars
    webchat_host = os.environ.get("NANOBOT_WEBCHAT_CONTAINER_ADDRESS", "0.0.0.0")
    webchat_port = os.environ.get("NANOBOT_WEBCHAT_CONTAINER_PORT", "8765")

    # Resolve MCP server env vars
    if "tools" in config and "mcpServers" in config["tools"]:
        for server_name, server_config in config["tools"]["mcpServers"].items():
            if "env" in server_config:
                for env_key in list(server_config["env"].keys()):
                    value = os.environ.get(env_key)
                    if value:
                        server_config["env"][env_key] = value

    # Write resolved config
    with open(resolved_path, "w") as f:
        json.dump(config, f, indent=2)
    
    # Write global config for Docker
    global_config = {
        "providers": {}
    }
    if provider in config and "apiKey" in config[provider]:
        global_config["providers"][provider] = {
            "apiKey": config[provider]["apiKey"],
            "apiBase": config[provider]["apiBase"]
        }
    with open(global_config_path, "w") as f:
        json.dump(global_config, f, indent=2)

    # Launch nanobot gateway using uv run
    os.execvp(
        "uv",
        [
            "uv",
            "run",
            "nanobot",
            "gateway",
            "--config",
            str(resolved_path),
            "--workspace",
            str(workspace_dir),
        ],
    )


if __name__ == "__main__":
    main()
