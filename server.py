#!/usr/bin/env python3
"""Local web video player server."""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime

from flask import Flask, abort, jsonify, render_template_string, request, send_file

app = Flask(__name__)

# Configuration for library structure
# Directory structure: Shows/<SeriesName>/<SeasonName>/episodes or Movies/<SeriesName>/<MovieName>/files
SHOWS_DIR: Path = None
MOVIES_DIR: Path = None

# Catalog structure: {route_path: {"dir": Path, "catalog": list[dict], ...}}
LIBRARY_CATALOG: dict[str, dict] = {}

# Route mapping: {route_id: {"type": "show" | "movie", "series": str, "season_or_movie": str, "path": Path}}
ROUTE_MAP: dict[str, dict] = {}

STATE_FILE = Path(__file__).parent / "state.json"
CONFIG_FILE = Path(__file__).parent / "library-config.json"
TRANSITION_TIMER_FILE = Path(__file__).parent / "parrot_transition_timer.html"


def load_state() -> dict:
    if STATE_FILE.exists():
        text = STATE_FILE.read_text().strip()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                app.logger.error("state.json is corrupt, resetting to empty state")
                return {}
    return {}


def save_state(state: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=STATE_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state, indent=2))
        Path(tmp_path).replace(STATE_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def load_config() -> dict:
    """Load library configuration from disk."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            app.logger.error("library-config.json is corrupt")
            return {}
    return {}


def save_config(config: dict) -> None:
    """Save library configuration to disk."""
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(config, indent=2, default=str))
        Path(tmp_path).replace(CONFIG_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def serialize_catalog(catalog: dict) -> dict:
    """Convert catalog with Path objects to JSON-serializable format."""
    def serialize_obj(obj):
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: serialize_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [serialize_obj(item) for item in obj]
        return obj
    return serialize_obj(catalog)


def deserialize_catalog(data: dict) -> dict:
    """Convert JSON data back to catalog format with Path objects."""
    def deserialize_obj(obj):
        if isinstance(obj, dict):
            # Check if this looks like a path string
            if "path" in obj and isinstance(obj.get("path"), str):
                obj_copy = obj.copy()
                obj_copy["path"] = Path(obj["path"])
                return {k: deserialize_obj(v) for k, v in obj_copy.items()}
            return {k: deserialize_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [deserialize_obj(item) for item in obj]
        return obj
    return deserialize_obj(data)


def _parse_title(stem: str) -> str:
    """Extract a human-readable title from a video filename stem."""
    # "Above & Beyond S03_01. Pininga Turtle" → "Pininga Turtle"
    m = re.search(r'S\d+_\d+\.\s*(.+)', stem)
    if m:
        return m.group(1).strip()
    # "Octonauts - Title | ..." or "Octonauts & Title"
    m = re.search(r'Octonauts\s+[-&]\s+([^|]+)', stem)
    if m:
        return m.group(1).strip()
    return stem


def load_all_metadata(directory: Path) -> list[dict]:
    has_metadata: dict[Path, dict] = {}
    for metadata_path in sorted(directory.glob("*_stills/metadata.json")):
        data = json.loads(metadata_path.read_text())
        has_metadata[Path(data["source"]).name] = data

    results = []
    for video in sorted(p for ext in ("*.mp4", "*.mkv") for p in directory.glob(ext)):
        if video.name in has_metadata:
            results.append(has_metadata[video.name])
        else:
            results.append({
                "title": _parse_title(video.stem),
                "source": str(video),
                "grids": [],
            })
    return results


def scan_shows_directory(shows_dir: Path) -> dict[str, dict]:
    """
    Scan Shows directory structure: Shows/<SeriesName>/<SeasonName>/episodes
    Returns: {series_key: {series_name, seasons: {season_key: {season_name, path, catalog}}}}
    """
    catalog = {}
    if not shows_dir or not shows_dir.is_dir():
        return catalog

    child_directories = sorted(p for p in shows_dir.iterdir() if p.is_dir())
    season_pattern = re.compile(r"^(?P<series>.+?)\s+Season\s+\d+$", re.IGNORECASE)
    season_matches = [season_pattern.match(path.name) for path in child_directories]
    if child_directories and all(season_matches):
      series_name = season_matches[0].group("series").strip()
      series_key = _slugify(series_name)
      seasons = {}
      for season_path in child_directories:
        season_name = season_path.name
        season_key = _slugify(season_name)
        seasons[season_key] = {
          "name": season_name,
          "path": season_path,
          "catalog": load_all_metadata(season_path),
        }
      return {
        series_key: {
          "name": series_name,
          "path": shows_dir,
          "seasons": seasons,
        }
      }
    
    for series_path in sorted(shows_dir.iterdir()):
        if not series_path.is_dir():
            continue
        series_name = series_path.name
        series_key = _slugify(series_name)
        seasons = {}
        
        for season_path in sorted(series_path.iterdir()):
            if not season_path.is_dir():
                continue
            season_name = season_path.name
            season_key = _slugify(season_name)
            
            # Load catalog for this season
            season_catalog = load_all_metadata(season_path)
            seasons[season_key] = {
                "name": season_name,
                "path": season_path,
                "catalog": season_catalog,
            }
        
        if seasons:
            catalog[series_key] = {
                "name": series_name,
                "path": series_path,
                "seasons": seasons,
            }
    
    return catalog


def scan_movies_directory(movies_dir: Path) -> dict[str, dict]:
    """
    Scan Movies directory structure: Movies/<SeriesName>/<MovieName>/files
    Returns: {series_key: {series_name, movies: {movie_key: {movie_name, path, catalog}}}}
    """
    catalog = {}
    if not movies_dir or not movies_dir.is_dir():
        return catalog
    
    for series_path in sorted(movies_dir.iterdir()):
        if not series_path.is_dir():
            continue
        series_name = series_path.name
        series_key = _slugify(series_name)
        movies = {}
        
        for movie_path in sorted(series_path.iterdir()):
            if not movie_path.is_dir():
                continue
            movie_name = movie_path.name
            movie_key = _slugify(movie_name)
            
            # Load catalog for this movie
            movie_catalog = load_all_metadata(movie_path)
            movies[movie_key] = {
                "name": movie_name,
                "path": movie_path,
                "catalog": movie_catalog,
            }
        
        if movies:
            catalog[series_key] = {
                "name": series_name,
                "path": series_path,
                "movies": movies,
            }
    
    return catalog


def _slugify(name: str) -> str:
    """Convert name to URL-safe slug."""
    return name.lower().replace(" ", "-").replace("_", "-")


def build_route_map() -> None:
    """Build the route mapping from catalog structure."""
    global ROUTE_MAP, LIBRARY_CATALOG
    ROUTE_MAP.clear()
    route_id = 0
    
    # Add shows routes
    if "shows" in LIBRARY_CATALOG:
        for series_key, series_data in LIBRARY_CATALOG["shows"].items():
            for season_key, season_data in series_data.get("seasons", {}).items():
                route_id += 1
                route_path = f"shows/{series_key}/{season_key}"
                ROUTE_MAP[route_id] = {
                    "type": "show",
                    "series": series_data["name"],
                    "series_key": series_key,
                    "season": season_data["name"],
                    "season_key": season_key,
                    "path": season_data["path"],
                    "route_path": route_path,
                }
    
    # Add movies routes
    if "movies" in LIBRARY_CATALOG:
        for series_key, series_data in LIBRARY_CATALOG["movies"].items():
            for movie_key, movie_data in series_data.get("movies", {}).items():
                route_id += 1
                route_path = f"movies/{series_key}/{movie_key}"
                ROUTE_MAP[route_id] = {
                    "type": "movie",
                    "series": series_data["name"],
                    "series_key": series_key,
                    "movie": movie_data["name"],
                    "movie_key": movie_key,
                    "path": movie_data["path"],
                    "route_path": route_path,
                }


def get_route_info_by_path(route_path: str) -> dict | None:
    """Get route info by path string like 'shows/series-name/season-name'."""
    for route_data in ROUTE_MAP.values():
        if route_data.get("route_path") == route_path:
            return route_data
    return None


def get_all_allowed_dirs() -> list[Path]:
    """Get all allowed directories for media serving."""
    dirs = []
    for route_data in ROUTE_MAP.values():
        dirs.append(route_data["path"])
    return dirs


LIBRARY_HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Media Library</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #8aafc5 url('/background.png') center center / cover fixed;
      color: #e0f4ff;
      font-family: Arial, Helvetica, sans-serif;
      min-height: 100vh;
    }

    header {
      background: #0b1e36;
      border-bottom: 2px solid #1a4a6e;
      padding: 14px 24px;
      display: flex;
      align-items: center;
    }
    header h1 {
      font-size: 1.4rem;
      letter-spacing: 4px;
      color: #5bc8f5;
      flex: 1;
      text-align: center;
    }

    .picker {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      gap: 40px;
      padding: 60px 28px;
      flex-wrap: wrap;
    }

    .series-card {
      width: 360px;
      background: #0d2240;
      border-radius: 16px;
      overflow: hidden;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid #1a3a5c;
      transition: transform 0.18s, box-shadow 0.18s;
      display: block;
    }
    .series-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 12px 32px rgba(0, 140, 220, 0.4);
    }
    .series-card-label {
      padding: 20px 18px;
      font-size: 1.2rem;
      letter-spacing: 2px;
      color: #7a9ebb;
      text-align: center;
      background: #0a1a30;
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
  </style>
</head>
<body>

<header>
  <h1>MEDIA LIBRARY</h1>
</header>

<div class="picker">
  <a class="series-card" href="/shows">
    <div class="series-card-label">🎬 TV SHOWS</div>
  </a>
  <a class="series-card" href="/movies">
    <div class="series-card-label">🎥 MOVIES</div>
  </a>
</div>

</body>
</html>
"""

SERIES_PICKER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #8aafc5 url('/background.png') center center / cover fixed;
      color: #e0f4ff;
      font-family: Arial, Helvetica, sans-serif;
      min-height: 100vh;
    }

    header {
      background: #0b1e36;
      border-bottom: 2px solid #1a4a6e;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    header h1 {
      font-size: 1.4rem;
      letter-spacing: 4px;
      color: #5bc8f5;
      flex: 1;
      text-align: center;
    }
    .home-link {
      background: #1a4a6e;
      color: #a0d8f0;
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 0.9rem;
      text-decoration: none;
      transition: background 0.15s;
    }
    .home-link:hover { background: #255f8a; }

    .picker {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      gap: 40px;
      padding: 60px 28px;
      flex-wrap: wrap;
    }

    .series-card {
      width: 360px;
      background: #0d2240;
      border-radius: 16px;
      overflow: hidden;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid #1a3a5c;
      transition: transform 0.18s, box-shadow 0.18s;
      display: block;
    }
    .series-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 12px 32px rgba(0, 140, 220, 0.4);
    }
    .series-card-label {
      padding: 14px 18px;
      font-size: 1rem;
      letter-spacing: 2px;
      color: #7a9ebb;
      text-align: center;
      background: #0a1a30;
      min-height: 60px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
  </style>
</head>
<body>

<header>
  <a class="home-link" href="{{ back_url }}">&#8592; Back</a>
  <h1>{{ title }}</h1>
</header>

<div class="picker" id="picker"></div>

<script>
  const seriesList = {{ series_list | tojson }};
  const picker = document.getElementById('picker');
  
  seriesList.forEach(item => {
    const a = document.createElement('a');
    a.href = item.url;
    a.className = 'series-card';
    a.innerHTML = '<div class="series-card-label">' + item.name + '</div>';
    picker.appendChild(a);
  });
</script>

</body>
</html>
"""

ABOVE_BEYOND_PICKER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Above &amp; Beyond &mdash; Seasons</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #8aafc5 url('/background.png') center center / cover fixed;
      color: #e0f4ff;
      font-family: Arial, Helvetica, sans-serif;
      min-height: 100vh;
    }

    header {
      background: #0b1e36;
      border-bottom: 2px solid #1a4a6e;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    header h1 {
      font-size: 1.4rem;
      letter-spacing: 4px;
      color: #5bc8f5;
      flex: 1;
      text-align: center;
    }
    .home-link {
      background: #1a4a6e;
      color: #a0d8f0;
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 0.9rem;
      text-decoration: none;
      transition: background 0.15s;
    }
    .home-link:hover { background: #255f8a; }

    .picker {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      gap: 40px;
      padding: 60px 28px;
      flex-wrap: wrap;
    }

    .series-card {
      width: 360px;
      background: #0d2240;
      border-radius: 16px;
      overflow: hidden;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid #1a3a5c;
      transition: transform 0.18s, box-shadow 0.18s;
      display: block;
    }
    .series-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 12px 32px rgba(0, 140, 220, 0.4);
    }
    .series-card img {
      width: 100%;
      display: block;
      aspect-ratio: 16 / 9;
      object-fit: cover;
    }
    .series-card-label {
      padding: 14px 18px;
      font-size: 1rem;
      letter-spacing: 2px;
      color: #7a9ebb;
      text-align: center;
    }
  </style>
</head>
<body>

<header>
  <a class="home-link" href="/">&#8592; Home</a>
  <h1>ABOVE &amp; BEYOND</h1>
</header>

<div class="picker">
  <a class="series-card" href="/above-and-beyond/s03">
    <img src="/images/octonauts_above_and_beyond.webp" alt="Season 3">
    <div class="series-card-label">SEASON 3</div>
  </a>
  <a class="series-card" href="/above-and-beyond/s04">
    <img src="/images/octonauts_above_and_beyond.webp" alt="Season 4">
    <div class="series-card-label">SEASON 4</div>
  </a>
</div>

</body>
</html>
"""

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Octonauts for Alexander</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #8aafc5 url('/background.png') center center / cover fixed;
      color: #e0f4ff;
      font-family: Arial, Helvetica, sans-serif;
      min-height: 100vh;
    }

    header {
      background: #0b1e36;
      border-bottom: 2px solid #1a4a6e;
      padding: 14px 24px;
      display: flex;
      align-items: center;
    }
    header h1 {
      font-size: 1.4rem;
      letter-spacing: 4px;
      color: #5bc8f5;
      flex: 1;
      text-align: center;
    }

    .picker {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      gap: 40px;
      padding: 60px 28px;
      flex-wrap: wrap;
    }

    .series-card {
      position: relative;
      width: 360px;
      background: #0d2240;
      border-radius: 16px;
      overflow: hidden;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid #1a3a5c;
      transition: transform 0.18s, box-shadow 0.18s;
      display: block;
    }
    .series-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 12px 32px rgba(0, 140, 220, 0.4);
    }
    .series-card img {
      width: 100%;
      display: block;
      aspect-ratio: 16 / 9;
      object-fit: cover;
    }
    .series-card-label {
      padding: 14px 18px;
      font-size: 1rem;
      letter-spacing: 2px;
      color: #7a9ebb;
      text-align: center;
    }

    .coming-soon-badge {
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(11, 30, 54, 0.82);
      color: #5bc8f5;
      font-size: 0.75rem;
      letter-spacing: 2px;
      padding: 5px 12px;
      border-radius: 20px;
      border: 1px solid #1a4a6e;
    }
  </style>
