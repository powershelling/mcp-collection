#!/bin/bash
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=$ID
    OS_LIKE=$ID_LIKE
else
    OS_ID="unknown"
fi

echo "--- MCP Setup: Detected $OS_ID ---"

install_arch() {
    sudo pacman -S --needed --noconfirm python-pip python-virtualenv docker docker-compose ffmpeg vnstat speedtest-cli
}

install_debian() {
    sudo apt update && sudo apt install -y python3-pip python3-venv docker.io docker-compose ffmpeg vnstat speedtest-cli
}

install_fedora() {
    sudo dnf install -y python3-pip docker docker-compose ffmpeg vnstat speedtest-cli
}

if [[ "$OS_ID" == "arch" || "$OS_ID" == "cachyos" || "$OS_LIKE" == *"arch"* ]]; then
    install_arch
elif [[ "$OS_ID" == "debian" || "$OS_ID" == "ubuntu" || "$OS_LIKE" == *"debian"* || "$OS_LIKE" == *"ubuntu"* ]]; then
    install_debian
elif [[ "$OS_ID" == "fedora" ]]; then
    install_fedora
else
    echo "Unsupported OS. Please install python, docker, and ffmpeg manually."
    exit 1
fi

python3 -m venv venv
source venv/bin/activate
pip install mcp[cli] fastmcp psutil docker pyyaml vnstat-py humanize
echo "Setup complete. Use 'source venv/bin/activate' to run scripts."
