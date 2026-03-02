#!/usr/bin/env python3
"""MCP Server — PostgreSQL via Docker (6 tools)."""

import json
import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("database-ops")

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

# Containers DB connus — ajouter ici les nouveaux
KNOWN_DBS = {}


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


def _resolve_db(container: str, user: str = "", db: str = "") -> tuple[str, str, str]:
    """Résout les paramètres de connexion. Utilise KNOWN_DBS si disponible."""
    if not SAFE_NAME.match(container):
        raise ValueError(f"Nom de container invalide: {container}")
    known = KNOWN_DBS.get(container, {})
    user = user or known.get("user", "postgres")
    db = db or known.get("db", "postgres")
    return container, user, db


def _psql(container: str, user: str, db: str, query: str, timeout: int = 30) -> str:
    """Exécute une requête psql dans un container Docker."""
    return _run(["docker", "exec", container, "psql", "-U", user, "-d", db,
                 "-c", query], timeout=timeout)


@mcp.tool()
def pg_query(container: str, query: str, user: str = "", db: str = "") -> str:
    """Exécuter une requête SQL (SELECT uniquement) sur une DB PostgreSQL dans Docker.
    Containers connus: project_db-db, project_db-db, project_db-db (user/db auto-résolus)."""
    container, user, db = _resolve_db(container, user, db)
    # Sécurité: bloquer les requêtes destructives
    q_upper = query.upper().strip()
    dangerous = ("DROP ", "DELETE ", "TRUNCATE ", "ALTER ", "UPDATE ", "INSERT ",
                 "CREATE ", "GRANT ", "REVOKE ", "COPY ")
    if any(q_upper.startswith(d) for d in dangerous):
        return "ERREUR: seules les requêtes SELECT / EXPLAIN / WITH (lecture) sont autorisées. Utiliser pg_execute pour les écritures."
    result = _psql(container, user, db, query, timeout=30)
    return result[:15000] if len(result) > 15000 else result


@mcp.tool()
def pg_execute(container: str, query: str, user: str = "", db: str = "", confirm: str = "") -> str:
    """Exécuter une requête d'écriture (INSERT, UPDATE, DELETE, CREATE, ALTER).
    confirm='yes' obligatoire pour les requêtes destructives (DROP, DELETE, TRUNCATE)."""
    container, user, db = _resolve_db(container, user, db)
    q_upper = query.upper().strip()
    destructive = ("DROP ", "DELETE ", "TRUNCATE ")
    if any(q_upper.startswith(d) for d in destructive) and confirm != "yes":
        return "ERREUR: requête destructive — ajouter confirm='yes' pour confirmer"
    result = _psql(container, user, db, query, timeout=60)
    return result[:10000] if len(result) > 10000 else result


@mcp.tool()
def pg_tables(container: str, user: str = "", db: str = "", schema: str = "public") -> str:
    """Lister les tables d'une DB avec colonnes, types et taille."""
    container, user, db = _resolve_db(container, user, db)
    query = f"""SELECT table_name,
       pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size,
       (SELECT count(*) FROM information_schema.columns c WHERE c.table_name = t.table_name AND c.table_schema = '{schema}') as cols
FROM information_schema.tables t
WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE'
ORDER BY pg_total_relation_size(quote_ident(table_name)) DESC;"""
    return _psql(container, user, db, query)


@mcp.tool()
def pg_columns(container: str, table: str, user: str = "", db: str = "") -> str:
    """Colonnes d'une table avec types, nullable, défauts."""
    container, user, db = _resolve_db(container, user, db)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return "ERREUR: nom de table invalide"
    query = f"""SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = '{table}' AND table_schema = 'public'
ORDER BY ordinal_position;"""
    return _psql(container, user, db, query)


@mcp.tool()
def pg_size(container: str, user: str = "", db: str = "") -> str:
    """Taille de la DB et des 20 plus grosses tables."""
    container, user, db = _resolve_db(container, user, db)
    query = """SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;"""
    db_size = _psql(container, user, db, query)
    tables = _psql(container, user, db, """
SELECT relname as table,
       pg_size_pretty(pg_total_relation_size(relid)) as total,
       pg_size_pretty(pg_relation_size(relid)) as data,
       pg_size_pretty(pg_indexes_size(relid)) as indexes,
       n_live_tup as rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;""")
    return f"=== Database ===\n{db_size}\n\n=== Top Tables ===\n{tables}"


@mcp.tool()
def pg_connections(container: str, user: str = "", db: str = "") -> str:
    """Connexions actives sur la DB (PID, user, state, query)."""
    container, user, db = _resolve_db(container, user, db)
    query = """SELECT pid, usename, state, left(query, 100) as query,
       now() - query_start as duration
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start DESC NULLS LAST;"""
    return _psql(container, user, db, query)


@mcp.tool()
def pg_backup(container: str, user: str = "", db: str = "", output_dir: str = "/home/user") -> str:
    """Backup pg_dump d'une DB dans un fichier SQL compressé."""
    container, user, db = _resolve_db(container, user, db)
    output_dir = output_dir.rstrip("/")
    if not output_dir.startswith("/home/user"):
        return "ERREUR: output limité à /home/user/"
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{db}_backup_{ts}.sql.gz"
    filepath = f"{output_dir}/{filename}"
    result = subprocess.run(
        f"docker exec {container} pg_dump -U {user} {db} | gzip > {filepath}",
        shell=True, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    size = _run(["du", "-h", filepath])
    return f"OK: backup créé → {filepath} ({size.split()[0] if size else '?'})"


@mcp.tool()
def pg_restore(container: str, filepath: str, user: str = "", db: str = "", confirm: str = "") -> str:
    """Restaurer un backup SQL(.gz) dans une DB. confirm='yes' obligatoire."""
    if confirm != "yes":
        return "ERREUR: ajouter confirm='yes' pour confirmer la restauration (écrase les données existantes)"
    container, user, db = _resolve_db(container, user, db)
    filepath = filepath.strip()
    if not filepath.startswith("/home/user"):
        return "ERREUR: fichier limité à /home/user/"
    if filepath.endswith(".gz"):
        cmd = f"gunzip -c {filepath} | docker exec -i {container} psql -U {user} -d {db}"
    else:
        cmd = f"cat {filepath} | docker exec -i {container} psql -U {user} -d {db}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()[:2000]}"
    return f"OK: {filepath} restauré dans {container}/{db}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