</head>
<body>

<header>
  <h1>OCTONAUTS for ALEXANDER</h1>
</header>

<div class="picker">
  <a class="series-card" href="/octonauts">
    <img src="/images/octonauts.jpg" alt="Octonauts">
    <div class="series-card-label">OCTONAUTS</div>
  </a>
  <a class="series-card" href="/above-and-beyond">
    <img src="/images/octonauts_above_and_beyond.webp" alt="Octonauts: Above & Beyond">
    <div class="series-card-label">ABOVE &amp; BEYOND</div>
  </a>
</div>

</body>
</html>
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ page_title }}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #8aafc5 url('/background.png') center center / cover fixed;
      color: #e0f4ff;
      font-family: Arial, Helvetica, sans-serif;
      min-height: 100vh;
    }

    /* ── Header ───────────────────────────────────────── */
    header {
      background: #0b1e36;
      border-bottom: 2px solid #1a4a6e;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    header h1 {
      font-size: 1.4rem;
      letter-spacing: 4px;
      color: #5bc8f5;
      flex: 1;
    }
    #back-btn {
      display: none;
      background: #1a4a6e;
      border: none;
      color: #a0d8f0;
      padding: 8px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.9rem;
      transition: background 0.15s;
    }
    #back-btn:hover { background: #255f8a; }
    .home-link {
      background: #1a4a6e;
      color: #a0d8f0;
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 0.9rem;
      text-decoration: none;
      transition: background 0.15s;
    }
    .home-link:hover { background: #255f8a; }

    /* ── Loading ──────────────────────────────────────── */
    #loading {
      text-align: center;
      padding: 80px 24px;
      color: #4a90b8;
      font-size: 1rem;
      letter-spacing: 1px;
    }

    /* ── Library grid ─────────────────────────────────── */
    #library {
      padding: 28px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 22px;
    }
    .card {
      position: relative;
      background: #0d2240;
      border-radius: 12px;
      overflow: hidden;
      cursor: pointer;
      transition: transform 0.18s, box-shadow 0.18s;
      border: 1px solid #1a3a5c;
    }
    .card:hover {
      transform: translateY(-5px);
      box-shadow: 0 10px 28px rgba(0, 140, 220, 0.35);
    }
    .card img {
      width: 100%;
      display: block;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      filter: grayscale(30%) brightness(0.75);
      transition: filter 0.18s;
    }
    .card:hover img {
      filter: grayscale(0%) brightness(1);
    }
    .card-no-thumb {
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #0a1a30;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #4a6a88;
      font-size: 0.85rem;
      padding: 12px;
      text-align: center;
    }
    .card-body {
      padding: 10px 14px 14px;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
    }
    .card-title {
      font-size: 0.88rem;
      color: #7a9ebb;
      line-height: 1.4;
    }
    .card-duration {
      font-size: 0.78rem;
      color: #4a8fb8;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .card-progress { height: 4px; background: #1a3a5c; }
    .card-progress-fill { height: 100%; background: #1a94e8; }
    .card-remaining { font-size: 0.75rem; color: #4a8fb8; padding: 2px 14px 10px; }
    .card-watched-badge {
      position: absolute;
      top: 8px; right: 8px;
      background: rgba(0,0,0,0.55);
      color: #4cdf80;
      font-size: 1.1rem;
      border-radius: 50%;
      width: 28px; height: 28px;
      display: flex; align-items: center; justify-content: center;
    }
    .card-watched-label { font-size: 0.75rem; color: #4cdf80; padding: 2px 14px 10px; }

    /* ── Slideshow ────────────────────────────────────── */
    #slideshow {
      display: none;
      flex-direction: column;
      align-items: center;
      padding: 24px;
      max-width: 1100px;
      margin: 0 auto;
    }
    #slideshow-title {
      font-size: 1.15rem;
      color: #5bc8f5;
      letter-spacing: 1px;
      margin-bottom: 18px;
      text-align: center;
    }
    .slide-stage {
      position: relative;
      width: 100%;
      background: #000;
      border-radius: 10px;
      overflow: hidden;
      line-height: 0;
    }
    #slide-img {
      width: 100%;
      display: block;
      max-height: 66vh;
      object-fit: contain;
      background: #000;
    }
    /* slide-in animations */
    @keyframes fromRight {
      from { opacity: 0; transform: translateX(60px); }
      to   { opacity: 1; transform: translateX(0);    }
    }
    @keyframes fromLeft {
      from { opacity: 0; transform: translateX(-60px); }
      to   { opacity: 1; transform: translateX(0);     }
    }
    .from-right { animation: fromRight 0.28s ease; }
    .from-left  { animation: fromLeft  0.28s ease; }

    /* arrow buttons overlaid on image */
    .slide-arrow {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      background: rgba(0, 0, 0, 0.45);
      border: none;
      color: #fff;
      font-size: 2rem;
      line-height: 1;
      padding: 14px 18px;
      cursor: pointer;
      transition: background 0.15s;
      z-index: 2;
    }
    .slide-arrow:hover:not(:disabled) { background: rgba(0, 100, 180, 0.65); }
    .slide-arrow:disabled { opacity: 0.2; cursor: default; }
    #arrow-prev { left: 0;  border-radius: 0 8px 8px 0; }
    #arrow-next { right: 0; border-radius: 8px 0 0 8px; }

    /* counter + play button below image */
    .slide-footer {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
      margin-top: 18px;
      width: 100%;
    }
    #slide-counter {
      color: #4a8fb8;
      font-size: 0.85rem;
      letter-spacing: 1px;
    }
    .slide-play-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; }
    #play-btn {
      background: #1278c4;
      border: none;
      color: #fff;
      padding: 13px 48px;
      border-radius: 10px;
      font-size: 1.1rem;
      cursor: pointer;
      letter-spacing: 1px;
      transition: background 0.15s;
    }
    #play-btn:hover { background: #1a94e8; }
    #btn-restart {
      background: #1a4a6e;
      border: none;
      color: #a0d8f0;
      padding: 13px 28px;
      border-radius: 10px;
      font-size: 1.1rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    #btn-restart:hover { background: #255f8a; }
    #btn-unwatch {
      background: #2a1a1a;
      border: 1px solid #6e2a2a;
      color: #e08080;
      padding: 13px 22px;
      border-radius: 10px;
      font-size: 0.95rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    #btn-unwatch:hover { background: #3d1f1f; }

    /* ── Video player ─────────────────────────────────── */
    #player {
      display: none;
      padding: 24px;
      max-width: 1100px;
      margin: 0 auto;
    }
    #player-title {
      font-size: 1.15rem;
      color: #ffffff;
      font-weight: bold;
      margin-bottom: 14px;
      letter-spacing: 1px;
    }
    #video-el {
      width: 100%;
      background: #000;
      border-radius: 10px;
      display: block;
    }
  </style>
