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
import re
import random
import struct
import tempfile
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from typing import Optional, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "BBox Studio"
DEFAULT_W, DEFAULT_H = 1000, 1000

BG_DARK   = "#12121a"
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

COMMON_SIZES = [
    (1000, 1000),
    (1024, 1024),
    (768, 1024),
    (1024, 768),
    (1536, 1024),
    (1024, 1536),
    (1280, 720),
    (1920, 1080),
    (512, 512),
    (768, 768),
]

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
        self.meta: List[str] = ["scene"]
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
                "meta": self.meta,
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
        self.meta = ["scene"]
        self.canvas_type = "single"
        self.caption = "A clean composition with carefully placed elements."
        self.items.clear()

    def load_from_dict(self, data: Dict[str, Any]):
        summary = data.get("summary", {})
        self.meta = list(summary.get("meta", ["scene"]))
        self.canvas_type = summary.get("canvas", "single")
        self.caption = summary.get("caption", "")
        self.items.clear()

        # adopt dimensions if present (draft format)
        if "width" in data and "height" in data:
            self.width = int(data["width"])
            self.height = int(data["height"])

        for raw in data.get("items", []):
            bbox = raw.get("bbox", [0, 0, 100, 100])
            fmt = data.get("bbox_format", "yxyx")
            if fmt == "xyxy":
                x1, y1, x2, y2 = bbox
                y_min, x_min, y_max, x_max = y1, x1, y2, x2
            else:
                y_min, x_min, y_max, x_max = bbox

            space = data.get("bbox_coord_space", "abs_centralized")
            if space == "abs":
                w = data.get("width", self.width)
                h = data.get("height", self.height)
                y_min -= h / 2
                x_min -= w / 2
                y_max -= h / 2
                x_max -= w / 2

            item = BBoxItem(
                label=raw.get("label", "object"),
                caption=raw.get("caption", ""),
                text=raw.get("text", ""),
                y_min=y_min, x_min=x_min, y_max=y_max, x_max=x_max,
            )
            self.items.append(item)


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

class BBoxStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1320x860")
        self.minsize(1020, 680)
        self.configure(bg=BG_DARK)

        self.model = LayoutModel()
        self.selected: Optional[BBoxItem] = None
        self.drag_mode: Optional[str] = None
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
        self._bg_path: Optional[str] = None
        self._bg_photo_orig = None  # tk.PhotoImage (source)
        self._bg_rgb: Optional[bytes] = None  # raw RGB for exact scaling
        self._bg_iw = 0
        self._bg_ih = 0
        self._bg_photo = None  # displayed PhotoImage
        self._bg_scale_key = None
        self._panning = False
        self._pan_last = (0, 0)

        self._setup_styles()
        self._build_ui()
        self._bind_events()
        self.after(50, self._initial_fit)
        self.after(10, self._center_on_screen)
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
    # Styles
    # ------------------------------------------------------------------

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=FG, fieldbackground=BG_PANEL)
        style.configure("TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG_DARK, foreground=FG, font=("Segoe UI", 11))
        style.configure("Dim.TLabel", background=BG_DARK, foreground=FG_DIM, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG_PANEL, foreground=FG, font=("Segoe UI", 13, "bold"))
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG, font=("Segoe UI", 11))
        style.configure("Brand.TLabel", background=BG_PANEL, foreground=ACCENT, font=("Segoe UI", 13, "bold"))
        style.configure("TButton", background=BG_PANEL, foreground=FG, borderwidth=0, focusthickness=0, font=("Segoe UI", 10))
        style.map("TButton", background=[("active", BORDER)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#0f0f17")
        style.map("Accent.TButton", background=[("active", "#9db4ff")])
        style.configure("Danger.TButton", background=DANGER, foreground="#0f0f17")
        style.map("Danger.TButton", background=[("active", "#fca5a5")])
        style.configure("Ghost.TButton", background=BG_PANEL, foreground=FG_DIM)
        style.map("Ghost.TButton", background=[("active", BORDER)])
        style.configure(
            "Add.TButton",
            background=BG_PANEL,
            foreground=FG,
            borderwidth=0,
            focusthickness=0,
            font=("Segoe UI", 10, "bold"),
            padding=(6, 4),
        )
        style.map("Add.TButton", background=[("active", BORDER)])
        style.configure("TCombobox", fieldbackground=BG_PANEL, background=BG_PANEL, foreground=FG, arrowcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", BG_PANEL)])
        style.configure("TEntry", fieldbackground=BG_PANEL, foreground=FG, insertcolor=FG)
        style.configure("TCheckbutton", background=BG_PANEL, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG_PANEL)])
        style.configure("Vertical.TScrollbar", background=BG_PANEL, troughcolor=BG_DARK, arrowcolor=FG)
        style.configure("Horizontal.TScrollbar", background=BG_PANEL, troughcolor=BG_DARK, arrowcolor=FG)

    # ------------------------------------------------------------------
    # Logo (drawn with Canvas — zero image deps)
    # ------------------------------------------------------------------

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
        about.resizable(False, False)
        about.transient(self)
        about.grab_set()

        # Center over main window
        self.update_idletasks()
        w, h = 340, 160
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        about.geometry(f"{w}x{h}+{x}+{y}")

        # Mini logo
        logo = self._draw_logo(about)
        # unbind recursive about from the mini logo
        logo.unbind("<Button-1>")
        logo.configure(cursor="")
        logo.pack(pady=(18, 8))

        ttk.Label(
            about,
            text="BBox Studio",
            style="Brand.TLabel",
        ).pack()

        ttk.Label(
            about,
            text="Coded with Grok by plk.\nAll rights reserved, 2026.",
            style="Dim.TLabel",
            justify=tk.CENTER,
        ).pack(pady=(6, 12))

        ttk.Button(about, text="Close", command=about.destroy).pack(pady=(0, 12))
        about.bind("<Escape>", lambda e: about.destroy())
        about.focus_set()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────
        top = ttk.Frame(self, style="Panel.TFrame")
        top.pack(side=tk.TOP, fill=tk.X)

        logo = self._draw_logo(top)
        logo.pack(side=tk.LEFT, padx=(10, 4), pady=6)

        ttk.Label(top, text="BBox Studio", style="Brand.TLabel").pack(side=tk.LEFT, padx=(0, 16), pady=8)

        size_frame = ttk.Frame(top, style="Panel.TFrame")
        size_frame.pack(side=tk.LEFT, padx=4)
        ttk.Label(size_frame, text="Canvas", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.size_var = tk.StringVar(value=f"{DEFAULT_W}×{DEFAULT_H}")
        self.size_cb = ttk.Combobox(
            size_frame, textvariable=self.size_var,
            values=[f"{w}×{h}" for w, h in COMMON_SIZES],
            width=11, state="readonly",
        )
        self.size_cb.pack(side=tk.LEFT)
        self.size_cb.bind("<<ComboboxSelected>>", self._on_size_preset)

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
            ent.bind("<FocusOut>", self._on_wh_commit)
            ent.bind("<KeyRelease>", self._on_wh_live)

        # Right cluster — pack side=RIGHT in reverse of visual left→right:
        # Save Project | Load Project | Import JSON | Export JSON | Copy Prompt to Clipboard | Undo | Redo | Reset
        ttk.Button(top, text="Reset", style="Ghost.TButton", command=self._reset).pack(side=tk.RIGHT, padx=(0, 4), pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=2, pady=6)
        ttk.Button(top, text="Redo", command=self._redo).pack(side=tk.RIGHT, padx=0, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=1, pady=6)
        ttk.Button(top, text="Undo", command=self._undo).pack(side=tk.RIGHT, padx=0, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=2, pady=6)
        ttk.Button(top, text="Copy Prompt to Clipboard", style="Accent.TButton", command=self._copy_json).pack(side=tk.RIGHT, padx=2, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)
        ttk.Button(top, text="Export JSON", command=self._export_json).pack(side=tk.RIGHT, padx=2, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=4, pady=6)
        ttk.Button(top, text="Import JSON", command=self._import_any).pack(side=tk.RIGHT, padx=2, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)
        ttk.Button(top, text="Load Project", command=self._load_project).pack(side=tk.RIGHT, padx=2, pady=6)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=4, pady=6)
        ttk.Button(top, text="Save Project", command=self._save_project).pack(side=tk.RIGHT, padx=2, pady=6)

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

        # Right panel
        right = ttk.Frame(main, width=400, style="Panel.TFrame")
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        right.pack_propagate(False)

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
        ttk.Label(right, text="Summary", style="Title.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 4))

        ttk.Label(right, text="Caption", style="Dim.TLabel").pack(anchor=tk.W, padx=12)
        self.caption_text = self._make_resizable_text(right, height=3)
        self.caption_text.insert("1.0", self.model.caption)
        self.caption_text.bind("<KeyRelease>", self._on_caption_change)

        meta_row = ttk.Frame(right, style="Panel.TFrame")
        meta_row.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(meta_row, text="Meta", style="Dim.TLabel").pack(side=tk.LEFT)
        # Default display: first matching preset or free-form join
        default_meta_label = "scene"
        for label, tags in META_PRESETS:
            if tags == self.model.meta:
                default_meta_label = label
                break
        self.meta_var = tk.StringVar(value=default_meta_label)
        self.meta_cb = ttk.Combobox(
            meta_row,
            textvariable=self.meta_var,
            values=META_LABELS,
            width=28,
            state="normal",  # allow typing custom values too
        )
        self.meta_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.meta_cb.bind("<<ComboboxSelected>>", self._on_meta_change)
        self.meta_cb.bind("<KeyRelease>", self._on_meta_change)
        self.meta_cb.bind("<FocusOut>", self._on_meta_change)

        canvas_row = ttk.Frame(right, style="Panel.TFrame")
        canvas_row.pack(fill=tk.X, padx=12, pady=2)
        ttk.Label(canvas_row, text="Type", style="Dim.TLabel").pack(side=tk.LEFT)
        self.canvas_type_var = tk.StringVar(value=self.model.canvas_type)
        ttk.Combobox(
            canvas_row, textvariable=self.canvas_type_var,
            values=["single", "multi_panel", "collage"], width=12, state="readonly",
        ).pack(side=tk.LEFT, padx=8)
        self.canvas_type_var.trace_add("write", lambda *_: self._on_canvas_type_change())

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)

        # Selected item
        ttk.Label(right, text="Selected Box", style="Title.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 4))

        type_row = ttk.Frame(right, style="Panel.TFrame")
        type_row.pack(fill=tk.X, padx=12, pady=2)
        ttk.Label(type_row, text="Label", style="Dim.TLabel").pack(side=tk.LEFT)
        self.label_var = tk.StringVar(value="object")
        label_cb = ttk.Combobox(
            type_row, textvariable=self.label_var,
            values=["text", "object", "character"], width=11, state="readonly",
        )
        label_cb.pack(side=tk.LEFT, padx=8)
        label_cb.bind("<<ComboboxSelected>>", self._on_label_change)

        # Color row
        color_row = ttk.Frame(right, style="Panel.TFrame")
        color_row.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(color_row, text="Color", style="Dim.TLabel").pack(side=tk.LEFT)
        self.color_preview = tk.Canvas(color_row, width=22, height=22, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER)
        self.color_preview.pack(side=tk.LEFT, padx=(8, 4))
        self.color_var = tk.StringVar(value="#7c9cff")
        color_entry = ttk.Entry(color_row, textvariable=self.color_var, width=10)
        color_entry.pack(side=tk.LEFT)
        color_entry.bind("<KeyRelease>", self._on_color_entry)
        color_entry.bind("<Return>", self._on_color_entry)
        ttk.Button(color_row, text="Pick…", command=self._pick_color).pack(side=tk.LEFT, padx=4)

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
        ttk.Checkbutton(lock_row, text="Lock aspect", variable=self.aspect_var,
                        command=self._on_aspect_toggle).pack(side=tk.LEFT, padx=(12, 0))

        btn_row = ttk.Frame(right, style="Panel.TFrame")
        btn_row.pack(fill=tk.X, padx=12, pady=8)
        ttk.Button(btn_row, text="Delete", style="Danger.TButton", command=self._delete_selected).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Duplicate", command=self._duplicate_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Bring To Front", command=self._bring_front).pack(side=tk.LEFT, padx=4)

        self.coord_label = ttk.Label(right, text="", style="Dim.TLabel")
        self.coord_label.pack(anchor=tk.W, padx=12, pady=2)

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=8)

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
        grip.bind("<Enter>", lambda e: grip.configure(bg=ACCENT))
        grip.bind("<Leave>", lambda e: grip.configure(bg=BORDER))

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

    def _draw_grid(self, x0, y0, x1, y1):
        """Draw guide grid according to self._grid_style (not used when bg image is set)."""
        style = getattr(self, "_grid_style", "default")
        if style == "none":
            return

        # Center cross for most styles
        if style in ("default", "fine", "coarse", "cross", "thirds", "golden"):
            cx, cy = self._img_to_canvas(0, 0)
            self.canvas.create_line(cx - 14, cy, cx + 14, cy, fill=BORDER, width=1)
            self.canvas.create_line(cx, cy - 14, cx, cy + 14, fill=BORDER, width=1)

        if style == "cross":
            return

        hw, hh = self.model.half_w, self.model.half_h
        grid_color = "#1e1e2c"
        accent = "#2a2a3c"

        if style == "dots":
            step = 50 if self.model.width <= 1200 else 80
            for gx in range(int(-hw), int(hw) + 1, step):
                for gy in range(int(-hh), int(hh) + 1, step):
                    px, py = self._img_to_canvas(gx, gy)
                    self.canvas.create_oval(px - 1, py - 1, px + 1, py + 1, fill=grid_color, outline="")
            return

        if style == "thirds":
            for t in (1 / 3, 2 / 3):
                gx = -hw + 2 * hw * t
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

        for gx in range(int(-hw), int(hw) + 1, step):
            xa, ya = self._img_to_canvas(gx, -hh)
            xb, yb = self._img_to_canvas(gx, hh)
            self.canvas.create_line(xa, ya, xb, yb, fill=grid_color, width=1)
        for gy in range(int(-hh), int(hh) + 1, step):
            xa, ya = self._img_to_canvas(-hw, gy)
            xb, yb = self._img_to_canvas(hw, gy)
            self.canvas.create_line(xa, ya, xb, yb, fill=grid_color, width=1)

    def _draw_item(self, item: BBoxItem):
        x0, y0 = self._img_to_canvas(item.x_min, item.y_min)
        x1, y1 = self._img_to_canvas(item.x_max, item.y_max)
        color = item.color
        is_sel = item is self.selected
        width = 3 if is_sel else 2

        # Semi-transparent fill via stipple
        dash = (4, 3) if getattr(item, "locked", False) else ()
        item.id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=color, width=width,
            fill=color if is_sel else "",
            stipple="gray25" if is_sel else "",
            dash=dash,
            tags=("box", f"item-{id(item)}"),
        )

        # Caption inside the box, prefixed with type label (no corner badge)
        pad = 6
        body = item.caption or (item.text if item.label == "text" else "")
        if body:
            display = f"{item.label} · {body}"
        else:
            display = item.label or "object"
        # limit visible length by box size
        max_chars = max(8, int((x1 - x0) / 7))
        if len(display) > max_chars:
            display = display[: max_chars - 1] + "…"

        item.caption_id = self.canvas.create_text(
            x0 + pad, y0 + pad,
            text=display,
            anchor=tk.NW,
            fill=color,
            font=("Segoe UI", 11),
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

    def _on_canvas_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=BORDER, activeforeground=FG)
        menu.add_command(label="Change Background…", command=self._change_background)
        menu.add_command(label="Remove Background", command=self._remove_background)

        grid_menu = tk.Menu(menu, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=BORDER, activeforeground=FG)
        for key, label in (
            ("default", "Default"),
            ("fine", "Fine grid"),
            ("coarse", "Coarse grid"),
            ("dots", "Dot grid"),
            ("thirds", "Rule of thirds"),
            ("golden", "Golden ratio"),
            ("cross", "Center cross only"),
            ("none", "No guides"),
        ):
            grid_menu.add_command(label=label, command=lambda k=key: self._set_grid_style(k))
        menu.add_cascade(label="Grid Layout", menu=grid_menu)

        menu.add_separator()
        scale_menu = tk.Menu(menu, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=BORDER, activeforeground=FG)
        scale_menu.add_command(label="50%", command=lambda: self._set_view_scale_pct(0.5))
        scale_menu.add_command(label="100%", command=lambda: self._set_view_scale_pct(1.0))
        scale_menu.add_command(label="200%", command=lambda: self._set_view_scale_pct(2.0))
        scale_menu.add_command(label="Scale To Fit", command=self._scale_to_fit)
        menu.add_cascade(label="Scale Canvas", menu=scale_menu)
        menu.add_command(label="Recenter Canvas", command=self._recenter_view)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _set_grid_style(self, style: str):
        # Not tracked in undo / project history
        self._grid_style = style
        self._redraw_all()
        self.status.configure(text=f"Grid layout → {style}")

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
        self._redraw_all()
        self.status.configure(text="Canvas scaled to fit")

    def _recenter_view(self):
        # Recenter + scale to fit
        self._fit_view_to_canvas(allow_upscale=True)
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
        try:
            self.status.configure(text="Loading background…")
            self.update_idletasks()
            size = self._probe_image_size(path)
            photo = tk.PhotoImage(file=path)
            iw, ih = photo.width(), photo.height()
            if size and size[0] > 0 and size[1] > 0:
                # Prefer header size when PhotoImage reports differently
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
            # Canvas model size = image pixel size (aspect + resolution)
            self._set_size(self._bg_iw, self._bg_ih, push=False)
            self.update_idletasks()
            self._center_canvas()
            # Allow full fit without the default 1.3× view cap when showing a bg
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
        """Extract RGB bytes from a PhotoImage (one-time cost at load)."""
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
                    # "r g b" or tuple-like
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
        """Nearest-neighbor resize of packed RGB."""
        tw = max(1, tw)
        th = max(1, th)
        out = bytearray(tw * th * 3)
        for y in range(th):
            sy = (y * ih) // th
            if sy >= ih:
                sy = ih - 1
            src_row = sy * iw * 3
            dst_row = y * tw * 3
            for x in range(tw):
                sx = (x * iw) // tw
                if sx >= iw:
                    sx = iw - 1
                si = src_row + sx * 3
                di = dst_row + x * 3
                out[di] = rgb[si]
                out[di + 1] = rgb[si + 1]
                out[di + 2] = rgb[si + 2]
        return bytes(out)

    def _photo_from_rgb(self, rgb: bytes, w: int, h: int) -> "tk.PhotoImage":
        """Build a PhotoImage from raw RGB via PPM (stdlib only)."""
        if len(rgb) < w * h * 3:
            raise ValueError("RGB buffer too small")
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
        """Scale background to exactly match the on-screen canvas rectangle."""
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
        try:
            if tw == self._bg_iw and th == self._bg_ih:
                scaled = self._bg_rgb
            else:
                scaled = self._resize_rgb_nn(self._bg_rgb, self._bg_iw, self._bg_ih, tw, th)
            photo = self._photo_from_rgb(scaled, tw, th)
            self._bg_photo = photo
            self._bg_scale_key = key
            return photo
        except Exception:
            try:
                photo = self._bg_photo_orig
                if photo is None:
                    return None
                iw, ih = max(1, photo.width()), max(1, photo.height())
                if tw < iw or th < ih:
                    f = max(1, min(iw // max(1, tw), ih // max(1, th)))
                    if f > 1:
                        photo = photo.subsample(f, f)
                elif tw > iw or th > ih:
                    z = max(1, min(max(1, tw // iw), max(1, th // ih)))
                    if z > 1:
                        photo = photo.zoom(z, z)
                self._bg_photo = photo
                self._bg_scale_key = key
                return photo
            except Exception:
                return self._bg_photo_orig

    def _fit_view_to_canvas(self, allow_upscale: bool = True):
        """Set scale/offset so the full model frame fits in the widget."""
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
        """Restore background from path for undo (best-effort)."""
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
        _safe(self.canvas, "<Button-4>", lambda e: self._zoom(1.1))
        _safe(self.canvas, "<Button-5>", lambda e: self._zoom(0.9))
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

    def _on_canvas_resize(self):
        # Redraw only — keep current pan/zoom (recenter is explicit via menu)
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

        # create
        self.selected = None
        self.drag_mode = "create"
        ix, iy = self._canvas_to_img(event.x, event.y)
        self.create_start = (ix, iy)
        self._temp_rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=ACCENT, width=2, dash=(5, 3), tags="temp",
        )
        self._redraw_all()

    def _on_drag(self, event):
        if self.drag_mode == "create":
            self.canvas.coords(self._temp_rect, self.drag_start[0], self.drag_start[1], event.x, event.y)
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
                self.drag_mode = None
                return
            color = self._next_color()
            item = BBoxItem(
                label="object",
                caption="",
                y_min=y_min, x_min=x_min, y_max=y_max, x_max=x_max,
                color=color,
            )
            item.clamp(self.model.half_w, self.model.half_h)
            self.model.items.append(item)
            self.selected = item
            self._redraw_all()
            self._update_json()
            self._push_history()
            self.status.configure(text="Box created · Double-click it to type a caption, or edit on the right")
        elif self.drag_mode in ("move", "resize"):
            self._push_history()
        self.drag_mode = None
        self.resize_handle = None
        self._aspect_ratio_cache = None

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
        h = 24

        self._inline_entry = tk.Entry(
            self.canvas,
            bg="#1a1a26", fg=item.color, insertbackground=item.color,
            relief=tk.FLAT, font=("Segoe UI", 10),
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
        self.status.configure(text=f"x={ix:.0f}  y={iy:.0f}   ·   scale {self.scale:.2f}×")

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
        self._bg_scale_key = None  # force bg image rebuild at new scale
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

    def _pick_color(self):
        if not self.selected:
            return
        result = colorchooser.askcolor(
            color=self.selected.color,
            title="Box Color",
            parent=self,
        )
        if result and result[1]:
            self.selected.color = result[1]
            self.color_var.set(result[1])
            self._update_color_preview(result[1])
            self._redraw_all()
            self._update_json()
            self._push_history()

    def _on_color_entry(self, *_):
        if self._updating_ui or not self.selected:
            return
        val = self.color_var.get().strip()
        if re.match(r"^#[0-9a-fA-F]{6}$", val):
            self.selected.color = val
            self._update_color_preview(val)
            self._redraw_all()

    def _update_color_preview(self, color: str):
        self.color_preview.delete("all")
        self.color_preview.create_rectangle(0, 0, 22, 22, fill=color, outline="")

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
        self.meta_var.set(self._meta_label_for(self.model.meta))
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

    def _update_item_panel(self):
        if not self.selected:
            self._clear_item_panel()
            return
        self._updating_ui = True
        self.label_var.set(self.selected.label)
        self.color_var.set(self.selected.color)
        self._update_color_preview(self.selected.color)
        self.item_caption.delete("1.0", tk.END)
        self.item_caption.insert("1.0", self.selected.caption)
        self.item_text.delete("1.0", tk.END)
        self.item_text.insert("1.0", self.selected.text)
        if hasattr(self, "lock_var"):
            self.lock_var.set(bool(self.selected.locked))
        if hasattr(self, "aspect_var"):
            self.aspect_var.set(bool(self.selected.aspect_locked))
        lock_note = "  🔒 locked" if self.selected.locked else ""
        self.coord_label.configure(
            text=f"[{self.selected.y_min:.0f}, {self.selected.x_min:.0f}, "
                 f"{self.selected.y_max:.0f}, {self.selected.x_max:.0f}]  "
                 f"({self.selected.width():.0f}×{self.selected.height():.0f}){lock_note}"
        )
        self._updating_ui = False

    def _clear_item_panel(self):
        self._updating_ui = True
        self.label_var.set("object")
        self.color_var.set("#7c9cff")
        self._update_color_preview("#7c9cff")
        self.item_caption.delete("1.0", tk.END)
        self.item_text.delete("1.0", tk.END)
        if hasattr(self, "lock_var"):
            self.lock_var.set(False)
        if hasattr(self, "aspect_var"):
            self.aspect_var.set(False)
        self.coord_label.configure(text="")
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

    def _meta_label_for(self, tags: List[str]) -> str:
        """Return the dropdown label that matches tags, or a free-form join."""
        for label, preset in META_PRESETS:
            if preset == tags:
                return label
        return ", ".join(tags)

    def _on_meta_change(self, *_):
        raw = self.meta_var.get().strip()
        if raw in META_MAP:
            self.model.meta = list(META_MAP[raw])
        else:
            # free-form: comma-separated tags
            self.model.meta = [t.strip() for t in raw.split(",") if t.strip()] or ["scene"]
        self._update_json()

    def _on_canvas_type_change(self, *_):
        self.model.canvas_type = self.canvas_type_var.get()
        self._update_json()

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def _on_size_preset(self, *_):
        """Apply a preset from the canvas size dropdown."""
        if self._updating_ui:
            return
        val = self.size_var.get()
        try:
            w, h = map(int, val.replace("×", "x").lower().split("x"))
            if w < 64 or h < 64:
                return
            self._set_size(w, h, push=True)
        except Exception:
            pass

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

    def _on_wh_commit(self, *_):
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
            return
        if w != self.model.width or h != self.model.height:
            self._set_size(w, h, push=True)
        else:
            self._updating_ui = True
            self.width_var.set(str(w))
            self.height_var.set(str(h))
            self._updating_ui = False

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

    def _update_json(self):
        text = self.model.to_json_str(pretty=True)
        self.json_text.configure(state=tk.NORMAL)
        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", text)
        self.json_text.configure(state=tk.DISABLED)

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
            self.width_var.set(str(self.model.width))
            self.height_var.set(str(self.model.height))
            if hasattr(self, "size_var"):
                self.size_var.set(f"{self.model.width}×{self.model.height}")
            self.caption_text.delete("1.0", tk.END)
            self.caption_text.insert("1.0", self.model.caption)
            self.meta_var.set(self._meta_label_for(self.model.meta))
            self.canvas_type_var.set(self.model.canvas_type)
            self._used_colors = {it.color for it in self.model.items}
            self._center_canvas()
            self._redraw_all()
            self._update_json()
            self.status.configure(text=f"Imported {len(self.model.items)} items from {path}")
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
        self.model.meta = list(snap.get("meta", ["scene"]))
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
        self.meta_var.set(self._meta_label_for(self.model.meta))
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

    def _project_dict(self) -> Dict[str, Any]:
        layout = self.model.to_json_dict()
        # embed editor-only fields
        for i, it in enumerate(self.model.items):
            if i < len(layout["items"]):
                layout["items"][i]["color"] = it.color
                layout["items"][i]["locked"] = bool(it.locked)
                layout["items"][i]["aspect_locked"] = bool(it.aspect_locked)
        layout["width"] = self.model.width
        layout["height"] = self.model.height
        # Ensure current state is represented in history
        if not self._history:
            self._push_history()
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
        view = data.get("view") or {}
        if "scale" in view:
            self.scale = float(view["scale"])
        if "offset_x" in view:
            self.offset_x = float(view["offset_x"])
        if "offset_y" in view:
            self.offset_y = float(view["offset_y"])
        self.selected = None
        self.width_var.set(str(self.model.width))
        self.height_var.set(str(self.model.height))
        if hasattr(self, "size_var"):
            self.size_var.set(f"{self.model.width}×{self.model.height}")
        self.caption_text.delete("1.0", tk.END)
        self.caption_text.insert("1.0", self.model.caption)
        self.meta_var.set(self._meta_label_for(self.model.meta))
        self.canvas_type_var.set(self.model.canvas_type)
        self._used_colors = {it.color for it in self.model.items}
        if "scale" not in view:
            self._center_canvas()
        self._redraw_all()
        self._update_json()

        # Restore undo/redo stack when present in the project file
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
            # Apply the indexed state so UI matches history pointer
            self._restore_snapshot(self._history[self._hist_index])
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
