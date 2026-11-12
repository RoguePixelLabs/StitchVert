import tkinter as tk
import webbrowser
from bisect import bisect_right
from copy import deepcopy
from itertools import accumulate, chain
from pathlib import Path
from tempfile import TemporaryDirectory
from queue import Empty, SimpleQueue
from threading import Thread
from time import monotonic
from tkinter import colorchooser, filedialog, messagebox, ttk
from worksheet import write_worksheet
from updates import RELEASES_URL, VERSION, latest_update

from converter import (
    FORMATS, INPUTS, OUTPUTS, PALETTE_FORMATS, RGB_FORMATS, export_design, load_design,
)


PREVIEW_BACKGROUNDS = {
    "Blue": "#456984",
    "Red": "#a75a56",
    "Black": "#181a1c",
    "Yellow": "#e0c572",
    "White": "#f9f9f6",
    "Grey": "#41464b",
}


def luminance(color):
    channels = (byte / 255 for byte in bytes.fromhex(color[1:]))
    red, green, blue = (
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    )
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def apply_interface_colors(root):
    background = "#e9eef2"
    surface = "#f7f9fb"
    ink = "#223240"
    border = "#aebbc5"
    teal = "#156c65"
    hover = "#dceae8"
    disabled = "#5c6b77"

    root.configure(background=background)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=background, foreground=ink, bordercolor=border,
                    lightcolor=background, darkcolor=border, troughcolor="#d5dfe7",
                    selectbackground=teal, selectforeground="#ffffff")
    style.configure("TButton", background=surface, lightcolor=surface, darkcolor=surface,
                    focuscolor=teal)
    style.map("TButton", background=[("disabled", background), ("pressed", "#c6dedb"),
                                    ("active", hover)],
              foreground=[("disabled", disabled)])
    style.configure("Accent.TButton", background=teal, foreground="#ffffff",
                    bordercolor=teal, lightcolor=teal, darkcolor=teal, focuscolor="#b9e7dc")
    style.map("Accent.TButton",
              background=[("disabled", background), ("pressed", "#0d4c46"), ("active", "#115b54")],
              foreground=[("disabled", disabled)],
              bordercolor=[("disabled", border)])
    style.configure("TCombobox", fieldbackground=surface, background=surface, arrowcolor=teal)
    style.map("TCombobox", fieldbackground=[("disabled", background), ("readonly", surface)],
              foreground=[("disabled", disabled)], selectbackground=[("readonly", surface)],
              selectforeground=[("readonly", ink)])
    style.configure("Treeview", background=surface, fieldbackground=surface, foreground=ink)
    style.map("Treeview", background=[("selected", "#d3e9e5")],
              foreground=[("selected", "#123e39")])
    style.configure("Treeview.Heading", background="#dce5eb", lightcolor="#dce5eb")
    style.map("Treeview.Heading", background=[("active", "#dce5eb")])
    style.configure("Horizontal.TScale", background=teal, lightcolor=teal, darkcolor=teal)
    style.map("Horizontal.TScale", background=[("disabled", border), ("active", "#115b54")])
    root.option_add("*TCombobox*Listbox.background", surface)
    root.option_add("*TCombobox*Listbox.foreground", ink)
    root.option_add("*TCombobox*Listbox.selectBackground", teal)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")


