#!/usr/bin/env python3
"""MCP Server — Docker & Compose (30 tools)."""

import json
import os
import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("docker-ops")

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_name(name: str) -> str:
    if not SAFE_NAME.match(name):
        raise ValueError(f"Nom invalide: {name}")
    return name


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


# ── Containers ────────────────────────────────────────────────────────


@mcp.tool()
def docker_list() -> str:
    """Liste tous les containers Docker (nom, status, ports, image)."""
    return _run(["docker", "ps", "-a", "--format",
                 "table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}"])


@mcp.tool()
def docker_start(container: str) -> str:
    """Démarre un container Docker par nom."""
    return _run(["docker", "start", _validate_name(container)])


@mcp.tool()
def docker_stop(container: str) -> str:
    """Stoppe un container Docker par nom."""
    return _run(["docker", "stop", _validate_name(container)])


@mcp.tool()
def docker_restart(container: str) -> str:
    """Redémarre un container Docker par nom."""
    return _run(["docker", "restart", _validate_name(container)])


@mcp.tool()
def docker_logs(container: str, lines: int = 100) -> str:
    """Affiche les dernières N lignes de logs d'un container."""
    lines = min(int(lines), 500)
    return _run(["docker", "logs", "--tail", str(lines), _validate_name(container)])


@mcp.tool()
def docker_stats(container: str = "") -> str:
    """CPU/RAM/réseau d'un ou tous les containers. Laisser vide pour tous."""
    cmd = ["docker", "stats", "--no-stream", "--format",
           "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"]
    if container:
        cmd.append(_validate_name(container))
    return _run(cmd)


@mcp.tool()
def docker_inspect(container: str) -> str:
    """Détails complets d'un container (config, réseau, mounts)."""
    raw = _run(["docker", "inspect", _validate_name(container)])
    try:
        data = json.loads(raw)
        if data and isinstance(data, list):
            c = data[0]
            info = {
                "Name": c.get("Name"),
                "State": c.get("State", {}),
                "Image": c.get("Config", {}).get("Image"),
                "Env": c.get("Config", {}).get("Env"),
                "Ports": c.get("NetworkSettings", {}).get("Ports"),
                "Mounts": [{"Source": m.get("Source"), "Destination": m.get("Destination"), "Type": m.get("Type")} for m in c.get("Mounts", [])],
                "Networks": list(c.get("NetworkSettings", {}).get("Networks", {}).keys()),
                "RestartPolicy": c.get("HostConfig", {}).get("RestartPolicy"),
            }
            return json.dumps(info, indent=2, default=str)
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return raw


@mcp.tool()
def docker_top(container: str) -> str:
    """Processus actifs dans un container."""
    return _run(["docker", "top", _validate_name(container)])


@mcp.tool()
def docker_diff(container: str) -> str:
    """Fichiers modifiés dans un container vs son image de base."""
    return _run(["docker", "diff", _validate_name(container)])


@mcp.tool()
def docker_exec(container: str, command: str) -> str:
    """Exécuter une commande dans un container. Commande passée à sh -c."""
    name = _validate_name(container)
    if any(c in command for c in (";", "&&", "||", "|", "`", "$(")):
        return "ERREUR: caractères shell dangereux interdits dans la commande"
    return _run(["docker", "exec", name, "sh", "-c", command], timeout=30)


# ── Images, Réseaux, Volumes ─────────────────────────────────────────


@mcp.tool()
def docker_images() -> str:
    """Liste des images Docker (repo, tag, taille)."""
    return _run(["docker", "images", "--format",
                 "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"])


@mcp.tool()
def docker_networks(network: str = "") -> str:
    """Liste des réseaux Docker, ou détails d'un réseau spécifique."""
    if network:
        raw = _run(["docker", "network", "inspect", _validate_name(network)])
        try:
            data = json.loads(raw)
            if data and isinstance(data, list):
                n = data[0]
                containers = {name: info.get("IPv4Address", "?") for name, info in n.get("Containers", {}).items()}
                info = {
                    "Name": n.get("Name"),
                    "Driver": n.get("Driver"),
                    "Subnet": [s.get("Subnet") for s in n.get("IPAM", {}).get("Config", [])],
                    "Containers": containers,
                }
                return json.dumps(info, indent=2)
        except (json.JSONDecodeError, KeyError):
            pass
        return raw
    return _run(["docker", "network", "ls", "--format",
                 "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"])


@mcp.tool()
def docker_volumes() -> str:
    """Liste des volumes Docker."""
    return _run(["docker", "volume", "ls", "--format",
                 "table {{.Name}}\t{{.Driver}}\t{{.Mountpoint}}"])


@mcp.tool()
def docker_port_map() -> str:
    """Vue synthétique de tous les containers avec leurs ports exposés."""
    return _run(["docker", "ps", "--format",
                 "table {{.Names}}\t{{.Ports}}\t{{.Status}}",
                 "--filter", "status=running"])


@mcp.tool()
def docker_prune(include_volumes: bool = False) -> str:
    """Nettoyage images/containers inutilisés. include_volumes=True pour aussi les volumes (DANGER)."""
    cmd = ["docker", "system", "prune", "-f"]
    if include_volumes:
        cmd.append("--volumes")
    return _run(cmd, timeout=120)


@mcp.tool()
def docker_pull(image: str) -> str:
    """Pull une image Docker depuis le registry."""
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$", image):
        return "ERREUR: nom d'image invalide"
    return _run(["docker", "pull", image], timeout=300)


@mcp.tool()
def docker_rm(container: str, force: bool = False) -> str:
    """Supprimer un container (force=True pour supprimer même s'il tourne)."""
    cmd = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(_validate_name(container))
    return _run(cmd)


