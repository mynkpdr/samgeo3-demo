from __future__ import annotations

import argparse
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


BLUE_RGBA = (56, 189, 248, 200)
WEBP_QUALITY = 50
WEBP_METHOD = 4
MAX_PREVIEW_SIZE = (1920, 1080)


@dataclass(frozen=True)
class GeoRef:
    pixel_size_x: float
    pixel_size_y: float
    upper_left_center_x: float
    upper_left_center_y: float


@dataclass(frozen=True)
class LakeTask:
    lake: str
    date: str
    original_tif: Path
    segmented_tif: Path
    tfw_path: Path
    output_original: Path
    output_segmented: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert lake TIFFs into WEBP/PNG previews and build lake_data.json."
    )
    parser.add_argument("--lakes-dir", default="lakes", help="Directory containing original lake TIFFs.")
    parser.add_argument(
        "--segmented-dir",
        default="lakes-segmented",
        help="Directory containing segmented TIFF masks.",
    )
    parser.add_argument("--previews-dir", default="previews", help="Output preview root directory.")
    parser.add_argument("--output-json", default="lake_data.json", help="Output metadata JSON file.")
    parser.add_argument(
        "--mask-threshold",
        type=int,
        default=0,
        help="Mask threshold used when converting segmented TIFFs to PNG.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(2, (os.cpu_count() or 4))),
        help="Number of worker threads.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List work without writing previews or JSON.",
    )
    return parser.parse_args()


