#!/usr/bin/env python3
"""
Convert all entry HTML files referenced in index.html to Markdown.
Outputs go to the md/ directory alongside index.html.
"""
import argparse
import html
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent

# Global paths (can be overridden via command line)
INPUT_DIR = ROOT
OUTPUT_DIR = ROOT / "md"
OUTPUT_ASSETS = OUTPUT_DIR / "assets"

# Global flag for HEIC conversion (set via command line)
CONVERT_HEIC_TO_JPEG = False


def convert_heic_to_jpeg(src_path: Path, dest_dir: Path) -> Path:
    """Convert a HEIC file to JPEG using macOS sips command."""
    jpeg_name = src_path.stem + ".jpeg"
    dest_path = dest_dir / jpeg_name
    if not dest_path.exists():
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(src_path), "--out", str(dest_path)],
            capture_output=True,
            check=True,
        )
    return dest_path


class SimpleHTMLToMarkdown(HTMLParser):
    def __init__(self, image_map: dict | None = None) -> None:
        super().__init__()
        self._parts: List[str] = []
        self._in_page_header = False
        self.heading_added = False
        self._image_map = image_map or {}
        self._skip_until_div_close = False
        self._in_link = False
        self._link_url = ""
        self._link_parts: List[str] = []
        self._in_audio = False
        self._audio_src = ""
        self._skip_ui_content = False
        self._ui_skip_depth = 0
        self._in_photo_asset = False
        self._in_video_asset = False
        self._video_src = ""
        self._in_drawing_asset = False

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag == "br":
            self._add("\n")
            return

        # Skip UI overlay elements from Apple Journal (with depth tracking)
        if tag == "div" and (self._has_class(attrs, "audioAssetHeader") or 
                             self._has_class(attrs, "gridItemOverlayText") or
                             self._has_class(attrs, "gridItemOverlayHeader") or
                             self._has_class(attrs, "gridItemOverlayFooter") or
                             self._has_class(attrs, "assetType_audio") or
                             self._has_class(attrs, "activityType") or
                             self._has_class(attrs, "activityMetrics") or
                             self._has_class(attrs, "durationText") or
                             self._has_class(attrs, "assetType_workoutRoute") or
                             self._has_class(attrs, "assetType_stateOfMind")):
            self._skip_ui_content = True
            self._ui_skip_depth = 1
            return

        # Track photo assets to include their images
        if tag == "div" and self._has_class(attrs, "assetType_photo"):
            self._in_photo_asset = True
            return

        # Track video assets to extract video source
        if tag == "div" and self._has_class(attrs, "assetType_video"):
            self._in_video_asset = True
            return

        if self._skip_ui_content:
            if tag == "div":
                self._ui_skip_depth += 1
            return

        if tag == "img":
            src = self._attr_value(attrs, "src")
            if not src:
                return
            # Include photos from assetType_photo divs
            if self._in_photo_asset and self._has_class(attrs, "asset_image"):
                alt = self._attr_value(attrs, "alt") or "Photo"
                dest = self._image_map.get(src, src)
                self._ensure_newline()
                self._add(f"![{alt}]({dest})\n")
                return
            # Include drawings from assetType_drawing divs
            if self._in_drawing_asset and self._has_class(attrs, "asset_image"):
                alt = self._attr_value(attrs, "alt") or "Drawing"
                dest = self._image_map.get(src, src)
                self._ensure_newline()
                self._add(f"![{alt}]({dest})\n")
                return
            # Skip other asset_image class images (UI elements)
            if self._has_class(attrs, "asset_image"):
                return
            alt = self._attr_value(attrs, "alt")
            dest = self._image_map.get(src, src)
            self._ensure_newline()
            self._add(f"![{alt}]({dest})\n")
            return

        if tag == "a":
            href = self._attr_value(attrs, "href")
            if href:
                self._in_link = True
                self._link_url = html.unescape(href)
                self._link_parts = []
            return

        if tag == "audio":
            self._ensure_newline()
            self._in_audio = True
            return

        if tag == "video":
            if self._in_video_asset:
                self._video_src = ""
            else:
                self._skip_ui_content = True
                self._ui_skip_depth = 1
            return

        if tag == "source":
            src = self._attr_value(attrs, "src")
            if self._in_audio and src:
                self._audio_src = src
            elif self._in_video_asset and src:
                self._video_src = src
            return

        if tag == "div" and self._has_class(attrs, "assetType_drawing"):
            self._in_drawing_asset = True
            return

        if tag == "div" and self._has_class(attrs, "pageHeader"):
            self._in_page_header = True

    def handle_endtag(self, tag: str) -> None:
        # Exit UI skip mode with depth tracking
        if self._skip_ui_content:
            if tag == "div":
                self._ui_skip_depth -= 1
                if self._ui_skip_depth == 0:
                    self._skip_ui_content = False
            return

        if tag == "a" and self._in_link:
            link_text = "".join(self._link_parts).strip()
            if link_text and self._link_url:
                self._add(f"[{link_text}]({self._link_url})")
            else:
                self._add("".join(self._link_parts))
            self._in_link = False
            self._link_url = ""
            self._link_parts = []
            return

        if tag == "audio" and self._in_audio:
            if self._audio_src:
                dest = self._image_map.get(self._audio_src, self._audio_src)
                filename = Path(self._audio_src).name
                self._add(f"🎙️ [Audio: {filename}]({dest})")
            else:
                self._add("[Audio Recording]")
            self._ensure_newline()
            self._in_audio = False
            self._audio_src = ""
            return

        if tag == "video":
            if self._in_video_asset and self._video_src:
                dest = self._image_map.get(self._video_src, self._video_src)
                filename = Path(self._video_src).name
                self._ensure_newline()
                self._add(f"🎬 [Video: {filename}]({dest})\n")
                self._video_src = ""
            elif self._skip_ui_content:
                self._ui_skip_depth -= 1
                if self._ui_skip_depth == 0:
                    self._skip_ui_content = False
            return

        # Close photo asset div
        if tag == "div" and self._in_photo_asset:
            self._in_photo_asset = False
            return

        # Close video asset div
        if tag == "div" and self._in_video_asset:
            self._in_video_asset = False
            return

        # Close drawing asset div
        if tag == "div" and self._in_drawing_asset:
            self._in_drawing_asset = False
            return

        if tag == "div" and self._in_page_header:
            self._in_page_header = False
            return

        if tag == "div" and self._skip_until_div_close:
            self._skip_until_div_close = False
            return

        if tag in {"p", "div", "section", "article", "body", "html", "li"}:
            self._ensure_newline()

    def handle_data(self, data: str) -> None:
        if self._skip_until_div_close or self._skip_ui_content or self._in_audio or self._in_video_asset:
            return

        text = html.unescape(data)
        if not text.strip():
            return

        if self._in_page_header:
            self._add_heading(text.strip())
            return

        if self._in_link:
            self._link_parts.append(text)
        else:
            self._add_text(text.strip())

    def _has_class(self, attrs: List[tuple], name: str) -> bool:
        for key, value in attrs:
            if key != "class" or not value:
                continue
            classes = value.split()
            if name in classes:
                return True
        return False

    def _attr_value(self, attrs: List[tuple], name: str) -> str:
        for key, value in attrs:
            if key == name:
                return value or ""
        return ""

    def _add(self, chunk: str) -> None:
        self._parts.append(chunk)

    def _add_heading(self, text: str) -> None:
        self._ensure_newline()
        self._add(f"# {text}\n")
        self.heading_added = True

    def _add_text(self, text: str) -> None:
        if self._parts and not self._parts[-1].endswith((" ", "\n")):
            self._add(" ")
        self._add(text)

    def _ensure_newline(self) -> None:
        if not self._parts:
            return
        if not self._parts[-1].endswith("\n"):
            self._add("\n")

    def markdown(self) -> str:
        raw = "​".join(self._parts)
        # Remove zero-width spaces and other invisible Unicode characters
        raw = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', raw)
        lines: List[str] = []
        for line in raw.splitlines():
            stripped = line.rstrip()
            if not stripped:
                if lines and not lines[-1]:
                    continue
                lines.append("")
            else:
                lines.append(stripped)
        cleaned = "\n".join(lines).strip()
        return cleaned + ("\n" if cleaned else "")


