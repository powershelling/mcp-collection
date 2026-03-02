#!/usr/bin/env python3
"""MCP Server — Fichiers & Utilitaires (20 tools)."""

import os
import re
import shutil
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("file-ops")

ALLOWED_READ_PATHS = ("/home/user/", "/var/log/")


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


# ── Fichiers ─────────────────────────────────────────────────────────


@mcp.tool()
def list_dir(path: str = "/home/user", show_hidden: bool = True) -> str:
    """Contenu d'un répertoire (fichiers, tailles, permissions)."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: seuls les chemins sous /home/user/ sont autorisés"
    cmd = ["ls", "-lh"]
    if show_hidden:
        cmd.append("-a")
    cmd.append(path)
    return _run(cmd)


@mcp.tool()
def tree_dir(path: str = "/home/user", depth: int = 3) -> str:
    """Arborescence d'un répertoire (profondeur limitée)."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: seuls les chemins sous /home/user/ sont autorisés"
    depth = min(int(depth), 5)
    return _run(["tree", "-L", str(depth), "--dirsfirst", "-C", path], timeout=30)


@mcp.tool()
def search_files(path: str, pattern: str, max_results: int = 50) -> str:
    """Chercher des fichiers par nom/pattern dans un répertoire."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: seuls les chemins sous /home/user/ sont autorisés"
    if not re.match(r"^[a-zA-Z0-9.*?_\[\]-]+$", pattern):
        return "ERREUR: pattern invalide"
    max_results = min(int(max_results), 200)
    result = _run(["find", path, "-name", pattern, "-maxdepth", "5"], timeout=30)
    lines = result.strip().split("\n")
    return "\n".join(lines[:max_results])


@mcp.tool()
def tail_file(filepath: str, lines: int = 50) -> str:
    """Lire les N dernières lignes d'un fichier (logs, etc.)."""
    filepath = os.path.realpath(filepath)
    if not any(filepath.startswith(p) for p in ALLOWED_READ_PATHS):
        return "ERREUR: seuls les fichiers sous /home/user/ ou /var/log/ sont autorisés"
    lines = min(int(lines), 500)
    return _run(["tail", "-n", str(lines), filepath])


@mcp.tool()
def file_info(filepath: str) -> str:
    """Métadonnées d'un fichier (taille, permissions, type MIME, dates)."""
    filepath = os.path.realpath(filepath)
    if not any(filepath.startswith(p) for p in ALLOWED_READ_PATHS):
        return "ERREUR: seuls les fichiers sous /home/user/ ou /var/log/ sont autorisés"
    stat_out = _run(["stat", filepath])
    file_out = _run(["file", "-b", filepath])
    return f"{stat_out}\n\nType: {file_out}"


@mcp.tool()
def checksum(filepath: str) -> str:
    """Hash SHA256 d'un fichier."""
    filepath = os.path.realpath(filepath)
    if not filepath.startswith("/home/user"):
        return "ERREUR: seuls les fichiers sous /home/user/ sont autorisés"
    return _run(["sha256sum", filepath])


# ── Lecture & Écriture ────────────────────────────────────────────────


def _check_path(path: str, write: bool = False) -> str | None:
    path = os.path.realpath(path)
    allowed = ("/home/user/",) if write else ALLOWED_READ_PATHS
    if not any(path.startswith(p) for p in allowed):
        return None
    return path


@mcp.tool()
def read_file(filepath: str, lines: int = 200, offset: int = 0) -> str:
    """Lire le contenu d'un fichier (max 200 lignes, offset possible)."""
    filepath = _check_path(filepath)
    if not filepath:
        return "ERREUR: chemin non autorisé"
    try:
        with open(filepath, "r", errors="replace") as f:
            all_lines = f.readlines()
        total = len(all_lines)
        lines = min(int(lines), 500)
        offset = max(0, int(offset))
        selected = all_lines[offset:offset + lines]
        content = "".join(selected)
        return f"[{total} lignes total, affichant {offset+1}-{offset+len(selected)}]\n{content}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def head_file(filepath: str, lines: int = 30) -> str:
    """Premières N lignes d'un fichier."""
    filepath = _check_path(filepath)
    if not filepath:
        return "ERREUR: chemin non autorisé"
    lines = min(int(lines), 200)
    return _run(["head", "-n", str(lines), filepath])


@mcp.tool()
def write_file(filepath: str, content: str) -> str:
    """Écrire du contenu dans un fichier (crée ou écrase). Limité à /home/user/."""
    filepath = _check_path(filepath, write=True)
    if not filepath:
        return "ERREUR: écriture limitée à /home/user/"
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)
        return f"OK: {len(content)} bytes écrits dans {filepath}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def append_file(filepath: str, content: str) -> str:
    """Ajouter du contenu à la fin d'un fichier existant."""
    filepath = _check_path(filepath, write=True)
    if not filepath:
        return "ERREUR: écriture limitée à /home/user/"
    try:
        with open(filepath, "a") as f:
            f.write(content)
        return f"OK: {len(content)} bytes ajoutés à {filepath}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def grep_content(path: str, pattern: str, max_results: int = 50) -> str:
    """Chercher un pattern (regex) dans les fichiers d'un répertoire."""
    path = _check_path(path)
    if not path:
        return "ERREUR: chemin non autorisé"
    if not re.match(r"^.{1,200}$", pattern):
        return "ERREUR: pattern trop long ou vide"
    max_results = min(int(max_results), 200)
    result = _run(["grep", "-rn", "--include=*.{py,js,ts,yml,yaml,json,md,txt,conf,cfg,ini,sh,toml}",
                   "-m", str(max_results), pattern, path], timeout=30)
    return result


