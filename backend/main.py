"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import json
import asyncio
import subprocess
import httpx
import platform
import urllib.request
import tarfile
import zipfile
import os
from pathlib import Path

from . import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings
from .config import CLIPROXY_API_URL

app = FastAPI(title="LLM Council API")

# Track proxy process
_proxy_process = None

# Proxy configuration
PROXY_DIR = Path(__file__).parent.parent / "cliproxy"
RELEASE_URL = "https://github.com/router-for-me/CLIProxyAPIPlus/releases/latest/download"


def get_platform_binary():
    """Get the appropriate binary name for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine

    if system == "darwin":
        return f"cliproxy-darwin-{arch}.tar.gz"
    elif system == "linux":
        return f"cliproxy-linux-{arch}.tar.gz"
    elif system == "windows":
        return f"cliproxy-windows-{arch}.zip"
    return None


def get_binary_path():
    """Get path to the proxy binary."""
    if platform.system() == "Windows":
        return PROXY_DIR / "cliproxy.exe"
    return PROXY_DIR / "cliproxy"


def download_proxy_binary():
    """Download pre-built binary for current platform."""
    PROXY_DIR.mkdir(parents=True, exist_ok=True)

    binary_name = get_platform_binary()
    if not binary_name:
        print(f"Error: Unsupported platform {platform.system()} {platform.machine()}")
        return False

    binary_path = get_binary_path()
    if binary_path.exists():
        return True

    url = f"{RELEASE_URL}/{binary_name}"
    archive_path = PROXY_DIR / binary_name

    print(f"Downloading CLIProxyAPIPlus ({binary_name})...")
    try:
        urllib.request.urlretrieve(url, archive_path)
        print("Download complete!")

        print("Extracting...")
        if binary_name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(PROXY_DIR)
        elif binary_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(PROXY_DIR)

        if platform.system() != "Windows":
            os.chmod(binary_path, 0o755)

        archive_path.unlink()
        print(f"Binary ready at {binary_path}")
        return True

    except Exception as e:
        print(f"Error downloading binary: {e}")
        return False


def setup_proxy_config():
    """Create default config if not present."""
    config_path = PROXY_DIR / "config.yaml"
    if config_path.exists():
        return True

    config = """# CLIProxyAPIPlus Configuration for LLM Council
server:
  port: 8080

providers:
  openai:
    enabled: true
  gemini:
    enabled: true
  claude:
    enabled: true
"""
    PROXY_DIR.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    return True


def run_oauth_login(provider: str):
    """Run OAuth login for a specific provider."""
    binary = get_binary_path()
    if not binary.exists():
        return False

    print(f"\nStarting OAuth login for {provider}...")
    print("A browser window will open for authentication.")
    try:
        subprocess.run(
            [str(binary), "login", provider],
            cwd=PROXY_DIR,
            check=True
        )
        print(f"Successfully authenticated with {provider}!")
        return True
    except subprocess.CalledProcessError:
        print(f"OAuth login for {provider} failed or was cancelled.")
        return False


def check_provider_auth(provider: str) -> bool:
    """Check if a provider has OAuth tokens stored."""
    auth_file = PROXY_DIR / "auths" / f"{provider}.json"
    return auth_file.exists()


def interactive_setup():
    """Run interactive setup menu for CLIProxyAPIPlus."""
    print("\n" + "="*60)
    print("  LLM Council - First Time Setup")
    print("="*60)

    # Step 1: Download binary
    binary = get_binary_path()
    if not binary.exists():
        print("\n[1/3] Setting up CLIProxyAPIPlus...")
        if not download_proxy_binary():
            print("Failed to download proxy. Please try manually.")
            return False
    else:
        print("\n[1/3] CLIProxyAPIPlus binary found.")

    # Step 2: Setup config
    print("\n[2/3] Checking configuration...")
    setup_proxy_config()
    print("Configuration ready.")

    # Step 3: OAuth login for each provider
    print("\n[3/3] Provider Authentication")
    print("-" * 40)

    providers = [
        ("openai", "OpenAI (GPT models)"),
        ("gemini", "Google (Gemini models)"),
        ("claude", "Anthropic (Claude models)"),
    ]

    for provider_id, provider_name in providers:
        if check_provider_auth(provider_id):
            print(f"  {provider_name}: Already authenticated")
        else:
            while True:
                response = input(f"\n  Set up {provider_name}? [y/n/skip all]: ").lower().strip()
                if response == 'y':
                    run_oauth_login(provider_id)
                    break
                elif response == 'n':
                    print(f"  Skipping {provider_name}")
                    break
                elif response == 'skip all':
                    print("  Skipping remaining providers...")
                    break
            if response == 'skip all':
                break

    print("\n" + "="*60)
    print("  Setup Complete!")
    print("="*60)
    print("\nYou can re-run provider setup anytime with:")
    print("  python backend/start_proxy.py login --provider <name>\n")
    return True


async def check_proxy_running() -> bool:
    """Check if CLIProxyAPIPlus is responding."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            base_url = CLIPROXY_API_URL.rsplit('/v1/', 1)[0]
            response = await client.get(f"{base_url}/health")
            return response.status_code == 200
    except:
        return False


def start_proxy():
    """Start CLIProxyAPIPlus if binary exists."""
    global _proxy_process

    binary = get_binary_path()
    if not binary.exists():
        return False

    print("Starting CLIProxyAPIPlus...")
    _proxy_process = subprocess.Popen(
        [str(binary), "server"],
        cwd=PROXY_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    print(f"CLIProxyAPIPlus started (PID: {_proxy_process.pid})")
    return True


def ensure_proxy_setup():
    """Ensure proxy is set up, running interactive setup if needed."""
    binary = get_binary_path()

    # Check if binary exists
    if not binary.exists():
        print("\nCLIProxyAPIPlus not found. Starting setup...")
        interactive_setup()
        return

    # Check if any providers are authenticated
    has_any_auth = any(
        check_provider_auth(p) for p in ["openai", "gemini", "claude"]
    )

    if not has_any_auth:
        print("\nNo provider authentication found.")
        response = input("Run setup wizard? [y/n]: ").lower().strip()
        if response == 'y':
            interactive_setup()


@app.on_event("startup")
async def startup_event():
    """Start proxy on app startup if not already running."""
    if not await check_proxy_running():
        start_proxy()
        await asyncio.sleep(1)
        if await check_proxy_running():
            print("CLIProxyAPIPlus is ready")
        else:
            print("Warning: CLIProxyAPIPlus may not have started correctly")
    else:
        print("CLIProxyAPIPlus already running")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop proxy on app shutdown."""
    global _proxy_process
    if _proxy_process:
        print("Stopping CLIProxyAPIPlus...")
        _proxy_process.terminate()
        _proxy_process.wait()
        _proxy_process = None

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn

    # Check setup before starting
    ensure_proxy_setup()

    print("\nStarting LLM Council API on http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
