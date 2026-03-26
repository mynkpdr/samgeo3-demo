#!/usr/bin/env python3
"""
get_data.py — Resumable historical satellite imagery downloader.

Downloads historical Google Earth imagery for one or more bounding boxes using
the GEHistoricalImagery CLI tool. Dates are selected with a preference for one
per year, then filled up to the --target-images limit. Only dates for which all
four corners of the bounding box are covered are downloaded.

Usage:
    # Single location
    python3 get_data.py -n bellandur-lake --ll "12.924,77.637" --ur "12.949,77.682"

    # Multiple locations from a JSON config file
    python3 get_data.py -c lakes.json -z 17 --min-date 2006/01/01 --max-date 2025/12/31 -t 100 -w 4
"""
import os
import subprocess
import re
import json
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_dates_at_location(lat: str, lon: str, zoom: str, bin_path: str) -> set:
    """Uses the non-interactive 'info' command to get dates for a specific point."""
    logger.debug(f"Checking dates at location: {lat}, {lon}...")
    cmd = [bin_path, "info", "--location", f"{lat},{lon}", "--zoom", zoom]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return set(re.findall(r"date = (\d{4}/\d{2}/\d{2})", result.stdout))
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch dates for {lat},{lon}: {e.stderr or e}")
        return set()
    except FileNotFoundError:
        logger.error(f"Binary not found at {bin_path}. Please check the path.")
        raise


def select_dates(
    available_dates: set, min_date: str, max_date: str, target: int
) -> list:
    """Select dates within the timeframe, prioritising one per year, up to the target count."""
    valid_dates = [d for d in available_dates if min_date <= d <= max_date]
    dates = sorted(list(set(valid_dates)), reverse=True)

    selected = []
    seen_years = set()
    remaining = []

    for d in dates:
        year = d[:4]
        if year not in seen_years:
            selected.append(d)
            seen_years.add(year)
        else:
            remaining.append(d)

    for d in remaining:
        if len(selected) >= target:
            break
        selected.append(d)

    return selected[:target]


def process_location(name: str, coords: dict, args: argparse.Namespace):
    """Checks corner availability and downloads images for a single location."""
    logger.info(f"[{name}] Analyzing coverage via boundary points...")
    os.makedirs(name, exist_ok=True)

    lat0, lon0 = coords["ll"].split(",")
    lat1, lon1 = coords["ur"].split(",")

    # 4 corners to ensure full coverage
    corners = [(lat0, lon0), (lat1, lon1), (lat0, lon1), (lat1, lon0)]
    common_dates = None

    for lat, lon in corners:
        dates = get_dates_at_location(lat, lon, args.zoom, args.bin_path)
        if common_dates is None:
            common_dates = dates
        else:
            common_dates = common_dates.intersection(dates)

    if not common_dates:
        logger.warning(
            f"[{name}] No dates found with complete coverage for all corners."
        )
        return

    dates_to_download = select_dates(
        common_dates, args.min_date, args.max_date, args.target_images
    )
    logger.info(f"[{name}] Found {len(dates_to_download)} valid dates for download.")

    for d in dates_to_download:
        safe_date = d.replace("/", "-")
        out_filename = os.path.join(name, f"{name}-{safe_date}.tif")

        if os.path.exists(out_filename):
            logger.info(f"[{name}] Skipping {d} - file already exists.")
            continue

        logger.info(f"[{name}] Downloading {d}...")
        cmd_dl = [
            args.bin_path,
            "download",
            "--lower-left",
            coords["ll"],
            "--upper-right",
            coords["ur"],
            "--zoom",
            args.zoom,
            "--date",
            d,
            "--output",
            out_filename,
        ]

        try:
            subprocess.run(cmd_dl, check=True, capture_output=True)
            logger.info(f"[{name}] Successfully saved {out_filename}")
        except subprocess.CalledProcessError as e:
            logger.error(f"[{name}] Failed to download {d}: {e.stderr or e}")


def main():
    parser = argparse.ArgumentParser(
        description="Resumable Historical Imagery Downloader"
    )

    # Input options (File vs Single via CLI)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-c", "--config", type=str, help="Path to JSON file containing location data."
    )
    group.add_argument(
        "-n", "--name", type=str, help="Name of a single location to process."
    )

    # Single location coordinates
    parser.add_argument(
        "--ll",
        type=str,
        help="Lower-left coordinates (lat,lon). Required if using --name.",
    )
    parser.add_argument(
        "--ur",
        type=str,
        help="Upper-right coordinates (lat,lon). Required if using --name.",
    )

    # Configuration parameters
    parser.add_argument(
        "-z", "--zoom", type=str, default="17", help="Zoom level (default: 17)"
    )
    parser.add_argument(
        "--min-date",
        type=str,
        default="2006/01/01",
        help="Minimum date YYYY/MM/DD (default: 2006/01/01)",
    )
    parser.add_argument(
        "--max-date",
        type=str,
        default="2025/12/31",
        help="Maximum date YYYY/MM/DD (default: 2025/12/31)",
    )
    parser.add_argument(
        "-t",
        "--target-images",
        type=int,
        default=100,
        help="Target number of images per location (default: 100)",
    )
    parser.add_argument(
        "-b",
        "--bin-path",
        type=str,
        default="GEHistoricalImagery",
        help="Path to GEHistoricalImagery binary",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent workers (default: 4)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Determine locations to process
    locations = {}
    if args.config:
        try:
            with open(args.config, "r") as f:
                locations = json.load(f)
        except Exception as e:
            logger.critical(f"Failed to load config file: {e}")
            return
    else:
        if not args.ll or not args.ur:
            parser.error(
                "--ll and --ur are required when processing a single location via --name"
            )
        locations[args.name] = {"ll": args.ll, "ur": args.ur}

    logger.info(
        f"Starting downloader with {args.workers} workers. Processing {len(locations)} location(s)."
    )

    # Execution
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_location, name, coords, args): name
            for name, coords in locations.items()
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error(
                    f"Location '{name}' generated an unexpected exception: {exc}"
                )

    logger.info("All tasks completed.")


if __name__ == "__main__":
    main()
