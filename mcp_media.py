#!/usr/bin/env python3
"""MCP Server — Media & Conversion (6 tools)."""

import json
import os
import re
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("media-tools")

ALLOWED_PATHS = ("/home/user/",)
SAFE_FORMAT = re.compile(r"^[a-zA-Z0-9]{2,10}$")


def _run(cmd: list[str], timeout: int = 30, **kwargs) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if r.returncode != 0:
        return f"ERREUR (code {r.returncode}):\n{r.stderr.strip()}"
    return r.stdout.strip()


def _check_path(path: str) -> str | None:
    path = os.path.realpath(path)
    if not any(path.startswith(p) for p in ALLOWED_PATHS):
        return None
    return path


@mcp.tool()
def ffmpeg_info(filepath: str) -> str:
    """Informations détaillées d'un fichier media (durée, codec, résolution, bitrate, audio)."""
    filepath = _check_path(filepath)
    if not filepath:
        return "ERREUR: chemin non autorisé"
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", filepath],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    try:
        data = json.loads(result.stdout)
        parts = []
        fmt = data.get("format", {})
        parts.append(f"Fichier: {fmt.get('filename', '?')}")
        parts.append(f"Format: {fmt.get('format_long_name', fmt.get('format_name', '?'))}")
        duration = float(fmt.get("duration", 0))
        parts.append(f"Durée: {int(duration//3600):02d}:{int((duration%3600)//60):02d}:{int(duration%60):02d}")
        parts.append(f"Taille: {int(fmt.get('size', 0)) / 1e6:.1f} MB")
        parts.append(f"Bitrate: {int(fmt.get('bit_rate', 0)) / 1000:.0f} kbps")
        for s in data.get("streams", []):
            codec_type = s.get("codec_type", "?")
            codec_name = s.get("codec_name", "?")
            if codec_type == "video":
                parts.append(f"\nVideo: {codec_name} {s.get('width')}x{s.get('height')} "
                           f"@ {s.get('r_frame_rate', '?')} fps, {s.get('pix_fmt', '?')}")
            elif codec_type == "audio":
                parts.append(f"Audio: {codec_name} {s.get('sample_rate', '?')} Hz, "
                           f"{s.get('channels', '?')} ch, {s.get('channel_layout', '?')}")
            elif codec_type == "subtitle":
                parts.append(f"Subtitle: {codec_name} ({s.get('tags', {}).get('language', '?')})")
        return "\n".join(parts)
    except (json.JSONDecodeError, KeyError):
        return result.stdout[:3000]


@mcp.tool()
def ffmpeg_convert(input_file: str, output_file: str, options: str = "") -> str:
    """Convertir un fichier media. options = flags ffmpeg supplémentaires (ex: '-c:v libx264 -crf 23').
    Output limité à /home/user/."""
    input_file = _check_path(input_file)
    output_file = _check_path(output_file)
    if not input_file or not output_file:
        return "ERREUR: chemins limités à /home/user/"
    cmd = ["ffmpeg", "-y", "-i", input_file]
    if options:
        # Sécurité basique
        if any(c in options for c in (";", "&&", "||", "`", "$(")):
            return "ERREUR: caractères shell dangereux"
        cmd.extend(options.split())
    cmd.append(output_file)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()[-500:]}"
    size = os.path.getsize(output_file) / 1e6
    return f"OK: {output_file} ({size:.1f} MB)"


@mcp.tool()
def ffmpeg_extract_audio(input_file: str, output_file: str = "", format: str = "mp3") -> str:
    """Extraire la piste audio d'un fichier vidéo."""
    input_file = _check_path(input_file)
    if not input_file:
        return "ERREUR: chemin non autorisé"
    if not SAFE_FORMAT.match(format):
        return "ERREUR: format invalide"
    if not output_file:
        base = os.path.splitext(input_file)[0]
        output_file = f"{base}.{format}"
    output_file = _check_path(output_file)
    if not output_file:
        return "ERREUR: chemin output non autorisé"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_file, "-vn", "-q:a", "2", output_file],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()[-500:]}"
    return f"OK: audio extrait → {output_file}"


@mcp.tool()
def image_info(filepath: str) -> str:
    """Informations d'une image (dimensions, format, profondeur, taille)."""
    filepath = _check_path(filepath)
    if not filepath:
        return "ERREUR: chemin non autorisé"
    result = _run(["identify", "-verbose", filepath], timeout=10)
    if result.startswith("ERREUR"):
        # Fallback avec file + exiftool
        return _run(["file", filepath])
    # Extraire les infos importantes
    important = []
    for line in result.split("\n"):
        line_stripped = line.strip()
        if any(line_stripped.startswith(k) for k in ("Filename:", "Format:", "Geometry:",
                                                       "Resolution:", "Depth:", "Filesize:",
                                                       "Colorspace:", "Type:", "Units:")):
            important.append(line_stripped)
    return "\n".join(important) if important else result[:2000]


@mcp.tool()
def image_resize(input_file: str, output_file: str = "", size: str = "1920x1080", quality: int = 85) -> str:
    """Redimensionner une image. size='1920x1080' ou '50%'. quality=1-100."""
    input_file = _check_path(input_file)
    if not input_file:
        return "ERREUR: chemin non autorisé"
    if not output_file:
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_resized{ext}"
    output_file = _check_path(output_file)
    if not output_file:
        return "ERREUR: chemin output non autorisé"
    if not re.match(r"^(\d+x\d+|\d+%)$", size):
        return "ERREUR: format size invalide (ex: '1920x1080' ou '50%')"
    quality = max(1, min(int(quality), 100))
    result = subprocess.run(
        ["convert", input_file, "-resize", size, "-quality", str(quality), output_file],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    return f"OK: {output_file} (redimensionné à {size})"


@mcp.tool()
def image_convert(input_file: str, output_file: str) -> str:
    """Convertir une image (format déterminé par l'extension output: png, jpg, webp, avif, etc.)."""
    input_file = _check_path(input_file)
    output_file = _check_path(output_file)
    if not input_file or not output_file:
        return "ERREUR: chemins limités à /home/user/"
    result = subprocess.run(
        ["convert", input_file, output_file],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return f"ERREUR: {result.stderr.strip()}"
    return f"OK: {input_file} → {output_file}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
