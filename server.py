#!/usr/bin/env python3
"""Local web video player server."""

import argparse
import json
import re
from pathlib import Path

from flask import Flask, abort, jsonify, render_template_string, request, send_file

app = Flask(__name__)
VIDEO_DIR: Path = None
ABOVE_BEYOND_S03_DIR: Path = None
ABOVE_BEYOND_S04_DIR: Path = None


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

  // ── load ─────────────────────────────────────────────
  const API_URL = '{{ api_url }}';

  async function loadVideos() {
    const res = await fetch(API_URL);
    videos = await res.json();
    renderLibrary();
    hide('loading');
    show('library', 'grid');
  }

  // ── localStorage helpers ─────────────────────────────
  function progressKey(v)     { return 'progress:' + v.source; }
  function watchedKey(v)      { return 'watched:'  + v.source; }
  function saveProgress(v, t) { localStorage.setItem(progressKey(v), t); }
  function loadProgress(v)    { return parseFloat(localStorage.getItem(progressKey(v))) || 0; }
  function clearProgress(v)   { localStorage.removeItem(progressKey(v)); }
  function markWatched(v)     { localStorage.setItem(watchedKey(v), '1'); }
  function clearWatched(v)    { localStorage.removeItem(watchedKey(v)); }
  function isWatched(v)       { return !!localStorage.getItem(watchedKey(v)); }

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
    return render_template_string(LANDING_HTML)


@app.route("/octonauts")
def octonauts():
    return render_template_string(HTML, page_title="OCTONAUTS for ALEXANDER", api_url="/api/videos", back_url="/")


@app.route("/above-and-beyond")
def above_and_beyond():
    return render_template_string(ABOVE_BEYOND_PICKER_HTML)


@app.route("/above-and-beyond/s03")
def above_and_beyond_s03():
    return render_template_string(HTML, page_title="ABOVE AND BEYOND — SEASON 3", api_url="/api/above-and-beyond/s03/videos", back_url="/above-and-beyond")


@app.route("/above-and-beyond/s04")
def above_and_beyond_s04():
    return render_template_string(HTML, page_title="ABOVE AND BEYOND — SEASON 4", api_url="/api/above-and-beyond/s04/videos", back_url="/above-and-beyond")


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


@app.route("/api/videos")
def api_videos():
    return jsonify(load_all_metadata(VIDEO_DIR))


@app.route("/api/above-and-beyond/s03/videos")
def api_above_and_beyond_s03_videos():
    if ABOVE_BEYOND_S03_DIR is None:
        return jsonify([])
    return jsonify(load_all_metadata(ABOVE_BEYOND_S03_DIR))


@app.route("/api/above-and-beyond/s04/videos")
def api_above_and_beyond_s04_videos():
    if ABOVE_BEYOND_S04_DIR is None:
        return jsonify([])
    return jsonify(load_all_metadata(ABOVE_BEYOND_S04_DIR))


@app.route("/media")
def media():
    raw = request.args.get("path", "")
    p = Path(raw).resolve()
    allowed_dirs = [VIDEO_DIR.resolve()]
    if ABOVE_BEYOND_S03_DIR is not None:
        allowed_dirs.append(ABOVE_BEYOND_S03_DIR.resolve())
    if ABOVE_BEYOND_S04_DIR is not None:
        allowed_dirs.append(ABOVE_BEYOND_S04_DIR.resolve())
    if not any(str(p).startswith(str(d)) for d in allowed_dirs):
        abort(403)
    if not p.is_file():
        abort(404)
    return send_file(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Octonauts video player.")
    parser.add_argument(
        "directory", nargs="?",
        default="/Users/bruno/Documents/Alexander stories/octonauts/s3",
        type=Path,
        help="Directory containing the Octonauts MP4 files and _stills folders",
    )
    parser.add_argument(
        "--above-and-beyond-s03",
        default="/Users/bruno/Documents/Alexander stories/octonauts-above-and-beyond/S03",
        type=Path,
        help="Directory for Above & Beyond Season 3",
    )
    parser.add_argument(
        "--above-and-beyond-s04",
        default="/Users/bruno/Documents/Alexander stories/octonauts-above-and-beyond/S04",
        type=Path,
        help="Directory for Above & Beyond Season 4",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    global VIDEO_DIR, ABOVE_BEYOND_S03_DIR, ABOVE_BEYOND_S04_DIR
    VIDEO_DIR = args.directory.resolve()
    if args.above_and_beyond_s03 and Path(args.above_and_beyond_s03).is_dir():
        ABOVE_BEYOND_S03_DIR = Path(args.above_and_beyond_s03).resolve()
    if args.above_and_beyond_s04 and Path(args.above_and_beyond_s04).is_dir():
        ABOVE_BEYOND_S04_DIR = Path(args.above_and_beyond_s04).resolve()
    if not VIDEO_DIR.is_dir():
        print(f"Error: directory not found: {VIDEO_DIR}")
        raise SystemExit(1)

    print(f"Octonauts:              {VIDEO_DIR}")
    if ABOVE_BEYOND_S03_DIR:
        print(f"Above & Beyond S03:     {ABOVE_BEYOND_S03_DIR}")
    if ABOVE_BEYOND_S04_DIR:
        print(f"Above & Beyond S04:     {ABOVE_BEYOND_S04_DIR}")
    print(f"Open http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
