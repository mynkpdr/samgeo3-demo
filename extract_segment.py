#!/usr/bin/env python3
"""
extract_segment.py — Batch water segmentation using SamGeo3.

Iterates over a folder of GeoTIFF images and applies SAM3-based text-prompted
segmentation to produce binary water masks, saving results to an output folder.

Requirements:
    pip install "segment-geospatial[samgeo3]" huggingface_hub
    export HF_TOKEN=<your_huggingface_token>

Usage:
    python3 extract_segment.py --input-dir lakes --output-dir lakes-segmented
    python3 extract_segment.py --input-dir lakes/bellandur-lake --output-dir lakes-segmented/bellandur-lake --prompt "Water"
    python3 extract_segment.py -c lakes -o lakes-segmented --confidence 0.5
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SAM3 initialisation (deferred until we know args are valid)
# ---------------------------------------------------------------------------

def init_sam3(confidence: float):
    """Authenticate with Hugging Face and return a configured SamGeo3 instance."""
    from huggingface_hub import login  # type: ignore

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        logger.error(
            "HF_TOKEN environment variable is not set. "
            "Export it before running: export HF_TOKEN=<your_token>"
        )
        sys.exit(1)

    logger.info("Authenticating with Hugging Face Hub…")
    login(token=hf_token)

    from samgeo import SamGeo3  # type: ignore

    logger.info("Initialising SamGeo3 (backend=meta, loading from HF)…")
    sam3 = SamGeo3(
        backend="meta",
        device=None,
        checkpoint_path=None,
        load_from_HF=True,
        confidence_threshold=confidence,
    )
    return sam3


# ---------------------------------------------------------------------------
# Core segmentation logic
# ---------------------------------------------------------------------------

TIFF_EXTENSIONS = {".tif", ".tiff"}


def segment_folder(
    sam3,
    input_folder: Path,
    output_folder: Path,
    prompt: str,
) -> tuple[int, int]:
    """
    Segment all GeoTIFF files in *input_folder* and write masks to *output_folder*.

    Returns:
        (processed_count, skipped_count) — number of files processed and skipped.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    tif_files = sorted(
        p for p in input_folder.iterdir()
        if p.suffix.lower() in TIFF_EXTENSIONS
    )

    if not tif_files:
        logger.warning("No TIFF files found in %s. Skipping.", input_folder)
        return 0, 0

    processed, skipped = 0, 0
    total = len(tif_files)

    for idx, src in enumerate(tif_files, start=1):
        # Normalise extension to .tif
        dst = output_folder / (src.stem + ".tif")
        logger.info("[%d/%d] Segmenting %s…", idx, total, src.name)

        try:
            sam3.set_image(str(src))
            sam3.generate_masks(prompt=prompt)

            if sam3.masks is not None and len(sam3.masks) > 0:
                sam3.save_masks(output=str(dst), unique=False)
                logger.info("  ✓ Saved mask → %s", dst)
                processed += 1
            else:
                logger.warning("  No objects found in %s — skipping save.", src.name)
                skipped += 1

        except Exception as exc:  # noqa: BLE001
            logger.error("  Failed to segment %s: %s", src.name, exc)
            skipped += 1

    return processed, skipped


def batch_segment(
    sam3,
    input_root: Path,
    output_root: Path,
    prompt: str,
) -> None:
    """
    Walk sub-folders of *input_root* and segment each one.

    Expected layout (matches get_data.py output)::

        input_root/
            <lake-name>/
                <lake-name>-YYYY-MM-DD.tif
                …

    Produces::

        output_root/
            <lake-name>/
                <lake-name>-YYYY-MM-DD.tif (mask)
                …
    """
    lake_dirs = sorted(p for p in input_root.iterdir() if p.is_dir())

    if not lake_dirs:
        # Flat layout — treat input_root itself as a single folder
        logger.info("No sub-folders found; treating %s as a single lake folder.", input_root)
        p, s = segment_folder(sam3, input_root, output_root, prompt)
        logger.info("Done — %d processed, %d skipped.", p, s)
        return

    total_p, total_s = 0, 0
    for lake_dir in lake_dirs:
        out_dir = output_root / lake_dir.name
        logger.info("=== Lake: %s ===", lake_dir.name)
        p, s = segment_folder(sam3, lake_dir, out_dir, prompt)
        total_p += p
        total_s += s

    logger.info(
        "All lakes processed — %d mask(s) saved, %d skipped.",
        total_p,
        total_s,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch water-body segmentation using SamGeo3.\n\n"
            "Iterates over GeoTIFF images in the input directory and produces "
            "binary water masks in the output directory, preserving the folder "
            "structure produced by get_data.py."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input-dir",
        type=str,
        default="lakes",
        help="Root folder containing input GeoTIFF images (default: lakes).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="lakes-segmented",
        help="Root folder where segmented masks will be saved (default: lakes-segmented).",
    )
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default="Water",
        help="Text prompt for SAM3 segmentation (default: 'Water').",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.4,
        help="Confidence threshold for SAM3 mask generation (default: 0.4).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    input_root = Path(args.input_dir)
    output_root = Path(args.output_dir)

    if not input_root.exists():
        logger.error("Input directory does not exist: %s", input_root)
        sys.exit(1)

    logger.info("Input  : %s", input_root.resolve())
    logger.info("Output : %s", output_root.resolve())
    logger.info("Prompt : '%s'  |  Confidence threshold: %.2f", args.prompt, args.confidence)

    sam3 = init_sam3(confidence=args.confidence)
    batch_segment(sam3, input_root, output_root, prompt=args.prompt)


if __name__ == "__main__":
    main()