#!/usr/bin/env python3
"""Concurrently extract stills and generate grid composites for all MP4s in a directory."""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from extract_stills import extract_frame, generate_title_card, get_duration, parse_episode
from generate_grids import PER_GRID, make_grid

NUM_STILLS = 20


def process_video(video_path: Path, skip_existing: bool) -> str:
    output_dir = video_path.parent / f"{video_path.stem}_stills"
    json_path = output_dir / "metadata.json"

    if skip_existing and json_path.exists():
        return f"SKIP  {video_path.name}"

    show, season, title = parse_episode(video_path.name, video_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = get_duration(video_path)
    timestamps = [duration * (i + 1) / (NUM_STILLS + 1) for i in range(NUM_STILLS)]

    still_paths = []
    for i, ts in enumerate(timestamps):
        still_path = output_dir / f"still_{i + 1:02d}.jpg"
        extract_frame(video_path, still_path, ts)
        if i == 0:
            generate_title_card(still_path, title)
        still_paths.append(still_path)

    num_grids = (len(still_paths) + PER_GRID - 1) // PER_GRID
    grid_paths = []
    for i in range(num_grids):
        chunk = still_paths[i * PER_GRID : (i + 1) * PER_GRID]
        grid_path = output_dir / f"grid_{i + 1:02d}.jpg"
        make_grid(chunk, grid_path)
        grid_paths.append(str(grid_path))

    for p in still_paths:
        p.unlink()

    json_path.write_text(json.dumps({
        "title": title,
        "show": show,
        "season": season,
        "source": str(video_path.resolve()),
        "duration": duration,
        "grids": grid_paths,
    }, indent=2))

    return f"DONE  {video_path.name}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process all MP4s in a directory: extract stills + generate grids."
    )
    parser.add_argument("directory", type=Path, help="Directory containing MP4 files")
    parser.add_argument(
        "-w", "--workers", type=int, default=4,
        help="Concurrent workers (default: 4)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip videos that already have a metadata.json",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: not a directory: {args.directory}", file=sys.stderr)
        sys.exit(1)

    videos = sorted(p for ext in ("*.mp4", "*.mkv") for p in args.directory.glob(ext))
    if not videos:
        print("No MP4 files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(videos)} videos — {args.workers} concurrent workers\n")

    completed = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_video, v, args.skip_existing): v for v in videos}
        for future in as_completed(futures):
            try:
                print(f"  [{completed + errors + 1}/{len(videos)}] {future.result()}")
                completed += 1
            except Exception as exc:
                video = futures[future]
                print(f"  [{completed + errors + 1}/{len(videos)}] ERROR {video.name}: {exc}")
                errors += 1

    print(f"\n{completed} succeeded, {errors} failed.")


if __name__ == "__main__":
    main()
