#!/usr/bin/env python3
"""MCP Server — Réseau & Sécurité & Cloudflare (29 tools)."""

import json
import re
import socket
import subprocess
import time

import yaml
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("network-ops")

CLOUDFLARE_CONFIG = "/home/user/mcp-config/tunnel-service/config.yml"
CLOUDFLARE_CONTAINER = "tunnel-service"
SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
SAFE_HOSTNAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}$")


def _validate_name(name: str) -> str:
    if not SAFE_NAME.match(name):
        raise ValueError(f"Nom invalide: {name}")
    return name


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


# ── Réseau ───────────────────────────────────────────────────────────


@mcp.tool()
def network_interfaces() -> str:
    """Interfaces réseau, adresses IP et status."""
    return _run(["ip", "-br", "addr", "show"])


@mcp.tool()
def open_ports() -> str:
    """Ports TCP en écoute avec processus associé."""
    return _run(["ss", "-tlnp"])


@mcp.tool()
def network_connections(count: int = 50) -> str:
    """Connexions TCP actives (max N lignes)."""
    count = min(int(count), 200)
    result = _run(["ss", "-tnp"])
    lines = result.strip().split("\n")
    return "\n".join(lines[:count + 1])


@mcp.tool()
def ping_host(host: str, count: int = 4) -> str:
    """Ping un hôte (latence, perte de paquets). Max 4 pings."""
    if not SAFE_HOSTNAME.match(host):
        return "ERREUR: hostname invalide"
    count = min(int(count), 4)
    return _run(["ping", "-c", str(count), "-W", "5", host], timeout=30)


@mcp.tool()
def dns_lookup(domain: str) -> str:
    """Résolution DNS d'un domaine (A, AAAA, MX, NS)."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", domain):
        return "ERREUR: domaine invalide"
    parts = []
    for qtype in ("A", "AAAA", "MX", "NS"):
        result = _run(["dig", "+short", domain, qtype])
        if result and not result.startswith("ERREUR"):
            parts.append(f"=== {qtype} ===\n{result}")
    return "\n\n".join(parts) if parts else f"Aucun enregistrement trouvé pour {domain}"


@mcp.tool()
def traceroute(host: str) -> str:
    """Traceroute vers un hôte (max 15 sauts)."""
    if not SAFE_HOSTNAME.match(host):
        return "ERREUR: hostname invalide"
    return _run(["traceroute", "-m", "15", "-w", "3", host], timeout=60)


@mcp.tool()
def bandwidth_usage() -> str:
    """Consommation bande passante (jour/mois) via vnstat."""
    return _run(["vnstat", "--oneline"])


@mcp.tool()
def ip_route() -> str:
    """Table de routage IP."""
    return _run(["ip", "route", "show"])


@mcp.tool()
def check_url(url: str) -> str:
    """Vérifier si une URL répond (status code, headers). HEAD only, timeout 10s."""
    if not re.match(r"^https?://[a-zA-Z0-9._:/-]+$", url):
        return "ERREUR: URL invalide"
    return _run(["curl", "-sI", "--max-time", "10", url], timeout=15)


@mcp.tool()
def whois_lookup(domain: str) -> str:
    """Informations WHOIS d'un domaine (registrar, dates, nameservers)."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", domain):
        return "ERREUR: domaine invalide"
    result = _run(["whois", domain], timeout=15)
    important = []
    for line in result.split("\n"):
        line_lower = line.lower()
        if any(k in line_lower for k in ("registrar", "creation", "expir", "updated",
                                          "name server", "status", "dnssec", "registrant")):
            important.append(line.strip())
    return "\n".join(important) if important else result[:2000]


@mcp.tool()
def speedtest() -> str:
    """Test de débit internet (download, upload, latence) via speedtest-cli."""
    return _run(["speedtest-cli", "--simple"], timeout=60)


@mcp.tool()
def arp_table() -> str:
    """Table ARP — machines connues sur le réseau local."""
    return _run(["ip", "neigh", "show"])


