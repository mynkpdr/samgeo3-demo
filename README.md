# Lake Monitor — End-to-end pipeline

Lightweight pipeline to download historical satellite imagery for defined bounding boxes, pair originals with segmented water masks, generate web-friendly previews, compute lake surface area, and produce a ready-to-serve JSON dataset for the web viewer.

This repository contains two main stages:
- Image acquisition: `get_data.py` — downloads historical imagery that fully covers a user-selected bounding box using the GEHistoricalImagery tool.
- Post-processing & preview generation: `process_tif.py` — converts TIFFs to previews, computes area, and writes `lake_data.json` used by the viewer `index.html`.

## Quickstart

1. Install Python dependencies:

```bash
python3 -m pip install --user --upgrade pip
python3 -m pip install pillow numpy
```

2. Prepare or obtain the GEHistoricalImagery command-line binary (see **GEHistoricalImagery** section).

3. Use the coordinate helper to pick bounding boxes:

```bash
# Serve the repository and open the map in a browser
python3 -m http.server 8000
# then open http://localhost:8000/get_coordinates.html
```

4. Create a JSON config with locations (example `areas.json`) and run the downloader:

```json
{
    "canyon-lake": {
        "ll": "29.84479383,-98.33190113",
        "ur": "29.92298862,-98.19288816"
    },
}
```

```bash
python3 get_data.py -c areas.json -z 17 --min-date 2006/01/01 --max-date 2025/12/31 -t 100 -b /path/to/GEHistoricalImagery -w 4
```

5. Place segmented masks into `lakes-segmented/<lake>/` matching the TIFF names produced by the downloader (see **Processing**).

6. Generate previews and `lake_data.json`:

```bash
python3 process_tif.py --lakes-dir lakes --segmented-dir lakes-segmented --previews-dir previews --output-json lake_data.json --workers 4
```

7. Serve the repository and open the viewer:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/index.html
```

## Files & layout

- `get_data.py` — downloader that queries the GEHistoricalImagery tool and writes TIFFs into a per-location folder (one TIFF per date). Usage: see examples below.
- `process_tif.py` — converts original TIFFs to compressed `webp` previews and segmented masks to transparent `png`, computes area in km², and writes `lake_data.json`.
- `get_coordinates.html` — small Leaflet tool to interactively pick a 16:9 bounding box and copy the `ll`/`ur` coordinates.
- `index.html` — the web viewer that consumes `lake_data.json` and `previews/`.

## Detailed usage

### 1) Picking coordinates

Open [get_coordinates.html](get_coordinates.html) in a browser (see Quickstart) and position the map. The helper enforces a 16:9 bounding box and displays the `Lower Left` and `Upper Right` coordinates which you can copy directly into your JSON config or CLI invocation.

Example minimal config (save as `areas.json`):

```json
{
    "my-lake": {"ll": "12.98000000,77.63000000", "ur": "12.99000000,77.64000000"}
}
```

### 2) GEHistoricalImagery (downloader) notes

- `get_data.py` calls an external tool (default binary name: `GEHistoricalImagery`) to query available dates and to download tiles. The script expects that binary to be installed and reachable either by name or by the full path you pass to `-b/--bin-path`.
- Source and further instructions for that tool: https://github.com/Mbucari/GEHistoricalImagery

If the binary is not on your PATH, pass the full path via `-b /path/to/GEHistoricalImagery`.

Example: single-location download

```bash
python3 get_data.py -n bellandur-lake --ll "12.92372883,77.63703272" --ur "12.94905157,77.68205091" -b /path/to/GEHistoricalImagery
```

Example: multi-location from file

```bash
python3 get_data.py -c areas.json -z 17 --min-date 2006/01/01 --max-date 2025/12/31 -t 100 -b /path/to/GEHistoricalImagery -w 4
```

Notes about downloader behavior
- The script checks the four corners of the requested bounding box and only selects dates that contain all four corner points (ensures full coverage).
- Dates are selected with a preference for one-per-year, then filled up to the `--target-images` limit if more are available.
- Output: a directory for each location (e.g., `bellandur-lake/`) containing TIFFs named `<location>-YYYY-MM-DD.tif`.

### 3) Preparing segmented masks

The pipeline expects segmented TIFF masks that correspond to each original TIFF. Masks should be placed under `lakes-segmented/<lake>/<lake>-YYYY-MM-DD.tif` and must have the same raster size as the original (or will be resized during preview generation).

If you do not yet have segmented masks, you will need to generate them with your segmentation workflow (not included here).

### 4) Processing TIFF pairs

`process_tif.py` discovers TIFF pairs by iterating `lakes-segmented/*/*.tif` and looking for matching originals in `lakes/<lake>/*.tif`.

Run a dry-run first to inspect the discovered pairs:

```bash
python3 process_tif.py --dry-run
```

Then run the real processing (creates `previews/` and `lake_data.json`):

```bash
python3 process_tif.py --lakes-dir lakes --segmented-dir lakes-segmented --previews-dir previews --output-json lake_data.json --workers 4
```

Outputs
- `previews/compressed/<lake>-<date>.webp` — compressed preview of the original image
- `previews/segmented/<lake>-<date>.png` — colored transparent mask for the segmented output
- `lake_data.json` — JSON mapping lakes to a list of entries `{date, area_km2, original_img, segmented_img, bounds}` used by `index.html`.

### 5) Viewer

Open [index.html](index.html) from the repository root in a browser (or serve with `python3 -m http.server`), then browse the available lakes and timelines.

## Common issues & troubleshooting

- Binary not found: If you see `Binary not found at ...`, verify the `GEHistoricalImagery` binary path and use `-b` to set it explicitly.
- No dates found / incomplete coverage: The downloader verifies that all four corners are covered. If your bounding box is too large (high zoom), there may be no fully covering images. Try reducing zoom or shrinking the box.
- Missing georeference: `process_tif.py` will use a corresponding `.tfw` world file if present, or read GeoTIFF tags. If georeferencing is missing, that TIFF pair will be skipped.
- Performance: adjust `--workers` in both scripts to tune parallelism.

## Dependencies

- Python 3.12+
- Python packages: `pillow`, `numpy`

Install with:

```bash
python3 -m pip install pillow numpy
```

## License

This repository is available under the MIT License. See the `LICENSE` file.
