# Lake Monitor

A simple viewer and processing pipeline for historical lake imagery and segmented water masks.

The project takes georeferenced original lake TIFF images and segmented TIFF masks, converts them into web-friendly preview files, calculates lake surface area in square kilometers, and prepares a JSON dataset for visualization.

The web viewer then lets you explore each lake across time with:
- overlaid original and segmented images
- date-wise area values
- timeline playback
- a clickable sparkline chart
- optional basemap display

## Main Files

- `process_tif.py`: converts original TIFFs to compressed `webp`, converts segmented TIFFs to transparent `png`, calculates area in `km²`, and writes `lake_data.json`
- `index.html`: web viewer for browsing the lake timeline
- `previews/`: generated image outputs used by the viewer
- `lake_data.json`: metadata file containing date, area, image paths, and bounds

## Usage

1. Run `process_tif.py` to generate previews and `lake_data.json`.
2. Open `index.html` in a browser or serve the folder with a simple static server.

## License

This project is available under the MIT License.