def find_entry_links(index_html: str) -> List[str]:
    hrefs = re.findall(r'href="([^"]+)"', index_html)
    entries = []
    for href in hrefs:
        decoded = html.unescape(href)
        if decoded.startswith("Entries/"):
            entries.append(decoded)
    # Preserve order, remove duplicates
    seen = set()
    unique: List[str] = []
    for href in entries:
        if href in seen:
            continue
        seen.add(href)
        unique.append(href)
    return unique


def convert_file(html_path: Path, out_path: Path) -> None:
    content = html_path.read_text(encoding="utf-8", errors="ignore")

    # Only parse inside <body> ... </body> to avoid style/script noise.
    body_match = re.search(r"<body[^>]*>(.*)</body>", content, flags=re.IGNORECASE | re.DOTALL)
    payload = body_match.group(1) if body_match else content

    # UI asset files to skip (not actual content)
    UI_ASSETS_TO_SKIP = {"audioPlayButton.heic", "audioWave.heic"}

    # Find images that are inside assetType_photo divs (actual photos to include)
    photo_pattern = r'<div[^>]+class="[^"]*assetType_photo[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>'
    photo_srcs = set(html.unescape(m) for m in re.findall(photo_pattern, payload, flags=re.IGNORECASE | re.DOTALL))

    # Find images that are inside assetType_drawing divs (drawings to include)
    drawing_pattern = r'<div[^>]+class="[^"]*assetType_drawing[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>'
    drawing_srcs = set(html.unescape(m) for m in re.findall(drawing_pattern, payload, flags=re.IGNORECASE | re.DOTALL))

    # Combine photo and drawing sources
    content_srcs = photo_srcs | drawing_srcs

    image_map: dict[str, str] = {}
    # Process photo and drawing images (skip workout routes, state of mind, etc.)
    for src in content_srcs:
        if src.startswith("http://") or src.startswith("https://"):
            image_map[src] = src
            continue

        src_path = (html_path.parent / src).resolve()
        try:
            src_path.relative_to(INPUT_DIR)
        except ValueError:
            continue
        if not src_path.exists() or not src_path.is_file():
            continue

        # Skip UI asset files
        if src_path.name in UI_ASSETS_TO_SKIP:
            continue

        OUTPUT_ASSETS.mkdir(parents=True, exist_ok=True)
        
        # Convert HEIC to JPEG if flag is set
        if CONVERT_HEIC_TO_JPEG and src_path.suffix.lower() == ".heic":
            dest_path = convert_heic_to_jpeg(src_path, OUTPUT_ASSETS)
        else:
            dest_path = OUTPUT_ASSETS / src_path.name
            if not dest_path.exists():
                shutil.copy2(src_path, dest_path)
        image_map[src] = f"assets/{dest_path.name}"

    # Handle audio files from <source> tags
    audio_srcs = re.findall(r"<source[^>]+src=\"([^\"]+)\"[^>]*>", payload, flags=re.IGNORECASE)
    for raw_src in audio_srcs:
        src = html.unescape(raw_src)
        if src.startswith("http://") or src.startswith("https://"):
            image_map[src] = src
            continue

        src_path = (html_path.parent / src).resolve()
        try:
            src_path.relative_to(INPUT_DIR)
        except ValueError:
            continue
        if not src_path.exists() or not src_path.is_file():
            continue

        OUTPUT_ASSETS.mkdir(parents=True, exist_ok=True)
        dest_path = OUTPUT_ASSETS / src_path.name
        if not dest_path.exists():
            shutil.copy2(src_path, dest_path)
        image_map[src] = f"assets/{dest_path.name}"

    parser = SimpleHTMLToMarkdown(image_map=image_map)
    parser.feed(payload)
    md = parser.markdown()

    # Extract heading suffix from filename (e.g., "2026-01-15_Heading" -> "Heading")
    filename_stem = html_path.stem
    heading_suffix = ""
    if "_" in filename_stem:
        # Get everything after the first underscore as the suffix
        heading_suffix = filename_stem.split("_", 1)[1].replace("_", " ")

    if not parser.heading_added:
        heading = filename_stem.replace("_", " ")
        if md:
            md = f"# {heading}\n\n{md}"
        else:
            md = f"# {heading}\n"
    elif heading_suffix:
        # Append the suffix to the existing heading
        # Find the first heading line and append the suffix
        lines = md.split("\n", 1)
        if lines[0].startswith("# "):
            lines[0] = f"{lines[0]} - {heading_suffix}"
            md = "\n".join(lines)

    out_path.write_text(md, encoding="utf-8")


