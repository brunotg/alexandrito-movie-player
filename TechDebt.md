# Tech Debt

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
