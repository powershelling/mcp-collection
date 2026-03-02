#!/usr/bin/env python3
"""MCP Server — Système, Hardware, Stockage, Services, Monitoring (56 tools)."""

import json
import os
import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("system-monitor")

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
SAFE_PACKAGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._+-]*$")
ALLOWED_READ_PATHS = ("/home/user/", "/var/log/")


def _validate_name(name: str) -> str:
    if not SAFE_NAME.match(name):
        raise ValueError(f"Nom invalide: {name}")
    return name


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


def _parse_size(s: str) -> float:
    s = s.strip()
    multipliers = {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return float(s[:-1]) * mult
    try:
        return float(s)
    except ValueError:
        return 0


# ── Système de base ──────────────────────────────────────────────────


@mcp.tool()
def system_info() -> str:
    """OS, kernel, uptime, load average."""
    parts = [
        "=== OS ===", _run(["cat", "/etc/os-release"]),
        "\n=== Kernel ===", _run(["uname", "-r"]),
        "\n=== Uptime ===", _run(["uptime", "-p"]),
        "\n=== Load ===", _run(["cat", "/proc/loadavg"]),
    ]
    return "\n".join(parts)


@mcp.tool()
def memory_usage() -> str:
    """RAM et swap utilisées."""
    return _run(["free", "-h"])


@mcp.tool()
def process_list(sort_by: str = "cpu", count: int = 15) -> str:
    """Top N processus triés par cpu ou mem."""
    sort_by = sort_by.lower()
    if sort_by not in ("cpu", "mem"):
        return "ERREUR: sort_by doit être 'cpu' ou 'mem'"
    count = min(int(count), 50)
    key = "-%cpu" if sort_by == "cpu" else "-%mem"
    return _run(["ps", "aux", "--sort", key, "--lines", str(count + 1)])


@mcp.tool()
def system_uptime_details() -> str:
    """Uptime précis et sessions utilisateur connectées."""
    uptime = _run(["uptime"])
    who = _run(["who"])
    return f"=== Uptime ===\n{uptime}\n\n=== Sessions ===\n{who}"


@mcp.tool()
def system_summary() -> str:
    """Dashboard one-shot : CPU, RAM, GPU, disque, top containers."""
    parts = []
    parts.append("=== CPU & Load ===")
    parts.append(_run(["uptime"]))
    parts.append("\n=== RAM ===")
    parts.append(_run(["free", "-h"]))
    parts.append("\n=== GPU ===")
    parts.append(_run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                        "--format=csv,noheader"]))
    parts.append("\n=== Disques ===")
    parts.append(_run(["df", "-h", "--output=source,size,used,avail,pcent,target",
                        "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"]))
    parts.append("\n=== Top Containers (CPU) ===")
    parts.append(_run(["docker", "stats", "--no-stream", "--format",
                        "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"]))
    return "\n".join(parts)


# ── GPU & Hardware ───────────────────────────────────────────────────


@mcp.tool()
def gpu_info() -> str:
    """Température, utilisation, VRAM et consommation du GPU NVIDIA."""
    return _run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit",
                 "--format=csv,noheader,nounits"])


@mcp.tool()
def gpu_processes() -> str:
    """Processus utilisant le GPU (PID, nom, VRAM utilisée)."""
    return _run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                 "--format=csv,noheader"])


@mcp.tool()
def gpu_clocks() -> str:
    """Fréquences GPU et mémoire (actuelles et max)."""
    return _run(["nvidia-smi", "--query-gpu=clocks.current.graphics,clocks.max.graphics,clocks.current.memory,clocks.max.memory",
                 "--format=csv,noheader"])


@mcp.tool()
def gpu_power_limit(watts: int) -> str:
    """Modifier le power limit du GPU en watts."""
    watts = int(watts)
    if watts < 50 or watts > 400:
        return "ERREUR: power limit doit être entre 50 et 400 watts"
    return _run(["nvidia-smi", "-pl", str(watts)])


