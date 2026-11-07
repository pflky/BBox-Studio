
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class BBoxStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("BBOX Studio - JSON Layout Prompt Editor")
        self.root.geometry("1450x900")
        self.root.minsize(1050, 650)

        self.width = 1024
        self.height = 1024
        self.items = []
        self.selected = None
        self.image = None
        self.photo = None
        self.image_path = None

        self.scale = 1
        self.offset_x = 0
        self.offset_y = 0
        self.drag_mode = None
        self.drag_start = None
        self.drag_original = None
        self.drawing_start = None

        self.caption = tk.StringVar()
        self.meta = tk.StringVar()
        self.canvas_width = tk.StringVar(value="1024")
        self.canvas_height = tk.StringVar(value="1024")

        self.build_ui()
        self.refresh_json()

    # ---------------- UI ----------------

    def build_ui(self):
        self.root.configure(bg="#20242b")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#20242b")
        style.configure("TLabel", background="#20242b",
                        foreground="#eeeeee")
        style.configure("TButton", padding=5)
        style.configure("TLabelframe", background="#20242b",
                        foreground="white")
        style.configure("TLabelframe.Label",
                        background="#20242b", foreground="white")

        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=8, pady=8)

        buttons = [
            ("New", self.new_project),
            ("Open JSON", self.load_json),
            ("Save JSON", self.save_json),
            ("Import Image", self.load_image),
            ("Add Box", self.add_box),
            ("Delete Box", self.delete_box),
            ("Copy Prompt", self.copy_prompt),
            ("Export JSON", self.export_json),
        ]

        for label, command in buttons:
            ttk.Button(toolbar, text=label,
                       command=command).pack(side="left", padx=3)

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=5)

        # Canvas area
        left = ttk.Frame(main)
        main.add(left, weight=3)

        settings = ttk.LabelFrame(left, text="Scene Settings")
        settings.pack(fill="x", padx=4, pady=4)

        ttk.Label(settings, text="Scene description:").grid(
            row=0, column=0, sticky="w", padx=5)

        ttk.Entry(settings, textvariable=self.caption).grid(
            row=0, column=1, sticky="ew", padx=5, pady=4)

        ttk.Label(settings, text="Meta tags:").grid(
            row=1, column=0, sticky="w", padx=5)

        ttk.Entry(settings, textvariable=self.meta).grid(
            row=1, column=1, sticky="ew", padx=5, pady=4)

        ttk.Label(settings, text="Width:").grid(
            row=2, column=0, sticky="w", padx=5)

        ttk.Entry(settings, textvariable=self.canvas_width,
                  width=10).grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(settings, text="Height:").grid(
            row=3, column=0, sticky="w", padx=5)

        ttk.Entry(settings, textvariable=self.canvas_height,
                  width=10).grid(row=3, column=1, sticky="w", padx=5)

        ttk.Button(settings, text="Apply Dimensions",
                   command=self.apply_dimensions).grid(
                       row=3, column=2, padx=5)

        settings.columnconfigure(1, weight=1)

        self.canvas = tk.Canvas(
            left, bg="#353b46",
            highlightthickness=1,
            highlightbackground="#596273"
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.canvas.bind("<Double-Button-1>", self.edit_text_item)

        self.canvas.bind("<Delete>", lambda e: self.delete_box())
        self.canvas.focus_set()

        ttk.Label(
            left,
            text="Drag empty space to draw a box. Drag a box to move it. "
                 "Drag its bottom-right handle to resize it.",
        ).pack(fill="x", padx=5, pady=4)

        # Right-side controls
        right = ttk.Frame(main)
        main.add(right, weight=2)

        # Object list
        list_frame = ttk.LabelFrame(right, text="Objects / Bounding Boxes")
        list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.object_list = tk.Listbox(
            list_frame,
            bg="#292e37",
            fg="white",
            selectbackground="#247caa",
            font=("Consolas", 10),
            height=10
        )
        self.object_list.pack(fill="both", expand=True, padx=5, pady=5)
        self.object_list.bind("<<ListboxSelect>>", self.list_select)

        # Properties
        props = ttk.LabelFrame(right, text="Selected Box Properties")
        props.pack(fill="x", padx=4, pady=4)

        self.label_var = tk.StringVar(value="object")
        self.desc_var = tk.StringVar()
        self.text_var = tk.StringVar()
        self.x_var = tk.StringVar(value="100")
        self.y_var = tk.StringVar(value="100")
        self.w_var = tk.StringVar(value="200")
        self.h_var = tk.StringVar(value="200")

        self.add_field(props, "Label / Type", self.label_var, 0)
        self.add_field(props, "Description", self.desc_var, 1)
        self.add_field(props, "Rendered Text", self.text_var, 2)
        self.add_field(props, "X", self.x_var, 3)
        self.add_field(props, "Y", self.y_var, 4)
        self.add_field(props, "Width", self.w_var, 5)
        self.add_field(props, "Height", self.h_var, 6)

        ttk.Button(
            props, text="Apply Properties",
            command=self.apply_properties
        ).grid(row=7, column=0, columnspan=2,
               sticky="ew", padx=5, pady=5)

        # JSON editor
        json_frame = ttk.LabelFrame(right, text="JSON Prompt Editor")
        json_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.json_editor = tk.Text(
            json_frame,
            bg="#171b22",
            fg="#a8e6cf",
            insertbackground="white",
            font=("Consolas", 10),
            wrap="none",
            undo=True
        )
        self.json_editor.pack(fill="both", expand=True, padx=5, pady=5)

        json_buttons = ttk.Frame(json_frame)
        json_buttons.pack(fill="x", padx=5, pady=4)

        ttk.Button(json_buttons, text="Apply JSON",
                   command=self.apply_json).pack(side="left", padx=3)

        ttk.Button(json_buttons, text="Format JSON",
                   command=self.refresh_json).pack(side="left", padx=3)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status).pack(
            fill="x", padx=10, pady=5)

    def add_field(self, parent, label, variable, row):
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=5, pady=3)
        parent.columnconfigure(1, weight=1)

    # ---------------- Coordinates ----------------

    def get_transform(self):
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        self.scale = min(
            (cw - 30) / self.width,
            (ch - 30) / self.height
        )

        self.offset_x = (cw - self.width * self.scale) / 2
        self.offset_y = (ch - self.height * self.scale) / 2

    def screen_to_image(self, x, y):
        self.get_transform()
        ix = (x - self.offset_x) / self.scale
        iy = (y - self.offset_y) / self.scale
        return ix, iy

    def image_to_screen(self, x, y):
        return (
            self.offset_x + x * self.scale,
            self.offset_y + y * self.scale
        )

    def export_bbox(self, item):
        x, y, w, h = item["bbox"]

        # Centered pixel coordinates, yxyx order
        return [
            round(y - self.height / 2),
            round(x - self.width / 2),
            round(y + h - self.height / 2),
            round(x + w - self.width / 2)
        ]

    def import_bbox(self, bbox):
        ymin, xmin, ymax, xmax = bbox
        return [
            xmin + self.width / 2,
            ymin + self.height / 2,
            xmax - xmin,
            ymax - ymin
        ]

    # ---------------- Drawing ----------------

    def redraw(self):
        self.canvas.delete("all")
        self.get_transform()

        x0, y0 = self.image_to_screen(0, 0)
        x1, y1 = self.image_to_screen(self.width, self.height)

        self.canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#eeeeee", outline="#ffffff"
        )

        if self.image is not None:
            self.draw_background()

        for i, item in enumerate(self.items):
            x, y, w, h = item["bbox"]
            sx, sy = self.image_to_screen(x, y)
            ex, ey = self.image_to_screen(x + w, y + h)

            color = "#00bfff"
            if item["label"] in ("character", "person"):
                color = "#ffad42"
            elif item["label"] == "text":
                color = "#258cff"
            elif item["label"] == "object":
                color = "#aaaaaa"

            if i == self.selected:
                color = "#ff3355"

            self.canvas.create_rectangle(
                sx, sy, ex, ey,
                outline=color,
                width=3 if i == self.selected else 2
            )

            self.canvas.create_text(
                sx + 5, sy + 5,
                text=item["label"],
                anchor="nw",
                fill=color,
                font=("Arial", 10, "bold")
            )

            if i == self.selected:
                size = 8
                self.canvas.create_rectangle(
                    ex-size, ey-size, ex+size, ey+size,
                    fill="#ff3355", outline="white"
                )

        self.canvas.tag_raise("overlay")

    def draw_background(self):
        if self.image is None:
            return

        self.get_transform()
        resized = self.image.resize((
            max(1, int(self.width * self.scale)),
            max(1, int(self.height * self.scale))
        ))

        self.photo = ImageTk.PhotoImage(resized)

        self.canvas.create_image(
            self.offset_x, self.offset_y,
            image=self.photo, anchor="nw"
        )

        self.canvas.tag_lower(self.canvas.find_all()[-1])

    # ---------------- Mouse interaction ----------------

    def mouse_down(self, event):
        self.canvas.focus_set()
        ix, iy = self.screen_to_image(event.x, event.y)

        if not (0 <= ix <= self.width and 0 <= iy <= self.height):
            return

        self.drag_start = (ix, iy)
        self.drag_mode = None

        if self.selected is not None:
            item = self.items[self.selected]
            x, y, w, h = item["bbox"]

            # Resize handle
            if abs(ix - (x+w)) < 15 and abs(iy - (y+h)) < 15:
                self.drag_mode = "resize"
                self.drag_original = item["bbox"][:]
                return

        # Find box under cursor, topmost first
        for i in reversed(range(len(self.items))):
            x, y, w, h = self.items[i]["bbox"]

            if x <= ix <= x+w and y <= iy <= y+h:
                self.selected = i
                self.drag_mode = "move"
                self.drag_original = self.items[i]["bbox"][:]
                self.update_properties()
                self.update_list()
                self.redraw()
                return

        # Empty canvas: start drawing
        self.selected = None
        self.drag_mode = "draw"
        self.drawing_start = (ix, iy)
        self.redraw()

    def mouse_move(self, event):
        if not self.drag_mode or not self.drag_start:
            return

        ix, iy = self.screen_to_image(event.x, event.y)
        sx, sy = self.drag_start

        if self.drag_mode == "draw":
            self.redraw()
            ax, ay = self.image_to_screen(sx, sy)
            bx, by = self.image_to_screen(ix, iy)
            self.canvas.create_rectangle(
                ax, ay, bx, by,
                outline="#ff3355", dash=(4, 3), width=2
            )

        elif self.drag_mode == "move":
            item = self.items[self.selected]
            ox, oy, w, h = self.drag_original
            nx = ox + ix - sx
            ny = oy + iy - sy

            nx = max(0, min(self.width-w, nx))
            ny = max(0, min(self.height-h, ny))

            item["bbox"] = [nx, ny, w, h]
            self.redraw()

        elif self.drag_mode == "resize":
            item = self.items[self.selected]
            ox, oy, _, _ = self.drag_original

            w = max(5, min(self.width-ox, ix-ox))
            h = max(5, min(self.height-oy, iy-oy))

            item["bbox"] = [ox, oy, w, h]
            self.redraw()

    def mouse_up(self, event):
        if not self.drag_mode:
            return

        ix, iy = self.screen_to_image(event.x, event.y)
        sx, sy = self.drag_start

        if self.drag_mode == "draw":
            x1, x2 = sorted((sx, ix))
            y1, y2 = sorted((sy, iy))

            w = x2-x1
            h = y2-y1

            if w > 4 and h > 4:
                self.items.append({
                    "label": "object",
                    "caption": "Describe this object",
                    "bbox": [x1, y1, w, h]
                })
                self.selected = len(self.items)-1
                self.update_properties()

        self.drag_mode = None
        self.drag_start = None
        self.drag_original = None

        self.update_list()
        self.refresh_json()
        self.redraw()

    # ---------------- Object management ----------------

    def add_box(self):
        self.items.append({
            "label": "object",
            "caption": "New object",
            "bbox": [
                self.width/2-100,
                self.height/2-100,
                200, 200
            ]
        })
        self.selected = len(self.items)-1
        self.update_list()
        self.update_properties()
        self.refresh_json()
        self.redraw()

    def delete_box(self):
        if self.selected is None:
            return

        del self.items[self.selected]
        self.selected = None

        self.update_list()
        self.clear_properties()
        self.refresh_json()
        self.redraw()

    def update_list(self):
        self.object_list.delete(0, "end")

        for i, item in enumerate(self.items):
            x, y, w, h = item["bbox"]
            caption = item.get("caption", "")
            self.object_list.insert(
                "end",
                f"{i+1}. [{item['label']}] "
                f"{caption[:28]} ({int(x)},{int(y)})"
            )

        if self.selected is not None:
            self.object_list.selection_set(self.selected)

    def list_select(self, event=None):
        selection = self.object_list.curselection()
        if not selection:
            return

        self.selected = selection[0]
        self.update_properties()
        self.redraw()

    def update_properties(self):
        if self.selected is None:
            return

        item = self.items[self.selected]
        x, y, w, h = item["bbox"]

        self.label_var.set(item["label"])
        self.desc_var.set(item.get("caption", ""))
        self.text_var.set(item.get("text", ""))

        self.x_var.set(str(round(x)))
        self.y_var.set(str(round(y)))
        self.w_var.set(str(round(w)))
        self.h_var.set(str(round(h)))

    def clear_properties(self):
        for var in (
            self.label_var, self.desc_var, self.text_var,
            self.x_var, self.y_var, self.w_var, self.h_var
        ):
            var.set("")

    def apply_properties(self):
        if self.selected is None:
            return

        try:
            x = float(self.x_var.get())
            y = float(self.y_var.get())
            w = float(self.w_var.get())
            h = float(self.h_var.get())

            if w <= 0 or h <= 0:
                raise ValueError("Width and height must be positive.")

            if x < 0 or y < 0 or x+w > self.width or y+h > self.height:
                raise ValueError("Box must fit inside the canvas.")

            item = self.items[self.selected]
            item["label"] = self.label_var.get().strip() or "object"
            item["caption"] = self.desc_var.get()
            item["bbox"] = [x, y, w, h]

            text = self.text_var.get()
            if text:
                item["text"] = text
            else:
                item.pop("text", None)

            self.update_list()
            self.refresh_json()
            self.redraw()

        except ValueError as e:
            messagebox.showerror("Invalid properties", str(e))

    def edit_text_item(self, event):
        ix, iy = self.screen_to_image(event.x, event.y)

        for i in reversed(range(len(self.items))):
            x, y, w, h = self.items[i]["bbox"]
            if x <= ix <= x+w and y <= iy <= y+h:
                self.selected = i
                self.update_properties()

                if self.items[i]["label"] == "text":
                    self.canvas.after(50, lambda: self.text_var.set(
                        self.items[i].get("text", "")
                    ))
                break

    # ---------------- JSON generation ----------------

    def generate_json(self):
        try:
            meta = [
                tag.strip() for tag in self.meta.get().split(",")
                if tag.strip()
            ]

            data = {
                "summary": {
                    "meta": meta,
                    "canvas": "single",
                    "caption": self.caption.get()
                },
                "items": [],
                "bbox_coord_space": "abs_centralized",
                "bbox_format": "yxyx"
            }

            for item in self.items:
                obj = {
                    "label": item["label"],
                    "caption": item.get("caption", ""),
                    "bbox": self.export_bbox(item)
                }

                if "text" in item:
                    obj["text"] = item["text"]

                data["items"].append(obj)

            return data

        except Exception as e:
            messagebox.showerror("JSON Error", str(e))
            return None

    def refresh_json(self):
        data = self.generate_json()
        if data is None:
            return

        output = json.dumps(
            data, indent=2, ensure_ascii=False
        )

        self.json_editor.delete("1.0", "end")
        self.json_editor.insert("1.0", output)

        self.status.set(
            f"{len(self.items)} boxes | Canvas: "
            f"{self.width} × {self.height}"
        )

    def apply_json(self):
        try:
            data = json.loads(self.json_editor.get("1.0", "end"))

            if "items" not in data or not isinstance(data["items"], list):
                raise ValueError("JSON must contain an items list.")

            if data.get("bbox_format", "yxyx") != "yxyx":
                raise ValueError("Only yxyx bounding boxes are supported.")

            if data.get("bbox_coord_space", "abs_centralized") != "abs_centralized":
                raise ValueError("Only abs_centralized coordinates are supported.")

            summary = data.get("summary", {})
            self.caption.set(summary.get("caption", ""))
            self.meta.set(", ".join(summary.get("meta", [])))

            converted = []

            for obj in data["items"]:
                bbox = obj.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    raise ValueError("Each item needs four bbox coordinates.")

                x, y, w, h = self.import_bbox(bbox)

                if w <= 0 or h <= 0:
                    raise ValueError("Bounding boxes must have positive dimensions.")

                if x < 0 or y < 0 or x+w > self.width or y+h > self.height:
                    raise ValueError("A bounding box is outside the canvas.")

                item = {
                    "label": obj.get("label", "object"),
                    "caption": obj.get("caption", ""),
                    "bbox": [x, y, w, h]
                }

                if "text" in obj:
                    item["text"] = obj["text"]

                converted.append(item)

            self.items = converted
            self.selected = None

            self.update_list()
            self.clear_properties()
            self.refresh_json()
            self.redraw()

            self.status.set("JSON successfully applied.")

        except Exception as e:
            messagebox.showerror("Invalid JSON", str(e))

    # ---------------- Files ----------------

    def save_json(self):
        data = self.generate_json()
        if data is None:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")]
        )

        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.status.set(f"Saved: {os.path.basename(path)}")

        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def load_json(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")]
        )

        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Read dimensions from the current project settings.
            self.apply_json_data(data)

            self.status.set(f"Loaded: {os.path.basename(path)}")

        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    def apply_json_data(self, data):
        summary = data.get("summary", {})
        self.caption.set(summary.get("caption", ""))
        self.meta.set(", ".join(summary.get("meta", [])))

        if data.get("bbox_format", "yxyx") != "yxyx":
            raise ValueError("Unsupported bounding box format.")

        if data.get("bbox_coord_space", "abs_centralized") != "abs_centralized":
            raise ValueError("Unsupported coordinate space.")

        new_items = []

        for obj in data.get("items", []):
            x, y, w, h = self.import_bbox(obj["bbox"])

            if w <= 0 or h <= 0:
                raise ValueError("Invalid bounding box dimensions.")

            if x < 0 or y < 0 or x+w > self.width or y+h > self.height:
                raise ValueError("A box exceeds the current canvas dimensions.")

            item = {
                "label": obj.get("label", "object"),
                "caption": obj.get("caption", ""),
                "bbox": [x, y, w, h]
            }

            if "text" in obj:
                item["text"] = obj["text"]

            new_items.append(item)

        self.items = new_items
        self.selected = None

        self.update_list()
        self.clear_properties()
        self.refresh_json()
        self.redraw()

    def export_json(self):
        data = self.generate_json()
        if data is None:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")]
        )

        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.status.set("JSON exported successfully.")

    def copy_prompt(self):
        data = self.generate_json()
        if data is None:
            return

        output = json.dumps(data, ensure_ascii=False)

        self.root.clipboard_clear()
        self.root.clipboard_append(output)
        self.root.update()

        self.status.set("JSON prompt copied to clipboard!")

    # ---------------- Image / canvas ----------------

    def load_image(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All Files", "*.*")
            ]
        )

        if not path:
            return

        try:
            if PIL_AVAILABLE:
                self.image = Image.open(path).convert("RGB")
                self.width, self.height = self.image.size
            else:
                self.image = tk.PhotoImage(file=path)
                self.width = self.image.width()
                self.height = self.image.height()

            self.image_path = path
            self.canvas_width.set(str(self.width))
            self.canvas_height.set(str(self.height))

            self.redraw()
            self.refresh_json()

            self.status.set(
                f"Image loaded: {os.path.basename(path)}"
            )

        except Exception as e:
            messagebox.showerror(
                "Image Error",
                "Could not load image. Install Pillow for JPEG/WebP support.\n\n"
                + str(e)
            )

    def apply_dimensions(self):
        try:
            w = int(self.canvas_width.get())
            h = int(self.canvas_height.get())

            if not (1 <= w <= 8192 and 1 <= h <= 8192):
                raise ValueError("Dimensions must be between 1 and 8192.")

            self.width = w
            self.height = h

            self.image = None
            self.image_path = None

            self.redraw()
            self.refresh_json()

        except ValueError as e:
            messagebox.showerror("Dimension Error", str(e))

    def new_project(self):
        if not messagebox.askyesno(
            "New Project", "Clear the current project?"
        ):
            return

        self.items = []
        self.selected = None
        self.caption.set("")
        self.meta.set("")
        self.image = None
        self.image_path = None

        self.width = 1024
        self.height = 1024
        self.canvas_width.set("1024")
        self.canvas_height.set("1024")

        self.update_list()
        self.clear_properties()
        self.refresh_json()
        self.redraw()


if __name__ == "__main__":
    root = tk.Tk()
    app = BBoxStudio(root)
    root.mainloop()
