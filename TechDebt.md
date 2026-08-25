# Tech Debt

Open and resolved technical debt items, newest last.

| # | Item | Status |
|---|------|--------|
| 1 | Catalog rescanned on every API request | Resolved |
| 2 | Media served by the Werkzeug development server | Resolved |

---

# 1. Catalog rescanned on every API request

**Status: Resolved.** The catalog is now built once in `main()` into `LIBRARY_CATALOG`,
cached to `library-config.json`, and served from memory. `test_api.py` covers this with
`test_api_calls_use_cached_data_not_filesystem`, which fails if `load_all_metadata` runs
during a request.

The description below is kept for context. Note it refers to globals (`VIDEO_DIR`,
`ABOVE_BEYOND_S03_DIR`) and a route (`/api/videos`) that the multi-directory refactor
has since removed.

## Context

The app currently resolves its media directories once at startup in `main()` and stores them as module globals in `server.py`:

- `VIDEO_DIR`
- `ABOVE_BEYOND_S03_DIR`
- `ABOVE_BEYOND_S04_DIR`

This gives the app a central source for the configured root folders, but the actual file metadata is still reloaded repeatedly at request time.

## Current issue

The runtime flow reads the folder contents when the API is called, not when the app starts:

- `/api/videos` in `server.py` calls `load_all_metadata(VIDEO_DIR)`
- `load_all_metadata()` scans the directory tree and reads `*_stills/metadata.json` files
- This happens on every browser refresh or library reload

This means the app is doing repeated filesystem scans even though the media and metadata are effectively static for the lifetime of the process.

## Desired behavior

We want the app to read the state of the files once at startup and keep that catalog in memory for the rest of the app lifetime.

That means:

- resolve the media directories once at startup
- load the episode catalog once
- keep it in an app-level cache or config object
- serve that cached catalog from the API endpoints instead of rescanning the disk every time

## Why this matters

This improves:

- startup predictability
- response latency for `/api/videos`
- reduced I/O churn on local filesystems
- simpler app-level state management

## Recommended refactor

The ideal location for a one-time load is `main()` in `server.py`, immediately after the video directories are validated.

Suggested flow:

1. resolve directories
2. validate they exist
3. build the catalog once with `load_all_metadata(...)`
4. attach the catalog to the Flask app (for example `app.config["VIDEO_CATALOG"]` or `app.video_catalog`)
5. have `/api/videos` return the cached catalog

This keeps the data source in one place and naturally centralizes the app state.

## Related files

- `server.py`
- `process_all.py`
- `extract_stills.py`
- `generate_grids.py`

## Notes

This is not a correctness bug today, but it is a runtime efficiency and architectural tech debt issue. The app should treat the media catalog as startup state, not as a per-request computation.

---

# 2. Media served by the Werkzeug development server

**Status: Resolved.** `main()` now serves through `waitress.serve(...)` with 16 threads,
and `--dev` still starts Flask's development server for working on the app. Verified:
three range requests to the running server now reuse a single TCP connection
(`num_connects: 1`), where the development server opened one per request.

## Context

`main()` in `server.py` serves the app with `app.run(host="0.0.0.0", port=...)`, which
starts Werkzeug's development server. That server exists for the edit-reload-debug loop,
and prints a warning on every startup saying it should not be used to actually serve.

Flask itself is not the issue: `server.app` is already a valid WSGI application
(`(environ, start_response) -> Iterable[bytes]`). Only the component that calls it would
change.

## Current issue

The development server replies `Connection: close` and does not keep connections alive:

```
$ curl -sD - '.../media?path=<episode>' | grep -i connection
Connection: close
```

A video player issues many HTTP range requests — on every seek and periodically while
buffering. Each one therefore pays a fresh TCP handshake and restarts congestion control.
On a fast link this is invisible. Over a weak Wi-Fi link it is not: slow-start on a lossy
connection is exactly where throughput is lost, and this contributes to intermittent
stalls when playing to another device on the LAN.

The development server also lacks request timeouts and sensible handling of slow or
vanishing clients — for example a laptop whose lid closes mid-episode.

## Desired behavior

Serve the existing Flask app through a production WSGI server, keeping `app.run()`
available behind a flag for development so the auto-reloader is not lost.

## Recommended change

`waitress` is the best fit here: pure Python, cross-platform, threaded, no configuration.

1. `pip3 install waitress`
2. In `main()`, replace `app.run(...)` with `waitress.serve(app, host="0.0.0.0", port=args.port)`
3. Add a `--dev` flag that still calls `app.run(..., debug=True)` for development
4. Update the README run instructions

`gunicorn` would also work but offers more process-model tuning than a local single-user
media server needs. `uvicorn` does not apply — it serves ASGI, and Flask is WSGI.

## Why this matters

Streaming large files to other devices is the app's main job, and it is the one workload
the development server is least suited to.

## Caveat

This is a resilience improvement, not a bandwidth fix. Measurements taken while debugging
intermittent playback showed the media drive sustaining ~250 MB/s against a ~4 Mbit/s video
bitrate, and the server handling three concurrent range requests at ~243 MB/s each. The
binding constraint was the Wi-Fi link (MCS index 3 at -72 dBm, with traffic crossing the
air twice because the server is also on Wi-Fi). Moving the serving machine to Ethernet
remains the larger win.

## Related files

- `server.py` (`main()`, the `/media` route)
- `README.md`