def main() -> None:
    global CONVERT_HEIC_TO_JPEG, INPUT_DIR, OUTPUT_DIR, OUTPUT_ASSETS
    
    parser = argparse.ArgumentParser(
        description="Convert Apple Journal HTML exports to Markdown."
    )
    parser.add_argument(
        "--convert-heic",
        action="store_true",
        help="Convert HEIC images to JPEG format (requires macOS sips command)",
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=None,
        help="Path to the exported Journal directory containing index.html, Entries/, and Resources/ (default: current script directory)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Path to output directory for Markdown files (default: md/ in input directory)",
    )
    args = parser.parse_args()
    
    CONVERT_HEIC_TO_JPEG = args.convert_heic
    
    # Set input directory
    if args.input:
        INPUT_DIR = args.input.resolve()
    else:
        INPUT_DIR = ROOT
    
    # Set output directory
    if args.output:
        OUTPUT_DIR = args.output.resolve()
    else:
        OUTPUT_DIR = INPUT_DIR / "md"
    OUTPUT_ASSETS = OUTPUT_DIR / "assets"
    
    index_path = INPUT_DIR / "index.html"
    if not index_path.exists():
        raise SystemExit(f"index.html not found in {INPUT_DIR}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    index_html = index_path.read_text(encoding="utf-8")
    links = find_entry_links(index_html)
    if not links:
        raise SystemExit("No entry links found in index.html")

    for rel_href in links:
        source_path = INPUT_DIR / rel_href
        if not source_path.exists():
            print(f"Skipping missing file: {rel_href}")
            continue
        dest_path = OUTPUT_DIR / (source_path.stem + ".md")
        convert_file(source_path, dest_path)
        print(f"Converted {rel_href} -> {dest_path}")


if __name__ == "__main__":
    main()
