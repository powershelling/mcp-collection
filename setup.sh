#!/bin/bash

# --- DETECTION OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    OS=$(uname -s)
fi

echo "--- MCP Collection Setup (OS: $OS) ---"

# --- INSTALLATION DEPENDANCES SYSTEME ---
case "$OS" in
    arch|cachyos)
        sudo pacman -S --needed --noconfirm python-pip python-virtualenv docker docker-compose ffmpeg vnstat speedtest-cli
        ;;
    ubuntu|debian)
        sudo apt update && sudo apt install -y python3-pip python3-venv docker.io docker-compose ffmpeg vnstat speedtest-cli
        ;;
    fedora)
        sudo dnf install -y python3-pip docker docker-compose ffmpeg vnstat speedtest-cli
        ;;
    *)
        echo "OS non supporte automatiquement. Installez python, docker et ffmpeg manuellement."
        ;;
esac

# --- CHOIX INSTALLATION ---
echo ""
echo "Comment souhaitez-vous installer les serveurs MCP ?"
echo "1) Localement (Python Virtualenv - Recommande pour monitoring systeme)"
echo "2) Docker (Conteneurise - Isole mais acces systeme restreint)"
read -p "Votre choix (1/2) : " CHOICE

if [ "$CHOICE" == "1" ]; then
    echo "--- Installation locale ---"
    python3 -m venv venv
    source venv/bin/activate
    pip install mcp[cli] fastmcp psutil docker pyyaml vnstat-py humanize
    echo "Installation terminee. Utilisez 'source venv/bin/activate' pour lancer les scripts."
else
    echo "--- Installation Docker ---"
    docker-compose up -d --build
    echo "Conteneurs MCP lances en arriere-plan."
fi