</head>
<body>

<header>
  <a class="home-link" href="{{ back_url }}">&#8592; Back</a>
  <button id="back-btn" onclick="goBack()">&#8592; Back</button>
  <h1>{{ page_title }}</h1>
</header>

<div id="loading">Loading library&hellip;</div>
<div id="library"   style="display:none;"></div>

<div id="slideshow">
  <div id="slideshow-title"></div>
  <div class="slide-stage">
    <button class="slide-arrow" id="arrow-prev" onclick="prevSlide()">&#8592;</button>
    <img id="slide-img" src="" alt="">
    <button class="slide-arrow" id="arrow-next" onclick="nextSlide()">&#8594;</button>
  </div>
  <div class="slide-footer">
    <div id="slide-counter"></div>
    <div class="slide-play-row"></div>
  </div>
</div>

<div id="player">
  <div id="player-title"></div>
  <video id="video-el" controls></video>
</div>

<script>
  let videos = [];
  let currentVideo = null;
  let slideIndex = 0;
  let view = 'library';   // 'library' | 'slideshow' | 'player'
  let state = {};          // { [source]: { progress?, watched? } }

  // ── helpers ──────────────────────────────────────────
  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function show(id, displayType = 'block') {
    document.getElementById(id).style.display = displayType;
  }
  function hide(id) {
    document.getElementById(id).style.display = 'none';
  }

  // ── server state helpers ──────────────────────────────
  function postState(source, updates) {
    fetch('/api/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, ...updates }),
    });
  }

  function saveProgress(v, t) {
    (state[v.source] = state[v.source] || {}).progress = t;
    postState(v.source, { progress: t });
  }
  function loadProgress(v)  { return state[v.source]?.progress || 0; }
  function clearProgress(v) {
    if (state[v.source]) delete state[v.source].progress;
    postState(v.source, { progress: null });
  }
  function markWatched(v) {
    (state[v.source] = state[v.source] || {}).watched = true;
    postState(v.source, { watched: true });
  }
  function clearWatched(v) {
    if (state[v.source]) delete state[v.source].watched;
    postState(v.source, { watched: false });
  }
  function isWatched(v) { return !!(state[v.source]?.watched); }

  // ── load ─────────────────────────────────────────────
  const API_URL = '{{ api_url }}';

  async function loadVideos() {
    const [videosRes, stateRes] = await Promise.all([fetch(API_URL), fetch('/api/state')]);
    videos = await videosRes.json();
    state  = await stateRes.json();
    renderLibrary();
    hide('loading');
    show('library', 'grid');
  }

  // ── library ──────────────────────────────────────────
  function fmtDuration(secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return h > 0
      ? `${h}h ${m}m`
      : `${m}m ${String(s).padStart(2,'0')}s`;
  }

  function renderLibrary() {
    document.getElementById('library').innerHTML = videos.map((v, i) => {
      const watched   = isWatched(v);
      const saved     = loadProgress(v);
      const pct       = v.duration && saved ? Math.min(100, (saved / v.duration) * 100) : 0;
      const remaining = v.duration && saved ? v.duration - saved : null;

      const progressBar = !watched && saved > 5
        ? `<div class="card-progress"><div class="card-progress-fill" style="width:${pct}%"></div></div>`
        : '<div class="card-progress"></div>';

      const badge  = watched ? `<div class="card-watched-badge">&#10003;</div>` : '';
      const footer = watched
        ? `<div class="card-watched-label">&#10003; Watched</div>`
        : remaining && remaining > 10
          ? `<div class="card-remaining">${fmtDuration(remaining)} remaining</div>`
          : '';

      const thumbSrc = v.grids && v.grids.length > 0 ? v.grids[0] : null;
      const thumb = thumbSrc
        ? `<img src="/media?path=${encodeURIComponent(thumbSrc)}" alt="${escHtml(v.title)}" loading="lazy">`
        : `<div class="card-no-thumb">${escHtml(v.title)}</div>`;
      return `
        <div class="card" onclick="openSlideshow(${i})">
          ${badge}
          ${thumb}
          ${progressBar}
          <div class="card-body">
            <div class="card-title">${escHtml(v.title)}</div>
            <div class="card-duration">${v.duration ? fmtDuration(v.duration) : ''}</div>
          </div>
          ${footer}
        </div>
      `;
    }).join('');
  }

  // ── slideshow ─────────────────────────────────────────
  function renderPlayButtons() {
    const saved   = loadProgress(currentVideo);
    const watched = isWatched(currentVideo);
    const row     = document.querySelector('.slide-play-row');
    if (watched || saved > 5) {
      const label = watched
        ? '&#9654;&nbsp; Play again'
        : `&#9654;&nbsp; Resume &mdash; ${fmtDuration(saved)} in`;
      const unwatchedBtn = watched
        ? `<button id="btn-unwatch" onclick="unmarkWatched()">&#10007; Mark as unwatched</button>`
        : '';
      row.innerHTML = `
        <button id="play-btn" onclick="startPlayer(false)">${label}</button>
        <button id="btn-restart" onclick="startPlayer(true)">&#8635; Start over</button>
        ${unwatchedBtn}
      `;
    } else {
      row.innerHTML = `<button id="play-btn" onclick="startPlayer(false)">&#9654;&nbsp; Play</button>`;
    }
  }

  function unmarkWatched() {
    clearWatched(currentVideo);
    renderPlayButtons();
  }

  function openSlideshow(i) {
    currentVideo = videos[i];
    if (!currentVideo.grids || currentVideo.grids.length === 0) {
      startPlayer(false);
      return;
    }
    slideIndex = 0;
    document.getElementById('slideshow-title').textContent = currentVideo.title;
    setSlide(null);
    renderPlayButtons();
    hide('library');
    show('slideshow', 'flex');
    show('back-btn');
    view = 'slideshow';
  }

  function setSlide(animClass) {
    const img = document.getElementById('slide-img');
    const grids = currentVideo.grids;

    img.classList.remove('from-right', 'from-left');
    void img.offsetWidth;   // force reflow to restart animation
    if (animClass) img.classList.add(animClass);

    img.src = `/media?path=${encodeURIComponent(grids[slideIndex])}`;
    img.alt = `Grid ${slideIndex + 1}`;

    document.getElementById('slide-counter').textContent =
      `${slideIndex + 1} / ${grids.length}`;
    document.getElementById('arrow-prev').disabled = slideIndex === 0;
    document.getElementById('arrow-next').disabled = slideIndex === grids.length - 1;
  }

  function prevSlide() {
    if (slideIndex > 0) { slideIndex--; setSlide('from-left'); }
  }
  function nextSlide() {
    if (slideIndex < currentVideo.grids.length - 1) { slideIndex++; setSlide('from-right'); }
  }

  // keyboard arrow support
  document.addEventListener('keydown', e => {
    if (view === 'slideshow') {
      if (e.key === 'ArrowLeft')  prevSlide();
      if (e.key === 'ArrowRight') nextSlide();
    }
  });

  // ── player ───────────────────────────────────────────
  function startPlayer(fromBeginning = false) {
    const v = currentVideo;
    document.getElementById('player-title').textContent = v.title;
    const vid = document.getElementById('video-el');
    vid.src = `/media?path=${encodeURIComponent(v.source)}`;
    vid.load();

    vid.addEventListener('loadedmetadata', () => {
      if (!fromBeginning) {
        const saved = loadProgress(v);
        if (saved > 5) vid.currentTime = saved;
      }
      vid.play();
    }, { once: true });

    let lastSave = 0;
    vid.addEventListener('timeupdate', () => {
      if (vid.currentTime - lastSave >= 5) {
        saveProgress(v, vid.currentTime);
        lastSave = vid.currentTime;
      }
    });

    vid.addEventListener('ended', () => {
      clearProgress(v);
      markWatched(v);
      renderLibrary();
    });

    hide('slideshow');
    show('player');
    view = 'player';
  }

  // ── navigation ───────────────────────────────────────
  function goBack() {
    if (view === 'player') {
      const vid = document.getElementById('video-el');
      vid.pause();
      vid.src = '';
      hide('player');
      renderPlayButtons();
      show('slideshow', 'flex');
      view = 'slideshow';
    } else if (view === 'slideshow') {
      hide('slideshow');
      renderLibrary();
      show('library', 'grid');
      hide('back-btn');
      view = 'library';
    }
  }

  loadVideos();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    """Library home page with shows and movies."""
    return render_template_string(LIBRARY_HOME_HTML)


