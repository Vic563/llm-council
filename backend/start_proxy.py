#!/usr/bin/env python3
"""
Script to start CLIProxyAPIPlus and handle OAuth setup.
Run this before starting the LLM Council backend.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Configuration
PROXY_DIR = Path(__file__).parent.parent / "cliproxy"
PROXY_REPO = "https://github.com/router-for-me/CLIProxyAPIPlus"
PROXY_PORT = 8080


def check_go_installed():
    """Check if Go is installed."""
    if shutil.which("go") is None:
        print("Error: Go is not installed. Please install Go first:")
        print("  https://go.dev/doc/install")
        return False
    return True


def clone_proxy():
    """Clone CLIProxyAPIPlus repository if not present."""
    if PROXY_DIR.exists():
        print(f"CLIProxyAPIPlus already exists at {PROXY_DIR}")
        return True

    print(f"Cloning CLIProxyAPIPlus to {PROXY_DIR}...")
    try:
        subprocess.run(
            ["git", "clone", PROXY_REPO, str(PROXY_DIR)],
            check=True
        )
        print("Clone successful!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository: {e}")
        return False


def build_proxy():
    """Build the CLIProxyAPIPlus binary."""
    print("Building CLIProxyAPIPlus...")
    try:
        subprocess.run(
            ["go", "build", "-o", "cliproxy", "./cmd/server"],
            cwd=PROXY_DIR,
            check=True
        )
        print("Build successful!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error building proxy: {e}")
        return False


def setup_config():
    """Create default config if not present."""
    config_path = PROXY_DIR / "config.yaml"
    example_config = PROXY_DIR / "config.example.yaml"

    if config_path.exists():
        print(f"Config already exists at {config_path}")
        return True

    if example_config.exists():
        shutil.copy(example_config, config_path)
        print(f"Created config from example at {config_path}")
        print("Please edit config.yaml to add your provider credentials.")
        return True

    # Create minimal config
    minimal_config = """# CLIProxyAPIPlus Configuration
# See https://github.com/router-for-me/CLIProxyAPIPlus for full options

server:
  port: 8080

# Add your provider configurations below
# OAuth login will be handled interactively

providers:
  openai:
    enabled: true
  gemini:
    enabled: true
  claude:
    enabled: true
"""
    config_path.write_text(minimal_config)
    print(f"Created minimal config at {config_path}")
    return True


def run_oauth_login(provider: str):
    """Run OAuth login for a specific provider."""
    binary = PROXY_DIR / "cliproxy"
    if not binary.exists():
        print("Error: Proxy binary not found. Run build first.")
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
    except subprocess.CalledProcessError as e:
        print(f"Error during OAuth login: {e}")
        return False


def start_proxy():
    """Start the proxy server."""
    binary = PROXY_DIR / "cliproxy"
    if not binary.exists():
        print("Error: Proxy binary not found. Run setup first.")
        return None

    print(f"\nStarting CLIProxyAPIPlus on port {PROXY_PORT}...")
    try:
        process = subprocess.Popen(
            [str(binary), "server"],
            cwd=PROXY_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        print(f"Proxy started with PID {process.pid}")
        print(f"API endpoint: http://localhost:{PROXY_PORT}/v1/chat/completions")
        return process
    except Exception as e:
        print(f"Error starting proxy: {e}")
        return None


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CLIProxyAPIPlus setup and launcher for LLM Council"
    )
    parser.add_argument(
        "command",
        choices=["setup", "login", "start", "all"],
        help="Command to run: setup (clone+build), login (OAuth), start (run server), all (full setup)"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "claude", "copilot", "kiro"],
        help="Provider for OAuth login (required for 'login' command)"
    )

    args = parser.parse_args()

    if args.command == "setup" or args.command == "all":
        if not check_go_installed():
            sys.exit(1)
        if not clone_proxy():
            sys.exit(1)
        if not build_proxy():
            sys.exit(1)
        if not setup_config():
            sys.exit(1)
        print("\n✓ Setup complete!")

    if args.command == "login":
        if not args.provider:
            print("Error: --provider is required for login command")
            print("Example: python start_proxy.py login --provider openai")
            sys.exit(1)
        if not run_oauth_login(args.provider):
            sys.exit(1)

    if args.command == "all":
        # Run OAuth for all main providers
        for provider in ["openai", "gemini", "claude"]:
            response = input(f"\nSet up OAuth for {provider}? [y/N] ")
            if response.lower() == 'y':
                run_oauth_login(provider)

    if args.command == "start" or args.command == "all":
        process = start_proxy()
        if process:
            print("\nProxy is running. Press Ctrl+C to stop.")
            try:
                process.wait()
            except KeyboardInterrupt:
                print("\nStopping proxy...")
                process.terminate()
                process.wait()


if __name__ == "__main__":
    main()
