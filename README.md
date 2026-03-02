# MCP Server Collection

A comprehensive collection of Model Context Protocol (MCP) servers for Linux system administration, database management, and development workflows.

## Features
- **system-monitor** (`mcp_system.py`): Advanced monitoring for CPU, RAM, NVIDIA GPUs, and system processes.
- **docker-ops** (`mcp_docker.py`): Full lifecycle management for Docker containers and Compose stacks.
- **network-ops** (`mcp_network.py`): Network diagnostics, port scanning, and interface management.
- **file-ops** (`mcp_files.py`): Secure file operations within the user environment.
- **git-ops** (`mcp_git.py`): Streamlined Git repository management.
- **database-ops** (`mcp_database.py`): PostgreSQL container administration and SQL execution.
- **media-tools** (`mcp_media.py`): Multimedia processing and metadata extraction via FFmpeg.
- **dev-tools** (`mcp_dev.py`): Python sandbox and virtual environment management.

## Installation
1. Install system dependencies (docker, python, ffmpeg, etc.).
2. Install required Python libraries:
   ```bash
   pip install mcp[cli] fastmcp psutil docker pyyaml vnstat-py humanize
   ```
3. Configure your MCP client (e.g., LM Studio) by adding the desired scripts to your `mcp.json` configuration.

## Setup Script
A setup script is provided to automate dependency installation and environment configuration:
```bash
chmod +x setup.sh
./setup.sh
```

## Security
- All file operations are restricted to the user's home directory.
- Destructive operations require explicit confirmation.
- Sensitive environment variables are automatically masked in outputs.
