# Lake Monitor — Historical Water-Body Analysis Pipeline

A lightweight, end-to-end pipeline that:

1. **Downloads** historical Google Earth satellite imagery for any water body worldwide
2. **Segments** water surfaces from imagery using SAM3 (Segment Anything Model 3)
3. **Processes** image pairs into web-optimised previews and computes surface area in km²
4. **Visualises** historical lake trends in an interactive geospatial web viewer

---

## Pipeline Overview

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐     ┌───────────────┐
│   get_coordinates   │     │     get_data.py     │     │  extract_segment.py │     │ process_tif.py│
│       .html         │────▶│  Download imagery   │────▶│  Segment water     │────▶│ Build previews│
│  Pick bounding box  │     │(GEHistoricalImagery)│     │  masks (SAM3)       │     │ + lake_data   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘     └───────┬───────┘
                                                                                            │
                                                                                            ▼
                                                                                     ┌─────────────┐
                                                                                     │  index.html │
                                                                                     │  Web viewer │
                                                                                     └─────────────┘
```

**Directory layout produced by the pipeline:**

```
.
├── lakes/                       ← Raw GeoTIFFs (get_data.py output)
│   └── <lake>/
│       └── <lake>-YYYY-MM-DD.tif
├── lakes-segmented/             ← Binary water masks (extract_segment.py output)
│   └── <lake>/
│       └── <lake>-YYYY-MM-DD.tif
├── previews/                    ← Web previews (process_tif.py output)
│   ├── compressed/              ← <lake>-<date>.webp  (original, space-efficient)
│   └── segmented/               ← <lake>-<date>.png   (transparent blue mask)
├── lake_data.json               ← Metadata consumed by index.html
├── lakes.json                   ← Bounding box configuration (user-created)
├── get_data.py
├── extract_segment.py
├── process_tif.py
├── get_coordinates.html
└── index.html
```

---

## Requirements

### Python (via uv by Astral)
- Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Python **3.12+**
- `pillow`, `numpy` — for `process_tif.py`
- `segment-geospatial[samgeo3]`, `huggingface_hub` — for `extract_segment.py`

```bash
# Create and activate a local virtual environment (once per clone)
uv venv --python 3.12
source .venv/bin/activate

# Core dependencies (always required)
uv pip install pillow numpy

# Segmentation dependencies (required for extract_segment.py only)
uv pip install "segment-geospatial[samgeo3]" huggingface_hub
```

### External Tool
- **[GEHistoricalImagery](https://github.com/Mbucari/GEHistoricalImagery)** CLI binary — required by `get_data.py`

  Download the appropriate binary for your OS from the [releases page](https://github.com/Mbucari/GEHistoricalImagery/releases) and make it executable. Either add it to your `$PATH` or pass the full path via `--bin-path`.

### Tokens
- A **Hugging Face token** is required for `extract_segment.py` to download the SAM3 model weights:

  ```bash
  export HF_TOKEN=hf_your_token_here
  ```
- Note: You need permission to access the `sam3` model on Hugging Face. If you encounter access issues, please request access from the model owner.
---

## Quickstart

### Step 1 — Pick bounding boxes

Serve the repository locally and open the coordinate picker:

```bash
uv run python -m http.server 8000
# Open http://localhost:8000/get_coordinates.html
```

Pan and zoom the map to your area of interest. The info box shows the **Lower Left** and **Upper Right** coordinates for the current 16:9 viewport — copy these values.

### Step 2 — Create a location config file

Save your coordinates in a JSON file (e.g. `lakes.json`):

```json
{
    "bellandur-lake": {
        "ll": "12.92372883,77.63703272",
        "ur": "12.94905157,77.68205091"
    },
    "canyon-lake": {
        "ll": "29.84479383,-98.33190113",
        "ur": "29.92298862,-98.19288816"
    }
}
```

Each key is the **location name** (used as directory and file prefix). `ll` = lower-left `lat,lon`, `ur` = upper-right `lat,lon`.

### Step 3 — Download imagery

```bash
uv run get_data.py -c lakes.json -z 17 \
    --min-date 2006/01/01 --max-date 2025/12/31 \
    -t 100 -w 4 -b /path/to/GEHistoricalImagery
