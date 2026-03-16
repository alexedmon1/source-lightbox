# source-lightbox

Static gallery builder for EEG source analysis results. Generates a self-contained, portable website from `source-localization` and `source-analytics` outputs.

## Installation

```bash
cd ~/sandbox/source-lightbox
uv sync
```

## Usage

```bash
# Build gallery
source-lightbox build \
  --localization /path/to/localization_output --label "Allen ROI" \
  --results /path/to/results --label "Allen ROI" \
  --analytics /path/to/analytics \
  --output ./gallery \
  --title "My Study"

# Serve locally
source-lightbox serve ./gallery --port 5500

# Print stats
source-lightbox info ./gallery
```

## Features

- Lightbox image viewer with zoom, pan, keyboard navigation
- Sortable statistical tables with significance highlighting
- Dark/light theme with system preference detection
- Comparison mode for multiple sources (ROI vs Shell, etc.)
- Search across all figures by filename, paradigm, analysis
- Lazy-loaded thumbnails for fast browsing of 500+ figures
- Fully static — drop on any web server