@mcp.tool()
def sensors_info() -> str:
    """Températures CPU, carte mère, et autres capteurs via lm-sensors."""
    return _run(["sensors"])


@mcp.tool()
def cpu_info() -> str:
    """Modèle CPU, cœurs, fréquences, cache."""
    return _run(["lscpu"])


# ── Stockage & I/O ───────────────────────────────────────────────────


@mcp.tool()
def disk_usage() -> str:
    """Espace disque par partition."""
    return _run(["df", "-h", "--output=source,size,used,avail,pcent,target",
                 "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"])


@mcp.tool()
def disk_usage_dir(path: str = "/home/user", depth: int = 1) -> str:
    """Taille des sous-dossiers d'un répertoire. depth contrôle la profondeur."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: seuls les chemins sous /home/user/ sont autorisés"
    depth = min(int(depth), 3)
    result = _run(["du", "-h", f"--max-depth={depth}", path], timeout=60)
    lines = result.strip().split("\n")
    try:
        lines.sort(key=lambda l: _parse_size(l.split("\t")[0]), reverse=True)
    except Exception:
        pass
    return "\n".join(lines[:50])


@mcp.tool()
def block_devices() -> str:
    """Disques, partitions et points de montage."""
    return _run(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL"])


@mcp.tool()
def mount_points() -> str:
    """Points de montage réels avec type FS et options."""
    return _run(["findmnt", "--real", "--notruncate", "-o",
                 "TARGET,SOURCE,FSTYPE,OPTIONS"])


@mcp.tool()
def io_stats() -> str:
    """Stats I/O disques (latence, throughput, queue depth)."""
    return _run(["iostat", "-xh", "1", "1"], timeout=10)


@mcp.tool()
def smart_health(device: str = "/dev/sda") -> str:
    """Santé SMART d'un disque. Ex: /dev/sda, /dev/nvme0n1."""
    if not re.match(r"^/dev/[a-zA-Z0-9]+$", device):
        return "ERREUR: chemin device invalide (ex: /dev/sda, /dev/nvme0n1)"
    return _run(["smartctl", "-H", "-A", device], timeout=15)


@mcp.tool()
def zpool_status() -> str:
    """Status pools ZFS ou BTRFS selon ce qui est disponible."""
    zfs = _run(["zpool", "status"])
    if not zfs.startswith("ERREUR"):
        return f"=== ZFS ===\n{zfs}"
    btrfs = _run(["btrfs", "filesystem", "show"])
    if not btrfs.startswith("ERREUR"):
        return f"=== BTRFS ===\n{btrfs}"
    return "Ni ZFS ni BTRFS détecté sur ce système"


@mcp.tool()
def find_large_files(path: str = "/home/user", count: int = 20) -> str:
    """Trouver les N plus gros fichiers dans un répertoire."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: seuls les chemins sous /home/user/ sont autorisés"
    count = min(int(count), 50)
    result = subprocess.run(
        f"find {path} -type f -printf '%s %p\\n' 2>/dev/null | sort -rn | head -n {count}",
        shell=True, capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    lines = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            size_bytes = int(parts[0])
            filepath = parts[1]
            if size_bytes >= 1e9:
                size_str = f"{size_bytes / 1e9:.1f}G"
            elif size_bytes >= 1e6:
                size_str = f"{size_bytes / 1e6:.1f}M"
            elif size_bytes >= 1e3:
                size_str = f"{size_bytes / 1e3:.1f}K"
            else:
                size_str = f"{size_bytes}B"
            lines.append(f"{size_str}\t{filepath}")
    return "\n".join(lines)


# ── Services & Daemons ───────────────────────────────────────────────


@mcp.tool()
def service_status(service: str = "") -> str:
    """Status d'un service systemd, ou liste des services actifs si vide."""
    if not service:
        return _run(["systemctl", "list-units", "--type=service",
                      "--state=running", "--no-pager", "--no-legend"])
    return _run(["systemctl", "status", _validate_name(service), "--no-pager"])


