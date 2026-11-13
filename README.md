<img width="1322" height="892" alt="image" src="https://github.com/user-attachments/assets/fb19c4b1-0879-4b04-b80d-384bc88abf35" />





# BBox Studio

### A standalone, zero-dependency visual bounding box prompt editor for MOSS-Image

BBox Studio is a feature-rich, intuitive desktop application for creating, editing, and exporting structured bounding box prompts for MOSS-Image.

Built entirely with Python and Tkinter, BBox Studio provides a visual canvas-based annotation workspace, flexible object editing tools, customizable canvas settings, and seamless JSON generation — all without requiring external Python packages.

- **One-click launch** — simply run the Python script.
- **Zero external dependencies** — requires only Python with Tkinter support.
- **Visual-first workflow** — create and edit bounding boxes directly on the canvas.

---

## ✨ Features

### 🎯 Visual Bounding Box Editor

- **Interactive Canvas:** Create bounding boxes directly over a visual workspace.
- **Drag-to-Create:** Click and drag anywhere on the canvas to create a new bounding box.
- **Move & Resize:** Freely reposition and resize existing boxes using interactive selection handles.
- **Eight Resize Handles:** Precisely adjust box dimensions from corners and edges.
- **Double-Click Caption Editing:** Double-click any bounding box to edit its caption directly.
- **Multiple Objects:** Create and manage as many individual bounding boxes as needed.
- **Object Selection:** Select individual boxes to access their properties and editing controls.
- **Minimum Box Size:** Prevents boxes from becoming too small to work with.
- **Automatic Coordinate Clamping:** Keeps bounding boxes within the defined canvas boundaries.

### 🏷️ Object Types & Properties

Create and customize three types of annotation elements:

- **Objects**
- **Characters**
- **Text Elements**

Each bounding box supports:

- Custom labels and captions.
- Individual text content for text-type elements.
- Independent bounding box colors.
- Editable position and dimensions.
- Position and size locking.
- Aspect ratio locking.
- Individual object selection and inspection.

Additional object management tools:

- **Duplicate:** Quickly create a copy of an existing bounding box.
- **Delete:** Remove selected elements.
- **Bring to Front:** Change the drawing order of overlapping elements.
- **Lock Position/Size:** Prevent accidental movement or resizing.
- **Lock Aspect Ratio:** Maintain proportions when resizing.

### 🎨 Customization & Color Management

- **Individual Box Colors:** Every bounding box can have its own color.
- **Random Color Assignment:** New boxes receive distinct colors from a built-in palette.
- **Custom Color Picker:** Choose colors visually or enter custom hexadecimal color values.
- **Color Preview:** See the currently selected object's color.
- **Dark Interface:** A modern dark-themed workspace designed for comfortable editing.

### 🖼️ Canvas & Image Controls

- **Custom Canvas Resolution:** Specify independent canvas width and height values.
- **Resolution Presets:** Quickly select from commonly used image-generation resolutions.
- **Square, Portrait & Landscape Presets:** Presets are conveniently grouped by aspect ratio.
- **Automatic Image Dimensions:** Detect supported background image dimensions and automatically match the canvas resolution.
- **Background Image Import:** Load reference images directly into the annotation workspace.
- **Background Removal:** Remove the currently loaded reference image at any time.
- **Automatic Canvas Fitting:** Scale the workspace to fit the available window.
- **Zoom Controls:** Zoom in and out using the mouse wheel or keyboard shortcuts.
- **Zoom Presets:** Quickly switch between 50%, 100%, and 200% magnification.
- **Canvas Panning:** Navigate the workspace using middle-mouse dragging.
- **Snap to Grid:** A toggle that enables or disables snapping to current grid configuration.
- **Recenter Canvas:** Restore the canvas to a centered, fitted view.

### 📐 Canvas Guides & Grid Options

Choose from multiple built-in canvas guide styles:

- Default Grid
- Fine Grid
- Coarse Grid
- Dotted Grid
- Rule of Thirds
- Golden Ratio
- Center Cross
- No Grid

Grid patterns are centered around the canvas origin, providing consistent visual alignment references.

Grid settings can be changed through the canvas right-click context menu.

### 📋 MOSS-Image JSON Generation

Generate structured JSON prompts following the MOSS-Image bounding box layout format.

**Supported output structure includes:**

