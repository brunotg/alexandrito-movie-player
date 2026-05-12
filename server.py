#!/usr/bin/env python3
"""Local web video player server."""

import argparse
import json
from pathlib import Path

from flask import Flask, abort, jsonify, render_template_string, request, send_file

app = Flask(__name__)
VIDEO_DIR: Path = None


def load_all_metadata() -> list[dict]:
    results = []
    for metadata_path in sorted(VIDEO_DIR.glob("*_stills/metadata.json")):
        data = json.loads(metadata_path.read_text())
        grids = sorted(metadata_path.parent.glob("grid_*.jpg"))
        data["grids"] = [str(g) for g in grids]
        results.append(data)
    return results


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Octonauts</title>
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
    .slide-play-row { display: flex; gap: 12px; }
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

    /* ── Video player ─────────────────────────────────── */
    #player {
      display: none;
      padding: 24px;
      max-width: 1100px;
      margin: 0 auto;
    }
    #player-title {
      font-size: 1.15rem;
      color: #5bc8f5;
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
  <button id="back-btn" onclick="goBack()">&#8592; Back</button>
  <h1>OCTONAUTS for ALEXANDER</h1>
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
  async function loadVideos() {
    const res = await fetch('/api/videos');
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

      return `
        <div class="card" onclick="openSlideshow(${i})">
          ${badge}
          <img src="/media?path=${encodeURIComponent(v.stills[0])}"
               alt="${escHtml(v.title)}" loading="lazy">
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
      row.innerHTML = `
        <button id="play-btn" onclick="startPlayer(false)">${label}</button>
        <button id="btn-restart" onclick="startPlayer(true)">&#8635; Start over</button>
      `;
    } else {
      row.innerHTML = `<button id="play-btn" onclick="startPlayer(false)">&#9654;&nbsp; Play</button>`;
    }
  }

  function openSlideshow(i) {
    currentVideo = videos[i];
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
    return render_template_string(HTML)


@app.route("/background.png")
def background():
    p = Path(__file__).parent / "background.png"
    return send_file(p)


@app.route("/api/videos")
def api_videos():
    return jsonify(load_all_metadata())


@app.route("/media")
def media():
    raw = request.args.get("path", "")
    p = Path(raw).resolve()
    allowed = VIDEO_DIR.resolve()
    if not str(p).startswith(str(allowed)):
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
        help="Directory containing the MP4 files and _stills folders",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    global VIDEO_DIR
    VIDEO_DIR = args.directory.resolve()
    if not VIDEO_DIR.is_dir():
        print(f"Error: directory not found: {VIDEO_DIR}")
        raise SystemExit(1)

    print(f"Serving {VIDEO_DIR}")
    print(f"Open http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