@mcp.tool()
def service_enable(service: str, enable: bool = True) -> str:
    """Activer ou désactiver un service systemd au boot."""
    action = "enable" if enable else "disable"
    return _run(["systemctl", action, _validate_name(service)])


@mcp.tool()
def service_restart(service: str) -> str:
    """Redémarrer un service systemd."""
    return _run(["systemctl", "restart", _validate_name(service)])


@mcp.tool()
def failed_services() -> str:
    """Liste des services systemd en erreur."""
    return _run(["systemctl", "--failed", "--no-pager"])


# ── Logs & Monitoring ────────────────────────────────────────────────


@mcp.tool()
def journal_logs(unit: str = "", priority: str = "", lines: int = 50) -> str:
    """Logs système récents via journalctl. Filtrable par unité et priorité."""
    lines = min(int(lines), 500)
    cmd = ["journalctl", "--no-pager", "-n", str(lines)]
    if unit:
        cmd.extend(["-u", _validate_name(unit)])
    if priority:
        valid_priorities = ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug",
                            "0", "1", "2", "3", "4", "5", "6", "7")
        if priority.lower() not in valid_priorities:
            return f"ERREUR: priorité invalide. Valeurs: {', '.join(valid_priorities)}"
        cmd.extend(["-p", priority.lower()])
    return _run(cmd, timeout=30)


@mcp.tool()
def swap_usage() -> str:
    """Détail utilisation swap et top processus consommateurs."""
    swap_info = _run(["cat", "/proc/swaps"])
    top_swap = subprocess.run(
        "for f in /proc/[0-9]*/status; do "
        "awk '/VmSwap/{swap=$2} /Name/{name=$2} END{if(swap>0) print swap,name}' \"$f\" 2>/dev/null; "
        "done | sort -rn | head -10",
        shell=True, capture_output=True, text=True, timeout=15
    )
    parts = ["=== Swap ===", swap_info, "\n=== Top swap consumers (kB, process) ==="]
    if top_swap.returncode == 0 and top_swap.stdout.strip():
        parts.append(top_swap.stdout.strip())
    else:
        parts.append("(aucun processus en swap)")
    return "\n".join(parts)


@mcp.tool()
def oom_events(lines: int = 20) -> str:
    """Historique des OOM kills du kernel."""
    lines = min(int(lines), 100)
    return _run(["journalctl", "--no-pager", "-k", "--grep=Out of memory",
                 "-n", str(lines)], timeout=15)


# ── Cron & Timers ────────────────────────────────────────────────────


@mcp.tool()
def list_crontabs() -> str:
    """Toutes les tâches planifiées (crontab utilisateur + /etc/cron.d/)."""
    parts = ["=== Crontab utilisateur ==="]
    crontab = _run(["crontab", "-l"])
    parts.append(crontab if crontab else "(vide)")
    parts.append("\n=== /etc/cron.d/ ===")
    try:
        for f in sorted(os.listdir("/etc/cron.d")):
            fpath = os.path.join("/etc/cron.d", f)
            if os.path.isfile(fpath):
                parts.append(f"--- {f} ---")
                with open(fpath) as fh:
                    content = fh.read().strip()
                    parts.append(content[:500] if len(content) > 500 else content)
    except FileNotFoundError:
        parts.append("(répertoire absent)")
    return "\n".join(parts)


@mcp.tool()
def list_timers() -> str:
    """Timers systemd actifs (prochain run, dernier run)."""
    return _run(["systemctl", "list-timers", "--all", "--no-pager"])


@mcp.tool()
def timer_logs(timer: str, lines: int = 30) -> str:
    """Logs d'exécution d'un timer systemd spécifique."""
    lines = min(int(lines), 200)
    return _run(["journalctl", "--no-pager", "-n", str(lines),
                 "-u", _validate_name(timer)])


# ── Packages (Arch/CachyOS) ─────────────────────────────────────────