```

Output: `lakes/<location-name>/<location-name>-YYYY-MM-DD.tif` per date.

### Step 4 — Segment water surfaces

```bash
export HF_TOKEN=hf_your_token_here
uv run extract_segment.py --input-dir lakes --output-dir lakes-segmented
```

Output: binary water mask TIFFs in `lakes-segmented/` mirroring the `lakes/` structure.

### Step 5 — Generate previews and metadata

```bash
# Dry-run first to verify discovered pairs
uv run process_tif.py --dry-run

# Full run
uv run process_tif.py \
    --lakes-dir lakes \
    --segmented-dir lakes-segmented \
    --previews-dir previews \
    --output-json lake_data.json \
    --workers 4
```

Output: `previews/`, `lake_data.json`.

### Step 6 — Open the viewer

```bash
uv run python -m http.server 8000
# Open http://localhost:8000/index.html
```

---

## Script Reference

### `get_data.py` — Historical imagery downloader

Downloads historical Google Earth imagery for one or more bounding boxes.

**Key behaviour:**
- Checks **all four corners** of each bounding box to ensure fully-covered imagery only
- Selects dates **preferring one per year**, then fills up to `--target-images`
- Skips dates for which the output file already exists (resumable)

```
usage: get_data.py [-h] (-c CONFIG | -n NAME) [--ll LL] [--ur UR]
                   [-z ZOOM] [--min-date MIN_DATE] [--max-date MAX_DATE]
                   [-t TARGET_IMAGES] [-b BIN_PATH] [-w WORKERS] [-v]

options:
  -c, --config CONFIG       Path to JSON file containing location data
  -n, --name NAME           Name of a single location to process
  --ll LL                   Lower-left coordinates (lat,lon) for --name
  --ur UR                   Upper-right coordinates (lat,lon) for --name
  -z, --zoom ZOOM           Zoom level (default: 17)
  --min-date MIN_DATE       Earliest date YYYY/MM/DD (default: 2006/01/01)
  --max-date MAX_DATE       Latest date YYYY/MM/DD (default: 2025/12/31)
  -t, --target-images N     Target images per location (default: 100)
  -b, --bin-path PATH       Path to GEHistoricalImagery binary
  -w, --workers N           Parallel location workers (default: 4)
  -v, --verbose             Enable DEBUG logging
```

**Examples:**

```bash
# Single location
uv run get_data.py \
    -n bellandur-lake \
    --ll "12.92372883,77.63703272" \
    --ur "12.94905157,77.68205091" \
    -b ./GEHistoricalImagery

# Multiple locations from file, custom date range
uv run get_data.py \
    -c lakes.json \
    -z 17 \
    --min-date 2010/01/01 \
    --max-date 2024/12/31 \
    -t 50 \
    -w 4 \
    -b /usr/local/bin/GEHistoricalImagery
```

---

### `extract_segment.py` — Water mask segmentation

Applies SAM3 text-prompted segmentation to produce binary water masks.

```
usage: extract_segment.py [-h] [-i INPUT_DIR] [-o OUTPUT_DIR]
                           [-p PROMPT] [--confidence CONFIDENCE] [-v]

options:
  -i, --input-dir DIR       Root folder of input GeoTIFFs (default: lakes)
  -o, --output-dir DIR      Root folder for output masks (default: lakes-segmented)
  -p, --prompt TEXT         Segmentation prompt (default: Water)
  --confidence FLOAT        SAM3 confidence threshold 0–1 (default: 0.4)
  -v, --verbose             Enable DEBUG logging

environment:
  HF_TOKEN                  Hugging Face token (required)
```

**Examples:**

```bash
# Full batch (all sub-folders in lakes/)
export HF_TOKEN=hf_your_token_here
uv run extract_segment.py

# Custom prompt and confidence
uv run extract_segment.py \
    -i lakes \
    -o lakes-segmented \
    -p "Lake water body" \
    --confidence 0.5

