# Alexandrito Movie Player

A local web video player for managing and viewing video collections organized by TV shows and movies. Generates still previews and grid thumbnails for each video, then serves them through a browser-based UI with hierarchical navigation.

---

## Directory Structure

The player expects directories organized in a specific hierarchy:

```
Shows/
├── TV Show Name/
│   ├── Season 1/
│   │   ├── episode-1.mp4
│   │   ├── episode-1_stills/
│   │   │   ├── metadata.json
│   │   │   ├── still_01.jpg
│   │   │   └── ...
│   │   └── ...
│   └── Season 2/
│       └── ...
└── Another Show/
    └── ...

Movies/
├── Movie Series/
│   ├── Movie Name 1/
│   │   ├── movie.mp4
│   │   ├── movie_stills/
│   │   │   ├── metadata.json
│   │   │   ├── grid_01.jpg
│   │   │   └── ...
│   │   └── ...
│   └── Movie Name 2/
│       └── ...
└── Standalone Movies/
    └── ...
```

---

## Scripts

### `extract_stills.py`
Extracts 20 stills from a single MP4 file and generates a `metadata.json`.

```bash
python3 extract_stills.py "/path/to/video.mp4"
python3 extract_stills.py "/path/to/video.mp4" -o my_output_dir/
```

**What it produces** (in `<video-name>_stills/`):
- `still_01.jpg` … `still_20.jpg` — frames evenly spaced at 1/21, 2/21 … 20/21 of the duration
- `still_01.jpg` has a styled title card overlaid (OCTONAUTS + episode title)
- `metadata.json` — title, source path, list of still paths

**Title parsing:** expects filenames like `Octonauts - <title> | ...` or `Octonauts & <title>`. Everything between the separator (`-` or `&`) and the first `|` becomes the episode title.

**Title card style:** first still gets a darkened background, "OCTONAUTS" in Impact font inside a white rounded box, episode title in Arial Bold below. Modelled on the in-show title card format.

**Dependencies:** `ffmpeg` (via Homebrew), `Pillow`

---

### `generate_grids.py`
Combines stills into 2×2 composite grid images.

```bash
python3 generate_grids.py "/path/to/<video>_stills/metadata.json"
```

**What it produces** (in the same stills directory):
- `grid_01.jpg` … `grid_05.jpg` — each is a 1280×720 composite of 4 stills (640×360 per cell)

**Dependencies:** `Pillow`

---

### `process_all.py`
Concurrently runs `extract_stills` + `generate_grids` for every MP4 in a directory.

```bash
python3 process_all.py "/path/to/video/directory/"
python3 process_all.py "/path/to/video/directory/" --workers 6
python3 process_all.py "/path/to/video/directory/" --skip-existing
```

- Default: 4 concurrent workers (each processes one video at a time)
- `--skip-existing` skips any video that already has a `metadata.json`

**Dependencies:** same as the two scripts above

---

### `server.py`
Flask web server — serves the player UI and all media files with dynamic multi-directory support.

```bash
# Initial setup: save configuration
python3 server.py --shows /path/to/Shows --movies /path/to/Movies --save-config

# Subsequent runs: load from saved config
python3 server.py

# Force rescan of directories
python3 server.py --rescan

# Clear cached configuration
python3 server.py --clear-cache
```

**Arguments:**
- `--shows <dir>` — directory containing TV shows organized as `Shows/<SeriesName>/<SeasonName>/episodes`
- `--movies <dir>` — directory containing movies organized as `Movies/<SeriesName>/<MovieName>/files`
- `--save-config` — save current `--shows` and `--movies` paths to `library-config.json` for future runs
- `--rescan` — force directory rescanning (ignore cached catalog)
- `--clear-cache` — delete cached configuration file
- `--port <number>` — port to serve on (default: 8080)

**Features:**
- Loads and caches all catalogs at startup for fast navigation
- Dynamically generates routes based on directory structure
- URL-safe slugs for all series, seasons, and movie names
- Hierarchical navigation: Home → Shows/Movies → Series → Seasons/Movies → Videos
- **Configuration persistence**: saves paths and catalogs to `library-config.json` for no-argument startup
- **Fast startup**: uses cached catalog on subsequent runs (rescan with `--rescan`)

**Routes:**
- `GET /` — library home with TV shows and movies options
- `GET /shows` — list all TV shows
- `GET /shows/<series_key>` — list seasons for a show
- `GET /shows/<series_key>/<season_key>` — watch videos for a season
- `GET /movies` — list all movie series
- `GET /movies/<series_key>` — list movies in a series
- `GET /movies/<series_key>/<movie_key>` — watch a specific movie
- `GET /api/shows/<series_key>/<season_key>/videos` — JSON list of season videos
- `GET /api/movies/<series_key>/<movie_key>/videos` — JSON list of movie videos
- `GET /api/state` — get/post viewing progress for all videos
- `GET /media?path=<absolute_path>` — serves video files and stills (403 if outside allowed dirs)

**Example:**
```bash
# First time: set up and save configuration
python3 server.py \
  --shows ~/Videos/Shows \
  --movies ~/Videos/Movies \
  --save-config \
  --port 8080

# Future runs: just load from saved config
python3 server.py
# or with different port:
python3 server.py --port 9000

# Update paths and save new config
python3 server.py --shows /new/shows/path --save-config

# Force rescan of directories
python3 server.py --rescan

# Clear all configuration
python3 server.py --clear-cache
```

**Configuration file** (`library-config.json`):
Automatically created by `--save-config`. Contains paths and cached catalog data for fast startup.

**Dependencies:** `flask`

---

## UI flow

```
Library (grid of episode cards)
  └── click episode → Slideshow (5 grid images, ← → arrows / keyboard)
                          └── click ▶ Play → Video player
                                                └── ← Back → Slideshow
                      └── ← Back → Library
```

- **Library:** shows `still_01.jpg` (the title card) for each episode
- **Slideshow:** shows the 5 grid composites (not individual stills) with slide-in animation
- **Player:** native HTML5 `<video>` element, full controls

---

## Video directory structure

```
octonauts/s3/
  Octonauts - The Yeti Crab | ....mp4
  Octonauts - The Yeti Crab | ...._stills/
    still_01.jpg        ← title card (with OCTONAUTS overlay)
    still_02.jpg … still_20.jpg
    grid_01.jpg … grid_05.jpg   ← 2×2 composites used in slideshow
    metadata.json
  ...
```

---

## Key decisions

| Decision | Choice | Reason |
|---|---|---|
| Frame extraction | `ffmpeg` via subprocess | Most reliable, handles all codecs |
| Title overlay | Pillow (not ffmpeg drawtext) | ffmpeg homebrew build lacks freetype/drawtext |
| Stills per video | 20 | Enough coverage without excessive storage |
| Slideshow images | 5 grid composites (not 20 individual stills) | Faster to browse; each grid shows 4 frames at a glance |
| Grid cell size | 640×360 per cell → 1280×720 composite | Matches native 16:9, reasonable file size |
| Server port | 8080 | Port 5000 is occupied by AirPlay (AirTunes) on macOS |
| File serving security | Path must start with `VIDEO_DIR.resolve()` | Prevents path traversal; app is local-only but still scoped |
| Back navigation | Per-level (player → slideshow → library) | Preserves context instead of dropping user to library |

---

## Dependencies

```bash
brew install ffmpeg
pip3 install pillow flask --break-system-packages
```
