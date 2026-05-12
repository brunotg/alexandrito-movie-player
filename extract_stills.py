#!/usr/bin/env python3
"""Extract 5 representative stills from an MP4 video file using ffmpeg."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def get_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())
    except FileNotFoundError:
        print("Error: ffprobe not found. Install ffmpeg with: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error getting video duration:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)


def parse_title(filename: str) -> str:
    """Extract title from filenames like 'Octonauts - <title> | ...' or 'Octonauts & <title>'"""
    stem = Path(filename).stem
    match = re.search(r'Octonauts\s+[-&]\s+([^|]+)', stem)
    return match.group(1).strip() if match else stem


def extract_frame(video_path: Path, output_path: Path, timestamp: float) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", "scale=1280:-1",
        "-q:v", "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Install it with: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frame at {timestamp:.1f}s:\n{e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def generate_title_card(image_path: Path, title: str) -> None:
    """Overlay a styled title card (OCTONAUTS + episode title) onto the image."""
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    # Darken the background so text pops
    dark = Image.new("RGBA", (w, h), (0, 20, 40, 170))
    img = Image.alpha_composite(img, dark)
    draw = ImageDraw.Draw(img)

    font_show = _load_font("/System/Library/Fonts/Supplemental/Impact.ttf", 96)
    font_title = _load_font("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 56)

    cx = w // 2
    cy = h // 2

    # --- "OCTONAUTS" in a white rounded box ---
    show_name = "OCTONAUTS"
    sb = draw.textbbox((0, 0), show_name, font=font_show)
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    pad = 22
    box_x0 = cx - sw // 2 - pad
    box_y0 = cy - sh - 60 - pad
    box_x1 = cx + sw // 2 + pad
    box_y1 = cy - 60 + pad
    draw.rounded_rectangle(
        [box_x0, box_y0, box_x1, box_y1],
        radius=24,
        fill=(255, 255, 255, 230),
        outline=(20, 80, 80),
        width=5,
    )
    draw.text((cx - sw // 2, cy - sh - 60), show_name, font=font_show, fill=(20, 90, 90))

    # --- Episode title below the box ---
    tb = draw.textbbox((0, 0), title, font=font_title)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tx = cx - tw // 2
    ty = cy + 10
    # subtle shadow
    draw.text((tx + 3, ty + 3), title, font=font_title, fill=(0, 0, 0, 160))
    draw.text((tx, ty), title, font=font_title, fill=(200, 240, 255))

    img.convert("RGB").save(image_path, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract 5 representative stills from an MP4 video.")
    parser.add_argument("video", type=Path, help="Path to the MP4 file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output directory (default: <video-name>_stills/)",
    )
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Error: file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    title = parse_title(args.video.name)
    output_dir = args.output or args.video.parent / f"{args.video.stem}_stills"
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = get_duration(args.video)
    num_stills = 20
    # Evenly spaced at 1/6, 2/6, 3/6, 4/6, 5/6 of the duration
    timestamps = [duration * (i + 1) / (num_stills + 1) for i in range(num_stills)]

    still_paths = []
    for i, ts in enumerate(timestamps):
        output_path = output_dir / f"still_{i + 1:02d}.jpg"
        extract_frame(args.video, output_path, ts)
        if i == 0:
            generate_title_card(output_path, title)
        still_paths.append(str(output_path.resolve()))
        print(f"  [{i + 1}/{num_stills}] {output_path.name} at {ts:.1f}s")

    metadata = {
        "title": title,
        "source": str(args.video.resolve()),
        "duration": duration,
        "stills": still_paths,
    }
    json_path = output_dir / "metadata.json"
    json_path.write_text(json.dumps(metadata, indent=2))
    print(f"\nTitle: {title!r}")
    print(f"Stills and metadata.json written to: {output_dir}/")


if __name__ == "__main__":
    main()