@mcp.tool()
def docker_rmi(image: str, force: bool = False) -> str:
    """Supprimer une image Docker."""
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$", image):
        return "ERREUR: nom d'image invalide"
    cmd = ["docker", "rmi"]
    if force:
        cmd.append("-f")
    cmd.append(image)
    return _run(cmd)


@mcp.tool()
def docker_cp(container: str, src: str, dst: str, to_container: bool = True) -> str:
    """Copier fichiers entre host et container. to_container=True: host→container, False: container→host."""
    name = _validate_name(container)
    if to_container:
        return _run(["docker", "cp", src, f"{name}:{dst}"], timeout=60)
    else:
        return _run(["docker", "cp", f"{name}:{src}", dst], timeout=60)


@mcp.tool()
def docker_events(minutes: int = 10) -> str:
    """Événements Docker récents (start, stop, die, etc.)."""
    minutes = min(int(minutes), 60)
    return _run(["docker", "events", "--since", f"{minutes}m",
                 "--until", "0s", "--format",
                 "{{.Time}} {{.Type}} {{.Action}} {{.Actor.Attributes.name}}"],
                timeout=15)


@mcp.tool()
def docker_health(container: str) -> str:
    """Status healthcheck d'un container (healthy/unhealthy/none + logs)."""
    name = _validate_name(container)
    raw = _run(["docker", "inspect", "--format",
                "{{json .State.Health}}", name])
    try:
        health = json.loads(raw)
        if not health:
            return f"{name}: pas de healthcheck configuré"
        status = health.get("Status", "unknown")
        logs = health.get("Log", [])[-3:]
        parts = [f"Status: {status}"]
        for log in logs:
            parts.append(f"  [{log.get('End', '?')}] exit={log.get('ExitCode')} → {log.get('Output', '').strip()[:200]}")
        return "\n".join(parts)
    except json.JSONDecodeError:
        return raw


@mcp.tool()
def docker_update_resources(container: str, memory: str = "", cpus: str = "") -> str:
    """Modifier les limites CPU/RAM d'un container. Ex: memory='512m', cpus='1.5'."""
    cmd = ["docker", "update"]
    if memory:
        if not re.match(r"^\d+[mgMG]$", memory):
            return "ERREUR: format mémoire invalide (ex: 512m, 2g)"
        cmd.extend(["--memory", memory])
    if cpus:
        try:
            float(cpus)
        except ValueError:
            return "ERREUR: cpus doit être un nombre (ex: 1.5)"
        cmd.extend(["--cpus", cpus])
    if len(cmd) == 2:
        return "ERREUR: spécifier au moins memory ou cpus"
    cmd.append(_validate_name(container))
    return _run(cmd)


@mcp.tool()
def docker_rename(container: str, new_name: str) -> str:
    """Renommer un container Docker."""
    return _run(["docker", "rename", _validate_name(container), _validate_name(new_name)])


@mcp.tool()
def docker_wait(container: str) -> str:
    """Attendre la fin d'un container et retourner son exit code."""
    return _run(["docker", "wait", _validate_name(container)], timeout=120)


@mcp.tool()
def docker_disk_usage() -> str:
    """Espace disque utilisé par Docker (images, containers, volumes, build cache)."""
    return _run(["docker", "system", "df", "-v"], timeout=30)


@mcp.tool()
def docker_history(image: str) -> str:
    """Historique des layers d'une image Docker (commandes, tailles)."""
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$", image):
        return "ERREUR: nom d'image invalide"
    return _run(["docker", "history", "--format",
                 "table {{.CreatedSince}}\t{{.Size}}\t{{.CreatedBy}}", image])


# ── Compose ──────────────────────────────────────────────────────────


@mcp.tool()
def docker_compose_up(project_dir: str) -> str:
    """Lance `docker compose up -d` dans un répertoire projet."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    if not os.path.isfile(os.path.join(project_dir, "docker-compose.yml")) and \
       not os.path.isfile(os.path.join(project_dir, "compose.yml")):
        return f"ERREUR: pas de fichier compose trouvé dans {project_dir}"
    return _run(["docker", "compose", "up", "-d"], cwd=project_dir)


@mcp.tool()
def docker_compose_down(project_dir: str) -> str:
    """Lance `docker compose down` dans un répertoire projet."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    return _run(["docker", "compose", "down"], cwd=project_dir)


@mcp.tool()
def docker_compose_status(project_dir: str) -> str:
    """Status d'un stack docker compose (services, état, ports)."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    return _run(["docker", "compose", "ps", "--format",
                 "table {{.Name}}\t{{.Status}}\t{{.Ports}}"], cwd=project_dir)


@mcp.tool()
def docker_compose_logs(project_dir: str, service: str = "", lines: int = 100) -> str:
    """Logs d'un stack docker compose (ou d'un service spécifique)."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    lines = min(int(lines), 500)
    cmd = ["docker", "compose", "logs", "--tail", str(lines)]
    if service:
        cmd.append(_validate_name(service))
    return _run(cmd, cwd=project_dir, timeout=30)


@mcp.tool()
def docker_compose_restart_service(project_dir: str, service: str) -> str:
    """Redémarrer un service spécifique dans un stack docker compose."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    return _run(["docker", "compose", "restart", _validate_name(service)],
                cwd=project_dir)


@mcp.tool()
def docker_compose_pull(project_dir: str) -> str:
    """Pull les dernières images pour un stack docker compose."""
    project_dir = os.path.realpath(project_dir)
    if not project_dir.startswith("/home/user/"):
        return "ERREUR: seuls les répertoires sous /home/user/ sont autorisés"
    return _run(["docker", "compose", "pull"], cwd=project_dir, timeout=300)


if __name__ == "__main__":
    mcp.run(transport="stdio")
