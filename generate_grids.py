#!/usr/bin/env python3
"""Combine stills into 2x2 grid composite images."""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


COLS, ROWS = 2, 2
PER_GRID = COLS * ROWS


def make_grid(paths: list[Path], output_path: Path, cell_w: int = 640) -> None:
    cells = []
    for p in paths:
        img = Image.open(p)
        ratio = img.height / img.width
        cell_h = round(cell_w * ratio)
        cells.append(img.resize((cell_w, cell_h), Image.LANCZOS))

    cell_h = cells[0].height
    grid = Image.new("RGB", (cell_w * COLS, cell_h * ROWS))

    for idx, cell in enumerate(cells):
        col = idx % COLS
        row = idx // COLS
        grid.paste(cell, (col * cell_w, row * cell_h))

    grid.save(output_path, quality=88)


def resolve_stills(data: dict, metadata_dir: Path) -> list[Path]:
    """Still paths from metadata, falling back to whatever is on disk beside it."""
    recorded = [Path(p) for p in data.get("stills", [])]
    existing = [p for p in recorded if p.exists()]
    if existing:
        return existing
    return sorted(metadata_dir.glob("still_*.jpg"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 2x2 grid composites from stills.")
    parser.add_argument("metadata", type=Path, help="Path to metadata.json from extract_stills.py")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output directory (default: same directory as metadata.json)",
    )
    args = parser.parse_args()

    if not args.metadata.exists():
        print(f"Error: file not found: {args.metadata}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.metadata.read_text())
    stills = resolve_stills(data, args.metadata.parent)
    if not stills:
        print(
            f"Error: no stills found for {args.metadata}. "
            "Run extract_stills.py first (process_all.py deletes stills once gridded).",
            file=sys.stderr,
        )
        sys.exit(1)
    output_dir = args.output or args.metadata.parent

    num_grids = (len(stills) + PER_GRID - 1) // PER_GRID
    grid_paths = []
    for i in range(num_grids):
        chunk = stills[i * PER_GRID : (i + 1) * PER_GRID]
        output_path = output_dir / f"grid_{i + 1:02d}.jpg"
        make_grid(chunk, output_path)
        grid_paths.append(str(output_path.resolve()))
        print(f"  [{i + 1}/{num_grids}] {output_path.name} ({len(chunk)} stills)")

    # The player reads `grids` from metadata.json, so record them or the
    # slideshow has nothing to show.
    data["grids"] = grid_paths
    args.metadata.write_text(json.dumps(data, indent=2))

    print(f"\n{num_grids} grid images written to: {output_dir}/")
    print(f"metadata.json updated with {len(grid_paths)} grid paths")


if __name__ == "__main__":
    main()