@app.route("/shows")
def shows_list():
    """List all TV shows."""
    shows = LIBRARY_CATALOG.get("shows", {})
    series_data = [
        {"name": series_data["name"], "key": series_key, "url": f"/shows/{series_key}"}
        for series_key, series_data in shows.items()
    ]
    return render_template_string(SERIES_PICKER_HTML, 
                                  title="TV SHOWS",
                                  series_list=series_data,
                                  back_url="/")


@app.route("/shows/<series_key>")
def show_seasons(series_key):
    """List all seasons for a TV show."""
    shows = LIBRARY_CATALOG.get("shows", {})
    if series_key not in shows:
        abort(404)
    
    series = shows[series_key]
    seasons_data = [
        {"name": season_data["name"], "key": season_key, "url": f"/shows/{series_key}/{season_key}"}
        for season_key, season_data in series.get("seasons", {}).items()
    ]
    
    return render_template_string(SERIES_PICKER_HTML,
                                  title=f"{series['name'].upper()} — SEASONS",
                                  series_list=seasons_data,
                                  back_url="/shows")


@app.route("/shows/<series_key>/<season_key>")
def show_season_videos(series_key, season_key):
    """Display videos for a specific season."""
    route_info = get_route_info_by_path(f"shows/{series_key}/{season_key}")
    if not route_info:
        abort(404)
    
    shows = LIBRARY_CATALOG.get("shows", {})
    series = shows[series_key]
    season = series["seasons"][season_key]
    
    page_title = f"{series['name']} — {season['name']}"
    api_url = f"/api/shows/{series_key}/{season_key}/videos"
    back_url = f"/shows/{series_key}"
    
    return render_template_string(HTML,
                                  page_title=page_title.upper(),
                                  api_url=api_url,
                                  back_url=back_url)


