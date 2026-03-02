FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y docker.io ffmpeg vnstat speedtest-cli 
    && pip install --no-cache-dir mcp[cli] fastmcp psutil docker pyyaml vnstat-py humanize 
    && rm -rf /var/lib/apt/lists/*
CMD ["python", "mcp_system.py"]
