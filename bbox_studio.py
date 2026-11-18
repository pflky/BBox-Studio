#!/usr/bin/env python3
"""
BBox Studio — Zero-dependency visual editor for MOSS-Image JSON layout prompts.

Format:
  bbox_coord_space : "abs_centralized"
  bbox_format      : "yxyx"  → [y_min, x_min, y_max, x_max]
  Origin at canvas center, y increases downward.
"""

import base64
import copy
import json
import math
import re
import random
import struct
import zlib
import ctypes
import tempfile
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter import font as tkfont
from typing import Optional, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "BBox Studio"
DEFAULT_W, DEFAULT_H = 1024, 1024
DEFAULT_UI_FONT_FAMILY = "Segoe UI"
DEFAULT_UI_FONT_SIZE = 12

BG_DARK   = "#12121a"
# Meta chips — pastel sea green that fits the dark UI
CHIP_BG     = "#1a3330"
CHIP_BORDER = "#3d8f7c"
CHIP_FG     = "#b8e8dc"
CHIP_FG_DIM = "#7ab5a8"
BG_PANEL  = "#1a1a26"
BG_CANVAS = "#16161f"
FG        = "#e4e4ef"
FG_DIM    = "#8b8ba0"
ACCENT    = "#7c9cff"
ACCENT2   = "#b794f6"
BORDER    = "#2e2e42"
SUCCESS   = "#6ee7a8"
DANGER    = "#f87171"
WARNING   = "#fbbf24"

HANDLE_SIZE = 7
MIN_BOX     = 20

# Distinct random palette for new boxes
PALETTE = [
    "#7c9cff", "#6ee7a8", "#f9a8d4", "#fbbf24", "#a78bfa",
    "#34d399", "#fb923c", "#60a5fa", "#e879f9", "#4ade80",
    "#f472b6", "#38bdf8", "#c084fc", "#facc15", "#2dd4bf",
]

# Common Stable Diffusion / image-gen canvas sizes
# Ordered by aspect: Square → Portrait → Landscape (each group by increasing size)
COMMON_SIZES = [
    # Square
    (512, 512),
    (1024, 1024),
    (1536, 1536),
    (2048, 2048),
    # Portrait
    (832, 1216),
    (896, 1152),
    (1024, 1536),
    (720, 1280),
    (1080, 1920),
    (1440, 2560),
    # Landscape
    (1216, 832),
    (1152, 896),
    (1536, 1024),
    (1280, 720),
    (1920, 1080),
    (2560, 1440),
]

# Dropdown: section titles + divider rows (non-selectable)
SIZE_DROPDOWN_DIVIDER = "──────────────"
SIZE_DROPDOWN_HEADERS = {
    "Square", "Portrait", "Landscape",
    SIZE_DROPDOWN_DIVIDER,
}
SIZE_DROPDOWN_VALUES = [
    SIZE_DROPDOWN_DIVIDER,
    "Square",
    SIZE_DROPDOWN_DIVIDER,
    "512×512",
    "1024×1024",
    "1536×1536",
    "2048×2048",
    SIZE_DROPDOWN_DIVIDER,
    "Portrait",
    SIZE_DROPDOWN_DIVIDER,
    "832×1216",
    "896×1152",
    "1024×1536",
    "720×1280",
    "1080×1920",
    "1440×2560",
    SIZE_DROPDOWN_DIVIDER,
    "Landscape",
    SIZE_DROPDOWN_DIVIDER,
    "1216×832",
    "1152×896",
    "1536×1024",
    "1280×720",
    "1920×1080",
    "2560×1440",
]


def nearest_higher_preset(need_w: int, need_h: int) -> tuple:
    """Pick the closest COMMON_SIZES entry that is >= need_w x need_h on both axes.
    Prefer smallest area excess, then smallest dimension excess. Fallback to largest preset
    or the needed size itself if nothing fits.
    """
    need_w = max(64, int(need_w))
    need_h = max(64, int(need_h))
    candidates = [(w, h) for w, h in COMMON_SIZES if w >= need_w and h >= need_h]
    if candidates:
        # Closest higher: minimize area delta, then max dimension overshoot
        def score(wh):
            w, h = wh
            return ((w * h) - (need_w * need_h), (w - need_w) + (h - need_h), w * h)
        return min(candidates, key=score)
    # No preset large enough — use max preset that covers as much as possible, or need itself
    if COMMON_SIZES:
        # largest by area
        best = max(COMMON_SIZES, key=lambda wh: wh[0] * wh[1])
        return (max(best[0], need_w), max(best[1], need_h))
    return (need_w, need_h)


# Meta presets: display label → actual meta list
META_PRESETS = [
    ("scene",                           ["scene"]),
    # Graphic Design & Print
    ("poster",                          ["poster"]),
    ("minimal graphic design",          ["minimal graphic design"]),
    ("editorial layout",                ["editorial layout"]),
    ("book cover",                      ["book cover"]),
    ("album art",                       ["album art"]),
    ("vintage travel poster",           ["vintage travel poster"]),
    # Commercial & Advertising
    ("product campaign + studio photo", ["product campaign", "studio photography"]),
    ("e-commerce banner",               ["e-commerce banner"]),
    ("advertisement",                   ["advertisement"]),
    ("packaging mockup",                ["packaging mockup"]),
    # Informational & UI
    ("infographic",                     ["infographic"]),
    ("knowledge graphic",               ["knowledge graphic"]),
    ("diagram",                         ["diagram"]),
    ("ui mockup",                       ["ui mockup"]),
    ("slide deck",                      ["slide deck"]),
    # Illustration & Comics
    ("anime illustration",              ["anime illustration"]),
    ("comic page",                      ["comic page"]),
    ("manga",                           ["manga"]),
    ("children's book illustration",    ["children's book illustration"]),
    ("flat vector art",                 ["flat vector art"]),
    # Photography
    ("cinematic still",                 ["cinematic still"]),
    ("street photography",              ["street photography"]),
    ("portrait photography",            ["portrait photography"]),
    ("macro photography",               ["macro photography"]),
]

META_LABELS = [label for label, _ in META_PRESETS]

META_MAP = {label: tags for label, tags in META_PRESETS}


def all_meta_tags():
    seen = set()
    out = []
    for _, tags in META_PRESETS:
        for t in tags:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


ALL_META_TAGS = all_meta_tags()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class BBoxItem:
    def __init__(
        self,
        label: str = "object",
        caption: str = "",
        text: str = "",
        y_min: float = -100,
        x_min: float = -100,
        y_max: float = 100,
        x_max: float = 100,
        color: Optional[str] = None,
    ):
        self.label = label
        self.caption = caption
        self.text = text
        self.y_min = y_min
        self.x_min = x_min
        self.y_max = y_max
        self.x_max = x_max
        self.color = color or random.choice(PALETTE)
        self.locked = False
        self.aspect_locked = False
        # canvas ids
        self.id: Optional[int] = None
        self.handle_ids: List[int] = []
        self.caption_id: Optional[int] = None
        self.badge_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "label": self.label,
            "caption": self.caption,
            "bbox": [
                int(round(self.y_min)),
                int(round(self.x_min)),
                int(round(self.y_max)),
                int(round(self.x_max)),
            ],
        }
        if self.label == "text" and self.text:
            d["text"] = self.text
        return d

    def clamp(self, half_w: float, half_h: float):
        self.y_min = max(-half_h, min(half_h - MIN_BOX, self.y_min))
        self.x_min = max(-half_w, min(half_w - MIN_BOX, self.x_min))
        self.y_max = max(self.y_min + MIN_BOX, min(half_h, self.y_max))
        self.x_max = max(self.x_min + MIN_BOX, min(half_w, self.x_max))

    def width(self) -> float:
        return self.x_max - self.x_min

    def height(self) -> float:
        return self.y_max - self.y_min


class LayoutModel:
    def __init__(self, width: int = DEFAULT_W, height: int = DEFAULT_H):
        self.width = width
        self.height = height
        self.meta: List[str] = []
        self.canvas_type = "single"
        self.caption = "A clean composition with carefully placed elements."
        self.items: List[BBoxItem] = []

    @property
    def half_w(self) -> float:
        return self.width / 2.0

    @property
    def half_h(self) -> float:
        return self.height / 2.0

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "meta": list(self.meta),
                "canvas": self.canvas_type,
                "caption": self.caption,
            },
            "items": [it.to_dict() for it in self.items],
            "bbox_coord_space": "abs_centralized",
            "bbox_format": "yxyx",
        }

    def to_json_str(self, pretty: bool = True) -> str:
        d = self.to_json_dict()
        if pretty:
            return json.dumps(d, indent=2, ensure_ascii=False)
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

    def reset(self):
        self.width = DEFAULT_W
        self.height = DEFAULT_H
        self.meta = []
        self.canvas_type = "single"
        self.caption = "A clean composition with carefully placed elements."
        self.items.clear()

    def load_from_dict(self, data: Dict[str, Any]):
        summary = data.get("summary", {})
        self.meta = list(summary.get("meta", []))
        self.canvas_type = summary.get("canvas", "single")
        self.caption = summary.get("caption", "")
        self.items.clear()

        # Optional explicit size (not part of official MOSS export; used if present)
        explicit_w = int(data["width"]) if "width" in data else None
        explicit_h = int(data["height"]) if "height" in data else None
        if explicit_w and explicit_h:
            self.width = explicit_w
            self.height = explicit_h

        space = data.get("bbox_coord_space", "abs_centralized")
        fmt = data.get("bbox_format", "yxyx")

        for raw in data.get("items", []):
            bbox = raw.get("bbox", [0, 0, 100, 100])
            if fmt == "xyxy":
                x1, y1, x2, y2 = bbox
                y_min, x_min, y_max, x_max = y1, x1, y2, x2
            else:
                y_min, x_min, y_max, x_max = bbox

            # Convert absolute top-left origin → centered coords when needed
            if space == "abs":
                w = explicit_w if explicit_w else self.width
                h = explicit_h if explicit_h else self.height
                y_min -= h / 2
                x_min -= w / 2
                y_max -= h / 2
                x_max -= w / 2

            item = BBoxItem(
                label=raw.get("label", "object"),
                caption=raw.get("caption", ""),
                text=raw.get("text", ""),
                y_min=float(y_min), x_min=float(x_min),
                y_max=float(y_max), x_max=float(x_max),
            )
            self.items.append(item)

        # Infer minimum size from abs_centralized extents, then snap up to the
        # closest preset that is >= that size on both axes. Export JSON unchanged.
        if self.items:
            max_ax = 0.0
            max_ay = 0.0
            for it in self.items:
                max_ax = max(max_ax, abs(it.x_min), abs(it.x_max))
                max_ay = max(max_ay, abs(it.y_min), abs(it.y_max))
            # Canvas must cover ±max → full size = 2 * max
            inferred_w = max(64, int(math.ceil(max_ax * 2 - 1e-9)))
            inferred_h = max(64, int(math.ceil(max_ay * 2 - 1e-9)))
            if explicit_w and explicit_h:
                inferred_w = max(inferred_w, explicit_w)
                inferred_h = max(inferred_h, explicit_h)
            # Floor: anything under 1024×1024 uses 1024×1024
            if inferred_w < 1024 and inferred_h < 1024:
                inferred_w, inferred_h = 1024, 1024
            self.width, self.height = nearest_higher_preset(inferred_w, inferred_h)


# ---------------------------------------------------------------------------
# Lightweight embedded-JSON extraction (no external deps)
# ---------------------------------------------------------------------------

def extract_json_from_bytes(data: bytes) -> Optional[Dict[str, Any]]:
    """Search binary for a MOSS-style layout JSON object."""
    # Try UTF-8 / latin-1 decode of the whole file first (works for pure JSON)
    for encoding in ("utf-8", "latin-1"):
        try:
            text = data.decode(encoding)
            # quick path: whole file is JSON
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and ("items" in obj or "summary" in obj):
                    return obj
            except Exception:
                pass
            # search for balanced { ... } that look like layout
            for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj, dict) and ("items" in obj or "summary" in obj
                                                  or "bbox_coord_space" in obj):
                        return obj
                except Exception:
                    continue
        except Exception:
            continue

    # PNG tEXt / iTXt / zTXt chunks (simple, no compression for tEXt)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        pos = 8
        while pos + 8 < len(data):
            length = struct.unpack(">I", data[pos:pos+4])[0]
            ctype = data[pos+4:pos+8]
            chunk = data[pos+8:pos+8+length]
            pos += 12 + length
            if ctype in (b"tEXt", b"iTXt"):
                try:
                    # tEXt: key\0text
                    if b"\x00" in chunk:
                        key, val = chunk.split(b"\x00", 1)
                        for enc in ("utf-8", "latin-1"):
                            try:
                                s = val.decode(enc)
                                obj = json.loads(s)
                                if isinstance(obj, dict) and ("items" in obj or "summary" in obj):
                                    return obj
                            except Exception:
                                pass
                except Exception:
                    pass

    # JPEG COM (comment) markers
    if data[:2] == b"\xff\xd8":
        pos = 2
        while pos + 4 < len(data):
            if data[pos] != 0xFF:
                break
            marker = data[pos+1]
            if marker in (0xD8, 0xD9):  # SOI/EOI
                pos += 2
                continue
            length = struct.unpack(">H", data[pos+2:pos+4])[0]
            if marker == 0xFE:  # COM
                comment = data[pos+4:pos+2+length]
                for enc in ("utf-8", "latin-1"):
                    try:
                        s = comment.decode(enc)
                        obj = json.loads(s)
                        if isinstance(obj, dict) and ("items" in obj or "summary" in obj):
                            return obj
                    except Exception:
                        pass
            pos += 2 + length

    return None


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