@app.route("/movies")
def movies_list():
    """List all movie series."""
    movies = LIBRARY_CATALOG.get("movies", {})
    series_data = [
        {"name": series_data["name"], "key": series_key, "url": f"/movies/{series_key}"}
        for series_key, series_data in movies.items()
    ]
    return render_template_string(SERIES_PICKER_HTML,
                                  title="MOVIES",
                                  series_list=series_data,
                                  back_url="/")


@app.route("/movies/<series_key>")
def movies_in_series(series_key):
    """List all movies in a series."""
    movies = LIBRARY_CATALOG.get("movies", {})
    if series_key not in movies:
        abort(404)
    
    series = movies[series_key]
    movies_data = [
        {"name": movie_data["name"], "key": movie_key, "url": f"/movies/{series_key}/{movie_key}"}
        for movie_key, movie_data in series.get("movies", {}).items()
    ]
    
    return render_template_string(SERIES_PICKER_HTML,
                                  title=f"{series['name'].upper()} — MOVIES",
                                  series_list=movies_data,
                                  back_url="/movies")


@app.route("/movies/<series_key>/<movie_key>")
def movie_videos(series_key, movie_key):
    """Display videos for a specific movie."""
    route_info = get_route_info_by_path(f"movies/{series_key}/{movie_key}")
    if not route_info:
        abort(404)
    
    movies = LIBRARY_CATALOG.get("movies", {})
    series = movies[series_key]
    movie = series["movies"][movie_key]
    
    page_title = f"{series['name']} — {movie['name']}"
    api_url = f"/api/movies/{series_key}/{movie_key}/videos"
    back_url = f"/movies/{series_key}"
    
    return render_template_string(HTML,
                                  page_title=page_title.upper(),
                                  api_url=api_url,
                                  back_url=back_url)