@mcp.tool()
def diff_files(file1: str, file2: str) -> str:
    """Comparer deux fichiers (diff unifié)."""
    file1 = _check_path(file1)
    file2 = _check_path(file2)
    if not file1 or not file2:
        return "ERREUR: chemin non autorisé"
    result = subprocess.run(["diff", "-u", file1, file2],
                            capture_output=True, text=True, timeout=15)
    if result.returncode == 0:
        return "Fichiers identiques"
    return result.stdout.strip()[:5000]


# ── Opérations fichiers ──────────────────────────────────────────────


@mcp.tool()
def create_dir(path: str) -> str:
    """Créer un répertoire (et parents si nécessaire)."""
    path = _check_path(path, write=True)
    if not path:
        return "ERREUR: limité à /home/user/"
    try:
        os.makedirs(path, exist_ok=True)
        return f"OK: répertoire créé {path}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def move_path(src: str, dst: str) -> str:
    """Déplacer/renommer un fichier ou répertoire."""
    src = _check_path(src, write=True)
    dst = _check_path(dst, write=True)
    if not src or not dst:
        return "ERREUR: limité à /home/user/"
    try:
        shutil.move(src, dst)
        return f"OK: {src} → {dst}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def copy_path(src: str, dst: str) -> str:
    """Copier un fichier ou répertoire."""
    src = _check_path(src)
    dst = _check_path(dst, write=True)
    if not src or not dst:
        return "ERREUR: chemin non autorisé"
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return f"OK: copié {src} → {dst}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def delete_path(path: str, confirm: str = "") -> str:
    """Supprimer un fichier ou répertoire. confirm doit être 'yes' pour confirmer."""
    if confirm != "yes":
        return "ERREUR: ajouter confirm='yes' pour confirmer la suppression"
    path = _check_path(path, write=True)
    if not path:
        return "ERREUR: limité à /home/user/"
    if path == os.path.realpath("/home/user"):
        return "ERREUR: impossible de supprimer le home directory"
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"OK: supprimé {path}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def symlink(target: str, link_path: str) -> str:
    """Créer un lien symbolique."""
    link_path = _check_path(link_path, write=True)
    if not link_path:
        return "ERREUR: limité à /home/user/"
    try:
        os.symlink(target, link_path)
        return f"OK: {link_path} → {target}"
    except Exception as e:
        return f"ERREUR: {e}"


@mcp.tool()
def count_lines(filepath: str) -> str:
    """Compter les lignes, mots et caractères d'un fichier."""
    filepath = _check_path(filepath)
    if not filepath:
        return "ERREUR: chemin non autorisé"
    return _run(["wc", filepath])


@mcp.tool()
def compress(path: str, format: str = "tar.gz") -> str:
    """Compresser un fichier ou répertoire. format: tar.gz ou zip."""
    path = _check_path(path)
    if not path:
        return "ERREUR: chemin non autorisé"
    base = os.path.basename(path.rstrip("/"))
    parent = os.path.dirname(path)
    if format == "tar.gz":
        output = f"{path}.tar.gz"
        return _run(["tar", "-czf", output, "-C", parent, base], timeout=120)
    elif format == "zip":
        output = f"{path}.zip"
        return _run(["zip", "-r", output, base], timeout=120, cwd=parent)
    return "ERREUR: format doit être 'tar.gz' ou 'zip'"


@mcp.tool()
def extract(archive: str, destination: str = "") -> str:
    """Extraire une archive (tar.gz, zip, 7z). destination optionnelle."""
    archive = _check_path(archive)
    if not archive:
        return "ERREUR: chemin non autorisé"
    if destination:
        destination = _check_path(destination, write=True)
        if not destination:
            return "ERREUR: destination limitée à /home/user/"
    else:
        destination = os.path.dirname(archive)
    if archive.endswith((".tar.gz", ".tgz")):
        return _run(["tar", "-xzf", archive, "-C", destination], timeout=120)
    elif archive.endswith(".tar.bz2"):
        return _run(["tar", "-xjf", archive, "-C", destination], timeout=120)
    elif archive.endswith(".tar.xz"):
        return _run(["tar", "-xJf", archive, "-C", destination], timeout=120)
    elif archive.endswith(".zip"):
        return _run(["unzip", "-o", archive, "-d", destination], timeout=120)
    elif archive.endswith(".7z"):
        return _run(["7z", "x", archive, f"-o{destination}", "-y"], timeout=120)
    return "ERREUR: format non supporté (.tar.gz, .tar.bz2, .tar.xz, .zip, .7z)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
