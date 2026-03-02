#!/usr/bin/env python3
"""MCP Server — Git (11 tools)."""

import os
import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("git-ops")

SAFE_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/~^@{}-]*$")


def _validate_repo(path: str) -> str:
    path = os.path.realpath(path)
    if not path.startswith("/home/user"):
        raise ValueError("Seuls les repos sous /home/user/ sont autorisés")
    if not os.path.isdir(os.path.join(path, ".git")):
        raise ValueError(f"Pas un repo git: {path}")
    return path


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


@mcp.tool()
def git_status(repo: str) -> str:
    """Status git d'un repo (branch, staged, modified, untracked)."""
    repo = _validate_repo(repo)
    return _run(["git", "-C", repo, "status", "--short", "--branch"])


@mcp.tool()
def git_log(repo: str, count: int = 20, oneline: bool = True) -> str:
    """Historique des commits. oneline=True pour format compact."""
    repo = _validate_repo(repo)
    count = min(int(count), 100)
    fmt = "--oneline" if oneline else "--format=%h %ai %an: %s"
    return _run(["git", "-C", repo, "log", fmt, f"-n{count}"])


@mcp.tool()
def git_diff(repo: str, ref: str = "", staged: bool = False) -> str:
    """Diff git. staged=True pour les changements staged. ref pour comparer avec un commit/branch."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "diff"]
    if staged:
        cmd.append("--cached")
    if ref:
        if not SAFE_REF.match(ref):
            return "ERREUR: référence git invalide"
        cmd.append(ref)
    result = _run(cmd, timeout=15)
    return result[:10000] if len(result) > 10000 else result


@mcp.tool()
def git_branches(repo: str, remote: bool = False) -> str:
    """Liste des branches. remote=True pour inclure les branches remote."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "branch", "-v"]
    if remote:
        cmd.append("-a")
    return _run(cmd)


@mcp.tool()
def git_commit(repo: str, message: str, files: str = ".") -> str:
    """Stage des fichiers et commit. files='.' pour tout, sinon 'file1.py file2.py'."""
    repo = _validate_repo(repo)
    if not message or len(message) > 500:
        return "ERREUR: message requis (max 500 chars)"
    # Stage
    file_list = files.split()
    add_cmd = ["git", "-C", repo, "add"] + file_list
    add_result = _run(add_cmd)
    if add_result.startswith("ERREUR"):
        return add_result
    # Commit
    return _run(["git", "-C", repo, "commit", "-m", message])


@mcp.tool()
def git_pull(repo: str, remote: str = "origin", branch: str = "") -> str:
    """Pull depuis un remote. branch vide = branche courante."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "pull", remote]
    if branch:
        if not SAFE_REF.match(branch):
            return "ERREUR: nom de branche invalide"
        cmd.append(branch)
    return _run(cmd, timeout=60)


@mcp.tool()
def git_push(repo: str, remote: str = "origin", branch: str = "") -> str:
    """Push vers un remote. branch vide = branche courante."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "push", remote]
    if branch:
        if not SAFE_REF.match(branch):
            return "ERREUR: nom de branche invalide"
        cmd.append(branch)
    return _run(cmd, timeout=60)


@mcp.tool()
def git_stash_list(repo: str) -> str:
    """Liste des stashs."""
    repo = _validate_repo(repo)
    return _run(["git", "-C", repo, "stash", "list"])


@mcp.tool()
def git_stash_save(repo: str, message: str = "") -> str:
    """Stash les changements en cours. message optionnel."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "stash", "push"]
    if message:
        cmd.extend(["-m", message])
    return _run(cmd)


@mcp.tool()
def git_blame(repo: str, filepath: str, lines: str = "") -> str:
    """Git blame sur un fichier. lines='10,20' pour limiter aux lignes 10-20."""
    repo = _validate_repo(repo)
    cmd = ["git", "-C", repo, "blame", "--date=short"]
    if lines:
        if re.match(r"^\d+,\d+$", lines):
            cmd.extend(["-L", lines])
        else:
            return "ERREUR: format lines='debut,fin' (ex: '10,20')"
    cmd.append(filepath)
    result = _run(cmd, timeout=15)
    return result[:8000] if len(result) > 8000 else result


@mcp.tool()
def git_show(repo: str, ref: str = "HEAD") -> str:
    """Afficher un commit (message + diff). ref = hash, tag, HEAD, etc."""
    repo = _validate_repo(repo)
    if not SAFE_REF.match(ref):
        return "ERREUR: référence git invalide"
    result = _run(["git", "-C", repo, "show", "--stat", ref])
    return result[:8000] if len(result) > 8000 else result


if __name__ == "__main__":
    mcp.run(transport="stdio")