@app.route("/images/<filename>")
def image_file(filename):
    p = (Path(__file__).parent / "images" / filename).resolve()
    allowed = (Path(__file__).parent / "images").resolve()
    if not str(p).startswith(str(allowed)):
        abort(403)
    if not p.is_file():
        abort(404)
    return send_file(p)


@app.route("/background.png")
def background():
    p = Path(__file__).parent / "background.png"
    return send_file(p)


@app.route("/transition-timer")
def transition_timer():
    """Serve the animated between-episode timer."""
    if not TRANSITION_TIMER_FILE.is_file():
        abort(404)
    return send_file(TRANSITION_TIMER_FILE)


@app.route("/api/shows/<series_key>/<season_key>/videos")
def api_show_season_videos(series_key, season_key):
    """Get videos for a TV show season."""
    route_info = get_route_info_by_path(f"shows/{series_key}/{season_key}")
    if not route_info:
        return jsonify([]), 404
    
    shows = LIBRARY_CATALOG.get("shows", {})
    if series_key not in shows or season_key not in shows[series_key]["seasons"]:
        return jsonify([]), 404
    
    catalog = shows[series_key]["seasons"][season_key]["catalog"]
    return jsonify(catalog)


@app.route("/api/movies/<series_key>/<movie_key>/videos")
def api_movie_videos(series_key, movie_key):
    """Get videos for a movie."""
    route_info = get_route_info_by_path(f"movies/{series_key}/{movie_key}")
    if not route_info:
        return jsonify([]), 404
    
    movies = LIBRARY_CATALOG.get("movies", {})
    if series_key not in movies or movie_key not in movies[series_key]["movies"]:
        return jsonify([]), 404
    
    catalog = movies[series_key]["movies"][movie_key]["catalog"]
    return jsonify(catalog)


