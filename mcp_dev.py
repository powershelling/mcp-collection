#!/usr/bin/env python3
"""MCP Server — Dev & Python (8 tools)."""

import os
import re
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("dev-tools")

SAFE_PACKAGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


# ── Python ────────────────────────────────────────────────────────────


@mcp.tool()
def run_python(code: str, timeout: int = 30) -> str:
    """Exécuter un snippet Python dans un sandbox temporaire. Max 30s."""
    timeout = min(int(timeout), 60)
    if len(code) > 50000:
        return "ERREUR: code trop long (max 50000 chars)"
    # Bloquer les imports dangereux
    dangerous = ("subprocess", "shutil.rmtree", "os.system", "os.popen",
                 "exec(", "eval(", "__import__")
    for d in dangerous:
        if d in code:
            return f"ERREUR: '{d}' interdit dans le sandbox"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["python3", f.name],
                capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )
            output = ""
            if result.stdout.strip():
                output += result.stdout.strip()
            if result.stderr.strip():
                output += f"\n[STDERR]\n{result.stderr.strip()}"
            if result.returncode != 0:
                output = f"[EXIT CODE: {result.returncode}]\n{output}"
            return output[:10000] if output else "(aucune sortie)"
        except subprocess.TimeoutExpired:
            return f"ERREUR: timeout après {timeout}s"
        finally:
            os.unlink(f.name)


@mcp.tool()
def python_version() -> str:
    """Version Python et chemin de l'interpréteur."""
    version = _run(["python3", "--version"])
    path = _run(["which", "python3"])
    return f"{version}\nPath: {path}"


@mcp.tool()
def pip_list(filter: str = "") -> str:
    """Liste des packages Python installés. filter pour chercher."""
    result = _run(["pip", "list", "--format=columns"], timeout=15)
    if filter:
        lines = result.split("\n")
        header = lines[:2] if len(lines) >= 2 else lines
        filtered = [l for l in lines[2:] if filter.lower() in l.lower()]
        return "\n".join(header + filtered) if filtered else f"Aucun paquet matching '{filter}'"
    return result


@mcp.tool()
def pip_install(package: str) -> str:
    """Installer un package Python via pip."""
    if not SAFE_PACKAGE.match(package):
        return "ERREUR: nom de package invalide"
    return _run(["pip", "install", package], timeout=120)


@mcp.tool()
def pip_show(package: str) -> str:
    """Infos détaillées d'un package pip (version, dépendances, localisation)."""
    if not SAFE_PACKAGE.match(package):
        return "ERREUR: nom de package invalide"
    return _run(["pip", "show", package])


@mcp.tool()
def venv_create(path: str, python: str = "python3") -> str:
    """Créer un virtualenv Python."""
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        return "ERREUR: limité à /home/user/"
    return _run([python, "-m", "venv", path], timeout=30)


@mcp.tool()
def venv_list_packages(venv_path: str) -> str:
    """Liste des packages dans un virtualenv."""
    venv_path = os.path.realpath(venv_path)
    if not venv_path.startswith("/home/user"):
        return "ERREUR: limité à /home/user/"
    pip_path = os.path.join(venv_path, "bin", "pip")
    if not os.path.isfile(pip_path):
        return f"ERREUR: pas de virtualenv trouvé à {venv_path}"
    return _run([pip_path, "list", "--format=columns"])


@mcp.tool()
def python_eval(expression: str) -> str:
    """Évaluer une expression Python simple (math, conversions, etc.). Max 200 chars."""
    if len(expression) > 200:
        return "ERREUR: expression trop longue (max 200 chars)"
    # Whitelist: que des opérations sûres
    allowed = set("0123456789+-*/.() ,[]{}:\"'_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if not all(c in allowed for c in expression):
        return "ERREUR: caractères non autorisés"
    try:
        result = subprocess.run(
            ["python3", "-c", f"print({expression})"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else f"ERREUR: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "ERREUR: timeout"


if __name__ == "__main__":
    mcp.run(transport="stdio")