@mcp.tool()
def package_search(query: str) -> str:
    """Rechercher un paquet dans les repos pacman."""
    if not SAFE_PACKAGE.match(query):
        return "ERREUR: nom de paquet invalide"
    return _run(["pacman", "-Ss", query])


@mcp.tool()
def package_info(package: str) -> str:
    """Infos détaillées d'un paquet installé."""
    if not SAFE_PACKAGE.match(package):
        return "ERREUR: nom de paquet invalide"
    return _run(["pacman", "-Qi", package])


@mcp.tool()
def orphan_packages() -> str:
    """Paquets orphelins (installés comme dépendance, plus requis)."""
    return _run(["pacman", "-Qdt"])


@mcp.tool()
def recent_updates(lines: int = 30) -> str:
    """Dernières mises à jour système (log pacman)."""
    lines = min(int(lines), 200)
    return _run(["tail", "-n", str(lines), "/var/log/pacman.log"])


@mcp.tool()
def cache_clean(keep: int = 2) -> str:
    """Nettoyer le cache pacman (garder N versions de chaque paquet)."""
    keep = max(1, min(int(keep), 5))
    return _run(["paccache", "-rk", str(keep)])


# ── Process Management ────────────────────────────────────────────────


@mcp.tool()
def kill_process(pid: int, signal: str = "TERM") -> str:
    """Envoyer un signal à un processus. signal: TERM, KILL, HUP, INT, USR1."""
    pid = int(pid)
    if pid <= 1:
        return "ERREUR: impossible de kill PID <= 1"
    valid_signals = ("TERM", "KILL", "HUP", "INT", "USR1", "USR2", "STOP", "CONT")
    signal = signal.upper()
    if signal not in valid_signals:
        return f"ERREUR: signal invalide. Valeurs: {', '.join(valid_signals)}"
    return _run(["kill", f"-{signal}", str(pid)])


@mcp.tool()
def find_process(name: str) -> str:
    """Trouver des processus par nom (pgrep + détails)."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", name):
        return "ERREUR: nom de processus invalide"
    return _run(["pgrep", "-a", name])


@mcp.tool()
def process_tree(pid: int = 0) -> str:
    """Arbre des processus. pid=0 pour tout, sinon sous-arbre d'un PID."""
    if pid:
        return _run(["pstree", "-p", str(int(pid))])
    return _run(["pstree", "-p", "-u"])


# ── Kernel & Hardware détaillé ────────────────────────────────────────


@mcp.tool()
def dmesg_logs(lines: int = 50, level: str = "") -> str:
    """Messages kernel récents (dmesg). level: emerg,alert,crit,err,warn,notice,info,debug."""
    lines = min(int(lines), 200)
    cmd = ["dmesg", "--human", "--nopager"]
    if level:
        valid = ("emerg", "alert", "crit", "err", "warn", "notice", "info", "debug")
        if level.lower() not in valid:
            return f"ERREUR: level invalide. Valeurs: {', '.join(valid)}"
        cmd.extend(["--level", level.lower()])
    result = _run(cmd, timeout=15)
    return "\n".join(result.strip().split("\n")[-lines:])


@mcp.tool()
def usb_devices() -> str:
    """Liste des périphériques USB connectés."""
    return _run(["lsusb"])


@mcp.tool()
def pci_devices() -> str:
    """Liste des périphériques PCI (GPU, réseau, stockage, etc.)."""
    return _run(["lspci"])


@mcp.tool()
def kernel_modules(filter: str = "") -> str:
    """Modules kernel chargés. filter pour chercher un module spécifique."""
    result = _run(["lsmod"])
    if filter:
        lines = result.split("\n")
        header = lines[0] if lines else ""
        filtered = [l for l in lines[1:] if filter.lower() in l.lower()]
        return header + "\n" + "\n".join(filtered) if filtered else f"Aucun module matching '{filter}'"
    return result


