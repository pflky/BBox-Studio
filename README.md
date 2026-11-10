


<img width="1322" height="892" alt="image" src="https://github.com/user-attachments/assets/8c5c4dd7-4df4-45e1-b3d8-edc97750d3de" />

A feature-rich, intuitive, standalone bounding box prompt generator for MOSS Image.

One-click launch – Simply run the application.

Zero dependencies – Requires only Python. No additional packages or installations needed.


What's New in This Version?

💾 Project Files & State Recovery

Added the ability to save projects as .bbox files.

Project files preserve application states, including custom bounding box colors and other settings.

Undo / Redo history is also saved directly into project files.

Full undo history preservation: You can save your entire undo history, all the way back to the very beginning of a project, and restore it when reopening the file.

↩️ Undo & Redo

Added Undo and Redo functionality.

All undo and redo states are stored in memory.

Undo history persists between sessions when saved in a .bbox project file.

📝 Improved Text Fields

Added the ability to vertically resize right-panel text fields by dragging the resize bar beneath them.

📐 Resolution & Dimensions

Simplified the editable Width / Height controls.

Preset resolution dropdowns remain directly editable, allowing you to enter custom dimensions.

🎨 UI Improvements

Rearranged and polished various UI elements.

Improved overall layout and usability.

🔒 Bounding Box Locks

Added new bounding box behavior locks:

Position Lock – Prevents a bounding box from being moved.

Size Lock – Prevents resizing.

Aspect Ratio Lock – Maintains the bounding box's aspect ratio when resizing.

Note: Bounding boxes will still automatically adjust when colliding with the canvas boundaries, regardless of lock settings.

🖱️ Canvas Right-Click Menu

Added several new options accessible by right-clicking the canvas:

Change the canvas background, including using an image.

Switch between different grid styles.

Adjust canvas scaling options.

Recenter the canvas.

Experimental Feature – Custom Background Images

The ability to use an image as the canvas background is still a work in progress. While functional, it currently introduces a performance hit when zooming in and out of the canvas. This may be optimized in future updates.