@mcp.tool()
def curl_fetch(url: str, method: str = "GET", max_size: int = 5000) -> str:
    """Récupérer le contenu d'une URL (GET/HEAD). Réponse tronquée à max_size chars."""
    if not re.match(r"^https?://[a-zA-Z0-9._:/-]+", url):
        return "ERREUR: URL invalide"
    method = method.upper()
    if method not in ("GET", "HEAD"):
        return "ERREUR: méthode doit être GET ou HEAD"
    max_size = min(int(max_size), 20000)
    if method == "HEAD":
        return _run(["curl", "-sI", "--max-time", "10", url], timeout=15)
    result = _run(["curl", "-s", "--max-time", "10", "-L", url], timeout=15)
    return result[:max_size]


@mcp.tool()
def ssl_cert_info(host: str, port: int = 443) -> str:
    """Vérifier le certificat SSL d'un hôte (expiration, émetteur, SAN)."""
    if not SAFE_HOSTNAME.match(host):
        return "ERREUR: hostname invalide"
    result = subprocess.run(
        f"echo | openssl s_client -servername {host} -connect {host}:{port} 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null",
        shell=True, capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip() if result.returncode == 0 else f"ERREUR: impossible de lire le cert de {host}:{port}"


@mcp.tool()
def network_stats() -> str:
    """Statistiques réseau par interface (bytes/paquets RX/TX, erreurs, drops)."""
    return _run(["ip", "-s", "link", "show"])


@mcp.tool()
def wireguard_status() -> str:
    """Status des tunnels WireGuard actifs."""
    return _run(["wg", "show"])


@mcp.tool()
def reverse_dns(ip: str) -> str:
    """Résolution DNS inverse d'une adresse IP."""
    if not re.match(r"^[0-9.:a-fA-F]+$", ip):
        return "ERREUR: adresse IP invalide"
    return _run(["dig", "+short", "-x", ip])


@mcp.tool()
def http_benchmark(url: str, requests: int = 10) -> str:
    """Benchmark HTTP simple — temps de réponse moyen via curl (max 20 requêtes)."""
    if not re.match(r"^https?://[a-zA-Z0-9._:/-]+", url):
        return "ERREUR: URL invalide"
    requests = min(int(requests), 20)
    times = []
    for _ in range(requests):
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{time_total}", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            try:
                times.append(float(result.stdout.strip()))
            except ValueError:
                pass
    if not times:
        return f"ERREUR: aucune réponse de {url}"
    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    return f"URL: {url}\nRequêtes: {len(times)}\nMoyenne: {avg:.3f}s\nMin: {mn:.3f}s\nMax: {mx:.3f}s"


# ── Sécurité & Firewall ─────────────────────────────────────────────


@mcp.tool()
def firewall_status() -> str:
    """Règles firewall actives (iptables ou nftables)."""
    nft = _run(["nft", "list", "ruleset"])
    if not nft.startswith("ERREUR"):
        return nft
    return _run(["iptables", "-L", "-n", "--line-numbers"])


@mcp.tool()
def failed_logins(lines: int = 30) -> str:
    """Tentatives de connexion échouées récentes (SSH, sudo, etc.)."""
    lines = min(int(lines), 200)
    return _run(["journalctl", "--no-pager", "-n", str(lines),
                 "-p", "err", "_SYSTEMD_UNIT=sshd.service"], timeout=15)


@mcp.tool()
def listening_services() -> str:
    """Map port → service → processus pour tous les ports en écoute."""
    return _run(["ss", "-tlnp", "-O"])


@mcp.tool()
def user_sessions(count: int = 20) -> str:
    """Historique des connexions utilisateur."""
    count = min(int(count), 100)
    return _run(["last", "-n", str(count)])


# ── Health & Monitoring ──────────────────────────────────────────────


@mcp.tool()
def health_check_url(url: str, expected_status: int = 200) -> str:
    """Vérifier si une URL répond avec le status code attendu + temps de réponse."""
    if not re.match(r"^https?://[a-zA-Z0-9._:/-]+", url):
        return "ERREUR: URL invalide"
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w",
         "status:%{http_code} time:%{time_total}s size:%{size_download}B",
         "--max-time", "10", "-L", url],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return f"DOWN — {url} ne répond pas ({result.stderr.strip()[:200]})"
    output = result.stdout.strip()
    try:
        status = int(output.split("status:")[1].split(" ")[0])
        healthy = "UP" if status == expected_status else "WARN"
        return f"{healthy} — {url} → {output}"
    except (IndexError, ValueError):
        return f"UNKNOWN — {output}"