@mcp.tool()
def memory_detailed() -> str:
    """Détail mémoire complet: RAM, buffers, cache, slab, huge pages."""
    result = _run(["cat", "/proc/meminfo"])
    important_keys = ("MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
                      "SwapTotal", "SwapFree", "Dirty", "Shmem", "SReclaimable",
                      "SUnreclaim", "HugePages_Total", "HugePages_Free", "Hugepagesize")
    lines = []
    for line in result.split("\n"):
        if any(line.startswith(k) for k in important_keys):
            lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def cpu_frequency() -> str:
    """Fréquences CPU par cœur (actuelle, min, max)."""
    result = subprocess.run(
        "cat /proc/cpuinfo | grep 'MHz' | head -16",
        shell=True, capture_output=True, text=True, timeout=5
    )
    scaling = _run(["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"])
    freq_info = result.stdout.strip() if result.returncode == 0 else "N/A"
    return f"=== Fréquences par cœur ===\n{freq_info}\n\n=== Governor ===\n{scaling}"


@mcp.tool()
def user_info() -> str:
    """Infos utilisateur courant: uid, gid, groupes, home, shell."""
    parts = [
        "=== ID ===", _run(["id"]),
        "\n=== Groups ===", _run(["groups"]),
        "\n=== Home & Shell ===",
        f"HOME={os.environ.get('HOME', '?')}",
        f"SHELL={os.environ.get('SHELL', '?')}",
    ]
    return "\n".join(parts)


@mcp.tool()
def environment_vars(filter: str = "") -> str:
    """Variables d'environnement. filter pour chercher (ex: 'PATH', 'DOCKER')."""
    env_list = sorted(os.environ.items())
    if filter:
        env_list = [(k, v) for k, v in env_list if filter.upper() in k.upper()]
    # Masquer les secrets potentiels
    safe_list = []
    for k, v in env_list:
        if any(s in k.upper() for s in ("SECRET", "TOKEN", "PASSWORD", "KEY", "CREDENTIAL")):
            safe_list.append(f"{k}=***MASKED***")
        else:
            safe_list.append(f"{k}={v}")
    return "\n".join(safe_list[:100])


@mcp.tool()
def system_locale() -> str:
    """Locale et timezone du système."""
    locale_info = _run(["locale"])
    tz = _run(["timedatectl", "show", "--property=Timezone", "--value"])
    return f"=== Locale ===\n{locale_info}\n\n=== Timezone ===\n{tz}"