@app.route("/api/state")
def api_get_state():
    return jsonify(load_state())


@app.route("/api/state", methods=["POST"])
def api_post_state():
    body = request.get_json(force=True)
    source = body.get("source")
    if not source:
        abort(400)
    state = load_state()
    entry = state.setdefault(source, {})
    if "progress" in body:
        if body["progress"] is None:
            entry.pop("progress", None)
        else:
            entry["progress"] = body["progress"]
    if "watched" in body:
        if body["watched"]:
            entry["watched"] = True
        else:
            entry.pop("watched", None)
    if not entry:
        state.pop(source, None)
    save_state(state)
    return jsonify({"ok": True})


@app.route("/media")
def media():
    raw = request.args.get("path", "")
    p = Path(raw).resolve()
    allowed_dirs = get_all_allowed_dirs()
    if not any(str(p).startswith(str(d)) for d in allowed_dirs):
        abort(403)
    if not p.is_file():
        abort(404)
    return send_file(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local media video player.")
    parser.add_argument(
        "--shows",
        default=None,
        type=Path,
        help="Directory containing TV shows (Shows/<SeriesName>/<SeasonName>/episodes)",
    )
    parser.add_argument(
        "--movies",
        default=None,
        type=Path,
        help="Directory containing movies (Movies/<SeriesName>/<MovieName>/files)",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save current --shows and --movies paths to config for future runs",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Force directory rescan (ignore cached catalog)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cached catalog from disk",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    global SHOWS_DIR, MOVIES_DIR, LIBRARY_CATALOG
    
    # Handle --clear-cache
    if args.clear_cache:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
            print("Cache cleared.")
        else:
            print("No cache file found.")
        return
    
    # Load config from disk if no arguments provided
    if not args.shows and not args.movies:
        config = load_config()
        if config:
            print(f"Loading configuration from {CONFIG_FILE}")
            args.shows = Path(config.get("shows")) if config.get("shows") else None
            args.movies = Path(config.get("movies")) if config.get("movies") else None
    
    # Validate and set directories
    if args.shows:
        SHOWS_DIR = args.shows.resolve()
        if not SHOWS_DIR.is_dir():
            print(f"Warning: Shows directory not found: {SHOWS_DIR}")
            SHOWS_DIR = None
    
    if args.movies:
        MOVIES_DIR = args.movies.resolve()
        if not MOVIES_DIR.is_dir():
            print(f"Warning: Movies directory not found: {MOVIES_DIR}")
            MOVIES_DIR = None
    
    # Load catalogs: try cache first, then rescan if needed
    should_rescan = args.rescan or not CONFIG_FILE.exists()
    
    if not should_rescan and CONFIG_FILE.exists():
        config = load_config()
        if config.get("catalog"):
            print("Loading cached catalog...")
            LIBRARY_CATALOG.update(deserialize_catalog(config.get("catalog", {})))
        else:
            should_rescan = True
    
    # If cache doesn't exist or --rescan was used, scan directories
    if should_rescan:
        print("Scanning directories...")
        if SHOWS_DIR:
            LIBRARY_CATALOG["shows"] = scan_shows_directory(SHOWS_DIR)
        else:
            LIBRARY_CATALOG["shows"] = {}
        
        if MOVIES_DIR:
            LIBRARY_CATALOG["movies"] = scan_movies_directory(MOVIES_DIR)
        else:
            LIBRARY_CATALOG["movies"] = {}
    
    # Build route map
    build_route_map()
    
    # Save config if requested or if paths are provided
    if args.save_config or (args.shows or args.movies):
        config = {
            "shows": str(SHOWS_DIR) if SHOWS_DIR else None,
            "movies": str(MOVIES_DIR) if MOVIES_DIR else None,
            "catalog": serialize_catalog(LIBRARY_CATALOG),
            "cached_at": datetime.now().isoformat(),
        }
        save_config(config)
        print(f"Configuration saved to {CONFIG_FILE}")

    # Print loaded content
    if SHOWS_DIR:
        print(f"Shows Directory:        {SHOWS_DIR}")
        for series_key, series_data in LIBRARY_CATALOG["shows"].items():
            print(f"  └─ {series_data['name']}")
            for season_key, season_data in series_data.get("seasons", {}).items():
                count = len(season_data.get("catalog", []))
                print(f"     └─ {season_data['name']} ({count} videos)")
    
    if MOVIES_DIR:
        print(f"Movies Directory:       {MOVIES_DIR}")
        for series_key, series_data in LIBRARY_CATALOG["movies"].items():
            print(f"  └─ {series_data['name']}")
            for movie_key, movie_data in series_data.get("movies", {}).items():
                count = len(movie_data.get("catalog", []))
                print(f"     └─ {movie_data['name']} ({count} videos)")
    
    if not SHOWS_DIR and not MOVIES_DIR:
        print("Warning: No Shows or Movies directories configured.")
        print("Use --shows and/or --movies to specify directories.")
        if CONFIG_FILE.exists():
            print(f"Or clear cache with: python3 server.py --clear-cache")
    
    print(f"Open http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