@mcp.tool()
def port_wait(host: str, port: int, timeout: int = 30) -> str:
    """Attendre qu'un port soit ouvert (polling 1s). Retourne dès que le port répond."""
    if not SAFE_HOSTNAME.match(host):
        return "ERREUR: hostname invalide"
    port = int(port)
    timeout = min(int(timeout), 120)
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
            elapsed = time.time() - start
            return f"OK: {host}:{port} ouvert après {elapsed:.1f}s"
        except (ConnectionRefusedError, OSError, socket.timeout):
            time.sleep(1)
    return f"TIMEOUT: {host}:{port} toujours fermé après {timeout}s"


# ── Cloudflare ───────────────────────────────────────────────────────


def _load_cf_config() -> dict:
    with open(CLOUDFLARE_CONFIG) as f:
        return yaml.safe_load(f)


def _save_cf_config(cfg: dict) -> None:
    with open(CLOUDFLARE_CONFIG, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


@mcp.tool()
def cloudflare_tunnel_status() -> str:
    """Status du container tunnel-service et infos tunnel."""
    container_status = _run(["docker", "inspect", "--format",
                             "{{.State.Status}} (started {{.State.StartedAt}})",
                             CLOUDFLARE_CONTAINER])
    try:
        cfg = _load_cf_config()
        tunnel_id = cfg.get("tunnel", "inconnu")
        routes = len([r for r in cfg.get("ingress", []) if "hostname" in r])
    except Exception as e:
        return f"Container: {container_status}\nConfig erreur: {e}"
    return f"Container: {container_status}\nTunnel: {tunnel_id}\nRoutes actives: {routes}"


@mcp.tool()
def cloudflare_list_routes() -> str:
    """Liste les routes ingress du tunnel Cloudflare."""
    try:
        cfg = _load_cf_config()
    except Exception as e:
        return f"ERREUR: {e}"
    lines = []
    for rule in cfg.get("ingress", []):
        hostname = rule.get("hostname", "(catch-all)")
        service = rule.get("service", "?")
        lines.append(f"{hostname} → {service}")
    return "\n".join(lines)


@mcp.tool()
def cloudflare_toggle_route(hostname: str, enable: bool = True) -> str:
    """Active ou désactive une route par hostname.
    Désactiver = supprime la route. Activer = impossible si déjà supprimée."""
    try:
        cfg = _load_cf_config()
    except Exception as e:
        return f"ERREUR: {e}"

    ingress = cfg.get("ingress", [])
    if enable:
        for rule in ingress:
            if rule.get("hostname") == hostname:
                return f"Route {hostname} déjà active"
        return f"ERREUR: impossible de réactiver {hostname} — utiliser cloudflare_add_route"

    new_ingress = [r for r in ingress if r.get("hostname") != hostname]
    if len(new_ingress) == len(ingress):
        return f"ERREUR: hostname {hostname} non trouvé"
    cfg["ingress"] = new_ingress
    _save_cf_config(cfg)
    _run(["docker", "restart", CLOUDFLARE_CONTAINER])
    return f"Route {hostname} désactivée et tunnel-service redémarré"


@mcp.tool()
def cloudflare_add_route(hostname: str, service: str) -> str:
    """Ajoute une nouvelle route hostname → service au tunnel Cloudflare."""
    if not re.match(r"^[a-zA-Z0-9.-]+$", hostname):
        return "ERREUR: hostname invalide"
    if not re.match(r"^https?://", service):
        return "ERREUR: service doit commencer par http:// ou https://"
    try:
        cfg = _load_cf_config()
    except Exception as e:
        return f"ERREUR: {e}"

    ingress = cfg.get("ingress", [])
    for rule in ingress:
        if rule.get("hostname") == hostname:
            return f"ERREUR: route {hostname} existe déjà"
    new_rule = {"hostname": hostname, "service": service}
    ingress.insert(-1, new_rule)
    cfg["ingress"] = ingress
    _save_cf_config(cfg)
    _run(["docker", "restart", CLOUDFLARE_CONTAINER])
    return f"Route ajoutée: {hostname} → {service}, tunnel-service redémarré"


if __name__ == "__main__":
    mcp.run(transport="stdio")
