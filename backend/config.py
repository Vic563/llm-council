"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# CLIProxyAPIPlus configuration
# API key is optional - CLIProxyAPIPlus uses OAuth for authentication
CLIPROXY_API_KEY = os.getenv("CLIPROXY_API_KEY", "")

# CLIProxyAPIPlus endpoint (default local instance)
CLIPROXY_API_URL = os.getenv("CLIPROXY_API_URL", "http://localhost:8080/v1/chat/completions")

# Council members - model identifiers for CLIProxyAPIPlus
# Format depends on your CLIProxyAPIPlus configuration
COUNCIL_MODELS = [
    "gpt-4o",              # OpenAI via CLIProxyAPIPlus
    "gemini-2.0-flash",    # Google via CLIProxyAPIPlus
    "claude-sonnet-4-5",   # Anthropic via CLIProxyAPIPlus
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "gpt-4o"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
