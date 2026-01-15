# Apple Journal Entries - AI Agent Instructions

## Project Overview
This is an **Apple Journal export converter** that transforms HTML journal entries (exported from the Apple Journal app) into clean Markdown files with embedded images and assets. The converter is designed to preserve journal content while extracting it into a portable, text-friendly format.

## Core Architecture

### Data Flow
1. **index.html** – Master index file containing links to all journal entries (sorted chronologically)
2. **Entries/*.html** – Individual journal entries exported from Apple Journal app with Apple-specific styling
3. **Resources/*.png/.heic** – Image assets referenced by entries
4. **convert_to_md.py** – Single converter script that orchestrates the entire process
5. **md/*.md** – Output markdown files (one per entry)
6. **md/assets/*.{png,heic}** – Copied image files referenced in markdown

### Key Design Pattern: HTMLParser-Based Conversion
The converter uses Python's `HTMLParser` class to incrementally parse HTML and emit markdown. This approach:
- **Avoids DOM parsing overhead** – no need for BeautifulSoup or similar for this use case
- **Cleanly separates concerns** – `SimpleHTMLToMarkdown` class handles HTML→Markdown translation
- **Enables state tracking** – `_in_page_header` flag tracks context for proper heading extraction

## Critical Implementation Details

### 1. Body Content Extraction
Always extract only `<body>` content from HTML:
```python
body_match = re.search(r"<body[^>]*>(.*)</body>", content, flags=re.IGNORECASE | re.DOTALL)
payload = body_match.group(1) if body_match else content
```
**Why:** Apple Journal HTML includes extensive CSS/styling in `<head>` that clutters output. Extracting body-only ensures clean markdown.

### 2. Image Handling Pipeline
Images are handled in three steps:
- **Find images** in HTML: `<img src="../Resources/UUID.heic" />`
- **Copy to assets**: Local images copied to `md/assets/`, remote URLs kept as-is
- **Remap paths**: Original `../Resources/X.heic` → `assets/X.heic` in markdown `![alt](assets/X.heic)`

**Important:** Image UUIDs are Apple-specific (e.g., `2D3F2814-26A1-4F44-9D70-B7CCC92FDF73.heic`). Use filename as-is; don't rename.

### 3. HTML Entity Decoding
Always decode HTML entities in hrefs and text:
```python
decoded = html.unescape(href)  # `&amp;` → `&`
```
**Why:** Some filenames contain special characters like `&` that are HTML-encoded in index.html links.

### 4. Heading Extraction Strategy
- Extract headings from `<div class="pageHeader">` (contains formatted date/time)
- If no pageHeader found, generate heading from filename: `2024-01-16.html` → `# 2024-01-16`
- Headings always appear at top of markdown file

## Current Limitations & Future Enhancements

### Not Yet Implemented
- ❌ **Links in text** – `<a>` tags inside journal content are skipped; consider converting to `[text](url)` markdown
- ❌ **Text formatting** – `<strong>`, `<em>`, `<u>` tags ignored (rendered as plain text)
- ❌ **Nested heading levels** – Only `<div class="pageHeader">` recognized; other heading structures lost
- ❌ **Blockquotes** – `<blockquote>` tags not processed

### Extension Points
If enhancing the parser:
1. Add `_in_link = False` tracking to `__init__` for capturing link URLs
2. Handle `<strong>` → `**text**`, `<em>` → `*text*` in `handle_starttag`
3. Use image_map pattern for URL remapping (already proven in img handling)

## Running the Converter

### Basic Usage
```bash
python3 convert_to_md.py
```
Scans `index.html` for all `Entries/` links, converts each to markdown in `md/`.

### Expected Output
```
Converted Entries/2026-01-14.html -> md/2026-01-14.md
Converted Entries/2026-01-11_joirnalling_after_long_time.html -> md/2026-01-11_joirnalling_after_long_time.md
...
```
Images are silently copied to `md/assets/` (only once per unique filename).

### Debugging Tips
- Check `img_srcs` extraction: Add `print(img_srcs)` before image_map loop
- Verify body extraction: Check if `payload` contains expected content (not empty)
- Test specific file: Wrap `convert_file()` call to isolate one entry

## Code Style & Conventions

### Type Hints
All functions use type hints; prefer union syntax `dict | None` over `Optional[dict]`.

### Naming
- `src` = original HTML source path (e.g., `../Resources/UUID.heic`)
- `dest` = destination path for markdown image link (e.g., `assets/UUID.heic`)
- `image_map` = dictionary mapping HTML src → markdown dest paths

### Path Handling
Always use `pathlib.Path` for cross-platform compatibility; avoid string concatenation for paths.

## Testing & Validation

### Quick Validation
1. Run converter, check `md/` has all expected `.md` files
2. Sample one markdown file: should contain text + image links
3. Verify `md/assets/` contains image files with correct names

### Edge Cases to Watch
- Entries with no pageHeader div (heading auto-generated from filename)
- Multiple images in one entry (all should be copied and linked)
- Filenames with special characters (`&`, `'`, spaces) in href attributes
