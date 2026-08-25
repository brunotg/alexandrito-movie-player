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
- `--dev` — serve with Flask's development server (auto-reload + debugger) instead of waitress
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
- **Play queue**: build a watch list that spans shows and movies; plays through it automatically
- **Watch counter**: counts how many times each video has been played to the end
- **Season posters**: a poster image in a season folder illustrates that season in the picker

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
- `GET /api/state` — get/post viewing progress, watched flags and play counts
  - POST body: `{source, progress?, watched?, played?, resetPlays?}`; `played: true`
    increments the counter server-side and the updated entry is returned
- `GET /api/queue` — the play queue as full video objects (dead entries pruned)
- `PUT /api/queue` — replace the queue; body `{"sources": [path, ...]}`
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

**Runtime state files** (created automatically, not part of configuration):
- `state.json` — per-video progress, watched flag and play count, keyed by absolute path
  (e.g. `{"/path/ep.mkv": {"watched": true, "plays": 3}}`)
- `queue.json` — the play queue, stored as an ordered list of absolute source paths

**Serving:** requests are served by [waitress](https://pypi.org/project/waitress/), a
production WSGI server, rather than Flask's development server. Streaming video is this
app's main job and it is the workload the dev server handles worst: it closes the
connection after every response, so each of a video player's many range requests pays a
fresh TCP handshake and restarts congestion control — noticeable over a weak Wi-Fi link.
waitress keeps connections alive and serves each request on one of 16 threads.

Use `--dev` when working on the app itself, to get auto-reload and the interactive
debugger back.

**Dependencies:** `flask`, `waitress`

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

### Paged episode lists

Seasons show **6 episodes per page** with a pager below the grid.

- Prev / Next plus numbered buttons, and an "Episodes 7\u201312 of 47" caption
- The pager hides itself when a season has 6 or fewer episodes, so short seasons
  and movie pages look exactly as before
- The current page is kept in the URL (`?page=4`), so a reload or a shared link
  lands in the same place; an out-of-range or malformed value falls back safely
- Left/Right arrow keys page the library (the same keys drive the slideshow when
  a slideshow is open)
- Paging is view-only: the season catalog is still fetched once and held as a
  single list, so auto-advance walks straight across a page boundary and the page
  follows the episode being played

### Season posters

The season picker (`/shows/<series_key>`) shows each season's poster instead of a
bare text card. A season is illustrated automatically when its folder contains an
image whose filename includes `poster`:

```
Paw Patrol Season 1/
├── paw_patrol_season_1_poster.webp   ← used as the season's artwork
├── PAW.Patrol.S01E01....mp4
└── ...
```

- Recognised extensions: `.webp`, `.jpg`, `.jpeg`, `.png`
- Posters are letterboxed, not cropped, so mixed aspect ratios (2:3, 4:5) all sit on
  a uniform card without losing any artwork
- Seasons without a poster keep the plain text card, so this is purely additive
- **Posters are picked up during a scan**, so run `python3 server.py --rescan` once
  after adding them to an already-cached library

### Watch counter

Every time a video plays through to the end, its counter goes up by one.

- **Library:** the corner badge shows `3\u00d7` once a video has been finished more than
  once (a plain `\u2713` for a single viewing), and the card footer reads *Watched 3\u00d7*
- **Slideshow:** the same tally appears under the episode title
- **Reset:** *Mark as unwatched* clears the flag and the tally together
- Videos finished before this feature existed have no stored count; they are treated
  as having been watched once, so the next completion takes them to 2

### Queue playback

A queue can hold videos from any collection — episodes from different seasons and
movies can sit in the same list.

- **Add:** the `+` button on any library card, or **Add to queue** on the slideshow
- **Manage:** the **Queue** button in the header opens a drawer to reorder (▲▼),
  remove (✗), clear, or start playing the queue
- **Auto-advance:** when a video ends, an *Up next* card appears over the player with
  an 8-second countdown, plus **Play now** and **Cancel**.
- **The queue ends where you built it.** Once the last queued video finishes,
  playback stops rather than continuing into the rest of the season \u2014 a queue is a
  finite playlist, not a jumping-off point. Auto-advance to the next episode in the
  collection still happens when you started a video normally and the queue is empty.
- **Persistence:** the queue lives in `queue.json` and survives reloads, navigation
  between collections, and server restarts. Entries whose media no longer exists are
  dropped on the next startup.

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
| WSGI server | waitress, with `--dev` for Flask's dev server | The dev server sends `Connection: close`, so every range request from a video player reopens a TCP connection and restarts slow-start; waitress keeps them alive |
| File serving security | Path must start with `VIDEO_DIR.resolve()` | Prevents path traversal; app is local-only but still scoped |
| Back navigation | Per-level (player → slideshow → library) | Preserves context instead of dropping user to library |
| Episode paging | Client-side slice of the already-loaded catalog | The queue, auto-advance and watch state all read the season as one continuous list; paging the data instead of the view would fragment all three |
| Page size | 6, as a constant at the top of the player script | One place to change it; no config plumbing for a value that rarely moves |
| Season poster | Any image in the season folder with `poster` in its name | No naming convention to maintain per show, and no separate config to keep in sync with the files |
| Poster fit | Letterboxed (`object-fit: contain`) | Posters come in 2:3 and 4:5; cropping to a single ratio would cut characters out of the artwork |
| Watch count | Incremented server-side on `played: true` | A stale client copy of `state` cannot clobber the tally, and one request carries the whole "finished it" transition |
| Queue storage | Ordered list of source paths in `queue.json` | Paths are the existing identity for a video (same key as `state.json`); titles stay fresh because the server rehydrates from the catalog |
| Queue API | Single `PUT` that replaces the whole list | Covers append, remove, reorder and clear without four endpoints |
| Queue exhaustion | Stop, do not fall through to the season | The queue is an explicit finite playlist; drifting into unqueued episodes after it ends is surprising, especially unattended |
| Auto-advance | 8s countdown with Play now / Cancel | Instant cuts are jarring, and a countdown gives a chance to stop after each episode |
| Video event handlers | Assigned as `on*` properties, not `addEventListener` | The one `<video>` element is reused for every episode; listeners would otherwise stack up on each play |

---

## Tests

```bash
python3 -m pytest -q
```

- `test_server.py` — pure-function coverage: title parsing, state load/save, catalog
  scanning, route/index building
- `test_api.py` — endpoint coverage: season and movie catalogs, state, play counter,
  queue, posters, media path scoping

Tests redirect `state.json` and `queue.json` to a temp directory, so running them
never touches your real watch history.

---

## Dependencies

```bash
brew install ffmpeg
pip3 install pillow flask waitress --break-system-packages
```