class ConverterWindow:
    def __init__(self, root):
        self.root = root
        self.update_result = None
        apply_interface_colors(root)
        self.design = self.source = None
        self.job = None
        self.playback_complete = False
        self.playback_time = 0.0
        self.stitch_credit = 0.0
        self.position = 0
        self.run_ends = []
        self.paths = []
        self.path_view = None
        self.last_segment = None
        self.segment_items = ()
        self.worksheet_directory = None
        self.worksheet_number = 0
        self.paint_job = None
        self.original_threads = []
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.drag_point = None
        self.seek_value = tk.DoubleVar()
        self.zoom_value = tk.StringVar(value="100%")
        self.preview_background = tk.StringVar(value="White")
        self.preview_luminance = luminance(PREVIEW_BACKGROUNDS["White"])
        self.format = tk.StringVar(value="PES")
        self.speed = tk.StringVar(value="6000")
        self.filename = tk.StringVar(value="Choose an embroidery file")
        self.status = tk.StringVar()
        self.details = tk.StringVar()
        self.progress = tk.StringVar()
        self.color_info = tk.StringVar()

        menu = tk.Menu(root)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Check for updates…", command=self.check_updates)
        help_menu.add_command(label="About StitchVert", command=self.show_version)
        menu.add_cascade(label="Help", menu=help_menu)
        root.configure(menu=menu)
        root.title("StitchVert")
        root.geometry("1050x700")
        root.resizable(True, True)
        root.minsize(600, 400)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(root, padding=(16, 16, 16, 12))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Button(toolbar, text="Open file…", command=self.open_file).grid(row=0, column=0)
        ttk.Label(toolbar, textvariable=self.filename, width=16).grid(row=0, column=1, padx=12, sticky="ew")
        ttk.Label(toolbar, text="Output format").grid(row=0, column=2, padx=(12, 8))
        formats = ttk.Combobox(toolbar, textvariable=self.format,
                               values=[ext.upper() for ext in OUTPUTS], width=9, state="readonly")
        formats.grid(row=0, column=3)
        formats.bind("<<ComboboxSelected>>", self.update_format)
        self.export_button = ttk.Button(toolbar, text="Export…", command=self.export,
                                        style="Accent.TButton", state="disabled")
        self.export_button.grid(row=0, column=4, padx=(10, 0))
        self.print_button = ttk.Button(toolbar, text="Print preview…", command=self.print_preview,
                                       state="disabled")
        self.print_button.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(toolbar, textvariable=self.color_info).grid(row=1, column=2, columnspan=3, sticky="e", pady=(6, 0))

        body = ttk.Frame(root, padding=(16, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        preview_bar = ttk.Frame(body)
        preview_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(preview_bar, text="Stitch preview").pack(side="left")
        self.zoom_buttons = []
        for label, action in (("Fit", self.fit_preview), ("+", lambda: self.zoom_by(1.25)),
                              ("−", lambda: self.zoom_by(0.8))):
            button = ttk.Button(preview_bar, text=label, command=action, width=4, state="disabled")
            button.pack(side="right", padx=(4, 0))
            self.zoom_buttons.append(button)
        ttk.Label(preview_bar, textvariable=self.zoom_value).pack(side="right", padx=(8, 2))
        ttk.Label(body, text="Thread colors").grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 6))

        self.preview = tk.Canvas(body, background=PREVIEW_BACKGROUNDS["White"], highlightthickness=1,
                                 highlightbackground="#aebbc5")
        self.preview.grid(row=1, column=0, sticky="nsew")
        self.preview.bind("<Configure>", self.resize_preview)
        self.preview.bind("<MouseWheel>", self.zoom_wheel)
        for button in (1, 2):
            self.preview.bind(f"<ButtonPress-{button}>", self.start_pan)
            self.preview.bind(f"<B{button}-Motion>", self.pan_preview)
            self.preview.bind(f"<ButtonRelease-{button}>", self.end_pan)

        background_controls = ttk.Frame(body)
        background_controls.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(background_controls, text="Preview background").pack(side="left", padx=(0, 6))
        background_picker = ttk.Combobox(background_controls, textvariable=self.preview_background,
                                         values=tuple(PREVIEW_BACKGROUNDS), state="readonly", width=10)
        background_picker.pack(side="left")
        background_picker.bind("<<ComboboxSelected>>", self.change_preview_background)

        sidebar = ttk.Frame(body)
        sidebar.grid(row=1, column=1, sticky="nsew", padx=(14, 0))
        sidebar.rowconfigure(0, weight=1)
        sidebar.columnconfigure(0, weight=1)
        self.colors = ttk.Treeview(sidebar, columns=("step", "color"), show="tree headings",
                                   selectmode="browse", height=10)
        self.colors.heading("#0", text="")
        self.colors.heading("step", text="Thread")
        self.colors.heading("color", text="Color")
        self.colors.column("#0", width=34, stretch=False)
        self.colors.column("step", width=87, stretch=False)
        self.colors.column("color", width=92, stretch=False)
        self.colors.grid(row=0, column=0, sticky="nsew")
        self.colors.bind("<Double-1>", self.edit_selected_row)
        self.colors.bind("<Return>", self.edit_color)
        self.colors.bind("<<TreeviewSelect>>", self.update_color_button)
        scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.colors.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.colors.configure(yscrollcommand=scroll.set)
        self.swatches = {}
        color_actions = ttk.Frame(sidebar)
        color_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.color_button = ttk.Button(color_actions, text="Change color…", command=self.edit_color,
                                       state="disabled")
        self.color_button.pack(side="left", fill="x", expand=True)
        self.reset_button = ttk.Button(color_actions, text="Reset colors", command=self.reset_colors,
                                       state="disabled")
        self.reset_button.pack(side="left", padx=(6, 0))

        playback = ttk.Frame(root, padding=(16, 12, 16, 4))
        playback.grid(row=2, column=0, sticky="ew")
        self.play_button = ttk.Button(playback, text="Play", command=self.toggle,
                                      style="Accent.TButton", state="disabled")
        self.play_button.pack(side="left")
        self.stop_button = ttk.Button(playback, text="Stop", command=self.stop_playback, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 16))
        ttk.Label(playback, text="Stitches/min").pack(side="left", padx=(0, 6))
        self.speed_control = ttk.Combobox(playback, width=7, textvariable=self.speed, state="disabled",
                                          values=("300", "600", "1200", "3000", "6000", "12000", "30000", "60000"))
        self.speed_control.pack(side="left")
        ttk.Label(playback, textvariable=self.progress).pack(side="right")
        self.timeline = ttk.Scale(root, from_=0, to=1, variable=self.seek_value,
                                  command=self.seek, state="disabled", takefocus=True)
        self.timeline.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 0))
        footer = ttk.Frame(root, padding=(16, 4, 16, 12))
        footer.grid(row=4, column=0, sticky="ew")
        ttk.Sizegrip(footer).pack(side="right")
        ttk.Label(footer, textvariable=self.details).pack(side="right", padx=(8, 6))
        ttk.Label(footer, textvariable=self.status, width=1).pack(side="left", fill="x", expand=True)
        root.bind("<Control-o>", lambda _: self.open_file())
        root.bind("<Control-p>", lambda _: self.print_preview())
        self.update_format()
        self.redraw()

    def show_version(self):
        messagebox.showinfo("About StitchVert", f"StitchVert {VERSION}", parent=self.root)

    def check_updates(self):
        if self.update_result is not None:
            return
        self.update_result = SimpleQueue()
        self.status.set("Checking GitHub for updates…")
        Thread(target=self.fetch_update, args=(self.update_result,), daemon=True).start()
        self.root.after(100, self.finish_update_check)

    @staticmethod
    def fetch_update(result):
        try:
            result.put((latest_update(), None))
        except (OSError, ValueError, AttributeError) as error:
            result.put((None, str(error)))

    def finish_update_check(self):
        try:
            version, error = self.update_result.get_nowait()
        except Empty:
            self.root.after(100, self.finish_update_check)
            return
        self.update_result = None
        if error:
            self.status.set("Update check failed")
            messagebox.showerror("StitchVert updates", error, parent=self.root)
        elif version is None:
            self.status.set(f"StitchVert {VERSION} is up to date")
            messagebox.showinfo("StitchVert updates", f"You have the latest version ({VERSION}).",
                                parent=self.root)
        else:
            self.status.set(f"StitchVert {version} is available")
            if messagebox.askyesno("StitchVert updates", f"Version {version} is available. Open GitHub releases?",
                                   parent=self.root):
                webbrowser.open(RELEASES_URL)

    def update_format(self, _event=None):
        ext = self.format.get().lower()
        note = "Stores edited thread colors"
        if ext in PALETTE_FORMATS:
            note = "Maps colors to the machine palette"
        elif ext not in RGB_FORMATS:
            note = "Keeps thread changes without RGB colors"
        self.color_info.set(note)

    def open_file(self):
        filetypes = [("Embroidery files", " ".join(f"*.{ext}" for ext in INPUTS))]
        filetypes.extend((f"{ext.upper()} files", f"*.{ext}") for ext in INPUTS)
        filename = filedialog.askopenfilename(parent=self.root, filetypes=filetypes)
        if not filename:
            return
        source = Path(filename)
        try:
            design = load_design(source)
        except Exception as error:
            messagebox.showerror("Could not open design", str(error), parent=self.root)
            return
        self.pause()
        self.design, self.source = design, source
        self.original_threads = deepcopy(design.pattern.threadlist)
        self.reset_button.configure(state="disabled")
        self.fit_preview()
        self.timeline.configure(to=design.count, state="normal")
        self.speed_control.configure(state="readonly")
        self.run_ends = list(accumulate(len(points) - 1 for _, points in design.runs))
        self.filename.set(source.name)
        self.root.title(f"{source.name}  |  StitchVert")
        left, top, right, bottom = design.bounds
        self.details.set(f"{(right-left)/10:.1f} × {(bottom-top)/10:.1f} mm")
        self.status.set("Preview colors assigned where thread data is missing" if design.estimated else "")
        self.colors.delete(*self.colors.get_children())
        self.swatches.clear()
        for step, index in enumerate(design.used_threads, 1):
            self.colors.insert("", "end", iid=str(index))
            self.update_thread(index, step)
        for button in (self.play_button, self.stop_button, self.export_button, self.print_button,
                       *self.zoom_buttons):
            button.configure(state="normal")
        self.update_color_button()
        self.stop_playback()

    def update_thread(self, index, step):
        color = self.design.pattern.threadlist[index].hex_color().upper()
        swatch = tk.PhotoImage(width=16, height=16)
        swatch.put(color, to=(0, 0, 16, 16))
        self.swatches[index] = swatch
        self.colors.item(str(index), image=swatch, values=(step, color))

    def update_color_button(self, _event=None):
        self.color_button.configure(state="normal" if self.colors.selection() else "disabled")

    def edit_selected_row(self, event):
        if self.colors.identify_row(event.y):
            self.edit_color()

    def edit_color(self, _event=None):
        if not self.colors.selection():
            return
        self.pause()
        item = self.colors.selection()[0]
        index = int(item)
        thread = self.design.pattern.threadlist[index]
        _, color = colorchooser.askcolor(thread.hex_color(), title="Thread color", parent=self.root)
        if color:
            # Readers may share palette entries across multiple steps.
            from pyembroidery import EmbThread
            self.design.pattern.threadlist[index] = EmbThread(color)
            self.update_thread(index, self.colors.item(item, "values")[0])
            self.reset_button.configure(state="normal")
            self.redraw()

    def reset_colors(self):
        self.design.pattern.threadlist = deepcopy(self.original_threads)
        for step, index in enumerate(self.design.used_threads, 1):
            self.update_thread(index, step)
        self.reset_button.configure(state="disabled")
        self.redraw()

    def print_preview(self):
        if self.design is None:
            return
        try:
            if self.worksheet_directory is None:
                self.worksheet_directory = TemporaryDirectory(prefix="embroidery-worksheet-")
            self.worksheet_number += 1
            destination = Path(self.worksheet_directory.name, f"worksheet-{self.worksheet_number}.html")
            write_worksheet(self.design, self.source.name, destination)
            if not webbrowser.open(destination.as_uri()):
                raise OSError("Windows could not open the worksheet in your default browser.")
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not open print preview", str(error), parent=self.root)

    def export(self):
        self.pause()
        ext = self.format.get().lower()
        output = filedialog.asksaveasfilename(
            parent=self.root, initialdir=self.source.parent,
            initialfile=f"{self.source.stem}-converted.{ext}", defaultextension=f".{ext}",
            filetypes=[(FORMATS[ext]["description"], f"*.{ext}")],
        )
        if not output:
            return
        destination = Path(output)
        try:
            if destination.suffix.lower() != f".{ext}":
                raise ValueError(f"Use a .{ext} filename for the selected output format.")
            if destination.resolve() == self.source.resolve():
                raise ValueError("Choose a different filename to keep the original file.")
            export_design(self.design, destination)
        except Exception as error:
            messagebox.showerror("Could not export design", str(error), parent=self.root)
            return
        self.status.set(f"Exported {destination.name}")

    def change_preview_background(self, _event=None):
        color = PREVIEW_BACKGROUNDS[self.preview_background.get()]
        self.preview_luminance = luminance(color)
        self.preview.configure(background=color)
        self.redraw()

    def fit_preview(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.zoom_value.set("100%")
        self.queue_redraw()

    def zoom_by(self, factor, x=None, y=None):
        if self.design is None:
            return
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        center_x, center_y = width / 2, height / 2
        x = center_x if x is None else x
        y = center_y if y is None else y
        new_zoom = min(16, max(0.25, self.zoom * factor))
        ratio = new_zoom / self.zoom
        self.pan_x = x - center_x + (self.pan_x + center_x - x) * ratio
        self.pan_y = y - center_y + (self.pan_y + center_y - y) * ratio
        self.zoom = new_zoom
        self.zoom_value.set(f"{self.zoom:.0%}")
        self.queue_redraw()

    def zoom_wheel(self, event):
        self.zoom_by(1.25 ** (event.delta / 120), event.x, event.y)
        return "break"

    def start_pan(self, event):
        if self.design is not None:
            self.drag_point = (event.x, event.y)

    def pan_preview(self, event):
        if self.drag_point is not None:
            x, y = self.drag_point
            dx, dy = event.x - x, event.y - y
            self.pan_x += dx
            self.pan_y += dy
            self.drag_point = (event.x, event.y)
            self.preview.move("all", dx, dy)

    def end_pan(self, _event):
        self.drag_point = None

    def resize_preview(self, _event):
        if self.paint_job is not None:
            self.root.after_cancel(self.paint_job)
        self.paint_job = self.root.after(45, self.redraw)

    def queue_redraw(self):
        if self.paint_job is None:
            self.paint_job = self.root.after_idle(self.redraw)

    def redraw(self):
        if self.paint_job is not None:
            self.root.after_cancel(self.paint_job)
            self.paint_job = None
        self.preview.delete("all")
        self.last_segment = None
        self.segment_items = ()
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        if not self.design:
            self.preview.create_text(width / 2, height / 2, text="Open an embroidery file to preview it",
                                     fill="#f2f3f4" if self.preview_luminance < 0.25 else "#263542",
                                     font=("Segoe UI", 12))
            return
        left, top, right, bottom = self.design.bounds
        dx, dy = right - left, bottom - top
        scale = min(max(width - 64, 1) / max(dx, 1), max(height - 64, 1) / max(dy, 1), 25)
        scale *= self.zoom
        offset_x = (width - dx * scale) / 2 - left * scale
        offset_y = (height - dy * scale) / 2 - top * scale
        view = (id(self.design), scale, offset_x, offset_y)
        if view != self.path_view:
            self.paths = [
                [(x * scale + offset_x, y * scale + offset_y) for x, y in points]
                for _, points in self.design.runs
            ]
            self.path_view = view
        self.paint(0, self.position)
        self.update_progress()

    def paint(self, start, end):
        run_number = bisect_right(self.run_ends, start)
        while start < end:
            run_end = self.run_ends[run_number]
            run_start = self.run_ends[run_number - 1] if run_number else 0
            limit = min(end, run_end)
            index, _ = self.design.runs[run_number]
            path = self.paths[run_number]
            color = self.design.pattern.threadlist[index].hex_color()
            foreground = luminance(color)
            background = self.preview_luminance
            contrast = (max(foreground, background) + 0.05) / (min(foreground, background) + 0.05)
            outline = ""
            if contrast < 2.5:
                outline = "#e7e9eb" if background < 0.25 else "#5a636d"
            offset = (start - run_start) // 1024 * 1024
            while offset < limit - run_start:
                stop = min(offset + 1024, limit - run_start)
                segment = (run_number, offset)
                items = self.segment_items if segment == self.last_segment else ()
                self.segment_items = self.draw_stitches(path[offset:stop + 1], color, outline, items)
                self.last_segment = segment
                offset += 1024
            start = limit
            run_number += 1

    def draw_stitches(self, points, color, outline, items):
        if len(points) == 2 and points[0] == points[1]:
            x, y = points[0]
            x += self.pan_x
            y += self.pan_y
            dot = self.preview.create_oval(x - 1, y - 1, x + 1, y + 1, fill=color,
                                           outline=outline)
            return (dot,)
        # Thick Canvas polylines repaint slowly on Windows. One-pixel
        # strokes and an offset outline keep the dense stitch preview responsive.
        strokes = ((outline, -1, 0), (outline, 1, 0), (outline, 0, -1), (outline, 0, 1)) if outline else ()
        strokes += ((color, 0, 0),)
        reuse = items and self.preview.type(items[0]) == "line"
        if not reuse:
            for item in items:
                self.preview.delete(item)
        lines = []
        for index, (stroke, dx, dy) in enumerate(strokes):
            offset_x, offset_y = self.pan_x + dx, self.pan_y + dy
            coordinates = tuple(chain.from_iterable((x + offset_x, y + offset_y) for x, y in points))
            if reuse:
                item = items[index]
                self.preview.coords(item, *coordinates)
            else:
                item = self.preview.create_line(*coordinates, fill=stroke, width=1)
            lines.append(item)
        return tuple(lines)

    def update_progress(self):
        self.seek_value.set(self.position)
        state = " · Complete" if self.playback_complete else ""
        self.progress.set(f"{self.position:,} / {self.design.count:,} stitches{state}")

    def seek(self, value):
        if self.design is None:
            return
        self.pause()
        self.playback_complete = False
        self.position = min(self.design.count, max(0, round(float(value))))
        self.play_button.configure(text="Resume" if 0 < self.position < self.design.count else "Play")
        self.update_progress()
        self.queue_redraw()

    def stop_playback(self):
        self.pause()
        self.playback_complete = False
        self.position = self.design.count
        self.play_button.configure(text="Play")
        self.redraw()

    def toggle(self):
        if self.job is not None:
            self.pause()
            return
        self.playback_complete = False
        if self.position == self.design.count:
            self.position = 0
        self.redraw()
        self.play_button.configure(text="Pause")
        self.playback_time = monotonic()
        self.stitch_credit = 1.0
        self.tick()

    def pause(self):
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
            self.play_button.configure(text="Resume")

    def tick(self):
        now = monotonic()
        stitches_per_second = int(self.speed.get()) / 60
        self.stitch_credit += (now - self.playback_time) * stitches_per_second
        self.playback_time = now
        ready = int(self.stitch_credit)
        if ready:
            end = min(self.design.count, self.position + ready)
            self.paint(self.position, end)
            self.position = end
            self.stitch_credit -= ready
        if self.position < self.design.count:
            self.job = self.root.after(33, self.tick)
        else:
            self.job = None
            self.playback_complete = True
            self.play_button.configure(text="Replay")
        if ready:
            self.update_progress()


if __name__ == "__main__":
    root = tk.Tk()
    ConverterWindow(root)
    root.mainloop()
