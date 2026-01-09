#!/usr/bin/env python3
"""
Script to start CLIProxyAPIPlus and handle OAuth setup.
Run this before starting the LLM Council backend.
"""

import os
import sys
import subprocess
import platform
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path

# Configuration
PROXY_DIR = Path(__file__).parent.parent / "cliproxy"
PROXY_PORT = 8080
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
    else:
        return None


def download_binary():
    """Download pre-built binary for current platform."""
    PROXY_DIR.mkdir(parents=True, exist_ok=True)

    binary_name = get_platform_binary()
    if not binary_name:
        print(f"Error: Unsupported platform {platform.system()} {platform.machine()}")
        return False

    binary_path = PROXY_DIR / "cliproxy"
    if platform.system() == "Windows":
        binary_path = PROXY_DIR / "cliproxy.exe"

    if binary_path.exists():
        print(f"Binary already exists at {binary_path}")
        return True

    url = f"{RELEASE_URL}/{binary_name}"
    archive_path = PROXY_DIR / binary_name

    print(f"Downloading {binary_name}...")
    try:
        urllib.request.urlretrieve(url, archive_path)
        print("Download complete!")

        # Extract archive
        print("Extracting...")
        if binary_name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(PROXY_DIR)
        elif binary_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(PROXY_DIR)

        # Make executable on Unix
        if platform.system() != "Windows":
            os.chmod(binary_path, 0o755)

        # Clean up archive
        archive_path.unlink()
        print(f"Binary ready at {binary_path}")
        return True

    except Exception as e:
        print(f"Error downloading binary: {e}")
        print("\nManual install: Download from https://github.com/router-for-me/CLIProxyAPIPlus/releases")
        return False


def setup_config():
    """Create default config if not present."""
    config_path = PROXY_DIR / "config.yaml"

    if config_path.exists():
        print(f"Config already exists at {config_path}")
        return True

    # Create config for LLM Council
    config = """# CLIProxyAPIPlus Configuration for LLM Council
server:
  port: 8080

# Provider configurations
# OAuth tokens will be stored in auths/ directory after login

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
    print(f"Created config at {config_path}")
    return True


def get_binary_path():
    """Get path to the binary."""
    if platform.system() == "Windows":
        return PROXY_DIR / "cliproxy.exe"
    return PROXY_DIR / "cliproxy"


def run_oauth_login(provider: str):
    """Run OAuth login for a specific provider."""
    binary = get_binary_path()
    if not binary.exists():
        print("Error: Binary not found. Run 'setup' first.")
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
    binary = get_binary_path()
    if not binary.exists():
        print("Error: Binary not found. Run 'setup' first.")
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
        help="Command: setup (download binary), login (OAuth), start (run server), all (full setup)"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "claude", "copilot", "kiro"],
        help="Provider for OAuth login"
    )

    args = parser.parse_args()

    if args.command == "setup" or args.command == "all":
        if not download_binary():
            sys.exit(1)
        if not setup_config():
            sys.exit(1)
        print("\n Setup complete!")

    if args.command == "login":
        if not args.provider:
            print("Error: --provider required")
            print("Example: python start_proxy.py login --provider openai")
            sys.exit(1)
        run_oauth_login(args.provider)

    if args.command == "all":
        for provider in ["openai", "gemini", "claude"]:
            response = input(f"\nSet up OAuth for {provider}? [y/N] ")
            if response.lower() == 'y':
                run_oauth_login(provider)

    if args.command == "start" or args.command == "all":
        process = start_proxy()
        if process:
            print("\nProxy running. Press Ctrl+C to stop.")
            try:
                process.wait()
            except KeyboardInterrupt:
                print("\nStopping proxy...")
                process.terminate()
                process.wait()


if __name__ == "__main__":
    main()