# 5x7 bitmap font rows (5 bits each) for screenshot captions — ASCII subset
_BITMAP_FONT_5X7 = {
    " ": [0, 0, 0, 0, 0, 0, 0],
    "!": [0x04, 0x04, 0x04, 0x04, 0x00, 0x04, 0x00],
    "?": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    ".": [0, 0, 0, 0, 0, 0x04, 0x00],
    ",": [0, 0, 0, 0, 0x04, 0x04, 0x08],
    ":": [0, 0x04, 0, 0, 0x04, 0, 0],
    "-": [0, 0, 0, 0x1F, 0, 0, 0],
    "_": [0, 0, 0, 0, 0, 0, 0x1F],
    "'": [0x04, 0x04, 0, 0, 0, 0, 0],
    '"': [0x0A, 0x0A, 0, 0, 0, 0, 0],
    "/": [0x01, 0x02, 0x04, 0x08, 0x10, 0, 0],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x1F, 0x01, 0x02, 0x06, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0E],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "a": [0, 0, 0x0E, 0x01, 0x0F, 0x11, 0x0F],
    "b": [0x10, 0x10, 0x1E, 0x11, 0x11, 0x11, 0x1E],
    "c": [0, 0, 0x0E, 0x10, 0x10, 0x11, 0x0E],
    "d": [0x01, 0x01, 0x0F, 0x11, 0x11, 0x11, 0x0F],
    "e": [0, 0, 0x0E, 0x11, 0x1F, 0x10, 0x0E],
    "f": [0x06, 0x08, 0x08, 0x1E, 0x08, 0x08, 0x08],
    "g": [0, 0, 0x0F, 0x11, 0x0F, 0x01, 0x0E],
    "h": [0x10, 0x10, 0x1E, 0x11, 0x11, 0x11, 0x11],
    "i": [0x04, 0, 0x0C, 0x04, 0x04, 0x04, 0x0E],
    "j": [0x02, 0, 0x06, 0x02, 0x02, 0x12, 0x0C],
    "k": [0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12],
    "l": [0x0C, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "m": [0, 0, 0x1A, 0x15, 0x15, 0x15, 0x15],
    "n": [0, 0, 0x1E, 0x11, 0x11, 0x11, 0x11],
    "o": [0, 0, 0x0E, 0x11, 0x11, 0x11, 0x0E],
    "p": [0, 0, 0x1E, 0x11, 0x1E, 0x10, 0x10],
    "q": [0, 0, 0x0F, 0x11, 0x0F, 0x01, 0x01],
    "r": [0, 0, 0x16, 0x19, 0x10, 0x10, 0x10],
    "s": [0, 0, 0x0F, 0x10, 0x0E, 0x01, 0x1E],
    "t": [0x08, 0x08, 0x1E, 0x08, 0x08, 0x08, 0x06],
    "u": [0, 0, 0x11, 0x11, 0x11, 0x11, 0x0F],
    "v": [0, 0, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "w": [0, 0, 0x11, 0x11, 0x15, 0x15, 0x0A],
    "x": [0, 0, 0x11, 0x0A, 0x04, 0x0A, 0x11],
    "y": [0, 0, 0x11, 0x11, 0x0F, 0x01, 0x0E],
    "z": [0, 0, 0x1F, 0x02, 0x04, 0x08, 0x1F],
}


class BBoxStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.after(50, self._try_dark_titlebar)
        self.geometry("1320x860")
        self.minsize(1020, 680)
        self.configure(bg=BG_DARK)

        self.model = LayoutModel()
        self.selected: Optional[BBoxItem] = None
        self.drag_mode: Optional[str] = None
        self._create_color: Optional[str] = None
        self.drag_start: Tuple[float, float] = (0.0, 0.0)
        self.create_start: Tuple[float, float] = (0.0, 0.0)
        self.resize_handle: Optional[str] = None
        self.scale = 0.55
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._updating_ui = False
        self._inline_entry: Optional[tk.Entry] = None
        self._inline_item: Optional[BBoxItem] = None
        self._used_colors: set = set()
        self._history: List[Dict[str, Any]] = []
        self._hist_index = -1
        self._hist_suppress = False
        self._aspect_ratio_cache: Optional[float] = None
        self._grid_style = "default"  # not tracked in undo / project history
        self._snap_to_grid = False
        # Customizable accent colors (Copy / meta chips / Delete)
        self._ui_colors = {
            "copy_bg": ACCENT,
            "copy_hi": "#9db4ff",
            "copy_fg": "#0f0f17",
            "chip_bg": CHIP_BG,
            "chip_border": CHIP_BORDER,
            "chip_fg": CHIP_FG,
            "delete_bg": DANGER,
            "delete_fg": "#0f0f17",
            "brand_fg": ACCENT,
            "menu_highlight": ACCENT,
            "menu_divider": FG_DIM,
            "grip_hover": ACCENT,
        }
        self._show_brand = True
        self._show_logo = True
        self._resize_grips = []
        self._meta_list = list(ALL_META_TAGS)  # available Meta dropdown tags (from meta.txt)
  # not tracked in undo / project history
        self._bg_path: Optional[str] = None
        self._bg_photo_orig = None
        self._bg_rgb: Optional[bytes] = None
        self._bg_iw = 0
        self._bg_ih = 0
        self._bg_photo = None
        self._bg_scale_key = None
        self._panning = False
        self._pan_last = (0, 0)
        self._resize_fit_after = None
        self._ui_font_family = DEFAULT_UI_FONT_FAMILY
        self._ui_font_size = DEFAULT_UI_FONT_SIZE

        self._setup_styles()
        self._build_ui()
        self._apply_ui_font()
        try:
            self._apply_ui_colors()
        except Exception:
            pass
        self._bind_events()
        self.after(50, self._initial_fit)
        # Load bbox.cfg (creates default file if missing); window geometry applied shortly after
        try:
            self._load_meta_txt()
        except Exception:
            self._meta_list = list(ALL_META_TAGS)
        try:
            self._load_cfg()
        except Exception:
            self.after(10, self._center_on_screen)
        else:
            # If window_load is false, still center default window
            try:
                data = self._parse_cfg_file()
                if not self._cfg_truthy(data.get("window_load", "true")):
                    self.after(10, self._center_on_screen)
            except Exception:
                self.after(10, self._center_on_screen)
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        # Color hex stays blank on load until a box is selected or created
        try:
            self.color_var.set("")
            self._update_color_preview(None)
            self._sync_pick_btn()
        except Exception:
            pass
        self._update_json()
        self._push_history()  # baseline

    def _center_on_screen(self):
        """Place the main window in the center of the primary monitor."""
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            w, h = 1320, 860
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")


    # ------------------------------------------------------------------
    # bbox.cfg — persistent UI preferences
    # ------------------------------------------------------------------


    def _meta_txt_path(self) -> str:
        return os.path.join(os.getcwd(), "meta.txt")

    def _load_meta_txt(self):
        """Load available Meta tags from meta.txt next to the run directory.
        Creates the file with program defaults if missing. Blank file => empty list.
        """
        path = self._meta_txt_path()
        if not os.path.isfile(path):
            # First run: write program defaults
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for t in ALL_META_TAGS:
                        f.write(f"{t}\n")
            except Exception:
                pass
            self._meta_list = list(ALL_META_TAGS)
            return
        tags = []
        seen = set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    t = line.strip()
                    if not t or t.startswith("#"):
                        continue
                    if t not in seen:
                        seen.add(t)
                        tags.append(t)
        except Exception:
            tags = list(ALL_META_TAGS)
        self._meta_list = tags

    def _save_meta_txt(self):
        """Write current Meta dropdown list to meta.txt (one tag per line)."""
        path = self._meta_txt_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                for t in list(getattr(self, "_meta_list", []) or []):
                    t = str(t).strip()
                    if t:
                        f.write(f"{t}\n")
        except Exception:
            pass

    def _cfg_path(self) -> str:
        """Config lives in the working directory the program was started from."""
        return os.path.join(os.getcwd(), "bbox.cfg")

    def _cfg_defaults(self) -> dict:
        return {
            "font_load": "true",
            "font_family": DEFAULT_UI_FONT_FAMILY,
            "font_size": str(DEFAULT_UI_FONT_SIZE),
            "color_load": "true",
            "copy_bg": ACCENT,
            "copy_hi": "#9db4ff",
            "copy_fg": "#0f0f17",
            "chip_bg": CHIP_BG,
            "chip_border": CHIP_BORDER,
            "chip_fg": CHIP_FG,
            "delete_bg": DANGER,
            "delete_fg": "#0f0f17",
            "brand_fg": ACCENT,
            "menu_highlight": ACCENT,
            "menu_divider": FG_DIM,
            "grip_hover": ACCENT,
            "show_brand": "true",
            "show_logo": "true",
            "window_load": "true",
            "window_state": "normal",
            "window_width": "1320",
            "window_height": "860",
            "window_x": "",
            "window_y": "",
            "snap_load": "true",
            "snap_to_grid": "false",
            "grid_load": "true",
            "grid_style": "default",
            "resolution_load": "true",
            "canvas_width": str(DEFAULT_W),
            "canvas_height": str(DEFAULT_H),
        }

    def _cfg_truthy(self, val) -> bool:
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    def _ensure_cfg_file(self):
        path = self._cfg_path()
        if os.path.isfile(path):
            return
        try:
            self._write_cfg_file(self._cfg_defaults())
        except Exception:
            pass

    def _parse_cfg_file(self) -> dict:
        data = self._cfg_defaults()
        path = self._cfg_path()
        if not os.path.isfile(path):
            return data
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key:
                        data[key] = val
        except Exception:
            pass
        return data

    def _write_cfg_file(self, data: dict):
        path = self._cfg_path()
        order = [
            ("# BBox Studio configuration", None),
            ("# Each *_load flag: true = apply on startup, false = ignore that group", None),
            ("", None),
            ("# Font (right-click Font…)", None),
            ("font_load", "font_load"),
            ("font_family", "font_family"),
            ("font_size", "font_size"),
            ("", None),
            ("# Colors (right-click Color…) + brand visibility", None),
            ("color_load", "color_load"),
            ("copy_bg", "copy_bg"),
            ("copy_hi", "copy_hi"),
            ("copy_fg", "copy_fg"),
            ("chip_bg", "chip_bg"),
            ("chip_border", "chip_border"),
            ("chip_fg", "chip_fg"),
            ("delete_bg", "delete_bg"),
            ("delete_fg", "delete_fg"),
            ("brand_fg", "brand_fg"),
            ("menu_highlight", "menu_highlight"),
            ("menu_divider", "menu_divider"),
            ("grip_hover", "grip_hover"),
            ("show_brand", "show_brand"),
            ("show_logo", "show_logo"),
            ("", None),
            ("# Window size / maximized state", None),
            ("window_load", "window_load"),
            ("window_state", "window_state"),
            ("window_width", "window_width"),
            ("window_height", "window_height"),
            ("window_x", "window_x"),
            ("window_y", "window_y"),
            ("", None),
            ("# Snap to grid", None),
            ("snap_load", "snap_load"),
            ("snap_to_grid", "snap_to_grid"),
            ("", None),
            ("# Canvas grid style", None),
            ("grid_load", "grid_load"),
            ("grid_style", "grid_style"),
            ("", None),
            ("# Canvas resolution", None),
            ("resolution_load", "resolution_load"),
            ("canvas_width", "canvas_width"),
            ("canvas_height", "canvas_height"),
        ]
        lines = []
        for label, key in order:
            if key is None:
                lines.append(label)
            else:
                lines.append(f"{key}={data.get(key, '')}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _collect_cfg_data(self) -> dict:
        """Merge current runtime state into cfg defaults (preserve *_load flags from file)."""
        data = self._parse_cfg_file()  # keeps user load flags
        data["font_family"] = str(getattr(self, "_ui_font_family", DEFAULT_UI_FONT_FAMILY))
        data["font_size"] = str(int(getattr(self, "_ui_font_size", DEFAULT_UI_FONT_SIZE)))
        cols = getattr(self, "_ui_colors", {}) or {}
        for k in (
            "copy_bg", "copy_hi", "copy_fg",
            "chip_bg", "chip_border", "chip_fg",
            "delete_bg", "delete_fg",
            "brand_fg", "menu_highlight", "menu_divider", "grip_hover",
        ):
            if k in cols:
                data[k] = str(cols[k])
        data["show_brand"] = "true" if getattr(self, "_show_brand", True) else "false"
        data["show_logo"] = "true" if getattr(self, "_show_logo", True) else "false"
        # Window
        try:
            self.update_idletasks()
            st = str(self.state())
            if st == "zoomed":
                data["window_state"] = "maximized"
            else:
                data["window_state"] = "normal"
                data["window_width"] = str(max(200, int(self.winfo_width())))
                data["window_height"] = str(max(200, int(self.winfo_height())))
                data["window_x"] = str(int(self.winfo_x()))
                data["window_y"] = str(int(self.winfo_y()))
        except Exception:
            data["window_state"] = "normal"
        data["snap_to_grid"] = "true" if getattr(self, "_snap_to_grid", False) else "false"
        data["grid_style"] = str(getattr(self, "_grid_style", "default") or "default")
        data["canvas_width"] = str(int(self.model.width))
        data["canvas_height"] = str(int(self.model.height))
        return data

    def _save_cfg(self):
        try:
            self._write_cfg_file(self._collect_cfg_data())
        except Exception:
            pass

    def _load_cfg(self):
        """Create cfg if missing, then apply groups whose *_load flag is true."""
        try:
            self._ensure_cfg_file()
        except Exception:
            return
        data = self._parse_cfg_file()

        if self._cfg_truthy(data.get("font_load", "true")):
            fam = (data.get("font_family") or "").strip()
            if fam:
                self._ui_font_family = fam
            try:
                self._ui_font_size = max(8, min(28, int(data.get("font_size", DEFAULT_UI_FONT_SIZE))))
            except Exception:
                pass
            try:
                self._apply_ui_font()
            except Exception:
                pass

        if self._cfg_truthy(data.get("color_load", "true")):
            for k in (
                "copy_bg", "copy_hi", "copy_fg",
                "chip_bg", "chip_border", "chip_fg",
                "delete_bg", "delete_fg",
                "brand_fg", "menu_highlight", "menu_divider", "grip_hover",
            ):
                val = (data.get(k) or "").strip()
                if val:
                    self._ui_colors[k] = val
            if "show_brand" in data:
                self._show_brand = self._cfg_truthy(data.get("show_brand"))
            if "show_logo" in data:
                self._show_logo = self._cfg_truthy(data.get("show_logo"))
            try:
                self._apply_ui_colors()
            except Exception:
                pass

        if self._cfg_truthy(data.get("snap_load", "true")):
            self._snap_to_grid = self._cfg_truthy(data.get("snap_to_grid", "false"))

        if self._cfg_truthy(data.get("grid_load", "true")):
            style = (data.get("grid_style") or "default").strip()
            allowed = {"default", "fine", "coarse", "dots", "thirds", "golden", "cross", "none"}
            if style in allowed:
                self._grid_style = style

        if self._cfg_truthy(data.get("resolution_load", "true")):
            try:
                w = int(data.get("canvas_width", DEFAULT_W))
                h = int(data.get("canvas_height", DEFAULT_H))
                if w >= 64 and h >= 64:
                    self._set_size(w, h, push=False)
            except Exception:
                pass

        if self._cfg_truthy(data.get("window_load", "true")):
            self.after(80, lambda d=data: self._apply_window_cfg(d))

        try:
            self._redraw_all()
        except Exception:
            pass

    def _apply_window_cfg(self, data: dict):
        try:
            state = (data.get("window_state") or "normal").strip().lower()
            if state in ("maximized", "zoomed"):
                try:
                    self.state("zoomed")
                except Exception:
                    try:
                        self.attributes("-zoomed", True)
                    except Exception:
                        pass
                return
            # normal geometry
            try:
                w = int(data.get("window_width") or 1320)
                h = int(data.get("window_height") or 860)
            except Exception:
                w, h = 1320, 860
            w = max(self.minsize()[0] if callable(getattr(self, "minsize", None)) else 1020, w)
            h = max(680, h)
            try:
                x = data.get("window_x", "")
                y = data.get("window_y", "")
                if str(x).strip() != "" and str(y).strip() != "":
                    self.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
                else:
                    self.geometry(f"{w}x{h}")
                    self._center_on_screen()
            except Exception:
                self.geometry(f"{w}x{h}")
        except Exception:
            pass

    def _on_app_close(self):
        try:
            self._save_cfg()
        except Exception:
            pass
        self.destroy()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _ui_font(self, size_delta: int = 0, bold: bool = False):
        family = getattr(self, "_ui_font_family", "Segoe UI") or "Segoe UI"
        base = int(getattr(self, "_ui_font_size", DEFAULT_UI_FONT_SIZE) or DEFAULT_UI_FONT_SIZE)
        size = max(8, min(28, base + size_delta))
        if bold:
            return (family, size, "bold")
        return (family, size)


    def _make_styled_field(
        self, parent, textvariable=None, values=None, kind="",
        expandable=False, width=12, readonly=False, show_arrow=True,
        on_pick=None, on_change=None,
    ):
        """Dark bordered field matching the meta bar: no blue focus ring, optional ▾."""
        box = tk.Frame(
            parent, bg=BG_DARK, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER,  # no accent/blue flash
        )
        btn = None
        if show_arrow:
            # Fixed-size chevron: large hit target without growing row height
            bw, bh = 22, 18
            btn = tk.Canvas(
                box, width=bw, height=bh, bg=BG_DARK,
                highlightthickness=0, cursor="hand2",
            )
            # Downward chevron (similar visual weight to combobox arrow)
            btn.create_polygon(
                6, 6, 16, 6, 11, 13,
                fill=FG, outline=FG, smooth=False,
            )
            btn.pack(side=tk.RIGHT, padx=(0, 3), pady=0)
            def _arrow_enter(_e, c=btn):
                c.configure(bg=BORDER)
            def _arrow_leave(_e, c=btn):
                c.configure(bg=BG_DARK)
            btn.bind("<Enter>", _arrow_enter)
            btn.bind("<Leave>", _arrow_leave)

        entry = tk.Entry(
            box,
            textvariable=textvariable,
            bg=BG_DARK,
            fg=FG,
            insertbackground=FG,
            insertwidth=2,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=self._ui_font(0),
            width=1 if expandable else width,
        )
        if expandable:
            entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 2), pady=4)
        else:
            entry.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 2), pady=4)

        if readonly:
            entry.configure(state="readonly", readonlybackground=BG_DARK, fg=FG)
            # Open list on click into the field
            entry.bind("<Button-1>", lambda e, k=kind, v=values, op=on_pick: self._styled_field_open(k, v, op, box, e))

        if on_change is not None:
            entry.bind("<KeyRelease>", lambda e, cb=on_change: cb(e))
            entry.bind("<FocusOut>", lambda e, cb=on_change: cb(e))
            entry.bind("<Return>", lambda e, cb=on_change: cb(e))

        if show_arrow and btn is not None:
            btn.bind(
                "<Button-1>",
                lambda e, k=kind, v=values, op=on_pick, b=box: self._styled_field_open(k, v, op, b, e),
            )

        # Track for font updates
        if not hasattr(self, "_styled_fields"):
            self._styled_fields = []
        self._styled_fields.append((box, entry, btn))
        return box, entry, btn

    def _styled_field_open(self, kind, values, on_pick, box, event=None):
        if not values:
            return "break"
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == kind:
            closer = getattr(self, "_list_popup_close", None)
            if callable(closer):
                closer()
            return "break"

        def _open():
            try:
                box.update_idletasks()
                x = box.winfo_rootx()
                y = box.winfo_rooty() + box.winfo_height()
                width_px = int(box.winfo_width())
            except Exception:
                x, y, width_px = self.winfo_pointerx(), self.winfo_pointery(), None
            entries = []
            for val in values:
                entries.append((str(val), lambda v=str(val), cb=on_pick: cb(v) if cb else None))
            self._open_list_popup(x, y, entries, width_px=width_px, kind=kind)

        self.after(1, _open)
        return "break"

    def _add_panel_divider(self, parent, padx: int = 10, pady: int = 8):
        """Full-width horizontal rule (same span as the old ttk.Separator)."""
        row = tk.Frame(parent, bg=BG_PANEL, highlightthickness=0)
        row.pack(fill=tk.X, padx=padx, pady=pady)
        # 1px line — same dim color as right-click menu separator text (FG_DIM)
        tk.Frame(row, height=1, bg=FG_DIM, highlightthickness=0).pack(fill=tk.X)

    def _try_dark_titlebar(self):
        """On Windows, request the immersive dark title bar so OS chrome matches the app.
        Full custom title bars need overrideredirect + home-grown min/max/close; this is
        the low-risk way to blend with the dark UI without replacing the system chrome.
        """
        try:
            import sys
            if sys.platform != "win32":
                return
            self.update_idletasks()
            hwnd = self.winfo_id()
            # Tk toplevel HWND; GetParent sometimes needed for the real frame
            try:
                parent = ctypes.windll.user32.GetParent(hwnd)
                if parent:
                    hwnd = parent
            except Exception:
                pass
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win10 1809+ / 19 on some builds)
            value = ctypes.c_int(1)
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _ui_scale(self) -> float:
        """Scale factor relative to default 11pt UI font."""
        base = int(getattr(self, "_ui_font_size", DEFAULT_UI_FONT_SIZE) or DEFAULT_UI_FONT_SIZE)
        return max(0.85, min(2.8, base / float(DEFAULT_UI_FONT_SIZE)))

    def _fit_dialog(self, win: tk.Toplevel, min_w: int = 320, min_h: int = 200, pad: int = 28):
        """Size and center a dialog from content + font scale so nothing clips."""
        self.update_idletasks()
        win.update_idletasks()
        s = self._ui_scale()
        rw = int(win.winfo_reqwidth()) + pad
        rh = int(win.winfo_reqheight()) + pad
        w = max(int(min_w * s), rw)
        h = max(int(min_h * s), rh)
        try:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            w = min(w, max(320, sw - 40))
            h = min(h, max(200, sh - 60))
        except Exception:
            pass
        try:
            x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        except Exception:
            x, y = 80, 80
        win.minsize(max(280, int(min_w * s * 0.85)), max(160, int(min_h * s * 0.85)))
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        f = self._ui_font
        style.configure(".", background=BG_DARK, foreground=FG, fieldbackground=BG_PANEL, font=f(0))
        style.configure("TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG_DARK, foreground=FG, font=f(0))
        style.configure("Dim.TLabel", background=BG_DARK, foreground=FG_DIM, font=f(-1))
        style.configure("Title.TLabel", background=BG_PANEL, foreground=FG, font=f(+2, bold=True))
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG, font=f(0))
        style.configure("Brand.TLabel", background=BG_PANEL, foreground=ACCENT, font=f(+2, bold=True))
        style.configure("TButton", background=BG_PANEL, foreground=FG, borderwidth=0, focusthickness=0, font=f(-1))
        style.map("TButton", background=[("active", BORDER)])
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#0f0f17",
            focusthickness=0,
            focuscolor=BG_PANEL,
            borderwidth=0,
            font=f(-1),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#9db4ff"), ("focus", ACCENT)],
            focuscolor=[("focus", BG_PANEL), ("!focus", BG_PANEL)],
        )
        style.configure("Danger.TButton", background=DANGER, foreground="#0f0f17", font=f(-1))
        style.map("Danger.TButton", background=[("active", "#fca5a5")])
        style.configure("Ghost.TButton", background=BG_PANEL, foreground=FG_DIM, font=f(-1))
        style.map(
            "Ghost.TButton",
            background=[("disabled", BG_PANEL), ("active", BORDER)],
            foreground=[
                ("disabled", "#5a5a6e"),
                ("active", "#ffffff"),
                ("!active", FG_DIM),
            ],
        )
        style.configure(
            "Add.TButton",
            background=BG_PANEL,
            foreground=FG,
            borderwidth=0,
            focusthickness=0,
            font=f(-1, bold=True),
            padding=(6, 4),
        )
        style.map("Add.TButton", background=[("active", BORDER)])
        style.configure(
            "Toolbar.TMenubutton",
            background=BG_PANEL,
            foreground=FG,
            borderwidth=0,
            focusthickness=0,
            padding=(8, 4),
            font=f(-1),
        )
        style.map(
            "Toolbar.TMenubutton",
            background=[("active", BORDER), ("pressed", BORDER)],
            foreground=[("active", FG), ("pressed", FG)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=BG_PANEL,
            background=BG_PANEL,
            foreground=FG,
            arrowcolor=FG,
            font=f(0),
            padding=2,
        )
        style.map("TCombobox", fieldbackground=[("readonly", BG_PANEL)], foreground=[("readonly", FG)])
        style.configure("TEntry", fieldbackground=BG_PANEL, foreground=FG, insertcolor=FG, font=f(0), padding=2)
        # Popdown list uses a separate Listbox — force its font via option database
        try:
            family, size = f(0)[0], f(0)[1]
            self.option_add("*TCombobox*Listbox.font", (family, size))
            self.option_add("*TCombobox*Listbox.background", BG_PANEL)
            self.option_add("*TCombobox*Listbox.foreground", FG)
            self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
            self.option_add("*TCombobox*Listbox.selectForeground", "#0f0f17")
        except Exception:
            pass
        style.configure("TCheckbutton", background=BG_PANEL, foreground=FG, font=f(0))
        style.map("TCheckbutton", background=[("active", BG_PANEL)])
        style.configure("Vertical.TScrollbar", background=BG_PANEL, troughcolor=BG_DARK, arrowcolor=FG)
        style.configure("Horizontal.TScrollbar", background=BG_PANEL, troughcolor=BG_DARK, arrowcolor=FG)

    def _set_combobox_list_font(self, cb, font=None):
        """Force the popdown list (Listbox) of a ttk Combobox to use the UI font."""
        if cb is None:
            return
        if font is None:
            font = self._ui_font(0)
        try:
            family, size = font[0], int(font[1])
            self.option_add("*TCombobox*Listbox.font", (family, size))
        except Exception:
            pass
        try:
            # Create / fetch the popdown shell and set the listbox font directly
            popdown = cb.tk.call("ttk::combobox::PopdownWindow", str(cb))
            # Typical path: popdown.f.l
            for path in (f"{popdown}.f.l", f"{popdown}.f.lb", f"{popdown}.lb"):
                try:
                    cb.tk.call(path, "configure", "-font", font)
                    break
                except Exception:
                    continue
        except Exception:
            pass

    def _bind_combobox_list_font(self, cb):
        """Re-apply list font whenever the user opens the dropdown."""
        if cb is None or getattr(cb, "_bbox_font_bound", False):
            return

        def _on_open(_event=None, box=cb):
            self.after(1, lambda: self._set_combobox_list_font(box))
            self.after(20, lambda: self._set_combobox_list_font(box))

        try:
            cb.bind("<Button-1>", _on_open, add="+")
            cb.bind("<Down>", _on_open, add="+")
            cb.bind("<space>", _on_open, add="+")
            cb._bbox_font_bound = True
        except Exception:
            pass

    def _apply_ui_font(self):
        """Apply current UI font to styles, text widgets, menus, and canvas captions.
        Also scales combobox/entry character widths and the right panel so controls
        don't clip (Live JSON scrollbar alone is not treated as clipping).
        """
        self._setup_styles()
        f = self._ui_font
        s = self._ui_scale()
        try:
            self.option_add("*Font", f(0))
        except Exception:
            pass

        def char_w(base: int) -> int:
            # Character width units already grow with font; do not multiply by scale
            # or fields become too wide. Keep a stable character count.
            return max(4, int(base))

        # Resolution preset + W/H — field font scales; character width stays fixed
        size_cb = getattr(self, "size_cb", None)
        if size_cb is not None:
            try:
                size_cb.configure(font=f(0), width=12)
            except Exception:
                try:
                    size_cb.configure(width=12)
                except Exception:
                    pass
            try:
                values = size_cb.cget("values")
                n = len(values) if values else len(SIZE_DROPDOWN_VALUES)
            except Exception:
                n = len(SIZE_DROPDOWN_VALUES)
            try:
                size_cb.configure(height=n)
            except Exception:
                pass
            self._set_combobox_list_font(size_cb, f(0))
            self._bind_combobox_list_font(size_cb)

        for name, base in (("width_entry", 6), ("height_entry", 6)):
            w = getattr(self, name, None)
            if w is None:
                continue
            try:
                w.configure(font=f(0), width=char_w(base))
            except Exception:
                try:
                    w.configure(width=char_w(base))
                except Exception:
                    pass

        # Right-panel dropdowns + color field (same base size as their Panel labels)
        for name, base in (
            ("canvas_type_cb", 11),
            ("label_cb", 11),
            ("color_entry", 7),
        ):
            w = getattr(self, name, None)
            if w is None:
                continue
            try:
                w.configure(width=char_w(base), font=f(0))
            except Exception:
                try:
                    w.configure(width=char_w(base))
                except Exception:
                    pass
            if name.endswith("_cb") or name in ("canvas_type_cb", "label_cb"):
                self._set_combobox_list_font(w, f(0))
                self._bind_combobox_list_font(w)

        # Right panel width (ignore Live JSON scrollbar as a clipping signal)
        if getattr(self, "right_panel", None) is not None:
            try:
                base = int(getattr(self, "_right_panel_base_w", 400))
                new_w = max(320, min(720, int(round(base * s))))
                self.right_panel.configure(width=new_w)
            except Exception:
                pass

        # Plain tk.Text widgets (captions / box text fields)
        for name in ("caption_text", "item_caption", "item_text", "json_text"):
            w = getattr(self, name, None)
            if w is None:
                continue
            try:
                if name == "json_text":
                    mono = "Cascadia Code" if self._font_exists("Cascadia Code") else "Consolas"
                    w.configure(font=(mono, max(8, self._ui_font_size - 2)))
                else:
                    w.configure(font=f(0))
            except Exception:
                pass

        # Inline caption editor on canvas
        if getattr(self, "_inline_entry", None) is not None:
            try:
                self._inline_entry.configure(font=f(0))
            except Exception:
                pass

        # Status bar
        try:
            if hasattr(self, "status"):
                self.status.configure(font=f(-1))
        except Exception:
            pass
        # List popups use _ui_font() when opened; nothing sticky to update here
        try:
            for box, entry, btn in getattr(self, "_styled_fields", []):
                try:
                    entry.configure(font=f(0), insertbackground=FG)
                except Exception:
                    pass
                if btn is not None:
                    try:
                        # Text buttons only; Canvas arrows have no font
                        if isinstance(btn, tk.Button):
                            btn.configure(font=f(0))
                    except Exception:
                        pass
        except Exception:
            pass
        self._redraw_all()

    # ------------------------------------------------------------------
    # Logo (drawn with Canvas — zero image deps)
    # ------------------------------------------------------------------


        try:
            if hasattr(self, "_sync_top_actions"):
                self.after_idle(self._sync_top_actions)
        except Exception:
            pass

    def _draw_logo(self, parent) -> tk.Canvas:
        c = tk.Canvas(parent, width=36, height=36, bg=BG_PANEL, highlightthickness=0, cursor="hand2")
        # sleek abstract "B" / box mark
        c.create_rectangle(4, 4, 32, 32, outline=ACCENT, width=2)
        c.create_rectangle(9, 9, 20, 20, outline=ACCENT2, width=1.5)
        c.create_rectangle(16, 16, 27, 27, fill=ACCENT, outline="")
        c.create_text(18, 18, text="B", fill="#0f0f17", font=("Segoe UI", 9, "bold"))
        c.bind("<Button-1>", lambda e: self._show_about())
        return c

    def _show_about(self):
        about = tk.Toplevel(self)
        about.title("About BBox Studio")
        about.configure(bg=BG_PANEL)
        about.resizable(True, True)
        about.transient(self)
        about.grab_set()

        s = self._ui_scale()
        pad = max(12, int(16 * s))

        logo = self._draw_logo(about)
        logo.unbind("<Button-1>")
        logo.configure(cursor="")
        logo.pack(pady=(pad, max(6, int(8 * s))))

        # Bold title like the top-bar brand name; same bg as dialog (no dark text chip)
        tk.Label(
            about,
            text="BBox Studio",
            font=self._ui_font(+2, bold=True),
            fg=ACCENT,
            bg=BG_PANEL,
        ).pack(padx=pad)

        ttk.Label(about, text="v1.4", style="Dim.TLabel").pack(
            pady=(max(2, int(2 * s)), 0), padx=pad
        )
        ttk.Label(
            about,
            text="Coded with Grok by plk.\nAll rights reserved, 2026.",
            style="Dim.TLabel",
            justify=tk.CENTER,
        ).pack(pady=(max(6, int(6 * s)), max(10, int(12 * s))), padx=pad)

        ttk.Button(about, text="Close", command=about.destroy).pack(
            pady=(0, max(10, int(12 * s))), padx=pad
        )
        about.bind("<Escape>", lambda e: about.destroy())
        self._fit_dialog(about, min_w=340, min_h=210, pad=max(20, int(24 * s)))
        about.focus_set()


    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────
        top = ttk.Frame(self, style="Panel.TFrame")
        top.pack(side=tk.TOP, fill=tk.X)

        self.logo_canvas = self._draw_logo(top)
        self.logo_canvas.pack(side=tk.LEFT, padx=(10, 4), pady=6)

        self.brand_label = ttk.Label(top, text="BBox Studio", style="Brand.TLabel")
        self.brand_label.pack(side=tk.LEFT, padx=(0, 16), pady=8)

        self.size_frame = ttk.Frame(top, style="Panel.TFrame")
        size_frame = self.size_frame
        size_frame.pack(side=tk.LEFT, padx=4)
        ttk.Label(size_frame, text="Canvas", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.size_var = tk.StringVar(value=f"{DEFAULT_W}×{DEFAULT_H}")
        self.size_cb = ttk.Combobox(
            size_frame, textvariable=self.size_var,
            values=SIZE_DROPDOWN_VALUES,
            width=12, state="readonly",
            height=len(SIZE_DROPDOWN_VALUES),
        )
        self.size_cb.pack(side=tk.LEFT)
        # Custom list popup (same look/behavior as right-click menu) instead of native dropdown
        self.size_cb.bind("<<ComboboxSelected>>", self._on_size_preset)
        self.size_cb.bind("<Button-1>", self._on_size_cb_press)
        self.size_cb.bind("<Down>", self._on_size_cb_press)
        self.size_cb.bind("<space>", self._on_size_cb_press)

        ttk.Label(size_frame, text="W:", style="Dim.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self.width_var = tk.StringVar(value=str(DEFAULT_W))
        self.width_entry = ttk.Entry(size_frame, textvariable=self.width_var, width=6)
        self.width_entry.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(size_frame, text="H:", style="Dim.TLabel").pack(side=tk.LEFT)
        self.height_var = tk.StringVar(value=str(DEFAULT_H))
        self.height_entry = ttk.Entry(size_frame, textvariable=self.height_var, width=6)
        self.height_entry.pack(side=tk.LEFT, padx=(2, 4))
        for ent in (self.width_entry, self.height_entry):
            ent.bind("<Return>", self._on_wh_commit)
            ent.bind("<FocusOut>", self._on_wh_focus_out)
            ent.bind("<KeyRelease>", self._on_wh_live)

        # Scrollable right action strip (File | Settings | Copy | Undo | Redo | Reset).
        # Logo + canvas controls stay fixed on the left; this strip takes remaining width
        # and scrolls horizontally when a large UI font makes the buttons overflow.
        self.top_actions_host = tk.Frame(top, bg=BG_PANEL, highlightthickness=0)
        self.top_actions_host.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self.top_actions_canvas = tk.Canvas(
            self.top_actions_host, bg=BG_PANEL, highlightthickness=0, bd=0, height=36,
        )
        self.top_actions_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.top_actions_inner = tk.Frame(self.top_actions_canvas, bg=BG_PANEL)
        self._top_actions_win = self.top_actions_canvas.create_window(
            (0, 0), window=self.top_actions_inner, anchor=tk.NW,
        )

        actions = self.top_actions_inner
        self.file_btn = ttk.Button(actions, text="File", command=self._open_file_menu)
        self.file_btn.pack(side=tk.LEFT, padx=2, pady=6)
        self.settings_btn = ttk.Button(actions, text="Settings", command=self._open_settings_menu)
        self.settings_btn.pack(side=tk.LEFT, padx=2, pady=6)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=6)
        self.copy_btn = ttk.Button(
            actions, text="Copy Prompt to Clipboard", style="Accent.TButton",
            command=self._copy_json_clicked, takefocus=False,
        )
        self.copy_btn.pack(side=tk.LEFT, padx=0, pady=6)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=6)
        ttk.Button(actions, text="Undo", command=self._undo).pack(side=tk.LEFT, padx=0, pady=6)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=1, pady=6)
        ttk.Button(actions, text="Redo", command=self._redo).pack(side=tk.LEFT, padx=0, pady=6)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=2, pady=6)
        ttk.Button(actions, text="Reset", style="Ghost.TButton", command=self._reset).pack(
            side=tk.LEFT, padx=(0, 4), pady=6,
        )

        def _sync_top_actions(_event=None):
            try:
                self.top_actions_inner.update_idletasks()
                iw = max(1, int(self.top_actions_inner.winfo_reqwidth()))
                ih = max(1, int(self.top_actions_inner.winfo_reqheight()))
                cw = max(1, int(self.top_actions_host.winfo_width()))
                ch = max(ih, int(self.top_actions_host.winfo_height() or ih))
                self.top_actions_canvas.configure(
                    scrollregion=(0, 0, iw, ih), width=cw, height=ch,
                )
                if iw <= cw:
                    # Pin actions to the right when they fit
                    self.top_actions_canvas.coords(self._top_actions_win, cw - iw, max(0, (ch - ih) // 2))
                    self.top_actions_canvas.xview_moveto(0)
                else:
                    self.top_actions_canvas.coords(self._top_actions_win, 0, max(0, (ch - ih) // 2))
                    # Keep the trailing end (Reset) visible by default when overflowing
                    self.top_actions_canvas.xview_moveto(max(0.0, (iw - cw) / float(iw)))
            except Exception:
                pass

        def _top_actions_wheel(event):
            try:
                iw = max(1, int(self.top_actions_inner.winfo_reqwidth()))
                cw = max(1, int(self.top_actions_host.winfo_width()))
                if iw <= cw:
                    return
                if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                    self.top_actions_canvas.xview_scroll(-3, "units")
                else:
                    self.top_actions_canvas.xview_scroll(3, "units")
            except Exception:
                pass
            return "break"

        self.top_actions_inner.bind("<Configure>", _sync_top_actions)
        self.top_actions_host.bind("<Configure>", _sync_top_actions)
        for w in (self.top_actions_host, self.top_actions_canvas, self.top_actions_inner):
            w.bind("<MouseWheel>", _top_actions_wheel)
            w.bind("<Shift-MouseWheel>", _top_actions_wheel)
            w.bind("<Button-4>", _top_actions_wheel)
            w.bind("<Button-5>", _top_actions_wheel)
        self._sync_top_actions = _sync_top_actions

        def _bind_top_actions_wheel(widget):
            for seq in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(seq, _top_actions_wheel)
            for child in widget.winfo_children():
                _bind_top_actions_wheel(child)

        def _top_actions_ready():
            try:
                _bind_top_actions_wheel(self.top_actions_inner)
            except Exception:
                pass
            _sync_top_actions()

        self.after(50, _top_actions_ready)

        # ── Main split ────────────────────────────────────────────────
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Canvas area
        canvas_wrap = ttk.Frame(main, style="Panel.TFrame")
        canvas_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_wrap, bg=BG_CANVAS, highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Right panel (width scales with UI font so controls don't clip)
        self._right_panel_base_w = 400
        self.right_panel = ttk.Frame(main, width=self._right_panel_base_w, style="Panel.TFrame")
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.right_panel.pack_propagate(False)
        right = self.right_panel

        # Add-box actions at top of right panel (equal columns, compact)
        add_row = ttk.Frame(right, style="Panel.TFrame")
        add_row.pack(fill=tk.X, padx=10, pady=(12, 14))
        add_row.columnconfigure(1, weight=1, uniform="addbtns")
        add_row.columnconfigure(2, weight=1, uniform="addbtns")
        add_row.columnconfigure(3, weight=1, uniform="addbtns")
        ttk.Label(add_row, text="Add:", style="Dim.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Button(add_row, text="Text", style="Add.TButton",
                   command=lambda: self._add_item("text")).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(add_row, text="Object", style="Add.TButton",
                   command=lambda: self._add_item("object")).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(add_row, text="Character", style="Add.TButton",
                   command=lambda: self._add_item("character")).grid(row=0, column=3, sticky="ew", padx=2)

        # Summary
        self._add_panel_divider(right, padx=10, pady=(4, 10))
        ttk.Label(right, text="Summary", style="Title.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 4))

        ttk.Label(right, text="Caption", style="Dim.TLabel").pack(anchor=tk.W, padx=12)
        self.caption_text = self._make_resizable_text(right, height=3)
        self.caption_text.insert("1.0", self.model.caption)
        self.caption_text.bind("<KeyRelease>", self._on_caption_change)

        # Meta — Option A: row1 type-in + ▾, row2 chip strip
        meta_block = ttk.Frame(right, style="Panel.TFrame")
        meta_block.pack(fill=tk.X, padx=12, pady=4)

        meta_row = ttk.Frame(meta_block, style="Panel.TFrame")
        meta_row.pack(fill=tk.X)
        ttk.Label(meta_row, text="Meta", style="Panel.TLabel", width=5).pack(side=tk.LEFT)

        self.meta_var = tk.StringVar(value="")
        self.meta_box, self.meta_entry, self.meta_add_btn = self._make_styled_field(
            meta_row, textvariable=self.meta_var, expandable=True,
            values=None, kind="meta", show_arrow=True,
            on_pick=None, on_change=None,
        )
        self.meta_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        # Focus border like Caption text fields (BORDER idle → system/accent focus)
        # Caption uses default highlightcolor on focus; match that on the outer frame.
        try:
            _cap = tk.Text(self)
            _focus_col = _cap.cget("highlightcolor")
            _cap.destroy()
        except Exception:
            _focus_col = ACCENT
        self._meta_focus_border = _focus_col or ACCENT

        def _meta_focus_in(_e=None):
            try:
                self.meta_box.configure(
                    highlightbackground=self._meta_focus_border,
                    highlightcolor=self._meta_focus_border,
                )
            except Exception:
                pass

        def _meta_focus_out(_e=None):
            try:
                self.meta_box.configure(
                    highlightbackground=BORDER,
                    highlightcolor=BORDER,
                )
            except Exception:
                pass

        self.meta_entry.bind("<FocusIn>", _meta_focus_in, add="+")
        self.meta_entry.bind("<FocusOut>", _meta_focus_out, add="+")
        # Type-to-add only (chips hold the real meta list)
        self.meta_entry.bind("<Return>", self._on_meta_type_commit)
        self.meta_entry.bind("<KP_Enter>", self._on_meta_type_commit)
        self.meta_entry.bind("<KeyRelease>", self._on_meta_type_key)
        if self.meta_add_btn is not None:
            self.meta_add_btn.unbind("<Button-1>")
            self.meta_add_btn.bind("<Button-1>", self._on_meta_picker_click)

        # Row 2: chips only (indented under the field)
        self.meta_chip_row = ttk.Frame(meta_block, style="Panel.TFrame")
        self.meta_chip_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(self.meta_chip_row, text="", style="Panel.TLabel", width=5).pack(side=tk.LEFT)
        self.meta_chip_canvas = tk.Canvas(
            self.meta_chip_row, height=30, bg=BG_PANEL, highlightthickness=0,
        )
        self.meta_chip_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.meta_chips = tk.Frame(self.meta_chip_canvas, bg=BG_PANEL)
        self._meta_chips_win = self.meta_chip_canvas.create_window(
            (0, 0), window=self.meta_chips, anchor=tk.NW,
        )
        self.meta_chips.bind("<Configure>", self._on_meta_chips_configure)
        self.meta_chip_canvas.bind("<Configure>", self._on_meta_chip_canvas_configure)
        for seq in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
            self.meta_chip_canvas.bind(seq, self._on_meta_chips_wheel)
            self.meta_chips.bind(seq, self._on_meta_chips_wheel)
            self.meta_chip_row.bind(seq, self._on_meta_chips_wheel)
        self._refresh_meta_chips()

        canvas_row = ttk.Frame(right, style="Panel.TFrame")
        canvas_row.pack(fill=tk.X, padx=12, pady=2)
        ttk.Label(canvas_row, text="Type", style="Panel.TLabel", width=5).pack(side=tk.LEFT)
        self.canvas_type_var = tk.StringVar(value=self.model.canvas_type)
        self.canvas_type_box, self.canvas_type_entry, self.canvas_type_btn = self._make_styled_field(
            canvas_row, textvariable=self.canvas_type_var, expandable=False, width=14,
            values=["single", "multi_panel", "collage"], kind="canvas_type",
            readonly=True, on_pick=self._on_canvas_type_picked,
        )
        self.canvas_type_box.pack(side=tk.LEFT, padx=(8, 0))
        # Keep name for any legacy defocus helpers
        self.canvas_type_cb = self.canvas_type_entry

        self._add_panel_divider(right, padx=10, pady=10)

        # Selected item
        ttk.Label(right, text="Selected Box", style="Title.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 4))

        type_row = ttk.Frame(right, style="Panel.TFrame")
        type_row.pack(fill=tk.X, padx=12, pady=2)
        ttk.Label(type_row, text="Label", style="Panel.TLabel", width=5).pack(side=tk.LEFT)
        self.label_var = tk.StringVar(value="object")
        self.label_box, self.label_entry, self.label_btn = self._make_styled_field(
            type_row, textvariable=self.label_var, expandable=False, width=14,
            values=["text", "object", "character"], kind="label",
            readonly=True, on_pick=self._on_label_picked,
        )
        self.label_box.pack(side=tk.LEFT, padx=(8, 0))
        self.label_cb = self.label_entry

        color_row = ttk.Frame(right, style="Panel.TFrame")
        color_row.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(color_row, text="Color", style="Panel.TLabel", width=5).pack(side=tk.LEFT)
        self.color_preview = tk.Canvas(
            color_row, width=22, height=22, bg=BG_PANEL,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER,
            cursor="arrow",
        )
        self.color_preview.pack(side=tk.LEFT, padx=(8, 4))
        self.color_preview.bind("<Button-1>", lambda e: self._pick_color())
        self.color_var = tk.StringVar(value="")  # blank until a box is selected/created
        self.color_box, self.color_entry, _color_btn = self._make_styled_field(
            color_row, textvariable=self.color_var, expandable=False, width=10,
            values=None, kind="color", readonly=False, show_arrow=False,
            on_change=self._on_color_entry,
        )
        self.color_box.pack(side=tk.LEFT)
        self._update_color_preview(None)

        ttk.Label(right, text="Caption  (also editable by double-clicking the box)", style="Dim.TLabel").pack(anchor=tk.W, padx=12, pady=(6, 0))
        self.item_caption = self._make_resizable_text(right, height=3)
        self.item_caption.bind("<KeyRelease>", self._on_item_caption_change)

        ttk.Label(right, text="Text content  (text items only)", style="Dim.TLabel").pack(anchor=tk.W, padx=12, pady=(4, 0))
        self.item_text = self._make_resizable_text(right, height=2)
        self.item_text.bind("<KeyRelease>", self._on_item_text_change)

        lock_row = ttk.Frame(right, style="Panel.TFrame")
        lock_row.pack(fill=tk.X, padx=12, pady=4)
        self.lock_var = tk.BooleanVar(value=False)
        self.aspect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(lock_row, text="Lock position/size", variable=self.lock_var,
                        command=self._on_lock_toggle).pack(side=tk.LEFT)
        ttk.Checkbutton(lock_row, text="Lock aspect ratio", variable=self.aspect_var,
                        command=self._on_aspect_toggle).pack(side=tk.LEFT, padx=(12, 0))

        btn_row = ttk.Frame(right, style="Panel.TFrame")
        btn_row.pack(fill=tk.X, padx=12, pady=8)
        ttk.Button(btn_row, text="Delete", style="Danger.TButton", command=self._delete_selected).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Duplicate", command=self._duplicate_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Bring To Front", command=self._bring_front).pack(side=tk.LEFT, padx=4)

        # Match panel bg when empty so no dark "patch" shows with no selection
        self.coord_label = tk.Label(
            right, text="", bg=BG_PANEL, fg=FG_DIM,
            font=self._ui_font(-1), anchor=tk.W, justify=tk.LEFT,
        )
        self.coord_label.pack(anchor=tk.W, padx=12, pady=2)

        self._add_panel_divider(right, padx=10, pady=8)

        # Live JSON
        ttk.Label(right, text="Live JSON", style="Title.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 4))
        json_frame = ttk.Frame(right, style="Panel.TFrame")
        json_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.json_text = tk.Text(
            json_frame, wrap=tk.NONE, bg="#0e0e14", fg="#6ee7a8",
            insertbackground=FG, relief=tk.FLAT,
            font=("Cascadia Code", 9) if self._font_exists("Cascadia Code") else ("Consolas", 9),
            highlightthickness=0,
        )
        yscroll = ttk.Scrollbar(json_frame, orient=tk.VERTICAL, command=self.json_text.yview)
        xscroll = ttk.Scrollbar(json_frame, orient=tk.HORIZONTAL, command=self.json_text.xview)
        self.json_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.json_text.configure(state=tk.DISABLED)

        # Status
        self.status = ttk.Label(
            self,
            text="Ready  ·  Drag empty space to create  ·  Double-click box to edit caption  ·  Scroll to zoom",
            style="Dim.TLabel",
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=4)

    def _make_resizable_text(self, parent, height: int = 3) -> tk.Text:
        """Text widget with a bottom drag grip to resize height downward."""
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill=tk.X, padx=12, pady=2)

        text = tk.Text(
            wrap, height=height, wrap=tk.WORD, bg=BG_DARK, fg=FG,
            insertbackground=FG, relief=tk.FLAT, font=("Segoe UI", 11),
            highlightthickness=1, highlightbackground=BORDER,
        )
        text.pack(fill=tk.X, expand=True)

        grip = tk.Frame(wrap, height=6, bg=BORDER, cursor="sb_v_double_arrow")
        grip.pack(fill=tk.X, pady=(2, 0))
        if not hasattr(self, "_resize_grips"):
            self._resize_grips = []
        self._resize_grips.append(grip)

        def _grip_enter(_e, g=grip):
            col = (getattr(self, "_ui_colors", {}) or {}).get("grip_hover", ACCENT)
            g.configure(bg=col)

        def _grip_leave(_e, g=grip):
            g.configure(bg=BORDER)

        grip.bind("<Enter>", _grip_enter)
        grip.bind("<Leave>", _grip_leave)

        state = {"start_y": 0, "start_h": height}

        def on_press(event):
            state["start_y"] = event.y_root
            state["start_h"] = int(text.cget("height"))

        def on_drag(event):
            dy = event.y_root - state["start_y"]
            # ~18px per text row
            new_h = max(2, min(20, state["start_h"] + int(round(dy / 18))))
            text.configure(height=new_h)

        grip.bind("<ButtonPress-1>", on_press)
        grip.bind("<B1-Motion>", on_drag)
        return text

    def _font_exists(self, name: str) -> bool:
        try:
            import tkinter.font as tkfont
            return name in tkfont.families()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _img_to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        cx = self.canvas.winfo_width() / 2 + self.offset_x
        cy = self.canvas.winfo_height() / 2 + self.offset_y
        return cx + x * self.scale, cy + y * self.scale

    def _canvas_to_img(self, cx: float, cy: float) -> Tuple[float, float]:
        ox = self.canvas.winfo_width() / 2 + self.offset_x
        oy = self.canvas.winfo_height() / 2 + self.offset_y
        return (cx - ox) / self.scale, (cy - oy) / self.scale

    def _initial_fit(self):
        self._center_canvas()
        self._redraw_all()

    def _center_canvas(self):
        # Default fit used by size changes / Scale To Fit
        self._fit_view_to_canvas(allow_upscale=False)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw_all(self):
        self.canvas.delete("all")
        # Image bounds
        x0, y0 = self._img_to_canvas(-self.model.half_w, -self.model.half_h)
        x1, y1 = self._img_to_canvas(self.model.half_w, self.model.half_h)
        # Background fill
        self.canvas.create_rectangle(x0, y0, x1, y1, fill="#0c0c12", outline="", tags="bg")

        # Background image (hides grid when present) — scaled to exact frame size
        if self._bg_rgb is not None:
            tw = max(1, int(round(abs(x1 - x0))))
            th = max(1, int(round(abs(y1 - y0))))
            photo = self._get_scaled_bg_photo(tw, th)
            if photo is not None:
                self.canvas.create_image(x0, y0, image=photo, anchor=tk.NW, tags="bgimage")
        else:
            self._draw_grid(x0, y0, x1, y1)

        # Frame outline on top
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=BORDER, width=2, tags="bgframe")

        for item in self.model.items:
            self._draw_item(item)

        if self.selected:
            self._draw_handles(self.selected)
            self._update_item_panel()

    def _centered_grid_coords(self, half: float, step: float) -> list:
        """Coordinates from -half..half that always include 0 (center cross)."""
        if step <= 0:
            return [0.0]
        half = float(half)
        step = float(step)
        vals = [0.0]
        k = step
        while k <= half + 1e-6:
            vals.append(k)
            vals.append(-k)
            k += step
        vals.sort()
        return vals

    def _draw_grid(self, x0, y0, x1, y1):
        """Draw guide grid according to self._grid_style (not used when bg image is set).
        All patterns are centered on the origin (center cross).
        """
        style = getattr(self, "_grid_style", "default")
        if style == "none":
            return

        hw, hh = self.model.half_w, self.model.half_h
        grid_color = "#1e1e2c"
        accent = "#2a2a3c"

        # Center cross for all guide styles (including dots)
        if style in ("default", "fine", "coarse", "cross", "thirds", "golden", "dots"):
            cx, cy = self._img_to_canvas(0, 0)
            self.canvas.create_line(cx - 14, cy, cx + 14, cy, fill=BORDER, width=1)
            self.canvas.create_line(cx, cy - 14, cx, cy + 14, fill=BORDER, width=1)

        if style == "cross":
            return

        if style == "dots":
            step = 50 if self.model.width <= 1200 else 80
            xs = self._centered_grid_coords(hw, step)
            ys = self._centered_grid_coords(hh, step)
            for gx in xs:
                for gy in ys:
                    px, py = self._img_to_canvas(gx, gy)
                    self.canvas.create_oval(px - 1, py - 1, px + 1, py + 1, fill=grid_color, outline="")
            return

        if style == "thirds":
            # Lines at ±1/6 of full size from center → classic rule-of-thirds
            for t in (1 / 3, 2 / 3):
                gx = -hw + 2 * hw * t  # equals ±hw/3 relative to center
                gy = -hh + 2 * hh * t
                xa, ya = self._img_to_canvas(gx, -hh)
                xb, yb = self._img_to_canvas(gx, hh)
                self.canvas.create_line(xa, ya, xb, yb, fill=accent, width=1, dash=(6, 4))
                xa, ya = self._img_to_canvas(-hw, gy)
                xb, yb = self._img_to_canvas(hw, gy)
                self.canvas.create_line(xa, ya, xb, yb, fill=accent, width=1, dash=(6, 4))
            return

        if style == "golden":
            phi = 0.6180339887
            for t in (1 - phi, phi):
                gx = -hw + 2 * hw * t
                gy = -hh + 2 * hh * t
                xa, ya = self._img_to_canvas(gx, -hh)
                xb, yb = self._img_to_canvas(gx, hh)
                self.canvas.create_line(xa, ya, xb, yb, fill=accent, width=1, dash=(8, 5))
                xa, ya = self._img_to_canvas(-hw, gy)
                xb, yb = self._img_to_canvas(hw, gy)
                self.canvas.create_line(xa, ya, xb, yb, fill=accent, width=1, dash=(8, 5))
            return

        if style == "fine":
            step = 25 if self.model.width <= 1200 else 50
        elif style == "coarse":
            step = 100 if self.model.width <= 1200 else 200
        else:  # default
            step = 50 if self.model.width <= 1200 else 100

        for gx in self._centered_grid_coords(hw, step):
            xa, ya = self._img_to_canvas(gx, -hh)
            xb, yb = self._img_to_canvas(gx, hh)
            self.canvas.create_line(xa, ya, xb, yb, fill=grid_color, width=1)
        for gy in self._centered_grid_coords(hh, step):
            xa, ya = self._img_to_canvas(-hw, gy)
            xb, yb = self._img_to_canvas(hw, gy)
            self.canvas.create_line(xa, ya, xb, yb, fill=grid_color, width=1)

    def _draw_item(self, item: BBoxItem):
        x0, y0 = self._img_to_canvas(item.x_min, item.y_min)
        x1, y1 = self._img_to_canvas(item.x_max, item.y_max)
        color = item.color
        is_sel = item is self.selected
        width = 3 if is_sel else 2
        locked = bool(getattr(item, "locked", False))

        # Semi-transparent fill via stipple
        dash = (4, 3) if locked else ()
        item.id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=color, width=width,
            fill=color if is_sel else "",
            stipple="gray25" if is_sel else "",
            dash=dash,
            tags=("box", f"item-{id(item)}"),
        )

        # Caption inside the box, prefixed with type label
        pad = 6
        body = item.caption or (item.text if item.label == "text" else "")
        if body:
            display = f"{item.label} · {body}"
        else:
            display = item.label or "object"
        max_chars = max(8, int((x1 - x0) / 7))
        if len(display) > max_chars:
            display = display[: max_chars - 1] + "…"

        item.caption_id = self.canvas.create_text(
            x0 + pad, y0 + pad,
            text=display,
            anchor=tk.NW,
            fill=color,
            font=self._ui_font(0),
            width=max(20, x1 - x0 - pad * 2),
            tags=("caption", f"item-{id(item)}"),
        )
        item.badge_id = None

    def _draw_handles(self, item: BBoxItem):
        for hid in item.handle_ids:
            self.canvas.delete(hid)
        item.handle_ids.clear()

        x0, y0 = self._img_to_canvas(item.x_min, item.y_min)
        x1, y1 = self._img_to_canvas(item.x_max, item.y_max)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hs = HANDLE_SIZE

        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w": (x0, cy),               "e": (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        for name, (hx, hy) in handles.items():
            hid = self.canvas.create_rectangle(
                hx - hs / 2, hy - hs / 2, hx + hs / 2, hy + hs / 2,
                fill=ACCENT, outline="#0f0f17", width=1,
                tags=("handle", f"h-{name}"),
            )
            item.handle_ids.append(hid)


    # ------------------------------------------------------------------
    # Background image, grid, view (zero-deps)
    # ------------------------------------------------------------------

    def _on_pan_start(self, event):
        self._panning = True
        self._pan_last = (event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, event):
        if not self._panning:
            return
        dx = event.x - self._pan_last[0]
        dy = event.y - self._pan_last[1]
        self._pan_last = (event.x, event.y)
        self.offset_x += dx
        self.offset_y += dy
        self._redraw_all()

    def _on_pan_end(self, event):
        self._panning = False
        self.canvas.configure(cursor="crosshair")

    def _ensure_list_popup_outside_bind(self):
        """Bind a single global press handler that closes list popups on outside click."""
        if getattr(self, "_list_popup_outside_bound", False):
            return
        self._list_popup_outside_bound = True
        # ButtonPress so it runs before widget handlers; outside → close
        self.bind_all("<ButtonPress-1>", self._on_list_popup_outside_press, add="+")

    def _on_list_popup_outside_press(self, event):
        pop = getattr(self, "_list_popup", None)
        if pop is None:
            return
        # Ignore the same click that opened the popup (File button / right-click)
        if not getattr(self, "_list_popup_armed", False):
            return
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            widget = None
        # Inside popup?
        w = widget
        while w is not None:
            if w == pop:
                return
            w = getattr(w, "master", None)
        # Clicks on the control that owns a toggleable popup: let that control
        # close it (so a second click toggles closed instead of close+reopen)
        kind = getattr(self, "_list_popup_kind", None)
        if kind == "size" and widget is getattr(self, "size_cb", None):
            return
        if kind == "file" and widget is getattr(self, "file_btn", None):
            return
        if kind == "settings" and widget is getattr(self, "settings_btn", None):
            return
        # Toggleable styled fields: ignore clicks on their own box
        if kind in ("meta", "canvas_type", "label", "size", "file"):
            w = widget
            while w is not None:
                if kind == "meta" and w in (getattr(self, "meta_box", None), getattr(self, "meta_add_btn", None), getattr(self, "meta_entry", None)):
                    return
                if kind == "canvas_type" and w in (getattr(self, "canvas_type_box", None), getattr(self, "canvas_type_btn", None), getattr(self, "canvas_type_entry", None)):
                    return
                if kind == "label" and w in (getattr(self, "label_box", None), getattr(self, "label_btn", None), getattr(self, "label_entry", None)):
                    return
                w = getattr(w, "master", None)
        # Outside — close; let the original click still reach the app underneath
        closer = getattr(self, "_list_popup_close", None)
        if callable(closer):
            self.after_idle(closer)
        else:
            try:
                pop.destroy()
            except Exception:
                pass
            self._list_popup = None
            self._list_popup_kind = None

    def _open_list_popup(self, x_root: int, y_root: int, entries: list, width_px: int = None, kind: str = None, min_rows: int = None, removable: dict = None, cascades: dict = None):
        """Dropdown/list popup styled like the resolution preset Combobox list.
        entries: list of (label, callback|None). callback None = separator (non-selectable).
        width_px: optional pixel width to match a control (e.g. resolution field).
        kind: optional id so the same control can toggle the popup closed.
        min_rows: optional minimum visible rows (e.g. so custom meta tags are not scrolled away).
        removable: optional {row_index: tag_str} for right-click Remove (custom meta tags).
        cascades: optional {row_index: [(label, cmd), ...]} for hover submenus (e.g. Batch).
        """
        # Dismiss any existing popup
        old = getattr(self, "_list_popup", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
            self._list_popup = None

        font = self._ui_font(0)
        pop = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=BORDER)
        self._list_popup = pop
        self._list_popup_kind = kind

        # Outer 1px border (BORDER color on pop shows through as hairline)
        wrap = tk.Frame(pop, bg=BG_PANEL, highlightthickness=0, bd=0)
        wrap.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        labels = []
        actions = []
        for label, cmd in entries:
            labels.append(label)
            actions.append(cmd)

        # Pixel width from real menu labels only (not the long separator glyph — that was
        # making File menus far too wide on the right). Left/right pad = measure("  ").
        try:
            fnt = tkfont.Font(font=font)
        except Exception:
            fnt = None
        side_pad_px = 0
        text_px = 0
        if fnt is not None:
            side_pad_px = fnt.measure("  ")  # same as the "  " prefix on each row
            for lab, cmd in entries:
                if cmd is None:
                    continue  # separators don't drive width
                s = str(lab)
                try:
                    text_px = max(text_px, fnt.measure(s))
                except Exception:
                    text_px = max(text_px, len(s) * 8)
            if text_px <= 0:
                # fallback if menu is only separators
                text_px = fnt.measure(SIZE_DROPDOWN_DIVIDER)
            zero = max(1, fnt.measure("0"))
            natural_inner_px = side_pad_px + text_px + side_pad_px
            content_chars = max(4, int(math.ceil(natural_inner_px / float(zero))))
        else:
            lens = [len(str(lab)) for lab, cmd in entries if cmd is not None]
            content_chars = (max(lens) if lens else 12) + 4
            natural_inner_px = None

        if width_px is not None and width_px > 0:
            try:
                zero = max(1, fnt.measure("0")) if fnt is not None else 8
                content_chars = max(content_chars, int(max(1, width_px - 2) / zero) + 1)
            except Exception:
                pass
            # Keep natural_inner_px so total width can be max(button, content)
            # (important when UI font grows larger than the Settings button label)

        menu_hi = (getattr(self, "_ui_colors", {}) or {}).get("menu_highlight", ACCENT)
        menu_div = (getattr(self, "_ui_colors", {}) or {}).get("menu_divider", FG_DIM)
        lb = tk.Listbox(
            wrap,
            font=font,
            bg=BG_PANEL,
            fg=FG,
            selectbackground=menu_hi,
            selectforeground="#0f0f17",
            activestyle="none",
            highlightthickness=0,
            relief=tk.FLAT,
            borderwidth=0,
            exportselection=False,
            width=content_chars,
            height=max(
                min(28, max(1, len(labels))),
                min(max(1, len(labels)), max(1, int(min_rows or 0))),
            ) if min_rows else min(28, max(1, len(labels))),
        )
        lb.pack(fill=tk.BOTH, expand=True)

        # Build a full-width divider string for the current UI font (label width only —
        # does not change menu width). Target the same span as the longest label text.
        def _full_width_sep() -> str:
            # Dash run at current UI font. Target width = longest label (File/canvas),
            # or the full menu inner width when min width is forced (e.g. Settings button).
            target = text_px if text_px > 0 else 0
            try:
                inner = None
                if natural_inner_px is not None:
                    inner = int(natural_inner_px)
                if width_px is not None and width_px > 0:
                    forced = max(0, int(width_px) - 2)
                    inner = max(inner or 0, forced)
                if inner is not None and fnt is not None:
                    # Leading "  " is side_pad_px; fill the rest with dashes
                    target = max(target, max(0, inner - side_pad_px))
            except Exception:
                pass
            if fnt is not None and target > 0:
                dash = "─"
                body = ""
                try:
                    while fnt.measure(body + dash) <= target:
                        body += dash
                        if len(body) > 120:
                            break
                except Exception:
                    body = "────────"
                if not body:
                    body = "─"
                return f"  {body}"
            return f"  {SIZE_DROPDOWN_DIVIDER}"

        sep_text = _full_width_sep()
        sep_indices = set()
        header_indices = set()
        for i, (label, cmd) in enumerate(entries):
            if cmd is None:
                lb.insert(tk.END, sep_text)
                lb.itemconfig(
                    i,
                    foreground=menu_div,
                    selectforeground=menu_div,
                    selectbackground=BG_PANEL,
                )
                sep_indices.add(i)
            elif cmd is False:
                # Section header (e.g. Square / Portrait) — not selectable
                lb.insert(tk.END, f"  {label}")
                lb.itemconfig(
                    i,
                    foreground=menu_div,
                    selectforeground=menu_div,
                    selectbackground=BG_PANEL,
                )
                header_indices.add(i)
            else:
                lb.insert(tk.END, f"  {label}")

        cascades = cascades or {}
        cascade_indices = set(cascades.keys())

        def close_cascade():
            cpop = getattr(self, "_cascade_popup", None)
            if cpop is not None:
                try:
                    cpop.destroy()
                except Exception:
                    pass
            self._cascade_popup = None
            self._cascade_parent_idx = None

        def close():
            close_cascade()
            try:
                pop.grab_release()
            except Exception:
                pass
            try:
                pop.destroy()
            except Exception:
                pass
            if getattr(self, "_list_popup", None) is pop:
                self._list_popup = None
                self._list_popup_kind = None

        self._list_popup_close = close  # used by global outside-click handler

        def open_cascade(idx: int):
            if getattr(self, "_cascade_parent_idx", None) == idx and getattr(self, "_cascade_popup", None) is not None:
                return
            close_cascade()
            sub = cascades.get(idx) or []
            if not sub:
                return
            hi = (getattr(self, "_ui_colors", {}) or {}).get("menu_highlight", ACCENT)
            cpop = tk.Toplevel(pop)
            cpop.withdraw()
            cpop.overrideredirect(True)
            cpop.configure(bg=BORDER)
            self._cascade_popup = cpop
            self._cascade_parent_idx = idx
            cwrap = tk.Frame(cpop, bg=BG_PANEL, highlightthickness=0, bd=0)
            cwrap.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            # Width from sub labels
            try:
                cfnt = tkfont.Font(font=self._ui_font(0))
                max_px = max(cfnt.measure(f"  {lab}") for lab, _ in sub)
                zero = max(1, cfnt.measure("0"))
                cchars = max(8, int(max_px / zero) + 2)
            except Exception:
                cchars = 22
            clb = tk.Listbox(
                cwrap, font=self._ui_font(0), bg=BG_PANEL, fg=FG,
                selectbackground=hi, selectforeground="#0f0f17",
                activestyle="none", highlightthickness=0, relief=tk.FLAT,
                borderwidth=0, exportselection=False, height=len(sub), width=cchars,
            )
            sub_actions = []
            for lab, cmd in sub:
                clb.insert(tk.END, f"  {lab}")
                sub_actions.append(cmd)
            clb.pack(fill=tk.BOTH, expand=True)
            try:
                clb.selection_clear(0, tk.END)
                clb.activate(-1)
            except Exception:
                pass

            def run_sub(i):
                if i < 0 or i >= len(sub_actions):
                    return
                cmd = sub_actions[i]
                close()
                if callable(cmd):
                    self.after(1, cmd)

            def c_click(_e=None):
                sel = clb.curselection()
                if sel:
                    run_sub(int(sel[0]))

            def c_motion(e):
                try:
                    i = clb.nearest(e.y)
                    clb.selection_clear(0, tk.END)
                    clb.selection_set(i)
                    clb.activate(i)
                except Exception:
                    pass

            def c_leave(_e=None):
                try:
                    clb.selection_clear(0, tk.END)
                    clb.activate(-1)
                except Exception:
                    pass
                # Close cascade if pointer left both menus
                self.after(80, maybe_close_cascade)

            clb.bind("<ButtonRelease-1>", c_click)
            clb.bind("<Motion>", c_motion)
            clb.bind("<Leave>", c_leave)
            cwrap.bind("<Leave>", c_leave)
            cpop.bind("<Leave>", c_leave)
            clb.bind("<Escape>", lambda e: close())
            cpop.bind("<Escape>", lambda e: close())

            cpop.update_idletasks()
            # Cascade underneath the parent item (not to the right)
            try:
                pop.update_idletasks()
                lb.update_idletasks()
                row_h = max(18, int(lb.winfo_height() / max(1, lb.size())))
                # Align left edge with parent menu; top just below the Batch row
                px = pop.winfo_rootx()
                py = pop.winfo_rooty() + 2 + (idx + 1) * row_h
                cw = max(cpop.winfo_reqwidth(), pop.winfo_width())
                ch = max(cpop.winfo_reqheight(), 28)
                sw, sh = cpop.winfo_screenwidth(), cpop.winfo_screenheight()
                # If it would go off the bottom, flip above the item
                if py + ch > sh - 4:
                    py = max(0, pop.winfo_rooty() + 2 + idx * row_h - ch)
                px = min(max(0, px), max(0, sw - cw - 4))
                py = min(max(0, py), max(0, sh - ch - 4))
                cpop.geometry(f"{cw}x{ch}+{px}+{py}")
            except Exception:
                cpop.geometry(f"+{self.winfo_pointerx()}+{self.winfo_pointery()}")
            cpop.deiconify()
            cpop.lift()

        def maybe_close_cascade():
            cpop = getattr(self, "_cascade_popup", None)
            if cpop is None:
                return
            try:
                x, y = self.winfo_pointerx(), self.winfo_pointery()
                w = self.winfo_containing(x, y)
            except Exception:
                close_cascade()
                return
            cur = w
            while cur is not None:
                if cur in (pop, wrap, lb, cpop) or str(cur).startswith(str(cpop)):
                    return
                # walk masters
                try:
                    if cur == cpop or cur.winfo_toplevel() == cpop:
                        return
                    if cur == pop or cur.winfo_toplevel() == pop:
                        return
                except Exception:
                    pass
                cur = getattr(cur, "master", None)
            close_cascade()

        def activate(idx: int):
            if idx in sep_indices or idx in header_indices or idx < 0 or idx >= len(actions):
                return
            if idx in cascade_indices:
                open_cascade(idx)
                return
            cmd = actions[idx]
            close()
            if callable(cmd):
                self.after(1, cmd)

        def on_click(_event=None):
            sel = lb.curselection()
            if sel:
                activate(int(sel[0]))

        def on_motion(event):
            try:
                idx = lb.nearest(event.y)
                lb.selection_clear(0, tk.END)
                if idx not in sep_indices and idx not in header_indices:
                    lb.selection_set(idx)
                    lb.activate(idx)
                if idx in cascade_indices:
                    open_cascade(idx)
                else:
                    close_cascade()
            except Exception:
                pass

        def on_key(event):
            if event.keysym in ("Escape",):
                close()
            elif event.keysym in ("Return", "space"):
                on_click()

        def on_leave(_event=None):
            try:
                lb.selection_clear(0, tk.END)
                lb.activate(-1)
            except Exception:
                pass
            self.after(80, maybe_close_cascade)

        lb.bind("<ButtonRelease-1>", on_click)
        lb.bind("<Motion>", on_motion)
        lb.bind("<Leave>", on_leave)
        wrap.bind("<Leave>", on_leave)
        pop.bind("<Leave>", on_leave)
        lb.bind("<Escape>", on_key)
        lb.bind("<Return>", on_key)
        pop.bind("<Escape>", lambda e: close())

        # Right-click Remove (same visual style as canvas / File list popups)
        removable = removable or {}

        def on_right_click(event):
            try:
                idx = lb.nearest(event.y)
            except Exception:
                return
            if idx not in removable:
                return "break"
            tag = removable[idx]
            is_builtin = False
            try:
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
            except Exception:
                pass
            # Nested list-style popup matching canvas right-click menus
            hi = (getattr(self, "_ui_colors", {}) or {}).get("menu_highlight", ACCENT)
            rm = tk.Toplevel(pop)
            rm.withdraw()
            rm.overrideredirect(True)
            rm.configure(bg=BORDER)
            wrap_rm = tk.Frame(rm, bg=BG_PANEL, highlightthickness=0, bd=0)
            wrap_rm.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            rlb = tk.Listbox(
                wrap_rm, font=self._ui_font(0), bg=BG_PANEL, fg=FG,
                selectbackground=hi, selectforeground="#0f0f17",
                activestyle="none", highlightthickness=0, relief=tk.FLAT,
                borderwidth=0, exportselection=False, height=1, width=12,
            )
            rlb.insert(tk.END, "  Remove")
            rlb.pack(fill=tk.BOTH, expand=True)
            # No default selection — highlight only on mouseover (like other menus)
            try:
                rlb.selection_clear(0, tk.END)
                rlb.activate(-1)
            except Exception:
                pass

            def do_remove(_e=None):
                try:
                    rm.destroy()
                except Exception:
                    pass
                self._hide_or_remove_meta_tag(tag, builtin=is_builtin)

            def rm_motion(e):
                try:
                    rlb.selection_clear(0, tk.END)
                    rlb.selection_set(0)
                    rlb.activate(0)
                except Exception:
                    pass

            def rm_leave(_e=None):
                try:
                    rlb.selection_clear(0, tk.END)
                    rlb.activate(-1)
                except Exception:
                    pass

            rlb.bind("<ButtonRelease-1>", do_remove)
            rlb.bind("<Return>", do_remove)
            rlb.bind("<Motion>", rm_motion)
            rlb.bind("<Enter>", rm_motion)
            rlb.bind("<Leave>", rm_leave)
            wrap_rm.bind("<Leave>", rm_leave)
            rlb.bind("<Escape>", lambda e: rm.destroy())
            rm.bind("<Escape>", lambda e: rm.destroy())
            rm.update_idletasks()
            rw = max(rlb.winfo_reqwidth() + 4, 90)
            rh = max(rlb.winfo_reqheight() + 4, 28)
            rx = min(event.x_root, max(0, rm.winfo_screenwidth() - rw - 4))
            ry = min(event.y_root, max(0, rm.winfo_screenheight() - rh - 4))
            rm.geometry(f"{rw}x{rh}+{rx}+{ry}")
            rm.deiconify()
            rm.lift()
            rlb.focus_set()
            # Dismiss if clicking away
            def outside(e):
                try:
                    w = self.winfo_containing(e.x_root, e.y_root)
                except Exception:
                    w = None
                cur = w
                while cur is not None:
                    if cur in (rm, wrap_rm, rlb):
                        return
                    cur = getattr(cur, "master", None)
                try:
                    rm.destroy()
                except Exception:
                    pass
            self._meta_remove_popup = rm
            def outside_guard(e):
                if getattr(self, "_meta_remove_popup", None) is not rm:
                    return
                outside(e)
            self.bind_all("<ButtonPress-1>", outside_guard, add="+")
            def on_rm_destroy(_e=None):
                if getattr(self, "_meta_remove_popup", None) is rm:
                    self._meta_remove_popup = None
            rm.bind("<Destroy>", on_rm_destroy)
            return "break"

        if removable:
            lb.bind("<Button-3>", on_right_click)
            lb.bind("<Control-Button-1>", on_right_click)

        pop.update_idletasks()
        w = pop.winfo_reqwidth()
        h = pop.winfo_reqheight()
        sw, sh = pop.winfo_screenwidth(), pop.winfo_screenheight()
        x = min(max(0, x_root), max(0, sw - w - 4))
        y = min(max(0, y_root), max(0, sh - h - 4))
        pop.update_idletasks()
        h = max(pop.winfo_reqheight(), 40)
        if width_px is not None and width_px > 0:
            # At least as wide as the control (Settings / resolution); grow with content/font
            total_w = int(width_px)
            if natural_inner_px is not None:
                total_w = max(total_w, int(natural_inner_px) + 2)
            else:
                total_w = max(total_w, int(pop.winfo_reqwidth()))
        elif natural_inner_px is not None:
            # Content width + equal side pads + 2px outer hairline border
            total_w = int(natural_inner_px) + 2
        else:
            total_w = max(pop.winfo_reqwidth(), 40)
        # Keep on-screen
        total_w = max(40, min(total_w, max(40, sw - 8)))
        pop.geometry(f"{total_w}x{h}+{x}+{y}")
        try:
            wrap.configure(width=max(1, total_w - 2))
        except Exception:
            pass
        pop.deiconify()
        pop.lift()
        # No grab_set — outside clicks must reach the global handler to dismiss
        lb.focus_set()

        def on_destroy(_e=None):
            if getattr(self, "_list_popup", None) is pop:
                self._list_popup = None
                self._list_popup_kind = None
            if getattr(self, "_list_popup_close", None) is close:
                self._list_popup_close = None
        pop.bind("<Destroy>", on_destroy)

        # Ensure one global outside-click listener (does not unbind other handlers)
        self._list_popup_armed = False
        self._ensure_list_popup_outside_bind()
        # Arm after the opening click finishes so the menu does not close immediately
        self.after(50, lambda: setattr(self, "_list_popup_armed", True))

    def _open_settings_menu(self, event=None):
        """Toolbar Settings menu: Font, Color, Config."""
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "settings":
            closer = getattr(self, "_list_popup_close", None)
            if callable(closer):
                closer()
            return "break"
        try:
            self.settings_btn.update_idletasks()
            x = self.settings_btn.winfo_rootx()
            y = self.settings_btn.winfo_rooty() + self.settings_btn.winfo_height()
            width_px = int(self.settings_btn.winfo_width())
            if width_px < 40:
                width_px = int(self.settings_btn.winfo_reqwidth())
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            width_px = None
        entries = [
            ("Font", self._font_dialog),
            ("────────", None),
            ("Color", self._color_theme_dialog),
            ("────────", None),
            ("Config", self._open_cfg_in_notepad),
            ("────────", None),
            ("Meta", self._open_meta_in_notepad),
            ("────────", None),
            ("Batch ▶", "cascade"),  # cascade via cascades map
        ]
        cascades = {
            len(entries) - 1: [
                ("Convert JSON to PNG", self._batch_json_to_png),
                ("Convert PNG to JSON", self._batch_png_to_json),
            ],
        }
        self._open_list_popup(
            x, y, entries, width_px=width_px, kind="settings", cascades=cascades,
        )
        return "break"

    def _open_cfg_in_notepad(self):
        """Open bbox.cfg in Windows Notepad (create file first if needed)."""
        try:
            self._ensure_cfg_file()
        except Exception:
            pass
        path = self._cfg_path()
        try:
            if sys.platform.startswith("win"):
                import subprocess
                subprocess.Popen(["notepad.exe", path], shell=False)
            else:
                import subprocess
                for cmd in (("xdg-open", path), ("open", path)):
                    try:
                        subprocess.Popen(cmd)
                        break
                    except Exception:
                        continue
            self.status.configure(text=f"Opened config → {path}")
        except Exception as e:
            try:
                messagebox.showerror("Config", f"Could not open config file:\n{path}\n{e}")
            except Exception:
                pass

    def _open_meta_in_notepad(self):
        """Open meta.txt in Notepad (create defaults if missing)."""
        try:
            self._load_meta_txt()
        except Exception:
            pass
        path = self._meta_txt_path()
        try:
            if not os.path.isfile(path):
                self._save_meta_txt()
            if sys.platform.startswith("win"):
                import subprocess
                subprocess.Popen(["notepad.exe", path], shell=False)
            else:
                import subprocess
                for cmd in (("xdg-open", path), ("open", path)):
                    try:
                        subprocess.Popen(cmd)
                        break
                    except Exception:
                        continue
            self.status.configure(text=f"Opened meta list → {path}")
        except Exception as e:
            try:
                messagebox.showerror("Meta", f"Could not open meta.txt:\n{path}\n{e}")
            except Exception:
                pass

    def _open_batch_submenu(self, event=None):
        """Secondary Settings menu for batch convert tools."""
        try:
            x = self.winfo_pointerx() + 4
            y = self.winfo_pointery() + 4
        except Exception:
            try:
                self.settings_btn.update_idletasks()
                x = self.settings_btn.winfo_rootx() + self.settings_btn.winfo_width()
                y = self.settings_btn.winfo_rooty()
            except Exception:
                x, y = 100, 100
        entries = [
            ("Convert JSON to PNG", self._batch_json_to_png),
            ("Convert PNG to JSON", self._batch_png_to_json),
        ]
        self._open_list_popup(x, y, entries, kind="batch")

    def _batch_json_to_png(self):
        """Load each .json in a folder and save a screenshot PNG with embedded JSON."""
        folder = filedialog.askdirectory(title="Select folder of JSON files")
        if not folder:
            return
        names = sorted(
            n for n in os.listdir(folder)
            if n.lower().endswith(".json") and os.path.isfile(os.path.join(folder, n))
        )
        if not names:
            messagebox.showinfo("Batch", "No .json files found in that folder.", parent=self)
            return
        snap = self._snapshot()
        ok, fail = 0, 0
        self.status.configure(text=f"Batch JSON→PNG: 0/{len(names)}…")
        self.update_idletasks()
        try:
            for i, name in enumerate(names):
                path = os.path.join(folder, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        fail += 1
                        continue
                    self._hist_suppress = True
                    self.model.load_from_dict(data)
                    self.selected = None
                    try:
                        rgb, w, h = self._render_export_rgb()
                        meta = self.model.to_json_str(pretty=False)
                        out = os.path.join(folder, os.path.splitext(name)[0] + ".png")
                        self._write_png_with_text(out, rgb, w, h, meta)
                        ok += 1
                    finally:
                        self._hist_suppress = False
                except Exception:
                    fail += 1
                self.status.configure(text=f"Batch JSON→PNG: {i + 1}/{len(names)}…")
                self.update_idletasks()
        finally:
            try:
                self._restore_snapshot(snap)
            except Exception:
                pass
        self.status.configure(text=f"Batch JSON→PNG done · {ok} saved · {fail} skipped")
        messagebox.showinfo(
            "Batch JSON → PNG",
            f"Folder: {folder}\nSaved: {ok}\nSkipped/failed: {fail}",
            parent=self,
        )

    def _batch_png_to_json(self):
        """Read embedded layout JSON from each PNG in a folder and write .json files."""
        folder = filedialog.askdirectory(title="Select folder of PNG files")
        if not folder:
            return
        names = sorted(
            n for n in os.listdir(folder)
            if n.lower().endswith(".png") and os.path.isfile(os.path.join(folder, n))
        )
        if not names:
            messagebox.showinfo("Batch", "No .png files found in that folder.", parent=self)
            return
        ok, fail = 0, 0
        self.status.configure(text=f"Batch PNG→JSON: 0/{len(names)}…")
        self.update_idletasks()
        for i, name in enumerate(names):
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                data = extract_json_from_bytes(raw)
                if not data or not isinstance(data, dict):
                    fail += 1
                    continue
                out = os.path.join(folder, os.path.splitext(name)[0] + ".json")
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                ok += 1
            except Exception:
                fail += 1
            self.status.configure(text=f"Batch PNG→JSON: {i + 1}/{len(names)}…")
            self.update_idletasks()
        self.status.configure(text=f"Batch PNG→JSON done · {ok} saved · {fail} skipped")
        messagebox.showinfo(
            "Batch PNG → JSON",
            f"Folder: {folder}\nSaved: {ok}\nSkipped (no metadata / failed): {fail}",
            parent=self,
        )

    def _open_file_menu(self, event=None):
        """Toolbar File menu as listbox-style popup under the File button."""
        # Toggle closed if this menu is already open
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "file":
            closer = getattr(self, "_list_popup_close", None)
            if callable(closer):
                closer()
            return "break"
        try:
            self.file_btn.update_idletasks()
            x = self.file_btn.winfo_rootx()
            y = self.file_btn.winfo_rooty() + self.file_btn.winfo_height()
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
        entries = [
            ("Save Project", self._save_project),
            ("Load Project", self._load_project),
            ("────────", None),
            ("Import JSON", self._import_any),
            ("Export JSON", self._export_json),
        ]
        # Natural width from labels (balanced left/right padding — not locked to button)
        self._open_list_popup(x, y, entries, width_px=None, kind="file")
        return "break"

    def _canvas_menu_entries(self) -> list:
        bg_active = (
            getattr(self, "_bg_rgb", None) is not None
            or getattr(self, "_bg_photo_orig", None) is not None
        )
        if bg_active:
            snap_label = "Snap to Grid: Off (no grid)"
        else:
            snap_label = "Snap to Grid: On" if self._snap_to_grid else "Snap to Grid: Off"
        entries = [
            ("Change Background…", self._change_background),
            ("────────", None),
            ("Remove Background", self._remove_background),
            ("────────", None),
            ("Take Screenshot", self._take_screenshot),
            ("────────", None),
            ("Grid: Default", lambda: self._set_grid_style("default")),
            ("Grid: Fine", lambda: self._set_grid_style("fine")),
            ("Grid: Coarse", lambda: self._set_grid_style("coarse")),
            ("Grid: Dots", lambda: self._set_grid_style("dots")),
            ("Grid: Rule of Thirds", lambda: self._set_grid_style("thirds")),
            ("Grid: Golden Ratio", lambda: self._set_grid_style("golden")),
            ("Grid: Center Cross", lambda: self._set_grid_style("cross")),
            ("Grid: None", lambda: self._set_grid_style("none")),
            ("────────", None),
            (snap_label, self._toggle_snap_to_grid),
            ("────────", None),
            ("Scale to Fit", self._scale_to_fit),
            ("Scale 50%", lambda: self._set_view_scale_pct(0.5)),
            ("Scale 100%", lambda: self._set_view_scale_pct(1.0)),
            ("Scale 200%", lambda: self._set_view_scale_pct(2.0)),
            ("────────", None),
            ("Recenter Canvas", self._recenter_view),
        ]
        return entries

    def _on_canvas_menu(self, event):
        self._open_list_popup(event.x_root, event.y_root, self._canvas_menu_entries())

    def _take_screenshot(self):
        """Render canvas at full model resolution (boxes + grid/bg + captions) and save PNG with JSON metadata.
        Background is taken from the full-res RGB buffer — never from the on-screen
        Tk zoom/subsample PhotoImage — so screenshots keep native quality.
        """
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
            title="Save Screenshot",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            rgb, w, h = self._render_export_rgb()
            meta = self.model.to_json_str(pretty=False)
            self._write_png_with_text(path, rgb, w, h, meta)
            self.status.configure(text=f"Screenshot saved → {path}")
        except Exception as e:
            messagebox.showerror("Screenshot failed", str(e), parent=self)

    def _render_export_rgb(self) -> Tuple[bytes, int, int]:
        """Software-render the layout at full model resolution (no external deps)."""
        w, h = int(self.model.width), int(self.model.height)
        hw, hh = w / 2.0, h / 2.0
        # Dark canvas base
        pixels = bytearray([0x0C, 0x0C, 0x12] * (w * h))

        def set_px(x: int, y: int, rgb: Tuple[int, int, int]):
            if 0 <= x < w and 0 <= y < h:
                i = (y * w + x) * 3
                pixels[i:i+3] = bytes(rgb)

        def blend_px(x: int, y: int, rgb: Tuple[int, int, int], a: float):
            if 0 <= x < w and 0 <= y < h:
                i = (y * w + x) * 3
                r0, g0, b0 = pixels[i], pixels[i+1], pixels[i+2]
                pixels[i] = int(r0 + (rgb[0] - r0) * a)
                pixels[i+1] = int(g0 + (rgb[1] - g0) * a)
                pixels[i+2] = int(b0 + (rgb[2] - b0) * a)

        def to_px(ix: float, iy: float) -> Tuple[int, int]:
            return int(round(ix + hw)), int(round(iy + hh))

        def parse_color(c: str) -> Tuple[int, int, int]:
            c = (c or "#7c9cff").strip()
            if c.startswith("#") and len(c) == 7:
                return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            return (124, 156, 255)

        # Background image — always from full-res master RGB, never Tk subsample/zoom display photo
        if self._bg_rgb and self._bg_iw and self._bg_ih:
            if int(self._bg_iw) == w and int(self._bg_ih) == h:
                # Exact match: copy native pixels (no resampling, full quality)
                pixels[:] = self._bg_rgb
            else:
                # Model size differs from image: resample from master RGB only (not display bitmap)
                scaled = self._resize_rgb_nn(
                    self._bg_rgb, int(self._bg_iw), int(self._bg_ih), w, h
                )
                pixels[:] = scaled
        else:
            # Grid (match on-screen styles, in image pixel space)
            style = getattr(self, "_grid_style", "default")
            grid_c = (0x1E, 0x1E, 0x2C)
            accent = (0x2A, 0x2A, 0x3C)
            border = (0x2E, 0x2E, 0x42)

            def hline(y_img: float, col, x0=None, x1=None):
                _, py = to_px(0, y_img)
                xa = 0 if x0 is None else to_px(x0, 0)[0]
                xb = w - 1 if x1 is None else to_px(x1, 0)[0]
                for x in range(min(xa, xb), max(xa, xb) + 1):
                    set_px(x, py, col)

            def vline(x_img: float, col, y0=None, y1=None):
                px, _ = to_px(x_img, 0)
                ya = 0 if y0 is None else to_px(0, y0)[1]
                yb = h - 1 if y1 is None else to_px(0, y1)[1]
                for y in range(min(ya, yb), max(ya, yb) + 1):
                    set_px(px, y, col)

            if style != "none":
                # center cross
                if style in ("default", "fine", "coarse", "cross", "thirds", "golden", "dots"):
                    cx, cy = to_px(0, 0)
                    for d in range(-14, 15):
                        set_px(cx + d, cy, border)
                        set_px(cx, cy + d, border)
                if style != "cross":
                    if style == "dots":
                        step = 50 if w <= 1200 else 80
                        for gx in self._centered_grid_coords(hw, step):
                            for gy in self._centered_grid_coords(hh, step):
                                px, py = to_px(gx, gy)
                                set_px(px, py, grid_c)
                    elif style == "thirds":
                        for t in (1 / 3, 2 / 3):
                            vline(-hw + 2 * hw * t, accent)
                            hline(-hh + 2 * hh * t, accent)
                    elif style == "golden":
                        phi = 0.6180339887
                        for t in (1 - phi, phi):
                            vline(-hw + 2 * hw * t, accent)
                            hline(-hh + 2 * hh * t, accent)
                    else:
                        if style == "fine":
                            step = 25 if w <= 1200 else 50
                        elif style == "coarse":
                            step = 100 if w <= 1200 else 200
                        else:
                            step = 50 if w <= 1200 else 100
                        for gx in self._centered_grid_coords(hw, step):
                            vline(gx, grid_c)
                        for gy in self._centered_grid_coords(hh, step):
                            hline(gy, grid_c)

        # Frame border
        border_c = (0x2E, 0x2E, 0x42)
        for x in range(w):
            set_px(x, 0, border_c)
            set_px(x, h - 1, border_c)
        for y in range(h):
            set_px(0, y, border_c)
            set_px(w - 1, y, border_c)

        # Bounding boxes
        for item in self.model.items:
            col = parse_color(item.color)
            x0, y0 = to_px(item.x_min, item.y_min)
            x1, y1 = to_px(item.x_max, item.y_max)
            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0
            # outline (2px)
            for t in range(2):
                for x in range(x0 - t, x1 + t + 1):
                    set_px(x, y0 - t, col)
                    set_px(x, y1 + t, col)
                for y in range(y0 - t, y1 + t + 1):
                    set_px(x0 - t, y, col)
                    set_px(x1 + t, y, col)
            # caption text inside box
            label = (item.label or "").strip()
            caption = (item.caption or "").strip()
            if label and caption:
                text = f"{label}: {caption}"
            else:
                text = caption or label
            if text:
                self._draw_bitmap_text(
                    pixels, w, h, x0 + 4, y0 + 4, text, col, max_width=max(8, x1 - x0 - 8)
                )

        return bytes(pixels), w, h

    def _draw_bitmap_text(self, pixels: bytearray, w: int, h: int,
                          x: int, y: int, text: str, color: Tuple[int, int, int],
                          max_width: int = 9999):
        """Draw caption text into an RGB buffer.
        Uses the built-in glyph set scaled to the active UI font size (zero-deps;
        full TrueType outlines are not available without external libraries).
        """
        # Compact font: each glyph is 5 columns x 7 rows stored as 7 rows of 5 bits
        font = _BITMAP_FONT_5X7
        # Map active UI font size → pixel scale for screenshot captions
        try:
            ui_sz = int(getattr(self, "_ui_font_size", DEFAULT_UI_FONT_SIZE) or DEFAULT_UI_FONT_SIZE)
        except Exception:
            ui_sz = DEFAULT_UI_FONT_SIZE
        # 12pt → ~2x on large canvases; grow/shrink with user font setting
        base = 2 if min(w, h) >= 768 else 1
        scale = max(1, min(8, int(round(base * (ui_sz / float(DEFAULT_UI_FONT_SIZE))))))
        cx, cy = x, y
        max_x = x + max_width
        for ch in text:
            if ch == "\n":
                cx, cy = x, cy + 8 * scale
                continue
            rows = font.get(ch) or font.get(ch.upper()) or font.get("?")
            if rows is None:
                cx += 6 * scale
                continue
            if cx + 6 * scale > max_x:
                break
            for row, bits in enumerate(rows):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        for sy in range(scale):
                            for sx in range(scale):
                                px = cx + col * scale + sx
                                py = cy + row * scale + sy
                                if 0 <= px < w and 0 <= py < h:
                                    i = (py * w + px) * 3
                                    pixels[i:i+3] = bytes(color)
            cx += 6 * scale

    def _write_png_with_text(self, path: str, rgb: bytes, width: int, height: int, text: str):
        """Write RGB PNG with a tEXt chunk embedding layout JSON (stdlib only)."""
        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        raw = bytearray()
        stride = width * 3
        for y in range(height):
            raw.append(0)  # filter: None
            raw.extend(rgb[y * stride:(y + 1) * stride])
        compressed = zlib.compress(bytes(raw), 9)

        # tEXt: keyword + null + text (latin-1/utf-8 as raw bytes)
        key = b"moss"
        val = text.encode("utf-8", errors="replace")
        # PNG tEXt is officially Latin-1; store UTF-8 bytes anyway (reader tries utf-8)
        text_chunk = key + b"\x00" + val

        png = bytearray()
        png.extend(b"\x89PNG\r\n\x1a\n")
        png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))  # 8-bit RGB
        png.extend(chunk(b"tEXt", text_chunk))
        png.extend(chunk(b"IDAT", compressed))
        png.extend(chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)

    def _set_grid_style(self, style: str):
        # Not tracked in undo / project history
        self._grid_style = style
        self._redraw_all()
        self.status.configure(text=f"Grid layout → {style}")
        try:
            self._save_cfg()
        except Exception:
            pass

    def _toggle_snap_to_grid(self):
        self._snap_to_grid = not self._snap_to_grid
        state = "On" if self._snap_to_grid else "Off"
        self.status.configure(text=f"Snap to Grid → {state}")
        try:
            self._save_cfg()
        except Exception:
            pass

    def _grid_step(self) -> float:
        """Spacing for the active uniform grid pattern."""
        style = getattr(self, "_grid_style", "default")
        w = self.model.width
        if style == "fine":
            return 25.0 if w <= 1200 else 50.0
        if style == "coarse":
            return 100.0 if w <= 1200 else 200.0
        if style == "dots":
            return 50.0 if w <= 1200 else 80.0
        # default / none / cross fallback spacing
        return 50.0 if w <= 1200 else 100.0

    def _snap_scalar(self, value: float, axis: str = "x") -> float:
        """Snap a centered coordinate to the active grid pattern."""
        if not getattr(self, "_snap_to_grid", False):
            return value
        # No grid when a background image is active — ignore snap
        if getattr(self, "_bg_rgb", None) is not None or getattr(self, "_bg_photo_orig", None) is not None:
            return value
        style = getattr(self, "_grid_style", "default")
        half = self.model.half_w if axis == "x" else self.model.half_h

        if style == "thirds":
            pts = [-half, -half / 3.0, 0.0, half / 3.0, half]
            return min(pts, key=lambda p: abs(p - value))
        if style == "golden":
            phi = 0.6180339887
            pts = sorted({
                -half,
                -half + 2 * half * (1 - phi),
                0.0,
                -half + 2 * half * phi,
                half,
            })
            return min(pts, key=lambda p: abs(p - value))
        if style == "cross":
            pts = [-half, 0.0, half]
            return min(pts, key=lambda p: abs(p - value))
        # default / fine / coarse / dots / none → uniform step from center
        step = self._grid_step()
        if step <= 0:
            return value
        return round(value / step) * step

    def _snap_item_edges(self, item, edges: str = "nsew"):
        """Snap selected edges of an item to the grid."""
        if not getattr(self, "_snap_to_grid", False):
            return
        if "n" in edges:
            item.y_min = self._snap_scalar(item.y_min, "y")
        if "s" in edges:
            item.y_max = self._snap_scalar(item.y_max, "y")
        if "w" in edges:
            item.x_min = self._snap_scalar(item.x_min, "x")
        if "e" in edges:
            item.x_max = self._snap_scalar(item.x_max, "x")
        # enforce minimum size after snap
        if item.y_max - item.y_min < MIN_BOX:
            item.y_max = item.y_min + MIN_BOX
        if item.x_max - item.x_min < MIN_BOX:
            item.x_max = item.x_min + MIN_BOX

    def _snap_item_move(self, item):
        """Snap moved box by anchoring top-left, preserving size."""
        if not getattr(self, "_snap_to_grid", False):
            return
        w = item.x_max - item.x_min
        h = item.y_max - item.y_min
        item.x_min = self._snap_scalar(item.x_min, "x")
        item.y_min = self._snap_scalar(item.y_min, "y")
        item.x_max = item.x_min + w
        item.y_max = item.y_min + h

    def _set_view_scale_pct(self, factor: float):
        # View-only; not tracked in undo
        self.scale = max(0.12, min(3.5, float(factor)))
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._bg_scale_key = None
        self._redraw_all()
        self.status.configure(text=f"Canvas scale → {int(factor * 100)}%")

    def _scale_to_fit(self):
        self._fit_view_to_canvas(allow_upscale=True)
        self._bg_scale_key = None
        self._redraw_all()
        self.status.configure(text="Canvas scaled to fit")

    def _recenter_view(self):
        self._fit_view_to_canvas(allow_upscale=True)
        self._bg_scale_key = None
        self._redraw_all()
        self.status.configure(text="Canvas recentered and scaled to fit")

    def _probe_image_size(self, path: str) -> Optional[Tuple[int, int]]:
        """Read width/height from PNG/GIF/JPEG headers without external deps."""
        try:
            with open(path, "rb") as f:
                data = f.read(256 * 1024)
        except Exception:
            return None
        # PNG
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        # GIF
        if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
            w, h = struct.unpack("<HH", data[6:10])
            return int(w), int(h)
        # JPEG SOF
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xD8, 0xD9):
                    i += 2
                    continue
                if i + 4 > len(data):
                    break
                seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    if i + 9 < len(data):
                        h, w = struct.unpack(">HH", data[i + 5:i + 9])
                        return int(w), int(h)
                i += 2 + seglen
        return None




    # ------------------------------------------------------------------
    # Font dialog
    # ------------------------------------------------------------------

    def _font_dialog(self):
        """Choose UI font family and size (saved in .bbox projects)."""
        dlg = tk.Toplevel(self)
        dlg.title("Font")
        dlg.configure(bg=BG_PANEL)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(True, True)

        s = self._ui_scale()
        pad = max(12, int(14 * s))
        list_rows = max(8, min(16, int(12 * s)))

        ttk.Label(dlg, text="Font family", style="Panel.TLabel").pack(
            anchor=tk.W, padx=pad, pady=(pad, max(4, int(4 * s)))
        )
        families = sorted(set(tkfont.families()), key=str.lower)
        fam_var = tk.StringVar(value=self._ui_font_family)
        if self._ui_font_family not in families and families:
            fam_var.set(families[0])
        list_frame = ttk.Frame(dlg, style="Panel.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=pad)
        lb = tk.Listbox(
            list_frame, height=list_rows, exportselection=False,
            bg=BG_DARK, fg=FG, selectbackground=ACCENT, selectforeground="#0f0f17",
            highlightthickness=0, relief=tk.FLAT, font=self._ui_font(0),
        )
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        for name in families:
            lb.insert(tk.END, name)
        try:
            idx = families.index(fam_var.get())
            lb.selection_set(idx)
            lb.see(idx)
        except Exception:
            if families:
                lb.selection_set(0)

        size_row = ttk.Frame(dlg, style="Panel.TFrame")
        size_row.pack(fill=tk.X, padx=pad, pady=max(8, int(10 * s)))
        ttk.Label(size_row, text="Size", style="Panel.TLabel").pack(side=tk.LEFT)
        size_var = tk.IntVar(value=int(self._ui_font_size))
        size_spin = tk.Spinbox(
            size_row, from_=8, to=28, textvariable=size_var, width=5,
            bg=BG_DARK, fg=FG, buttonbackground=BG_PANEL, relief=tk.FLAT,
            font=self._ui_font(0),
        )
        size_spin.pack(side=tk.LEFT, padx=max(6, int(8 * s)))
        preview = ttk.Label(dlg, text="The quick brown fox — 123", style="Panel.TLabel")
        preview.pack(anchor=tk.W, padx=pad, pady=(0, max(6, int(8 * s))))

        def update_preview(*_):
            sel = lb.curselection()
            family = lb.get(sel[0]) if sel else fam_var.get()
            try:
                sz = int(size_var.get())
            except Exception:
                sz = self._ui_font_size
            sz = max(8, min(28, sz))
            preview.configure(font=(family, sz))
            # Grow dialog if large preview would clip
            try:
                self._fit_dialog(dlg, min_w=400, min_h=440, pad=max(24, int(28 * (sz / float(DEFAULT_UI_FONT_SIZE)))))
            except Exception:
                pass

        lb.bind("<<ListboxSelect>>", update_preview)
        size_spin.bind("<KeyRelease>", update_preview)
        size_spin.bind("<ButtonRelease-1>", update_preview)

        btn_row = ttk.Frame(dlg, style="Panel.TFrame")
        btn_row.pack(fill=tk.X, padx=pad, pady=(max(4, int(4 * s)), pad))

        def apply_and_close():
            sel = lb.curselection()
            family = lb.get(sel[0]) if sel else fam_var.get()
            try:
                sz = int(size_var.get())
            except Exception:
                sz = DEFAULT_UI_FONT_SIZE
            self._ui_font_family = family
            self._ui_font_size = max(8, min(28, sz))
            self._apply_ui_font()
            try:
                self._save_cfg()
            except Exception:
                pass
            self.status.configure(text=f"Font → {self._ui_font_family} {self._ui_font_size}")
            dlg.destroy()

        def reset_defaults():
            self._ui_font_family = DEFAULT_UI_FONT_FAMILY
            self._ui_font_size = DEFAULT_UI_FONT_SIZE
            self._apply_ui_font()
            try:
                self._save_cfg()
            except Exception:
                pass
            self.status.configure(
                text=f"Font → {self._ui_font_family} {self._ui_font_size} (defaults)"
            )
            dlg.destroy()
            # Reopen so list selection and size field show the defaults
            self.after(30, self._font_dialog)

        ttk.Button(btn_row, text="Reset Defaults", command=reset_defaults).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Apply", style="Accent.TButton", command=apply_and_close).pack(
            side=tk.RIGHT, padx=(0, max(6, int(8 * s)))
        )
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Return>", lambda e: apply_and_close())
        update_preview()
        self._fit_dialog(dlg, min_w=400, min_h=440, pad=max(24, int(28 * s)))


    def _apply_brand_visibility(self):
        """Show/hide top-left logo and BBox Studio title (keep order before canvas size)."""
        logo = getattr(self, "logo_canvas", None)
        brand = getattr(self, "brand_label", None)
        anchor = getattr(self, "size_frame", None)
        for w in (logo, brand):
            if w is not None:
                try:
                    w.pack_forget()
                except Exception:
                    pass
        pack_kw = {"side": tk.LEFT}
        if anchor is not None:
            pack_kw["before"] = anchor
        try:
            if logo is not None and getattr(self, "_show_logo", True):
                logo.pack(padx=(10, 4), pady=6, **pack_kw)
            if brand is not None and getattr(self, "_show_brand", True):
                brand.pack(padx=(0, 16), pady=8, **pack_kw)
        except Exception:
            pass

    def _apply_ui_colors(self):
        """Apply custom UI colors (Copy, chips, Delete, brand, menus, grips)."""
        c = getattr(self, "_ui_colors", None) or {}
        style = ttk.Style(self)
        try:
            style.configure(
                "Accent.TButton",
                background=c.get("copy_bg", ACCENT),
                foreground=c.get("copy_fg", "#0f0f17"),
            )
            style.map(
                "Accent.TButton",
                background=[
                    ("active", c.get("copy_hi", "#9db4ff")),
                    ("focus", c.get("copy_bg", ACCENT)),
                ],
            )
            style.configure(
                "Danger.TButton",
                background=c.get("delete_bg", DANGER),
                foreground=c.get("delete_fg", "#0f0f17"),
            )
            try:
                db = c.get("delete_bg", DANGER)
                style.map("Danger.TButton", background=[("active", db)])
            except Exception:
                pass
            brand_fg = c.get("brand_fg", ACCENT)
            style.configure("Brand.TLabel", foreground=brand_fg, background=BG_PANEL)
            try:
                if getattr(self, "brand_label", None) is not None:
                    self.brand_label.configure(foreground=brand_fg)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._refresh_meta_chips()
        except Exception:
            pass
        try:
            self._apply_brand_visibility()
        except Exception:
            pass

    def _color_theme_dialog(self):
        """Centered popup to customize UI accent colors and brand visibility."""
        dlg = tk.Toplevel(self)
        dlg.title("UI Colors")
        dlg.configure(bg=BG_PANEL)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        s = self._ui_scale()
        pad = max(12, int(16 * s))
        c = dict(getattr(self, "_ui_colors", {}) or {})

        # Scrollable body for the longer form
        outer = ttk.Frame(dlg, style="Panel.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=BG_PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        body = ttk.Frame(canvas, style="Panel.TFrame")
        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        win = canvas.create_window((0, 0), window=body, anchor=tk.NW)
        canvas.configure(yscrollcommand=scroll.set)

        def _on_canvas_configure(event):
            canvas.itemconfigure(win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _wheel(event):
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-3, "units")
            else:
                canvas.yview_scroll(3, "units")
            return "break"

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, _wheel)

        ttk.Label(body, text="UI Colors", style="Title.TLabel").pack(
            anchor=tk.W, padx=pad, pady=(pad, max(4, int(4 * s)))
        )
        self._add_panel_divider(body, padx=pad, pady=(max(4, int(4 * s)), max(6, int(8 * s))))

        def _hex_ok(val: str) -> bool:
            return bool(re.match(r"^#[0-9a-fA-F]{6}$", (val or "").strip()))

        def section(title: str):
            ttk.Label(body, text=title, style="Panel.TLabel").pack(
                anchor=tk.W, padx=pad, pady=(max(10, int(12 * s)), max(2, int(4 * s)))
            )

        def color_row(parent, label, key):
            """Hex field styled like the right-panel Color entry (dark field + border)."""
            row = ttk.Frame(parent, style="Panel.TFrame")
            row.pack(fill=tk.X, padx=pad, pady=2)
            ttk.Label(row, text=label, style="Dim.TLabel", width=16).pack(side=tk.LEFT)
            var = tk.StringVar(value=c.get(key, "#ffffff"))

            box = tk.Frame(row, bg=BORDER, highlightthickness=0)
            box.pack(side=tk.LEFT, padx=(4, 0))
            inner = tk.Frame(box, bg=BG_DARK, highlightthickness=0)
            inner.pack(padx=1, pady=1)

            sw = tk.Canvas(
                inner, width=18, height=18, bg=BG_DARK,
                highlightthickness=1, highlightbackground=BORDER, cursor="hand2",
            )
            sw.pack(side=tk.LEFT, padx=(4, 2), pady=2)

            ent = tk.Entry(
                inner, textvariable=var, width=9,
                bg=BG_DARK, fg=FG, insertbackground=FG,
                relief=tk.FLAT, bd=0, highlightthickness=0,
                font=self._ui_font(0),
            )
            ent.pack(side=tk.LEFT, padx=(0, 4), pady=2)

            def paint(val=None):
                val = (val if val is not None else var.get()).strip()
                if _hex_ok(val):
                    sw.delete("all")
                    sw.configure(bg=val)
                    sw.create_rectangle(0, 0, 22, 22, fill=val, outline="")

            def on_key(*_):
                paint()

            def pick():
                initial = var.get().strip() if _hex_ok(var.get()) else "#888888"
                result = colorchooser.askcolor(color=initial, title=label, parent=dlg)
                if result and result[1]:
                    var.set(result[1])
                    paint(result[1])

            ent.bind("<KeyRelease>", on_key)
            sw.bind("<Button-1>", lambda e: pick())
            paint()
            return var

        # Brand / logo
        section("Top bar brand")
        vis = ttk.Frame(body, style="Panel.TFrame")
        vis.pack(fill=tk.X, padx=pad, pady=2)
        show_brand = tk.BooleanVar(value=bool(getattr(self, "_show_brand", True)))
        show_logo = tk.BooleanVar(value=bool(getattr(self, "_show_logo", True)))
        ttk.Checkbutton(vis, text="Show “BBox Studio” title", variable=show_brand).pack(
            anchor=tk.W
        )
        ttk.Checkbutton(vis, text="Show logo", variable=show_logo).pack(anchor=tk.W)
        v_brand_fg = color_row(body, "Title color", "brand_fg")

        section("Copy Prompt to Clipboard")
        v_copy_bg = color_row(body, "Background", "copy_bg")
        v_copy_hi = color_row(body, "Highlight", "copy_hi")
        v_copy_fg = color_row(body, "Text", "copy_fg")

        section("Meta chips")
        v_chip_bg = color_row(body, "Background", "chip_bg")
        v_chip_bd = color_row(body, "Border", "chip_border")
        v_chip_fg = color_row(body, "Text", "chip_fg")

        section("Delete button")
        v_del_bg = color_row(body, "Background", "delete_bg")
        v_del_fg = color_row(body, "Text", "delete_fg")

        section("Menus & lists")
        ttk.Label(
            body,
            text="Affects File menu, right-click menu, resolution list, and panel dropdowns.",
            style="Dim.TLabel",
            wraplength=max(300, int(320 * s)),
        ).pack(anchor=tk.W, padx=pad, pady=(0, 2))
        v_menu_hi = color_row(body, "Selection highlight", "menu_highlight")
        v_menu_div = color_row(body, "Divider", "menu_divider")

        section("Panel caption resize grips")
        v_grip = color_row(body, "Mouseover", "grip_hover")

        def apply_and_close():
            pairs = [
                ("brand_fg", v_brand_fg),
                ("copy_bg", v_copy_bg), ("copy_hi", v_copy_hi), ("copy_fg", v_copy_fg),
                ("chip_bg", v_chip_bg), ("chip_border", v_chip_bd), ("chip_fg", v_chip_fg),
                ("delete_bg", v_del_bg), ("delete_fg", v_del_fg),
                ("menu_highlight", v_menu_hi), ("menu_divider", v_menu_div),
                ("grip_hover", v_grip),
            ]
            for key, var in pairs:
                val = var.get().strip()
                if not _hex_ok(val):
                    messagebox.showwarning(
                        "Invalid color",
                        f"Use a hex color like #7c9cff for {key}.",
                        parent=dlg,
                    )
                    return
                self._ui_colors[key] = val
            self._show_brand = bool(show_brand.get())
            self._show_logo = bool(show_logo.get())
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass
            self._apply_ui_colors()
            try:
                self._save_cfg()
            except Exception:
                pass
            dlg.destroy()

        def reset_defaults():
            defaults = {
                "copy_bg": ACCENT,
                "copy_hi": "#9db4ff",
                "copy_fg": "#0f0f17",
                "chip_bg": CHIP_BG,
                "chip_border": CHIP_BORDER,
                "chip_fg": CHIP_FG,
                "delete_bg": DANGER,
                "delete_fg": "#0f0f17",
                "brand_fg": ACCENT,
                "menu_highlight": ACCENT,
                "menu_divider": FG_DIM,
                "grip_hover": ACCENT,
            }
            for key, val in defaults.items():
                self._ui_colors[key] = val
            self._show_brand = True
            self._show_logo = True
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass
            dlg.destroy()
            self._apply_ui_colors()
            self.after(30, self._color_theme_dialog)

        def on_close():
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass
            dlg.destroy()

        btn = ttk.Frame(dlg, style="Panel.TFrame")
        btn.pack(fill=tk.X, padx=pad, pady=(max(8, int(10 * s)), pad))
        ttk.Button(btn, text="Reset Defaults", command=reset_defaults).pack(side=tk.LEFT)
        ttk.Button(btn, text="Cancel", command=on_close).pack(side=tk.RIGHT)
        ttk.Button(btn, text="Apply", style="Accent.TButton", command=apply_and_close).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        dlg.protocol("WM_DELETE_WINDOW", on_close)
        dlg.bind("<Escape>", lambda e: on_close())
        self._fit_dialog(dlg, min_w=420, min_h=520, pad=max(20, int(24 * s)))
        try:
            dlg.update_idletasks()
            w, h = dlg.winfo_width(), dlg.winfo_height()
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            dlg.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        except Exception:
            pass
        dlg.focus_set()


    def _change_background(self):

        path = filedialog.askopenfilename(
            title="Change Background",
            filetypes=[
                ("Images", "*.png;*.gif;*.pgm;*.ppm;*.PNG;*.GIF"),
                ("PNG", "*.png;*.PNG"),
                ("GIF", "*.gif;*.GIF"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._load_background_file(path)

    def _load_background_file(self, path: str):
        """Load an image as canvas background (same as Change Background). Does not read embedded JSON."""
        try:
            self.status.configure(text="Loading background…")
            self.update_idletasks()
            size = self._probe_image_size(path)
            photo = tk.PhotoImage(file=path)
            iw, ih = photo.width(), photo.height()
            if size and size[0] > 0 and size[1] > 0:
                if abs(size[0] - iw) > 1 or abs(size[1] - ih) > 1:
                    iw, ih = size
            max_side = 4096
            if max(iw, ih) > max_side:
                messagebox.showwarning(
                    "Image too large",
                    f"Image is {iw}×{ih}. Please use an image ≤ {max_side}px on a side.",
                    parent=self,
                )
                return
            rgb = self._photo_to_rgb(photo)
            self._bg_photo_orig = photo
            self._bg_rgb = rgb
            self._bg_iw, self._bg_ih = photo.width(), photo.height()
            self._bg_photo = None
            self._bg_scale_key = None
            self._bg_path = path
            self._set_size(self._bg_iw, self._bg_ih, push=False)
            self.update_idletasks()
            self._fit_view_to_canvas(allow_upscale=True)
            self._redraw_all()
            self._push_history()
            self.status.configure(
                text=f"Background → {path}  ({self._bg_iw}×{self._bg_ih})"
            )
        except Exception as e:
            messagebox.showerror(
                "Background failed",
                "Could not load image.\n\n"
                "Tkinter supports PNG, GIF, PGM, and PPM without extra packages.\n"
                "Convert JPEG/WebP to PNG for use as a background.\n\n"
                f"Details: {e}",
                parent=self,
            )

    def _remove_background(self):
        if self._bg_photo_orig is None and not self._bg_path:
            self.status.configure(text="No background to remove")
            return
        self._bg_photo_orig = None
        self._bg_rgb = None
        self._bg_iw = self._bg_ih = 0
        self._bg_photo = None
        self._bg_scale_key = None
        self._bg_path = None
        self._redraw_all()
        self._push_history()
        self.status.configure(text="Background removed")

    def _photo_to_rgb(self, photo: "tk.PhotoImage") -> bytes:
        w, h = photo.width(), photo.height()
        out = bytearray(w * h * 3)
        i = 0
        for y in range(h):
            for x in range(w):
                c = photo.get(x, y)
                if isinstance(c, str) and c.startswith("#") and len(c) >= 7:
                    out[i] = int(c[1:3], 16)
                    out[i + 1] = int(c[3:5], 16)
                    out[i + 2] = int(c[5:7], 16)
                else:
                    if isinstance(c, (tuple, list)):
                        r, g, b = int(c[0]), int(c[1]), int(c[2])
                    else:
                        parts = str(c).replace(",", " ").split()
                        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                    out[i] = r
                    out[i + 1] = g
                    out[i + 2] = b
                i += 3
        return bytes(out)

    def _resize_rgb_nn(self, rgb: bytes, iw: int, ih: int, tw: int, th: int) -> bytes:
        tw = max(1, tw)
        th = max(1, th)
        out = bytearray(tw * th * 3)
        xmap = [min(iw - 1, (x * iw) // tw) for x in range(tw)]
        mv = memoryview(rgb)
        for y in range(th):
            sy = min(ih - 1, (y * ih) // th)
            src_row = sy * iw * 3
            dst_row = y * tw * 3
            for x, sx in enumerate(xmap):
                si = src_row + sx * 3
                di = dst_row + x * 3
                out[di:di + 3] = mv[si:si + 3]
        return bytes(out)

    def _photo_from_rgb(self, rgb: bytes, w: int, h: int) -> "tk.PhotoImage":
        header = ("P6\n%d %d\n255\n" % (w, h)).encode("ascii")
        payload = header + rgb
        try:
            return tk.PhotoImage(data=base64.b64encode(payload))
        except Exception:
            pass
        try:
            return tk.PhotoImage(data=base64.b64encode(payload).decode("ascii"))
        except Exception:
            pass
        fd, path = tempfile.mkstemp(suffix=".ppm")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            return tk.PhotoImage(file=path)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def _get_scaled_bg_photo(self, tw: Optional[int] = None, th: Optional[int] = None):
        """Scale background to on-screen size.
        Prefer fast Tk PhotoImage.zoom / subsample when the scale ratio is an
        integer (native C path, same NN-style look). Otherwise pure-Python NN.
        """
        if self._bg_rgb is None or self._bg_iw <= 0:
            return None
        if tw is None:
            tw = max(1, int(round(self.model.width * self.scale)))
        if th is None:
            th = max(1, int(round(self.model.height * self.scale)))
        tw = max(1, min(int(tw), 4096))
        th = max(1, min(int(th), 4096))
        key = (tw, th, id(self._bg_rgb))
        if self._bg_photo is not None and self._bg_scale_key == key:
            return self._bg_photo

        iw, ih = int(self._bg_iw), int(self._bg_ih)
        photo = None
        try:
            orig = self._bg_photo_orig
            # Exact size — reuse original PhotoImage
            if tw == iw and th == ih and orig is not None:
                photo = orig
            # Integer upscale: Tk zoom (C-speed)
            elif (
                orig is not None
                and tw >= iw and th >= ih
                and iw > 0 and ih > 0
                and tw % iw == 0 and th % ih == 0
            ):
                zx, zy = tw // iw, th // ih
                cand = orig.zoom(zx, zy)
                if cand.width() == tw and cand.height() == th:
                    photo = cand
            # Integer downscale: Tk subsample (C-speed)
            elif (
                orig is not None
                and iw >= tw and ih >= th
                and tw > 0 and th > 0
                and iw % tw == 0 and ih % th == 0
            ):
                sx, sy = iw // tw, ih // th
                cand = orig.subsample(sx, sy)
                if cand.width() == tw and cand.height() == th:
                    photo = cand

            # Fractional / non-integer ratio — pure-Python nearest-neighbor
            if photo is None:
                if tw == iw and th == ih:
                    scaled = self._bg_rgb
                else:
                    scaled = self._resize_rgb_nn(self._bg_rgb, iw, ih, tw, th)
                photo = self._photo_from_rgb(scaled, tw, th)

            self._bg_photo = photo
            self._bg_scale_key = key
            return photo
        except Exception:
            return self._bg_photo_orig

    def _fit_view_to_canvas(self, allow_upscale: bool = True):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.update_idletasks()
        cw = max(120, self.canvas.winfo_width() - 48)
        ch = max(120, self.canvas.winfo_height() - 48)
        sx = cw / max(1, self.model.width)
        sy = ch / max(1, self.model.height)
        s = min(sx, sy)
        if not allow_upscale:
            s = min(s, 1.3)
        self.scale = max(0.05, min(4.0, s))
        self._bg_scale_key = None

    def _apply_background_path(self, path: Optional[str]):
        if not path:
            self._bg_photo_orig = None
            self._bg_rgb = None
            self._bg_iw = self._bg_ih = 0
            self._bg_photo = None
            self._bg_scale_key = None
            self._bg_path = None
            return
        if path == self._bg_path and self._bg_rgb is not None:
            return
        try:
            photo = tk.PhotoImage(file=path)
            self._bg_photo_orig = photo
            self._bg_rgb = self._photo_to_rgb(photo)
            self._bg_iw, self._bg_ih = photo.width(), photo.height()
            self._bg_photo = None
            self._bg_scale_key = None
            self._bg_path = path
        except Exception:
            self._bg_photo_orig = None
            self._bg_rgb = None
            self._bg_iw = self._bg_ih = 0
            self._bg_photo = None
            self._bg_scale_key = None
            self._bg_path = None


    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _bind_events(self):
        def _safe(widget, seq, handler):
            try:
                widget.bind(seq, handler)
            except Exception:
                pass

        _safe(self.canvas, "<Configure>", lambda e: self._on_canvas_resize())
        _safe(self.canvas, "<ButtonPress-1>", self._on_press)
        _safe(self.canvas, "<B1-Motion>", self._on_drag)
        _safe(self.canvas, "<ButtonRelease-1>", self._on_release)
        _safe(self.canvas, "<Double-Button-1>", self._on_double_click)
        _safe(self.canvas, "<Motion>", self._on_motion)
        _safe(self.canvas, "<MouseWheel>", self._on_wheel)
        _safe(self.canvas, "<Button-4>", lambda e: self._zoom(1.1, e.x, e.y))
        _safe(self.canvas, "<Button-5>", lambda e: self._zoom(0.9, e.x, e.y))
        # Middle-mouse pan
        _safe(self.canvas, "<ButtonPress-2>", self._on_pan_start)
        _safe(self.canvas, "<B2-Motion>", self._on_pan_move)
        _safe(self.canvas, "<ButtonRelease-2>", self._on_pan_end)
        # Right-click context menu (+ ctrl-click fallback)
        _safe(self.canvas, "<ButtonPress-3>", self._on_canvas_menu)
        _safe(self.canvas, "<Control-Button-1>", self._on_canvas_menu)
        _safe(self, "<Delete>", lambda e: self._delete_selected())
        _safe(self, "<Control-c>", lambda e: self._copy_json())
        _safe(self, "<Control-z>", lambda e: self._undo())
        _safe(self, "<Control-y>", lambda e: self._redo())
        _safe(self, "<Control-Z>", lambda e: self._undo())
        _safe(self, "<Control-Y>", lambda e: self._redo())
        _safe(self, "<Control-s>", lambda e: self._save_project())
        _safe(self, "<Control-o>", lambda e: self._load_project())
        _safe(self, "<Escape>", lambda e: self._finish_inline() or self._deselect())
        _safe(self, "<Control-r>", lambda e: self._reset())
        _safe(self, "<Key-plus>", lambda e: self._zoom(1.1))
        _safe(self, "<Key-minus>", lambda e: self._zoom(0.9))
        _safe(self, "<Key-equal>", lambda e: self._zoom(1.1))
        # Single binding only — duplicate self+canvas handlers skipped every other box
        _safe(self, "<Left>", lambda e: self._cycle_selection(-1))
        _safe(self, "<Right>", lambda e: self._cycle_selection(1))

    def _on_canvas_resize(self, *_):
        """On window/canvas resize, scale the view to fit (debounced while dragging)."""
        if self._resize_fit_after is not None:
            try:
                self.after_cancel(self._resize_fit_after)
            except Exception:
                pass
        # Debounce so continuous drag-resize doesn't thrash; still feels live
        self._resize_fit_after = self.after(50, self._apply_resize_fit)

    def _apply_resize_fit(self):
        self._resize_fit_after = None
        if self.canvas.winfo_width() < 40 or self.canvas.winfo_height() < 40:
            return
        self._fit_view_to_canvas(allow_upscale=True)
        self._bg_scale_key = None
        self._redraw_all()

    def _hit_test(self, cx: float, cy: float) -> Tuple[Optional[BBoxItem], Optional[str]]:
        if self.selected:
            x0, y0 = self._img_to_canvas(self.selected.x_min, self.selected.y_min)
            x1, y1 = self._img_to_canvas(self.selected.x_max, self.selected.y_max)
            cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
            hs = HANDLE_SIZE + 5
            handles = {
                "nw": (x0, y0), "n": (cxm, y0), "ne": (x1, y0),
                "w": (x0, cym),               "e": (x1, cym),
                "sw": (x0, y1), "s": (cxm, y1), "se": (x1, y1),
            }
            for name, (hx, hy) in handles.items():
                if abs(cx - hx) <= hs and abs(cy - hy) <= hs:
                    return self.selected, name

        for item in reversed(self.model.items):
            x0, y0 = self._img_to_canvas(item.x_min, item.y_min)
            x1, y1 = self._img_to_canvas(item.x_max, item.y_max)
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return item, None
        return None, None

    def _on_press(self, event):
        self._finish_inline()
        # Canvas click takes focus back so Left/Right cycle works after editing fields
        try:
            self.canvas.focus_set()
        except Exception:
            pass
        item, handle = self._hit_test(event.x, event.y)
        self.drag_start = (event.x, event.y)
        self._aspect_ratio_cache = None

        if handle:
            self.selected = item
            if item and item.locked:
                self.drag_mode = None
                self._redraw_all()
                self._update_item_panel()
                self.status.configure(text="Box is locked — unlock to resize")
                return
            self.drag_mode = "resize"
            self.resize_handle = handle
            if item and item.aspect_locked and item.height() > 0:
                self._aspect_ratio_cache = item.width() / item.height()
            self._redraw_all()
            self._update_item_panel()
            return

        if item:
            self.selected = item
            if item.locked:
                self.drag_mode = None
                self._redraw_all()
                self._update_item_panel()
                self.status.configure(text="Box is locked — unlock to move")
                return
            self.drag_mode = "move"
            self._redraw_all()
            self._update_item_panel()
            return

        # empty canvas click — deselect and start rubber-band create
        self.selected = None
        self._clear_item_panel()
        self.drag_mode = "create"
        ix, iy = self._canvas_to_img(event.x, event.y)
        self.create_start = (ix, iy)
        # Redraw first (delete("all") would wipe the preview), then draw temp box
        self._redraw_all()
        # Hide crosshair while drawing so it doesn't blend over the edge
        self.canvas.configure(cursor="none")
        # Color chosen now so the rubber-band matches the final box
        self._create_color = self._next_color()
        self._temp_rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=self._create_color, width=2, tags="temp",
        )

    def _on_drag(self, event):
        if self.drag_mode == "create":
            if self._temp_rect is not None:
                try:
                    self.canvas.coords(
                        self._temp_rect,
                        self.drag_start[0], self.drag_start[1],
                        event.x, event.y,
                    )
                    self.canvas.tag_raise(self._temp_rect)
                except Exception:
                    # Recreate if the item was lost
                    self._temp_rect = self.canvas.create_rectangle(
                        self.drag_start[0], self.drag_start[1], event.x, event.y,
                        outline=self._create_color or ACCENT, width=2, tags="temp",
                    )
            return

        if not self.selected or self.selected.locked:
            return

        dx = (event.x - self.drag_start[0]) / self.scale
        dy = (event.y - self.drag_start[1]) / self.scale
        self.drag_start = (event.x, event.y)

        if self.drag_mode == "move":
            self.selected.x_min += dx
            self.selected.x_max += dx
            self.selected.y_min += dy
            self.selected.y_max += dy
            self.selected.clamp(self.model.half_w, self.model.half_h)
            self._redraw_all()
            self._update_json()
            return

        if self.drag_mode == "resize" and self.resize_handle:
            h = self.resize_handle
            it = self.selected
            if "n" in h:
                it.y_min += dy
            if "s" in h:
                it.y_max += dy
            if "w" in h:
                it.x_min += dx
            if "e" in h:
                it.x_max += dx
            if it.y_max - it.y_min < MIN_BOX:
                if "n" in h:
                    it.y_min = it.y_max - MIN_BOX
                else:
                    it.y_max = it.y_min + MIN_BOX
            if it.x_max - it.x_min < MIN_BOX:
                if "w" in h:
                    it.x_min = it.x_max - MIN_BOX
                else:
                    it.x_max = it.x_min + MIN_BOX
            # Aspect ratio lock
            if it.aspect_locked and self._aspect_ratio_cache:
                ar = self._aspect_ratio_cache
                bw = it.x_max - it.x_min
                bh = it.y_max - it.y_min
                if abs(dx) >= abs(dy):
                    # width drives height
                    new_h = max(MIN_BOX, bw / ar)
                    if "n" in h and "s" not in h:
                        it.y_min = it.y_max - new_h
                    else:
                        it.y_max = it.y_min + new_h
                else:
                    new_w = max(MIN_BOX, bh * ar)
                    if "w" in h and "e" not in h:
                        it.x_min = it.x_max - new_w
                    else:
                        it.x_max = it.x_min + new_w
            it.clamp(self.model.half_w, self.model.half_h)
            self._redraw_all()
            self._update_json()

    def _on_release(self, event):
        if self.drag_mode == "create":
            self.canvas.delete("temp")
            ix0, iy0 = self.create_start
            ix1, iy1 = self._canvas_to_img(event.x, event.y)
            x_min, x_max = min(ix0, ix1), max(ix0, ix1)
            y_min, y_max = min(iy0, iy1), max(iy0, iy1)
            if x_max - x_min < MIN_BOX or y_max - y_min < MIN_BOX:
                # cancelled create — free the reserved color
                if self._create_color and self._create_color in self._used_colors:
                    self._used_colors.discard(self._create_color)
                self._create_color = None
                self.drag_mode = None
                try:
                    self.canvas.configure(cursor="crosshair")
                except Exception:
                    pass
                return
            color = self._create_color or self._next_color()
            item = BBoxItem(
                label="object",
                caption="",
                y_min=y_min, x_min=x_min, y_max=y_max, x_max=x_max,
                color=color,
            )
            self._snap_item_edges(item, edges="nsew")
            item.clamp(self.model.half_w, self.model.half_h)
            self.model.items.append(item)
            self.selected = item
            self._redraw_all()
            self._update_json()
            self._push_history()
            self._refresh_status(cursor=self._canvas_to_img(event.x, event.y))
        elif self.drag_mode in ("move", "resize"):
            if self.selected and not self.selected.locked:
                if self.drag_mode == "move":
                    self._snap_item_move(self.selected)
                elif self.drag_mode == "resize":
                    edges = self.resize_handle or "nsew"
                    self._snap_item_edges(self.selected, edges=edges)
                self.selected.clamp(self.model.half_w, self.model.half_h)
                self._redraw_all()
                self._update_json()
            self._push_history()
        self.drag_mode = None
        self.resize_handle = None
        self._aspect_ratio_cache = None
        self._create_color = None
        try:
            self.canvas.configure(cursor="crosshair")
        except Exception:
            pass

    def _on_double_click(self, event):
        item, _ = self._hit_test(event.x, event.y)
        if not item:
            return
        self.selected = item
        self._redraw_all()
        self._start_inline_edit(item)

    def _start_inline_edit(self, item: BBoxItem):
        self._finish_inline()
        x0, y0 = self._img_to_canvas(item.x_min, item.y_min)
        x1, y1 = self._img_to_canvas(item.x_max, item.y_max)
        w = max(80, x1 - x0 - 8)
        h = max(22, int(round(24 * self._ui_scale())))

        self._inline_entry = tk.Entry(
            self.canvas,
            bg="#1a1a26", fg=item.color, insertbackground=item.color,
            relief=tk.FLAT, font=self._ui_font(0),
            highlightthickness=1, highlightbackground=item.color,
        )
        self._inline_entry.insert(0, item.caption)
        self._inline_entry.select_range(0, tk.END)
        self._inline_entry.focus_set()
        self._inline_window = self.canvas.create_window(
            x0 + 4, y0 + 4, anchor=tk.NW, window=self._inline_entry, width=w, height=h,
        )
        self._inline_item = item
        self._inline_entry.bind("<Return>", lambda e: self._finish_inline())
        self._inline_entry.bind("<Escape>", lambda e: self._finish_inline(cancel=True))
        self._inline_entry.bind("<FocusOut>", lambda e: self._finish_inline())

    def _finish_inline(self, cancel: bool = False):
        if not self._inline_entry:
            return
        if not cancel and self._inline_item:
            new_cap = self._inline_entry.get()
            self._inline_item.caption = new_cap
            # also push to right panel
            self._updating_ui = True
            self.item_caption.delete("1.0", tk.END)
            self.item_caption.insert("1.0", new_cap)
            self._updating_ui = False
            self._update_json()
            self._push_history()
        self.canvas.delete(self._inline_window)
        self._inline_entry.destroy()
        self._inline_entry = None
        self._inline_item = None
        self._redraw_all()

    def _on_motion(self, event):
        # While dragging/creating, leave cursor alone (prevents edge color flicker)
        if not self.drag_mode:
            item, handle = self._hit_test(event.x, event.y)
            if handle:
                cursors = {
                    "nw": "top_left_corner", "ne": "top_right_corner",
                    "sw": "bottom_left_corner", "se": "bottom_right_corner",
                    "n": "top_side", "s": "bottom_side",
                    "w": "left_side", "e": "right_side",
                }
                self.canvas.configure(cursor=cursors.get(handle, "crosshair"))
            elif item:
                self.canvas.configure(cursor="fleur")
            else:
                self.canvas.configure(cursor="crosshair")

        ix, iy = self._canvas_to_img(event.x, event.y)
        self._refresh_status(cursor=(ix, iy))


    def _box_count_label(self) -> str:
        n = len(self.model.items)
        if self.selected is not None:
            try:
                idx = self.model.items.index(self.selected) + 1
                return f"Box {idx}/{n}"
            except ValueError:
                pass
        if n == 0:
            return "No boxes"
        if n == 1:
            return "1 box"
        return f"{n} boxes"

    def _refresh_status(self, cursor: Optional[Tuple[float, float]] = None, message: Optional[str] = None):
        """Status bar: box count · coordinates · scale (normal display)."""
        if not hasattr(self, "status"):
            return
        if cursor is not None:
            self._last_cursor = cursor
        else:
            cursor = getattr(self, "_last_cursor", None)
        parts = [self._box_count_label()]
        if cursor is not None:
            parts.append(f"x={cursor[0]:.0f} y={cursor[1]:.0f}")
        parts.append(f"scale {self.scale:.2f}×")
        body = "  ·  ".join(parts)
        if message:
            body = f"{message}  ·  {body}"
        self.status.configure(text=body)

    def _on_wheel(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self._zoom(factor, event.x, event.y)

    def _zoom(self, factor: float, cx: Optional[float] = None, cy: Optional[float] = None):
        if cx is not None and cy is not None:
            ix, iy = self._canvas_to_img(cx, cy)
        else:
            ix = iy = 0.0
        self.scale = max(0.08, min(4.0, self.scale * factor))
        if cx is not None and cy is not None:
            self.offset_x = cx - self.canvas.winfo_width() / 2 - ix * self.scale
            self.offset_y = cy - self.canvas.winfo_height() / 2 - iy * self.scale
        self._bg_scale_key = None
        self._redraw_all()

    # ------------------------------------------------------------------
    # Colors
    # ------------------------------------------------------------------

    def _next_color(self) -> str:
        available = [c for c in PALETTE if c not in self._used_colors]
        if not available:
            self._used_colors.clear()
            available = PALETTE[:]
        color = random.choice(available)
        self._used_colors.add(color)
        return color

    def _sync_pick_btn(self):
        """Color swatch: hand cursor when a box is selected; inactive otherwise."""
        sw = getattr(self, "color_preview", None)
        if sw is None:
            return
        try:
            if self.selected is not None:
                sw.configure(cursor="hand2")
            else:
                sw.configure(cursor="arrow")
        except Exception:
            pass

    def _pick_color(self):
        """Centered color picker (palette + hex). Avoids off-center system dialogs."""
        if not self.selected:
            return
        initial = self.selected.color or "#7c9cff"

        dlg = tk.Toplevel(self)
        dlg.title("Box Color")
        dlg.configure(bg=BG_PANEL)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(True, True)

        s = self._ui_scale()
        pad = max(10, int(12 * s))
        chosen = {"hex": initial}

        ttk.Label(dlg, text="Palette", style="Panel.TLabel").pack(anchor=tk.W, padx=pad, pady=(pad, max(4, int(4 * s))))
        grid = ttk.Frame(dlg, style="Panel.TFrame")
        grid.pack(padx=pad, pady=(0, max(6, int(8 * s))))

        sw = max(22, int(26 * s))
        preview = tk.Canvas(
            dlg, width=max(120, int(140 * s)), height=max(28, int(32 * s)),
            bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER,
        )

        def set_color(hex_color: str):
            if not re.match(r"^#[0-9a-fA-F]{6}$", hex_color or ""):
                return
            chosen["hex"] = hex_color
            hex_var.set(hex_color)
            try:
                preview.delete("all")
                preview.create_rectangle(0, 0, preview.winfo_reqwidth() or 140, preview.winfo_reqheight() or 32, fill=hex_color, outline="")
            except Exception:
                pass

        cols = 8
        for i, col in enumerate(PALETTE):
            r, c = divmod(i, cols)
            cell = tk.Canvas(
                grid, width=sw, height=sw, bg=col,
                highlightthickness=1, highlightbackground=BORDER, cursor="hand2",
            )
            cell.grid(row=r, column=c, padx=2, pady=2)
            cell.bind("<Button-1>", lambda e, hc=col: set_color(hc))

        # Hex label + field centered
        hex_block = ttk.Frame(dlg, style="Panel.TFrame")
        hex_block.pack(fill=tk.X, padx=pad, pady=(max(2, int(2 * s)), max(6, int(8 * s))))
        ttk.Label(hex_block, text="Hex", style="Panel.TLabel").pack()
        hex_var = tk.StringVar(value=initial)
        hex_entry = ttk.Entry(hex_block, textvariable=hex_var, width=12, justify=tk.CENTER)
        hex_entry.pack(pady=(max(2, int(2 * s)), 0))
        try:
            hex_entry.configure(font=self._ui_font(0))
        except Exception:
            pass

        def on_hex(*_):
            val = hex_var.get().strip()
            if re.match(r"^#[0-9a-fA-F]{6}$", val):
                set_color(val)

        hex_entry.bind("<KeyRelease>", on_hex)
        hex_entry.bind("<Return>", on_hex)

        preview.pack(padx=pad, pady=(0, max(6, int(8 * s))))
        set_color(initial)

        def more_system():
            # Optional system chooser; still parented to this dialog
            result = colorchooser.askcolor(color=chosen["hex"], title="Box Color", parent=dlg)
            if result and result[1]:
                set_color(result[1])

        def apply_and_close():
            val = chosen["hex"]
            if not re.match(r"^#[0-9a-fA-F]{6}$", val):
                val = hex_var.get().strip()
            if not re.match(r"^#[0-9a-fA-F]{6}$", val):
                messagebox.showwarning("Invalid color", "Use a hex color like #7c9cff.", parent=dlg)
                return
            self.selected.color = val
            self.color_var.set(val)
            self._update_color_preview(val)
            self._redraw_all()
            self._update_json()
            self._push_history()
            dlg.destroy()

        # Evenly spaced bottom buttons: System… | Apply | Cancel
        btn = ttk.Frame(dlg, style="Panel.TFrame")
        btn.pack(fill=tk.X, padx=pad, pady=(0, pad))
        btn.columnconfigure(0, weight=1, uniform="colorbtns")
        btn.columnconfigure(1, weight=1, uniform="colorbtns")
        btn.columnconfigure(2, weight=1, uniform="colorbtns")
        ttk.Button(btn, text="System…", command=more_system).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(btn, text="Apply", style="Accent.TButton", command=apply_and_close).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(btn, text="Cancel", command=dlg.destroy).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )

        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Return>", lambda e: apply_and_close())
        self._fit_dialog(dlg, min_w=320, min_h=280, pad=max(20, int(24 * s)))
        # Center on the screen (not only over the main window)
        try:
            dlg.update_idletasks()
            w, h = dlg.winfo_width(), dlg.winfo_height()
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            dlg.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        hex_entry.focus_set()

    def _on_color_entry(self, *_):
        if self._updating_ui or not self.selected:
            return
        val = self.color_var.get().strip()
        if re.match(r"^#[0-9a-fA-F]{6}$", val):
            self.selected.color = val
            self._update_color_preview(val)
            self._redraw_all()

    def _update_color_preview(self, color: str = None):
        """Fill swatch with box color, or caption-field background when nothing selected."""
        if not getattr(self, "color_preview", None):
            return
        if color is None or not self.selected:
            fill = BG_DARK  # same as Caption text fields
        else:
            fill = color
        self.color_preview.delete("all")
        self.color_preview.configure(bg=fill)
        self.color_preview.create_rectangle(0, 0, 28, 28, fill=fill, outline="")

    # ------------------------------------------------------------------
    # Item operations
    # ------------------------------------------------------------------

    def _add_item(self, label: str):
        w, h = 220, 160
        n = len(self.model.items)
        item = BBoxItem(
            label=label,
            caption="",
            text="",
            y_min=-h / 2 + (n % 4) * 28,
            x_min=-w / 2 + (n % 5) * 28,
            y_max=h / 2 + (n % 4) * 28,
            x_max=w / 2 + (n % 5) * 28,
            color=self._next_color(),
        )
        item.clamp(self.model.half_w, self.model.half_h)
        self.model.items.append(item)
        self.selected = item
        self._redraw_all()
        self._update_json()
        self._push_history()
        self.status.configure(text=f"Added {label} box")

    def _delete_selected(self):
        if not self.selected:
            return
        self.model.items = [i for i in self.model.items if i is not self.selected]
        self.selected = None
        self._redraw_all()
        self._update_json()
        self._clear_item_panel()
        self._push_history()

    def _duplicate_selected(self):
        if not self.selected:
            return
        src = self.selected
        new = BBoxItem(
            label=src.label,
            caption=src.caption,
            text=src.text,
            y_min=src.y_min + 24,
            x_min=src.x_min + 24,
            y_max=src.y_max + 24,
            x_max=src.x_max + 24,
            color=self._next_color(),
        )
        new.clamp(self.model.half_w, self.model.half_h)
        self.model.items.append(new)
        self.selected = new
        self._redraw_all()
        self._update_json()
        self._push_history()

    def _bring_front(self):
        if not self.selected:
            return
        self.model.items = [i for i in self.model.items if i is not self.selected]
        self.model.items.append(self.selected)
        self._redraw_all()
        self._update_json()
        self._push_history()

    def _cycle_selection(self, direction: int):
        """Left/Right arrow: cycle selected bounding box. Skip when typing in fields."""
        focus = self.focus_get()
        if focus is not None:
            if focus is getattr(self, "_inline_entry", None):
                return
            cls = focus.winfo_class()
            if cls in ("Text", "TEntry", "Entry", "TCombobox", "Combobox"):
                return
        items = self.model.items
        n = len(items)
        if n == 0:
            return
        idx = 0
        if self.selected is not None:
            for i, it in enumerate(items):
                if it is self.selected:
                    idx = i
                    break
            else:
                # selected not in list — start from end/start by direction
                idx = 0 if direction >= 0 else n - 1
                idx = (idx - direction) % n  # so + direction lands on 0
        idx = (idx + direction) % n
        self.selected = items[idx]
        self._redraw_all()
        self._update_item_panel()
        # Update box count immediately (no "Selected · label" message)
        self._refresh_status()

    def _deselect(self):
        self.selected = None
        self._redraw_all()
        self._clear_item_panel()

    def _reset(self):
        if self.model.items and not messagebox.askyesno(
            "Reset", "Clear all boxes and restore defaults?", parent=self
        ):
            return
        self.model.reset()
        self.selected = None
        self._used_colors.clear()
        self.width_var.set(str(DEFAULT_W))
        self.height_var.set(str(DEFAULT_H))
        if hasattr(self, "size_var"):
            self.size_var.set(f"{DEFAULT_W}×{DEFAULT_H}")
        self.caption_text.delete("1.0", tk.END)
        self.caption_text.insert("1.0", self.model.caption)
        self._sync_meta_entry_from_model()
        self.canvas_type_var.set(self.model.canvas_type)
        self._clear_item_panel()
        self._center_canvas()
        self._redraw_all()
        self._update_json()
        self._history.clear()
        self._hist_index = -1
        self._push_history()
        self.status.configure(text="Reset to defaults")

    # ------------------------------------------------------------------
    # Property panel
    # ------------------------------------------------------------------

    def _set_text_if_changed(self, widget: tk.Text, new_text: str):
        """Update a Text widget only when content differs; preserve caret/selection."""
        try:
            current = widget.get("1.0", "end-1c")
        except Exception:
            current = None
        if current == new_text:
            return
        try:
            insert = widget.index(tk.INSERT)
            sel = None
            if widget.tag_ranges(tk.SEL):
                sel = (widget.index(tk.SEL_FIRST), widget.index(tk.SEL_LAST))
        except Exception:
            insert, sel = "end", None
        widget.delete("1.0", tk.END)
        widget.insert("1.0", new_text)
        try:
            # Clamp caret to valid range after shorter text (e.g. backspace)
            widget.mark_set(tk.INSERT, insert)
            widget.see(tk.INSERT)
            if sel is not None:
                widget.tag_add(tk.SEL, sel[0], sel[1])
        except Exception:
            pass

    def _update_item_panel(self):
        if not self.selected:
            self._clear_item_panel()
            return
        self._updating_ui = True
        self.label_var.set(self.selected.label)
        self.color_var.set(self.selected.color)
        self._update_color_preview(self.selected.color)
        # Only rewrite fields when text actually changed — keeps caret while typing
        self._set_text_if_changed(self.item_caption, self.selected.caption)
        self._set_text_if_changed(self.item_text, self.selected.text)
        if hasattr(self, "lock_var"):
            self.lock_var.set(bool(self.selected.locked))
        if hasattr(self, "aspect_var"):
            self.aspect_var.set(bool(self.selected.aspect_locked))
        lock_note = "  🔒 locked" if self.selected.locked else ""
        self.coord_label.configure(
            text=f"[{self.selected.y_min:.0f}, {self.selected.x_min:.0f}, "
                 f"{self.selected.y_max:.0f}, {self.selected.x_max:.0f}]  "
                 f"({self.selected.width():.0f}×{self.selected.height():.0f}){lock_note}",
            bg=BG_DARK,  # dark text plate only while a box is selected
            fg=FG_DIM,
        )
        self._sync_pick_btn()
        self._updating_ui = False

    def _clear_item_panel(self):
        self._updating_ui = True
        self.label_var.set("object")
        self.color_var.set("")
        self._update_color_preview(None)
        self.item_caption.delete("1.0", tk.END)
        self.item_text.delete("1.0", tk.END)
        if hasattr(self, "lock_var"):
            self.lock_var.set(False)
        if hasattr(self, "aspect_var"):
            self.aspect_var.set(False)
        self.coord_label.configure(text="", bg=BG_PANEL, fg=FG_DIM)
        self._sync_pick_btn()
        self._updating_ui = False

    def _on_lock_toggle(self):
        if self._updating_ui or not self.selected:
            return
        self.selected.locked = bool(self.lock_var.get())
        self._redraw_all()
        self._update_item_panel()
        self._push_history()

    def _on_aspect_toggle(self):
        if self._updating_ui or not self.selected:
            return
        self.selected.aspect_locked = bool(self.aspect_var.get())
        self._push_history()

    def _on_label_change(self, *_):
        if self._updating_ui or not self.selected:
            return
        self.selected.label = self.label_var.get()
        self._redraw_all()
        self._update_json()
        self._push_history()

    def _on_item_caption_change(self, *_):
        if self._updating_ui or not self.selected:
            return
        self.selected.caption = self.item_caption.get("1.0", "end-1c")
        self._redraw_all()
        self._update_json()

    def _on_item_text_change(self, *_):
        if self._updating_ui or not self.selected:
            return
        self.selected.text = self.item_text.get("1.0", "end-1c")
        self._redraw_all()
        self._update_json()

    def _on_caption_change(self, *_):
        self.model.caption = self.caption_text.get("1.0", "end-1c")
        self._update_json()

    def _on_meta_chips_configure(self, event=None):
        """Keep scrollregion matched to chip content width (do not stretch to canvas)."""
        try:
            self.meta_chips.update_idletasks()
            req_w = max(self.meta_chips.winfo_reqwidth(), 1)
            req_h = max(self.meta_chips.winfo_reqheight(), 28)
            self.meta_chip_canvas.itemconfigure(self._meta_chips_win, width=req_w, height=req_h)
            self.meta_chip_canvas.configure(
                scrollregion=(0, 0, req_w, req_h),
                height=req_h,
            )
        except Exception:
            pass

    def _on_meta_chip_canvas_configure(self, event=None):
        # Viewport size changed — refresh scrollregion only
        try:
            self._on_meta_chips_configure()
        except Exception:
            pass

    def _on_meta_chips_wheel(self, event):
        try:
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                steps = -3
            else:
                steps = 3
            self.meta_chip_canvas.xview_scroll(steps, "units")
        except Exception:
            pass
        return "break"

    def _bind_meta_chip_wheel(self, widget):
        for seq in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, self._on_meta_chips_wheel)
        for child in widget.winfo_children():
            self._bind_meta_chip_wheel(child)

    def _refresh_meta_chips(self):
        box = getattr(self, "meta_chips", None)
        if box is None:
            return
        for child in list(box.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        tags = [str(t).strip() for t in (self.model.meta or []) if str(t).strip()]
        self.model.meta = list(tags)
        if not tags:
            tk.Label(
                box, text="No tags", bg=BG_PANEL, fg=FG_DIM,
                font=self._ui_font(-1), padx=4,
            ).pack(side=tk.LEFT)
        for tag in tags:
            cbg = self._ui_colors.get("chip_bg", CHIP_BG)
            cbd = self._ui_colors.get("chip_border", CHIP_BORDER)
            cfg = self._ui_colors.get("chip_fg", CHIP_FG)
            chip = tk.Frame(box, bg=cbd, highlightthickness=0)
            chip.pack(side=tk.LEFT, padx=(0, 4), pady=1)
            inner = tk.Frame(chip, bg=cbg, highlightthickness=0)
            inner.pack(padx=1, pady=1)
            tk.Label(
                inner, text=tag, bg=cbg, fg=cfg,
                font=self._ui_font(-1), padx=6, pady=1,
            ).pack(side=tk.LEFT)
            x_lbl = tk.Label(
                inner, text="×", bg=cbg, fg=CHIP_FG_DIM,
                font=self._ui_font(0), padx=4, cursor="hand2",
            )
            x_lbl.pack(side=tk.LEFT)
            x_lbl.bind("<ButtonRelease-1>", lambda e, t=tag: self._remove_meta_tag(t))
            x_lbl.bind("<Enter>", lambda e, w=x_lbl: w.configure(fg="#ff8a8a"))
            x_lbl.bind("<Leave>", lambda e, w=x_lbl: w.configure(fg=CHIP_FG_DIM))
        try:
            box.update_idletasks()
            self._on_meta_chips_configure()
            self._bind_meta_chip_wheel(box)
            # Show the newest chips
            self.meta_chip_canvas.xview_moveto(1.0)
        except Exception:
            pass

    def _ensure_meta_list_tag(self, tag: str):
        """Add tag to the Meta dropdown list + meta.txt if not already present."""
        tag = str(tag).strip()
        if not tag:
            return
        lst = getattr(self, "_meta_list", None)
        if lst is None:
            self._meta_list = []
            lst = self._meta_list
        if tag not in lst:
            lst.append(tag)
            try:
                self._save_meta_txt()
            except Exception:
                pass

    def _add_meta_tag(self, tag: str):
        tag = (tag or "").strip().strip(",")
        if not tag:
            return
        if tag in META_MAP:
            for t in META_MAP[tag]:
                self._ensure_meta_list_tag(t)
                if t not in self.model.meta:
                    self.model.meta.append(t)
        else:
            self._ensure_meta_list_tag(tag)
            if tag not in self.model.meta:
                self.model.meta.append(tag)
        self._refresh_meta_chips()
        self._update_json()

    def _remove_meta_tag(self, tag: str):
        tag = str(tag)
        self.model.meta = [t for t in list(self.model.meta) if str(t) != tag]
        # Empty is allowed — no forced default tag
        self._refresh_meta_chips()
        self._update_json()

    def _add_meta_tags(self, tags):
        for t in tags:
            t = str(t)
            if t not in self.model.meta:
                self.model.meta.append(t)
        self._refresh_meta_chips()
        self._update_json()

    def _toggle_meta_tag(self, tag: str):
        tag = str(tag)
        if tag in self.model.meta:
            self._remove_meta_tag(tag)
        else:
            self._add_meta_tag(tag)

    def _on_meta_type_key(self, event=None):
        try:
            raw = self.meta_entry.get()
        except Exception:
            return
        if not raw.endswith(","):
            return
        parts = [p.strip() for p in raw[:-1].split(",") if p.strip()]
        for p in parts:
            self._add_meta_tag(p)
        try:
            self.meta_entry.delete(0, tk.END)
        except Exception:
            pass

    def _on_meta_type_commit(self, event=None):
        try:
            raw = self.meta_entry.get().strip()
        except Exception:
            return "break"
        if not raw:
            return "break"
        parts = [p.strip().strip(",") for p in raw.split(",") if p.strip().strip(",")]
        for p in parts:
            self._add_meta_tag(p)
        try:
            self.meta_entry.delete(0, tk.END)
        except Exception:
            pass
        return "break"

    def _on_meta_picker_click(self, event=None):
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "meta":
            closer = getattr(self, "_list_popup_close", None)
            if callable(closer):
                closer()
            return "break"
        self.after(1, self._open_meta_picker)
        return "break"

    def _hide_or_remove_meta_tag(self, tag: str, builtin: bool = False):
        """Remove tag from Meta dropdown list and meta.txt (builtin flag ignored)."""
        tag = str(tag).strip()
        if not tag:
            return
        lst = list(getattr(self, "_meta_list", []) or [])
        self._meta_list = [t for t in lst if str(t) != tag]
        if tag in (self.model.meta or []):
            self.model.meta = [t for t in list(self.model.meta) if str(t) != tag]
        try:
            self._save_meta_txt()
        except Exception:
            pass
        try:
            self._refresh_meta_chips()
            self._update_json()
        except Exception:
            pass
        closer = getattr(self, "_list_popup_close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        self.after(30, self._open_meta_picker)
        try:
            self.status.configure(text=f"Removed meta tag → {tag}")
        except Exception:
            pass

    def _open_meta_picker(self, event=None):
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "meta":
            return
        # Refresh from meta.txt so external edits (e.g. Notepad) appear immediately
        try:
            self._load_meta_txt()
        except Exception:
            pass
        try:
            self.meta_box.update_idletasks()
            x = self.meta_box.winfo_rootx()
            y = self.meta_box.winfo_rooty() + self.meta_box.winfo_height()
            width_px = int(self.meta_box.winfo_width())
        except Exception:
            x, y, width_px = self.winfo_pointerx(), self.winfo_pointery(), None
        entries = []
        current = [str(t) for t in (self.model.meta or [])]
        current_set = set(current)
        meta_list = [str(t).strip() for t in (getattr(self, "_meta_list", []) or []) if str(t).strip()]
        removable = {}
        for tag in meta_list:
            mark = "✓ " if tag in current_set else "    "
            idx = len(entries)
            entries.append((f"{mark}{tag}", lambda tag=tag: self._toggle_meta_tag(tag)))
            removable[idx] = tag
        # Ensure any active chips not in the file still appear (and get saved)
        for tag in current:
            if tag and tag not in meta_list:
                mark = "✓ "
                idx = len(entries)
                entries.append((f"{mark}{tag}", lambda tag=tag: self._toggle_meta_tag(tag)))
                removable[idx] = tag
                self._ensure_meta_list_tag(tag)
        min_rows = max(1, min(28, len(entries) + 2))
        self._open_list_popup(
            x, y, entries, width_px=width_px, kind="meta", min_rows=min_rows,
            removable=removable,
        )

    def _on_meta_change(self, *_):
        """Commit any text still in the type-in field into tags (e.g. on save)."""
        try:
            raw = (self.meta_entry.get() or "").strip()
            if raw:
                self._on_meta_type_commit()
        except Exception:
            pass
        if not self.model.meta:
            pass  # allow empty in-model; JSON export can default

    def _on_canvas_type_picked(self, value: str):
        self.canvas_type_var.set(value)
        self._on_canvas_type_change()

    def _on_label_picked(self, value: str):
        self.label_var.set(value)
        self._on_label_change()

    def _sync_meta_entry_from_model(self):
        try:
            self._refresh_meta_chips()
            if getattr(self, "meta_entry", None) is not None:
                self.meta_entry.delete(0, tk.END)
        except Exception:
            pass

    def _meta_label_for(self, tags) -> str:
        tags = list(tags or [])
        for label, preset in META_PRESETS:
            if list(preset) == tags:
                return label
        return ", ".join(tags) if tags else ""

    def _defocus_combobox(self, cb=None):
        """Clear sticky blue selection highlight after choosing a dropdown item."""
        try:
            if cb is not None:
                cb.selection_clear()
        except Exception:
            pass
        try:
            self.canvas.focus_set()
        except Exception:
            pass

    def _on_canvas_type_selected(self, event=None):
        self._on_canvas_type_change()
        self._defocus_combobox(getattr(self, "canvas_type_cb", None))

    def _on_canvas_type_change(self, *_):
        self.model.canvas_type = self.canvas_type_var.get()
        self._update_json()

    def _on_label_selected(self, event=None):
        self._on_label_change()
        self._defocus_combobox(getattr(self, "label_cb", None))

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def _on_size_cb_press(self, event=None):

        """Open/close resolution list (second click on field/arrow closes it)."""
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "size":
            closer = getattr(self, "_list_popup_close", None)
            if callable(closer):
                closer()
            return "break"
        self.after_idle(self._open_size_popup)
        return "break"

    def _open_size_popup(self):
        # If already open, do not spawn a second popup
        if getattr(self, "_list_popup", None) is not None and getattr(self, "_list_popup_kind", None) == "size":
            return
        try:
            self.size_cb.update_idletasks()
            x = self.size_cb.winfo_rootx()
            y = self.size_cb.winfo_rooty() + self.size_cb.winfo_height()
            self.size_cb.update_idletasks()
            width_px = int(self.size_cb.winfo_width())
            if width_px < 40:
                width_px = int(self.size_cb.winfo_reqwidth())
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            width_px = None
        entries = []
        for val in SIZE_DROPDOWN_VALUES:
            if val == SIZE_DROPDOWN_DIVIDER or (isinstance(val, str) and val.startswith("─")):
                entries.append((val, None))
            elif val in SIZE_DROPDOWN_HEADERS:
                entries.append((val, False))  # header, non-selectable
            else:
                entries.append((val, lambda v=val: self._apply_size_string(v)))
        self._open_list_popup(x, y, entries, width_px=width_px, kind="size")

    def _apply_size_string(self, val: str):
        """Apply a WxH preset string from the resolution popup."""
        if self._updating_ui:
            return
        val = (val or "").strip()
        if (
            val in SIZE_DROPDOWN_HEADERS
            or val.startswith("─")
            or (val.startswith("[") and val.endswith("]"))
        ):
            return
        try:
            w, h = map(int, val.replace("×", "x").lower().split("x"))
            if w < 64 or h < 64:
                return
            self.size_var.set(val)
            self._set_size(w, h, push=True)
        except Exception:
            self._updating_ui = True
            self.size_var.set(f"{self.model.width}×{self.model.height}")
            self._updating_ui = False
        self._defocus_combobox(self.size_cb)

    def _on_size_preset(self, *_):
        """Apply a preset from the canvas size dropdown (fallback if native list used)."""
        if self._updating_ui:
            return
        val = self.size_var.get().strip()
        # Section headers are not real sizes — restore current resolution label
        if (
            val in SIZE_DROPDOWN_HEADERS
            or val.startswith("─")
            or (val.startswith("[") and val.endswith("]"))
        ):
            self._updating_ui = True
            self.size_var.set(f"{self.model.width}×{self.model.height}")
            self._updating_ui = False
            self._defocus_combobox(self.size_cb)
            return
        try:
            w, h = map(int, val.replace("×", "x").lower().split("x"))
            if w < 64 or h < 64:
                return
            self._set_size(w, h, push=True)
        except Exception:
            self._updating_ui = True
            self.size_var.set(f"{self.model.width}×{self.model.height}")
            self._updating_ui = False
        self._defocus_combobox(self.size_cb)

    def _on_wh_live(self, *_):
        """Apply canvas size while typing when both fields are valid integers >= 64."""
        if self._updating_ui:
            return
        try:
            w = int(self.width_var.get().strip())
            h = int(self.height_var.get().strip())
        except Exception:
            return
        if w < 64 or h < 64:
            return
        if w == self.model.width and h == self.model.height:
            return
        self._set_size(w, h, push=False)

    def _clear_wh_selection(self):
        """Remove blue text selection highlight from W/H fields."""
        for ent in (getattr(self, "width_entry", None), getattr(self, "height_entry", None)):
            if ent is None:
                continue
            try:
                ent.selection_clear()
            except Exception:
                pass

    def _on_wh_focus_out(self, event=None):
        self._on_wh_commit(event)
        self._clear_wh_selection()

    def _on_wh_commit(self, event=None):
        if self._updating_ui:
            return
        try:
            w = int(self.width_var.get().strip())
            h = int(self.height_var.get().strip())
            if w < 64 or h < 64:
                raise ValueError
        except Exception:
            self._updating_ui = True
            self.width_var.set(str(self.model.width))
            self.height_var.set(str(self.model.height))
            self._updating_ui = False
            self._clear_wh_selection()
            if event is not None and getattr(event, "keysym", "") == "Return":
                try:
                    self.canvas.focus_set()
                except Exception:
                    pass
            return
        if w != self.model.width or h != self.model.height:
            self._set_size(w, h, push=True)
        else:
            self._updating_ui = True
            self.width_var.set(str(w))
            self.height_var.set(str(h))
            self._updating_ui = False
        self._clear_wh_selection()
        # Enter commits and moves focus off the field so highlight doesn't stick
        if event is not None and getattr(event, "keysym", "") == "Return":
            try:
                self.canvas.focus_set()
            except Exception:
                pass

    def _set_size(self, w: int, h: int, push: bool = True):
        old_w, old_h = self.model.width, self.model.height
        if w == old_w and h == old_h:
            return
        self.model.width = w
        self.model.height = h
        if old_w and old_h:
            sx, sy = w / old_w, h / old_h
            for item in self.model.items:
                item.x_min *= sx
                item.x_max *= sx
                item.y_min *= sy
                item.y_max *= sy
                item.clamp(self.model.half_w, self.model.half_h)
        self._updating_ui = True
        self.width_var.set(str(w))
        self.height_var.set(str(h))
        if hasattr(self, "size_var"):
            self.size_var.set(f"{w}×{h}")
        self._updating_ui = False
        self._center_canvas()
        self._redraw_all()
        self._update_json()
        if push:
            self._push_history()
        self.status.configure(text=f"Canvas -> {w}×{h}")
        try:
            self._save_cfg()
        except Exception:
            pass

    def _update_json(self):
        text = self.model.to_json_str(pretty=True)
        self.json_text.configure(state=tk.NORMAL)
        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", text)
        self.json_text.configure(state=tk.DISABLED)

    def _copy_json_clicked(self):
        """Copy prompt and drop focus so the dotted focus ring does not stick."""
        self._copy_json()
        try:
            self.canvas.focus_set()
        except Exception:
            self.focus_set()

    def _copy_json(self):
        self.clipboard_clear()
        self.clipboard_append(self.model.to_json_str(pretty=True))
        self.status.configure(text="JSON copied to clipboard")
        self.after(1500, lambda: self.status.configure(
            text="Ready  ·  Drag empty space to create  ·  Double-click box to edit caption  ·  Scroll to zoom"
        ))

    def _export_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Export Layout JSON",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.model.to_json_str(pretty=True))
            self.status.configure(text=f"Exported → {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _import_any(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("JSON & Images", "*.json;*.png;*.jpg;*.jpeg;*.webp;*.txt"),
                ("JSON", "*.json"),
                ("Images", "*.png;*.jpg;*.jpeg;*.webp"),
                ("All files", "*.*"),
            ],
            title="Import Layout (JSON or image with embedded JSON)",
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()

            data = None
            # Prefer pure JSON first
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = extract_json_from_bytes(raw)

            if not data or not isinstance(data, dict):
                messagebox.showwarning(
                    "No layout found",
                    "Could not find a MOSS-style layout JSON in this file.\n"
                    "Supported: .json files, or images/files that embed the JSON "
                    "in PNG tEXt, JPEG comments, or as plain text.",
                    parent=self,
                )
                return

            self.model.load_from_dict(data)
            self.selected = None
            self._clear_item_panel()
            self.width_var.set(str(self.model.width))
            self.height_var.set(str(self.model.height))
            if hasattr(self, "size_var"):
                self.size_var.set(f"{self.model.width}×{self.model.height}")
            self.caption_text.delete("1.0", tk.END)
            self.caption_text.insert("1.0", self.model.caption)
            self._sync_meta_entry_from_model()
            self.canvas_type_var.set(self.model.canvas_type)
            self._used_colors = {it.color for it in self.model.items}
            self._fit_view_to_canvas(allow_upscale=True)
            self._redraw_all()
            self._update_json()
            self._push_history()
            self.status.configure(
                text=f"Imported {len(self.model.items)} items · canvas {self.model.width}×{self.model.height}"
            )
        except Exception as e:
            messagebox.showerror("Import failed", str(e))



    # ------------------------------------------------------------------
    # Undo / redo (in-memory only)
    # ------------------------------------------------------------------

    def _snapshot(self) -> Dict[str, Any]:
        items = []
        for it in self.model.items:
            items.append({
                "label": it.label,
                "caption": it.caption,
                "text": it.text,
                "color": it.color,
                "locked": bool(getattr(it, "locked", False)),
                "aspect_locked": bool(getattr(it, "aspect_locked", False)),
                "bbox": [it.y_min, it.x_min, it.y_max, it.x_max],
            })
        sel = None
        if self.selected is not None:
            try:
                sel = self.model.items.index(self.selected)
            except ValueError:
                sel = None
        return {
            "width": self.model.width,
            "height": self.model.height,
            "meta": list(self.model.meta),
            "canvas_type": self.model.canvas_type,
            "caption": self.model.caption,
            "items": items,
            "selected": sel,
            "bg_path": self._bg_path,
        }

    def _restore_snapshot(self, snap: Dict[str, Any]):
        self._hist_suppress = True
        self.model.width = int(snap.get("width", DEFAULT_W))
        self.model.height = int(snap.get("height", DEFAULT_H))
        self.model.meta = list(snap.get("meta", []))
        self.model.canvas_type = snap.get("canvas_type", "single")
        self.model.caption = snap.get("caption", "")
        self.model.items.clear()
        for raw in snap.get("items", []):
            b = raw.get("bbox", [-100, -100, 100, 100])
            it = BBoxItem(
                label=raw.get("label", "object"),
                caption=raw.get("caption", ""),
                text=raw.get("text", ""),
                y_min=float(b[0]), x_min=float(b[1]),
                y_max=float(b[2]), x_max=float(b[3]),
                color=raw.get("color"),
            )
            it.locked = bool(raw.get("locked", False))
            it.aspect_locked = bool(raw.get("aspect_locked", False))
            self.model.items.append(it)
        sel = snap.get("selected")
        self.selected = self.model.items[sel] if isinstance(sel, int) and 0 <= sel < len(self.model.items) else None
        # View scale/pan and grid style are intentionally NOT restored (not part of undo)
        self._apply_background_path(snap.get("bg_path"))
        self.width_var.set(str(self.model.width))
        self.height_var.set(str(self.model.height))
        if hasattr(self, "size_var"):
            self.size_var.set(f"{self.model.width}×{self.model.height}")
        self.caption_text.delete("1.0", tk.END)
        self.caption_text.insert("1.0", self.model.caption)
        self._sync_meta_entry_from_model()
        self.canvas_type_var.set(self.model.canvas_type)
        self._used_colors = {it.color for it in self.model.items}
        self._redraw_all()
        self._update_json()
        self._update_item_panel()
        self._hist_suppress = False

    def _push_history(self):
        if self._hist_suppress:
            return
        snap = self._snapshot()
        # drop redo branch
        if self._hist_index < len(self._history) - 1:
            self._history = self._history[: self._hist_index + 1]
        # skip identical consecutive
        if self._history and self._history[-1] == snap:
            return
        self._history.append(snap)
        if len(self._history) > 80:
            self._history = self._history[-80:]
        self._hist_index = len(self._history) - 1

    def _undo(self, *_):
        if self._hist_index <= 0:
            self.status.configure(text="Nothing to undo")
            return
        self._hist_index -= 1
        self._restore_snapshot(self._history[self._hist_index])
        self.status.configure(text=f"Undo ({self._hist_index + 1}/{len(self._history)})")

    def _redo(self, *_):
        if self._hist_index >= len(self._history) - 1:
            self.status.configure(text="Nothing to redo")
            return
        self._hist_index += 1
        self._restore_snapshot(self._history[self._hist_index])
        self.status.configure(text=f"Redo ({self._hist_index + 1}/{len(self._history)})")

    # ------------------------------------------------------------------
    # Project (.bbox) + open
    # ------------------------------------------------------------------

    def _sync_summary_from_ui(self):
        """Push Summary caption / meta / canvas type from widgets into the model."""
        try:
            if hasattr(self, "caption_text"):
                self.model.caption = self.caption_text.get("1.0", "end-1c")
        except Exception:
            pass
        try:
            # meta chips already write through to model.meta; commit any typed text
            self._on_meta_change()
        except Exception:
            pass
        try:
            if hasattr(self, "canvas_type_var"):
                self.model.canvas_type = self.canvas_type_var.get() or "single"
        except Exception:
            pass

    def _sync_summary_to_ui(self):
        """Refresh Summary widgets from the model."""
        try:
            if hasattr(self, "caption_text"):
                self.caption_text.delete("1.0", tk.END)
                self.caption_text.insert("1.0", self.model.caption or "")
        except Exception:
            pass
        try:
            self._sync_meta_entry_from_model()
        except Exception:
            pass
        try:
            if hasattr(self, "canvas_type_var"):
                self.canvas_type_var.set(self.model.canvas_type or "single")
        except Exception:
            pass

    def _project_dict(self) -> Dict[str, Any]:
        self._sync_summary_from_ui()
        layout = self.model.to_json_dict()
        # embed editor-only fields
        for i, it in enumerate(self.model.items):
            if i < len(layout["items"]):
                layout["items"][i]["color"] = it.color
                layout["items"][i]["locked"] = bool(it.locked)
                layout["items"][i]["aspect_locked"] = bool(it.aspect_locked)
        layout["width"] = self.model.width
        layout["height"] = self.model.height
        # Ensure current state (incl. summary caption/meta) is the history tip
        self._hist_suppress = False
        snap = self._snapshot()
        if not self._history:
            self._history = [snap]
            self._hist_index = 0
        else:
            # Replace tip so caption-only edits are not lost
            if self._hist_index < 0 or self._hist_index >= len(self._history):
                self._hist_index = len(self._history) - 1
            self._history = self._history[: self._hist_index + 1]
            self._history[self._hist_index] = snap
        # History for disk: drop background paths (and never persist grid / view scale)
        clean_states = []
        for s in self._history:
            if not isinstance(s, dict):
                continue
            sc = dict(s)
            sc.pop("bg_path", None)
            sc.pop("scale", None)
            sc.pop("offset_x", None)
            sc.pop("offset_y", None)
            sc.pop("grid_style", None)
            clean_states.append(sc)
        return {
            "format": "bbox-studio-project",
            "version": 2,
            "view": {
                "scale": self.scale,
                "offset_x": self.offset_x,
                "offset_y": self.offset_y,
            },
            "ui": {
                "font_family": getattr(self, "_ui_font_family", "Segoe UI"),
                "font_size": int(getattr(self, "_ui_font_size", DEFAULT_UI_FONT_SIZE)),
            },
            "layout": layout,
            "history": {
                "index": self._hist_index,
                "states": clean_states,
            },
        }

    def _save_project(self, *_):
        path = filedialog.asksaveasfilename(
            defaultextension=".bbox",
            filetypes=[("BBox Studio project", "*.bbox"), ("All files", "*.*")],
            title="Save Project",
        )
        if not path:
            return
        if not path.lower().endswith(".bbox"):
            path += ".bbox"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._project_dict(), f, indent=2, ensure_ascii=False)
            self.status.configure(text=f"Project saved → {path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _load_project_dict(self, data: Dict[str, Any]):
        layout = data.get("layout") or data
        self.model.load_from_dict(layout)
        # restore editor fields from layout items if present
        raw_items = layout.get("items", [])
        for i, it in enumerate(self.model.items):
            if i < len(raw_items):
                if raw_items[i].get("color"):
                    it.color = raw_items[i]["color"]
                it.locked = bool(raw_items[i].get("locked", False))
                it.aspect_locked = bool(raw_items[i].get("aspect_locked", False))
        # Explicit size on layout root (project format)
        if "width" in layout:
            try:
                self.model.width = int(layout["width"])
            except Exception:
                pass
        if "height" in layout:
            try:
                self.model.height = int(layout["height"])
            except Exception:
                pass
        view = data.get("view") or {}
        if "scale" in view:
            self.scale = float(view["scale"])
        if "offset_x" in view:
            self.offset_x = float(view["offset_x"])
        if "offset_y" in view:
            self.offset_y = float(view["offset_y"])
        self.selected = None
        self._clear_item_panel()
        self.width_var.set(str(self.model.width))
        self.height_var.set(str(self.model.height))
        if hasattr(self, "size_var"):
            self.size_var.set(f"{self.model.width}×{self.model.height}")
        # Summary panel from layout (authoritative for the loaded document)
        self._sync_summary_to_ui()
        # UI font from project
        ui = data.get("ui") or {}
        if ui.get("font_family"):
            self._ui_font_family = str(ui["font_family"])
        else:
            self._ui_font_family = DEFAULT_UI_FONT_FAMILY
        if ui.get("font_size") is not None:
            try:
                self._ui_font_size = max(8, min(28, int(ui["font_size"])))
            except Exception:
                self._ui_font_size = DEFAULT_UI_FONT_SIZE
        else:
            self._ui_font_size = DEFAULT_UI_FONT_SIZE
        self._apply_ui_font()
        self._used_colors = {it.color for it in self.model.items}
        if "scale" not in view:
            self._center_canvas()
        self._redraw_all()
        self._update_json()

        # Restore undo/redo stack when present — do NOT re-apply a history snapshot
        # over the layout, or Summary caption/meta can be overwritten by a stale tip.
        hist = data.get("history") or {}
        states = hist.get("states")
        if isinstance(states, list) and states:
            self._history = [s for s in states if isinstance(s, dict)]
            idx = hist.get("index", len(self._history) - 1)
            try:
                idx = int(idx)
            except Exception:
                idx = len(self._history) - 1
            self._hist_index = max(0, min(idx, len(self._history) - 1))
            # Align history tip with the layout we just loaded (summary + items)
            if 0 <= self._hist_index < len(self._history):
                self._history[self._hist_index] = self._snapshot()
        else:
            self._history.clear()
            self._hist_index = -1
            self._push_history()

    def _load_project(self, *_):
        path = filedialog.askopenfilename(
            filetypes=[
                ("BBox Studio project", "*.bbox"),
                ("All files", "*.*"),
            ],
            title="Load Project",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Invalid project file")
            if data.get("format") not in (None, "bbox-studio-project") and "layout" not in data and "items" not in data:
                # still try if it looks like a project
                pass
            self._load_project_dict(data if data.get("format") == "bbox-studio-project" or "layout" in data else {
                "format": "bbox-studio-project",
                "version": 1,
                "layout": data,
            })
            self.status.configure(text=f"Loaded project → {path}")
        except Exception as e:
            messagebox.showerror("Load project failed", str(e))


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    app = BBoxStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