def read_world_file(tfw_path: Path) -> GeoRef | None:
    if not tfw_path.exists():
        return None

    try:
        values = [float(line.strip()) for line in tfw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        print(f"[WARN] Could not read world file {tfw_path}: {exc}")
        return None

    if len(values) < 6:
        return None

    return GeoRef(
        pixel_size_x=values[0],
        pixel_size_y=values[3],
        upper_left_center_x=values[4],
        upper_left_center_y=values[5],
    )


def read_geotiff_georef(tif_path: Path) -> GeoRef | None:
    try:
        with Image.open(tif_path) as image:
            tags = image.tag_v2
            scale = tags.get(33550)
            tiepoint = tags.get(33922)
            if not scale or not tiepoint or len(scale) < 2 or len(tiepoint) < 6:
                return None

            pixel_size_x = float(scale[0])
            pixel_size_y = -abs(float(scale[1]))
            raster_x = float(tiepoint[0])
            raster_y = float(tiepoint[1])
            model_x = float(tiepoint[3])
            model_y = float(tiepoint[4])

            upper_left_center_x = model_x + ((0.5 - raster_x) * pixel_size_x)
            upper_left_center_y = model_y + ((0.5 - raster_y) * pixel_size_y)

            return GeoRef(
                pixel_size_x=pixel_size_x,
                pixel_size_y=pixel_size_y,
                upper_left_center_x=upper_left_center_x,
                upper_left_center_y=upper_left_center_y,
            )
    except Exception as exc:
        print(f"[WARN] Could not read GeoTIFF metadata {tif_path}: {exc}")
        return None


def load_georef(original_tif: Path, tfw_path: Path) -> GeoRef | None:
    return read_world_file(tfw_path) or read_geotiff_georef(original_tif)


def calculate_bounds(georef: GeoRef, width: int, height: int) -> list[list[float]]:
    lon_min = georef.upper_left_center_x - (georef.pixel_size_x / 2.0)
    lat_max = georef.upper_left_center_y - (georef.pixel_size_y / 2.0)
    lon_max = lon_min + (width * georef.pixel_size_x)
    lat_min = lat_max + (height * georef.pixel_size_y)
    return [[lat_min, lon_min], [lat_max, lon_max]]


def meters_per_degree(latitude_deg: float) -> tuple[float, float]:
    lat_rad = math.radians(latitude_deg)
    meters_lat = (
        111132.92
        - 559.82 * math.cos(2 * lat_rad)
        + 1.175 * math.cos(4 * lat_rad)
        - 0.0023 * math.cos(6 * lat_rad)
    )
    meters_lon = (
        111412.84 * math.cos(lat_rad)
        - 93.5 * math.cos(3 * lat_rad)
        + 0.118 * math.cos(5 * lat_rad)
    )
    return meters_lat, meters_lon


def calculate_area_km2(segmented_tif: Path, georef: GeoRef) -> float:
    with Image.open(segmented_tif) as image:
        mask = np.array(image) > 0

    pixel_width_deg = abs(georef.pixel_size_x)
    pixel_height_deg = abs(georef.pixel_size_y)
    water_pixels_per_row = np.count_nonzero(mask, axis=1)
    row_indices = np.nonzero(water_pixels_per_row)[0]
    if row_indices.size == 0:
        return 0.0

    latitudes = georef.upper_left_center_y - (row_indices * pixel_height_deg)
    lat_radians = np.radians(latitudes)
    meters_lat = (
        111132.92
        - 559.82 * np.cos(2 * lat_radians)
        + 1.175 * np.cos(4 * lat_radians)
        - 0.0023 * np.cos(6 * lat_radians)
    )
    meters_lon = (
        111412.84 * np.cos(lat_radians)
        - 93.5 * np.cos(3 * lat_radians)
        + 0.118 * np.cos(5 * lat_radians)
    )
    pixel_area_m2 = (pixel_width_deg * meters_lon) * (pixel_height_deg * meters_lat)
    area_m2 = float(np.sum(water_pixels_per_row[row_indices] * pixel_area_m2))

    return round(area_m2 / 1_000_000.0, 4)


def convert_original_to_webp(src_path: Path, dst_path: Path) -> tuple[tuple[int, int], tuple[int, int]]:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as image:
        source_size = image.size
        rgb = image.convert("RGB")
        rgb.thumbnail(MAX_PREVIEW_SIZE, Image.Resampling.LANCZOS)
        rgb.save(dst_path, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
        return source_size, rgb.size


def convert_segmented_to_png(src_path: Path, dst_path: Path, threshold: int, target_size: tuple[int, int]) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as image:
        mask = image.convert("L")
        if mask.size != target_size:
          mask = mask.resize(target_size, Image.Resampling.NEAREST)

        binary = mask.point(lambda value: 1 if value > threshold else 0).convert("P")
        palette = [0, 0, 0, BLUE_RGBA[0], BLUE_RGBA[1], BLUE_RGBA[2]]
        palette += [0, 0, 0] * (256 - 2)
        binary.putpalette(palette[:768])
        binary.save(dst_path, format="PNG", optimize=True, transparency=0)


def discover_tasks(
    lakes_dir: Path,
    segmented_dir: Path,
    previews_dir: Path,
) -> list[LakeTask]:
    if not segmented_dir.exists():
        raise FileNotFoundError(f"Segmented directory not found: {segmented_dir}")

    tasks: list[LakeTask] = []
    for lake_dir in sorted(path for path in segmented_dir.iterdir() if path.is_dir()):
        for segmented_tif in sorted(lake_dir.glob("*.tif")):
            lake = lake_dir.name
            date = segmented_tif.stem.removeprefix(f"{lake}-")
            original_tif = lakes_dir / lake / segmented_tif.name
            tfw_path = original_tif.with_suffix(".tfw")

            if not original_tif.exists():
                print(f"[WARN] Skipping {segmented_tif}: missing original TIFF {original_tif}")
                continue

            tasks.append(
                LakeTask(
                    lake=lake,
                    date=date,
                    original_tif=original_tif,
                    segmented_tif=segmented_tif,
                    tfw_path=tfw_path,
                    output_original=previews_dir / "compressed" / f"{lake}-{date}.webp",
                    output_segmented=previews_dir / "segmented" / f"{lake}-{date}.png",
                )
            )

    return tasks


def process_one(task: LakeTask, threshold: int, dry_run: bool) -> tuple[str, dict] | None:
    georef = load_georef(task.original_tif, task.tfw_path)
    if georef is None:
        print(f"[WARN] Skipping {task.original_tif}: no georeferencing found")
        return None

    if dry_run:
        print(f"[DRY-RUN] {task.original_tif} -> {task.output_original}")
        print(f"[DRY-RUN] {task.segmented_tif} -> {task.output_segmented}")
        return None

    source_size, preview_size = convert_original_to_webp(task.original_tif, task.output_original)
    convert_segmented_to_png(
        task.segmented_tif,
        task.output_segmented,
        threshold=threshold,
        target_size=preview_size,
    )

    item = {
        "date": task.date,
        "area_km2": calculate_area_km2(task.segmented_tif, georef),
        "original_img": task.output_original.as_posix(),
        "segmented_img": task.output_segmented.as_posix(),
        "bounds": calculate_bounds(georef, source_size[0], source_size[1]),
    }
    return task.lake, item


def format_task_label(task: LakeTask) -> str:
    return f"{task.lake} {task.date}"


def group_results(results: Iterable[tuple[str, dict]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for lake, item in results:
        grouped.setdefault(lake, []).append(item)

    for lake in grouped:
        grouped[lake].sort(key=lambda entry: entry["date"])

    return dict(sorted(grouped.items()))


def main() -> int:
    args = parse_args()
    lakes_dir = Path(args.lakes_dir)
    segmented_dir = Path(args.segmented_dir)
    previews_dir = Path(args.previews_dir)
    output_json = Path(args.output_json)

    tasks = discover_tasks(lakes_dir, segmented_dir, previews_dir)
    if not tasks:
        print("[WARN] No TIFF pairs found.")
        return 0

    print(f"[INFO] Found {len(tasks)} TIFF pairs across {len({task.lake for task in tasks})} lakes.")

    processed: list[tuple[str, dict]] = []
    total = len(tasks)
    workers = max(1, args.workers)
    print(f"[INFO] Using {workers} worker(s).", flush=True)

    if workers == 1:
        for index, task in enumerate(tasks, start=1):
            print(f"[{index}/{total}] Processing {format_task_label(task)}...", flush=True)
            result = process_one(task, args.mask_threshold, args.dry_run)
            if result is not None:
                processed.append(result)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(process_one, task, args.mask_threshold, args.dry_run): (index, task)
                for index, task in enumerate(tasks, start=1)
            }
            for future in as_completed(futures):
                index, task = futures[future]
                result = future.result()
                print(f"[{index}/{total}] Finished {format_task_label(task)}", flush=True)
                if result is not None:
                    processed.append(result)

    if args.dry_run:
        print("[DONE] Dry run complete.")
        return 0

    lake_data = group_results(processed)
    output_json.write_text(json.dumps(lake_data, indent=2), encoding="utf-8")
    print(f"[DONE] Wrote {output_json} with {sum(len(items) for items in lake_data.values())} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
