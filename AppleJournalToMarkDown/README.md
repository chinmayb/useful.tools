# Apple Journal to Markdown Converter

Convert Apple Journal HTML exports to Markdown files.

## Prerequisites

- Python 3.10+
- macOS (for HEIC to JPEG conversion using `sips`)
- No external dependencies required (uses Python standard library only)

## Exporting from Apple Journal

1. Open the **Journal** app on your iPhone/iPad
2. Tap on the entry you want to export (or select multiple entries)
3. Tap the **Share** button (square with arrow)
4. Select **Export Journal**
5. Choose **All Entries** or **Selected Entries**
6. Select export format: **HTML** (required for this tool)
7. Save/AirDrop the exported folder to your Mac
8. The export contains:
   - `index.html` - Entry index
   - `Entries/` - HTML files for each entry
   - `Resources/` - Media files (photos, audio, video, drawings)

## Setup

1. Export your Apple Journal entries (this creates an `index.html` and `Entries/` folder)
2. Either:
   - Place the script in the same directory as `index.html`, OR
   - Use the `--input` flag to specify the export directory

## Usage

### Basic conversion (keeps HEIC images)

```bash
python3 convert_html_to_markdown.py
```

### Convert HEIC images to JPEG

```bash
python3 convert_html_to_markdown.py --convert-heic
```

### Specify custom input/output directories

```bash
# Specify input directory (where index.html, Entries/, Resources/ are located)
python3 convert_html_to_markdown.py --input /path/to/journal/export

# Specify both input and output directories
python3 convert_html_to_markdown.py -i /path/to/journal/export -o /path/to/output

# Combine with HEIC conversion
python3 convert_html_to_markdown.py -i /path/to/export -o /path/to/output --convert-heic
```

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--input` | `-i` | Path to exported Journal directory (default: script directory) |
| `--output` | `-o` | Path to output directory (default: `md/` in input directory) |
| `--convert-heic` | | Convert HEIC images to JPEG format |

## Output

- Markdown files are saved to `md/` directory
- Assets (images, audio, video) are copied to `md/assets/`

## Supported Content

| Type | Output |
|------|--------|
| Photos | `![Photo](assets/...)` |
| Drawings | `![Drawing](assets/...)` |
| Audio | `🎙️ [Audio: filename](assets/...)` |
| Video | `🎬 [Video: filename](assets/...)` |
| Text | Plain text |
| Links | `[text](url)` |

## File Naming

If the HTML filename has a suffix after `_`, it becomes part of the heading:

- `2026-01-15.html` → `# Thursday, 15 January 2026`
- `2026-01-15_My Trip.html` → `# Thursday, 15 January 2026 - My Trip`