# Single lake folder
uv run extract_segment.py \
    -i lakes/bellandur-lake \
    -o lakes-segmented/bellandur-lake
```

---

### `process_tif.py` — Preview generation and metadata

Converts TIFF pairs into web previews and builds `lake_data.json`.

```
usage: process_tif.py [-h] [--lakes-dir DIR] [--segmented-dir DIR]
                      [--previews-dir DIR] [--output-json FILE]
                      [--mask-threshold N] [--workers N] [--dry-run]

options:
  --lakes-dir DIR           Original TIFFs root (default: lakes)
  --segmented-dir DIR       Segmented masks root (default: lakes-segmented)
  --previews-dir DIR        Preview output root (default: previews)
  --output-json FILE        Output JSON path (default: lake_data.json)
  --mask-threshold N        Mask binarisation threshold 0–255 (default: 0)
  --workers N               Parallel workers (default: auto, max 2)
  --dry-run                 List pairs without writing files
```

**Outputs per TIFF pair:**

| File | Description |
|---|---|
| `previews/compressed/<lake>-<date>.webp` | Compressed preview of the original (≤1920×1080, quality 50) |
| `previews/segmented/<lake>-<date>.png`   | Transparent PNG overlay with blue water mask |
| `lake_data.json`                         | JSON mapping each lake to a list of `{date, area_km2, original_img, segmented_img, bounds}` entries |

**Examples:**

```bash
# Dry-run inspection
uv run process_tif.py --dry-run

# Standard run
uv run process_tif.py \
    --lakes-dir lakes \
    --segmented-dir lakes-segmented \
    --previews-dir previews \
    --output-json lake_data.json \
    --workers 4
```

---

### `get_coordinates.html` — Interactive bounding box picker

A Leaflet-based map tool for selecting bounding boxes interactively.

- Displays the current view as a **16:9 bounding box** (matching GEHistoricalImagery tile layout)
- Shows **Zoom**, **Lower Left**, and **Upper Right** coordinates in real time
- Supports **place search** (via Nominatim) and **direct coordinate navigation**
- Toggles between Street and Satellite base layers

Serve locally and open in a browser:

```bash
uv run python -m http.server 8000
# http://localhost:8000/get_coordinates.html
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Binary not found at …` | GEHistoricalImagery not on PATH | Pass full path with `-b /path/to/GEHistoricalImagery` |
| No dates found / incomplete coverage | Bounding box too large at chosen zoom | Reduce zoom (`-z 16`) or shrink the bounding box |
| Missing georeference warning | TIFF has no world file (`.tfw`) and no embedded GeoTIFF tags | Re-download the TIFF or ensure GEHistoricalImagery writes metadata |
| `HF_TOKEN` not set | Token missing from environment | `export HF_TOKEN=hf_…` before running `extract_segment.py` |
| No masks generated by SAM3 | Prompt doesn't match scene / low confidence | Try a more specific prompt (`-p "Open water"`) or lower `--confidence` |
| TIFF pair skipped in process_tif | Segmented mask present but original TIFF missing | Ensure `lakes/` and `lakes-segmented/` filenames match exactly |
| Slow processing | Default worker count | Increase `--workers` in both `get_data.py` and `process_tif.py` |

---

## Dependencies

| Package | Used by | Purpose |
|---|---|---|
| `pillow` | `process_tif.py` | TIFF/WEBP/PNG I/O |
| `numpy` | `process_tif.py` | Fast pixel-level area computation |
| `segment-geospatial[samgeo3]` | `extract_segment.py` | SAM3 inference |
| `huggingface_hub` | `extract_segment.py` | Model weight download |
| [GEHistoricalImagery](https://github.com/Mbucari/GEHistoricalImagery) | `get_data.py` | Tile download from Google Earth |
| [Leaflet](https://leafletjs.com/) | `index.html`, `get_coordinates.html` | Interactive mapping |
| [Chart.js](https://www.chartjs.org/) | `index.html` | Area trend chart |

---

## License

This repository is available under the **MIT License**. See the [`LICENSE`](LICENSE) file for details.