- Summary metadata.
- Canvas type.
- Overall composition caption.
- Individual annotated items.
- Object labels and captions.
- Text content for text elements.
- Bounding box coordinates.
- Coordinate space and format identifiers.

**Coordinate conventions:**

- `bbox_coord_space`: `abs_centralized`
- `bbox_format`: `yxyx`
- Coordinate origin: Canvas center.
- Y-axis: Increases downward.
- Bounding box order: `[y_min, x_min, y_max, x_max]`.

Additional JSON features:

- Pretty-printed JSON generation.
- Automatic JSON updates as annotations are edited.
- UTF-8 output with Unicode character support.
- Direct clipboard copying.
- Dedicated JSON export.

### 📂 Import, Export & Project Management

BBox Studio supports two different saving workflows.

**1. BBox Studio Projects (`.bbox`)**

Save and restore your complete annotation editing state.

Project files preserve:

- Canvas dimensions.
- Bounding box positions and dimensions.
- Object labels and captions.
- Individual object colors.
- Text content.
- Position and size lock settings.
- Aspect ratio lock settings.
- Summary metadata and canvas type.
- Canvas zoom and pan position.
- Undo/redo history.

This allows you to save your work and continue editing it later without losing important editor-specific information.

**2. MOSS-Image JSON (`.json`)**

Export the generated layout as a standalone JSON file for use with compatible MOSS-Image workflows.

Supported import capabilities include:

- Standard JSON layout files.
- `yxyx` and `xyxy` bounding box formats.
- Centered and absolute coordinate spaces.
- Automatic canvas dimension inference from bounding box coordinates.
- Extraction of embedded layout JSON from supported image metadata and text-based files.

**Embedded JSON extraction supports:**

- PNG text metadata (`tEXt` / `iTXt`).
- JPEG comment segments.
- Plain-text JSON content.

### ↩️ Undo & Redo

- Full undo and redo functionality.
- Up to 80 editing history states retained in memory.
- Automatic history tracking for supported editing operations.
- Undo/redo history is preserved inside saved `.bbox` project files.
- Restores object properties, colors, canvas dimensions, and other tracked editing states.

### ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + C` | Copy generated JSON |
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + S` | Save project |
| `Ctrl + O` | Load project |
| `Ctrl + R` | Reset workspace |
| `Delete` | Delete selected bounding box |
| `Escape` | Exit inline editing / deselect |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `← or →` | Cycle bounding box selection |
| Mouse Wheel | Zoom toward cursor |
| Middle Mouse Drag | Pan canvas |
| Double-Click Box | Edit box caption |
| Right-Click Canvas | Open canvas options |

### 🛠️ Additional Quality-of-Life Features

- Automatically centered application window on startup.
- Context-sensitive canvas controls.
- Live coordinate display when moving the mouse over the canvas.
- Automatic canvas scaling after resolution changes.
- Resizable text fields in the properties panel.
- Customizable metadata presets.
- Support for custom metadata entries.
- Multiple canvas types:
  - `single`
  - `multi_panel`
  - `collage`
- Reset workspace to default settings.
- Built-in About dialog and custom application logo.
- Status messages for important operations.

---

## 🚀 Getting Started

### Requirements

- Python 3.x
- Tkinter support

No third-party Python packages or additional installations are required.

### Running BBox Studio

1. Download or clone this repository.
2. Locate `bbox_studio.py`.
3. Run the following command:

```bash
python bbox_studio.py
```

The application will launch directly.

...Or just double click the .py file ya filthy animal! 

---

## 📁 Project Format

BBox Studio uses its own `.bbox` project format to preserve editing information that is not included in standard MOSS-Image JSON exports.

| Format | Purpose |
|---|---|
| `.bbox` | Editable BBox Studio project |
| `.json` | Standalone MOSS-Image layout export |

**Tip:** Use `.bbox` when you intend to continue editing your annotations later. Use `.json` when you want the generated prompt data for external workflows.

---

## 💡 Design Philosophy

BBox Studio was designed to make structured bounding box prompt creation as straightforward as possible.

Rather than manually writing coordinate values and constructing JSON layouts, users can visually arrange elements, customize their properties, and generate structured output automatically.

The goal is to provide a lightweight, self-contained annotation tool that is easy to launch, easy to use, and flexible enough for detailed image-layout prompting.

**No accounts. No subscriptions. No external packages. Just Python.**

---

## 📜 License & Credits

BBox Studio

Coded with Grok.

© 2026 — All rights reserved.