@mcp.tool()
def open_file_descriptors(count: int = 20) -> str:
    """Top processus par nombre de fichiers ouverts."""
    count = min(int(count), 50)
    result = subprocess.run(
        f"for pid in /proc/[0-9]*/fd; do "
        f"echo $(ls -1 $pid 2>/dev/null | wc -l) $(cat $(dirname $pid)/comm 2>/dev/null) $pid; "
        f"done 2>/dev/null | sort -rn | head -n {count}",
        shell=True, capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0 or not result.stdout.strip():
        return _run(["cat", "/proc/sys/fs/file-nr"])
    return f"=== FDs ouverts (count, process, path) ===\n{result.stdout.strip()}\n\n=== Limites système ===\n{_run(['cat', '/proc/sys/fs/file-nr'])}"


@mcp.tool()
def boot_time() -> str:
    """Heure de démarrage du système et temps depuis le boot."""
    return _run(["systemd-analyze"])


# ── Tmux ──────────────────────────────────────────────────────────────


@mcp.tool()
def tmux_list() -> str:
    """Liste des sessions tmux actives avec leurs fenêtres."""
    sessions = _run(["tmux", "list-sessions"])
    if sessions.startswith("ERREUR"):
        return "Aucune session tmux active"
    windows = _run(["tmux", "list-windows", "-a"])
    return f"=== Sessions ===\n{sessions}\n\n=== Fenêtres ===\n{windows}"


@mcp.tool()
def tmux_new(session_name: str, command: str = "") -> str:
    """Créer une nouvelle session tmux détachée. command optionnel pour lancer un programme."""
    if not SAFE_NAME.match(session_name):
        return "ERREUR: nom de session invalide"
    cmd = ["tmux", "new-session", "-d", "-s", session_name]
    if command:
        cmd.extend([command])
    return _run(cmd)


@mcp.tool()
def tmux_send(session: str, keys: str) -> str:
    """Envoyer des touches/commande à une session tmux. Ajoute Enter automatiquement."""
    if not SAFE_NAME.match(session):
        return "ERREUR: nom de session invalide"
    result = _run(["tmux", "send-keys", "-t", session, keys, "Enter"])
    return result if result else "OK: commande envoyée"


@mcp.tool()
def tmux_capture(session: str, lines: int = 50) -> str:
    """Capturer le contenu visible d'un pane tmux."""
    if not SAFE_NAME.match(session):
        return "ERREUR: nom de session invalide"
    lines = min(int(lines), 500)
    return _run(["tmux", "capture-pane", "-t", session, "-p", "-S", f"-{lines}"])


# ── Cron Management ──────────────────────────────────────────────────


@mcp.tool()
def crontab_add(schedule: str, command: str, comment: str = "") -> str:
    """Ajouter une entrée crontab. schedule='0 2 * * *', command='/path/to/script.sh'."""
    if not re.match(r"^[0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+$", schedule):
        return "ERREUR: format cron invalide (ex: '0 2 * * *')"
    if any(c in command for c in ("`", "$(")):
        return "ERREUR: caractères shell dangereux"
    # Lire crontab actuel
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = current.stdout if current.returncode == 0 else ""
    # Ajouter la nouvelle entrée
    entry = f"{schedule} {command}"
    if comment:
        entry = f"# {comment}\n{entry}"
    new_crontab = existing.rstrip("\n") + "\n" + entry + "\n"
    result = subprocess.run(["crontab", "-"], input=new_crontab,
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    return f"OK: cron ajouté → {schedule} {command}"


@mcp.tool()
def crontab_remove(pattern: str) -> str:
    """Supprimer des entrées crontab matching un pattern (dans la commande)."""
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if current.returncode != 0:
        return "ERREUR: pas de crontab ou erreur de lecture"
    lines = current.stdout.split("\n")
    new_lines = [l for l in lines if pattern not in l]
    removed = len(lines) - len(new_lines)
    if removed == 0:
        return f"Aucune entrée matching '{pattern}'"
    new_crontab = "\n".join(new_lines)
    result = subprocess.run(["crontab", "-"], input=new_crontab,
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    return f"OK: {removed} entrée(s) supprimée(s) matching '{pattern}'"


# ── Notifications ────────────────────────────────────────────────────


@mcp.tool()
def notify_desktop(title: str, message: str, urgency: str = "normal") -> str:
    """Envoyer une notification desktop. urgency: low, normal, critical."""
    if urgency not in ("low", "normal", "critical"):
        return "ERREUR: urgency doit être low, normal ou critical"
    return _run(["notify-send", f"--urgency={urgency}", title, message])


# ── Process Watching ─────────────────────────────────────────────────


@mcp.tool()
def watch_process(name: str) -> str:
    """Vérifier si un processus tourne + détails (PID, CPU, RAM, uptime)."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", name):
        return "ERREUR: nom invalide"
    pids = _run(["pgrep", "-f", name])
    if pids.startswith("ERREUR") or not pids.strip():
        return f"'{name}' ne tourne PAS"
    pid_list = pids.strip().split("\n")[:5]
    parts = [f"'{name}' tourne — {len(pid_list)} processus"]
    for pid in pid_list:
        info = _run(["ps", "-p", pid.strip(), "-o", "pid,pcpu,pmem,etime,comm", "--no-headers"])
        if not info.startswith("ERREUR"):
            parts.append(f"  {info.strip()}")
    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run(transport="stdio")
