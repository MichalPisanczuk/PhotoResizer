import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import UnidentifiedImageError

from optimizer import Options, SkippedImage, optimize


FORMATS = {"WebP": "WEBP", "JPG": "JPEG", "PNG": "PNG"}
FILE_TYPES = [
    ("Obrazy", "*.jpg *.jpeg *.jfif *.png *.webp *.bmp *.tif *.tiff *.gif *.ico *.jp2 *.ppm *.pgm"),
    ("Wszystkie pliki", "*.*"),
]


def file_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MiB".replace(".", ",")
    return f"{size / 1024:.1f} KiB".replace(".", ",")


class Resizer:
    def __init__(self, root):
        self.root = root
        self.files = {}
        self.events = queue.Queue()
        self.directory = tk.StringVar()
        self.mode = tk.StringVar(value="lossless")
        self.format = tk.StringVar(value="WebP")
        self.resize = tk.BooleanVar(value=True)
        self.quality = tk.IntVar(value=92)
        self.description = tk.StringVar()
        self.status = tk.StringVar(value="Dodaj zdjęcia i wybierz folder zapisu.")
        self.detail = tk.StringVar(value="Zaznacz zdjęcie, aby zobaczyć szczegóły.")
        self.details = {}
        self.busy = False

        root.title("Resizer — optymalizacja zdjęć")
        root.geometry("1010x730")
        root.minsize(810, 660)
        root.option_add("*Font", ("Segoe UI", 10))
        root.configure(background="#edf2f8")
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf2f8")
        style.configure("TLabel", background="#edf2f8", foreground="#18283e")
        style.configure("Muted.TLabel", foreground="#40536e")
        style.configure("Title.TLabel", font=("Segoe UI", 29, "bold"), foreground="#14243a")
        style.configure("TLabelframe", background="#edf2f8", bordercolor="#bfcddd")
        style.configure("TLabelframe.Label", background="#edf2f8", foreground="#18283e", font=("Segoe UI", 11, "bold"))
        for widget_style in ("TRadiobutton", "TCheckbutton", "TScale"):
            style.configure(widget_style, background="#edf2f8")
            style.map(widget_style, background=[("active", "#e1eaf5")])
        style.configure("TButton", padding=(12, 6), background="#f7f9fd", foreground="#18283e")
        style.configure("Primary.TButton", background="#1c57bb", foreground="white", padding=(17, 8))
        style.map("Primary.TButton", background=[("disabled", "#dce5f0"), ("pressed", "#18418a"), ("active", "#2466d1")],
                  foreground=[("disabled", "#536782")])
        style.configure("Treeview", rowheight=29, background="white", fieldbackground="white", foreground="#18283e")
        style.configure("Treeview.Heading", padding=(7, 6), background="#e3ecf8", foreground="#18283e")
        style.configure("Horizontal.TProgressbar", background="#1c57bb", troughcolor="#d9e4f2")

        main = ttk.Frame(root, padding=(24, 15, 24, 16))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        ttk.Label(main, text="Resizer", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main, text="Zmniejsz wagę zdjęć do wysyłki i na strony WWW.", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(0, 12))

        bar = ttk.Frame(main)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.add_button = ttk.Button(bar, text="Dodaj zdjęcia…", command=self.add_files)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(bar, text="Usuń zaznaczone", command=self.remove_files)
        self.remove_button.pack(side="left", padx=8)
        self.clear_button = ttk.Button(bar, text="Wyczyść listę", command=self.clear_files)
        self.clear_button.pack(side="left")

        table = ttk.Frame(main)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("before", "after", "size", "result"), show="tree headings", height=4)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        for column, label, width in (
            ("#0", "Zdjęcie", 320), ("before", "Przed", 90), ("after", "Po", 90),
            ("size", "Wymiary po", 110), ("result", "Wynik", 145),
        ):
            self.tree.heading(column, text=label, anchor="w")
            self.tree.column(column, width=width, minwidth=width if column != "#0" else 130,
                             stretch=column == "#0")
        self.tree.tag_configure("odd", background="#f3f7fc")
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        self.tree.bind("<Delete>", lambda event: self.remove_files())
        detail_label = ttk.Label(main, textvariable=self.detail, style="Muted.TLabel")
        detail_label.grid(row=4, column=0, sticky="ew", pady=(5, 9))
        detail_label.bind("<Configure>", lambda event: detail_label.configure(wraplength=event.width))

        settings = ttk.Labelframe(main, text=" Ustawienia zapisu ", padding=(12, 7, 12, 8))
        settings.grid(row=5, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)
        self.lossless_button = ttk.Radiobutton(settings, text="Bezstratny", value="lossless", variable=self.mode,
                                               command=self.refresh)
        self.lossless_button.grid(row=0, column=0, sticky="w", padx=(0, 15))
        self.web_button = ttk.Radiobutton(settings, text="WWW", value="web", variable=self.mode, command=self.refresh)
        self.web_button.grid(row=0, column=1, sticky="w")
        ttk.Label(settings, text="Format").grid(row=0, column=2, sticky="e", padx=(0, 8))
        self.format_box = ttk.Combobox(settings, values=list(FORMATS), textvariable=self.format, width=9, state="readonly")
        self.format_box.grid(row=0, column=3, sticky="e")
        self.format_box.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        settings_note = ttk.Label(settings, textvariable=self.description, style="Muted.TLabel")
        settings_note.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(5, 3))
        settings_note.bind("<Configure>", lambda event: settings_note.configure(wraplength=event.width))
        self.resize_box = ttk.Checkbutton(settings, text="Zmniejsz wymiary dużych zdjęć", variable=self.resize)
        self.resize_box.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(settings, text="Jakość JPG / WebP").grid(row=2, column=2, sticky="e", padx=(8, 8))
        self.quality_box = ttk.Spinbox(settings, from_=70, to=100, textvariable=self.quality, width=9,
                                       state="readonly", wrap=False)
        self.quality_box.grid(row=2, column=3, sticky="e")

        destination = ttk.Frame(main)
        destination.grid(row=6, column=0, sticky="ew", pady=(11, 8))
        destination.columnconfigure(1, weight=1)
        ttk.Label(destination, text="Folder zapisu").grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.directory_entry = ttk.Entry(destination, textvariable=self.directory)
        self.directory_entry.grid(row=0, column=1, sticky="ew")
        self.browse_button = ttk.Button(destination, text="Wybierz…", command=self.choose_directory)
        self.browse_button.grid(row=0, column=2, padx=(8, 0))

        footer = ttk.Frame(main)
        footer.grid(row=7, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 7))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.open_button = ttk.Button(footer, text="Otwórz folder", command=self.open_directory)
        self.open_button.grid(row=1, column=1, padx=8)
        self.start_button = ttk.Button(footer, text="Optymalizuj", command=self.start, style="Primary.TButton")
        self.start_button.grid(row=1, column=2)
        self.directory.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        lossless = self.mode.get() == "lossless"
        output = self.format.get()
        if lossless and output == "JPG":
            note = "Źródłowe JPG zostaną skopiowane bez zmian. Dla innych obrazów wybierz PNG lub WebP."
        elif lossless:
            note = "Zachowuje piksele i wymiary. Wybierz PNG, jeśli obraz wymaga więcej niż 8 bitów na kanał."
        else:
            note = "Minimum 1920 × 1080 w poziomie lub 1080 × 1920 w pionie. Mniejsze zdjęcia zachowują wymiary."
            if output == "JPG":
                note += " Przezroczystość otrzyma białe tło."
        self.description.set(note)
        for widget in (self.add_button, self.lossless_button, self.web_button, self.browse_button, self.directory_entry):
            widget.state(["disabled" if self.busy else "!disabled"])
        for widget in (self.clear_button, self.remove_button):
            widget.state(["!disabled" if self.files and not self.busy else "disabled"])
        self.format_box.configure(state="disabled" if self.busy else "readonly")
        self.resize_box.state(["disabled" if self.busy or lossless else "!disabled"])
        self.quality_box.configure(state="disabled" if self.busy or lossless or output == "PNG" else "readonly")
        has_directory = bool(self.directory.get().strip())
        self.open_button.state(["!disabled" if has_directory and not self.busy else "disabled"])
        self.start_button.state(["!disabled" if self.files and has_directory and not self.busy else "disabled"])

    def add_files(self):
        selected = filedialog.askopenfilenames(parent=self.root, title="Dodaj zdjęcia", filetypes=FILE_TYPES)
        known = {os.path.normcase(str(path)) for path, _ in self.files.values()}
        for filename in selected:
            path = Path(filename)
            key = os.path.normcase(str(path))
            if key in known:
                continue
            try:
                size = file_size(path.stat().st_size)
            except OSError:
                size = "—"
            row = self.tree.insert("", "end", text=path.name, values=(size, "—", "—", "W kolejce"),
                                   tags=("odd",) if len(self.files) % 2 else ())
            self.files[row] = path, size
            known.add(key)
        if selected:
            self.status.set(f"Zdjęcia na liście: {len(self.files)}")
        self.refresh()

    def show_detail(self, *_):
        selected = self.tree.selection()
        if selected and selected[0] in self.files:
            row = selected[0]
            self.detail.set(self.details.get(row, str(self.files[row][0])))
        else:
            self.detail.set("Zaznacz zdjęcie, aby zobaczyć szczegóły.")

    def remove_files(self, rows=None):
        if self.busy:
            return
        for row in self.tree.selection() if rows is None else rows:
            self.tree.delete(row)
            self.files.pop(row)
            self.details.pop(row, None)
        for index, row in enumerate(self.files):
            self.tree.item(row, tags=("odd",) if index % 2 else ())
        self.status.set(f"Zdjęcia na liście: {len(self.files)}" if self.files else "Dodaj zdjęcia i wybierz folder zapisu.")
        self.progress.configure(value=0)
        self.show_detail()
        self.refresh()

    def clear_files(self):
        self.remove_files(tuple(self.files))

    def choose_directory(self):
        folder = filedialog.askdirectory(parent=self.root, title="Wybierz folder zapisu", mustexist=True,
                                         initialdir=self.directory.get() or None)
        if folder:
            self.directory.set(folder)

    def open_directory(self):
        try:
            os.startfile(self.directory.get().strip())
        except OSError:
            self.status.set("Nie można otworzyć wskazanego folderu.")

    def start(self):
        directory = Path(self.directory.get().strip())
        if not directory.is_dir():
            self.status.set("Wybierz istniejący folder zapisu.")
            return
        options = Options(FORMATS[self.format.get()], self.mode.get() == "lossless", self.resize.get(), self.quality.get())
        jobs = tuple(self.files.items())
        self.details.clear()
        self.show_detail()
        for row, (_, size) in jobs:
            self.tree.item(row, values=(size, "—", "—", "W kolejce"))
        self.busy = True
        self.progress.configure(maximum=len(jobs), value=0)
        self.refresh()
        threading.Thread(target=self.process, args=(jobs, directory, options), daemon=True).start()
        self.root.after(60, self.poll)

    def process(self, jobs, directory, options):
        saved = skipped = errors = total_before = total_after = 0
        for index, (row, (path, size)) in enumerate(jobs, 1):
            self.events.put(("current", row, size, index, len(jobs)))
            try:
                result = optimize(path, directory, options)
                saved += 1
                total_before += result.before
                total_after += result.after
                dimensions = f"{result.dimensions[0]} × {result.dimensions[1]}"
                if result.copied:
                    label = "Kopia oryginału"
                else:
                    reduction = (result.before - result.after) / result.before * 100
                    label = f"{abs(reduction):.1f}% {'mniej' if reduction >= 0 else 'więcej'}".replace(".", ",")
                values = (file_size(result.before), file_size(result.after), dimensions, label)
                detail = f"Zapisano: {result.path}"
            except SkippedImage as exc:
                skipped += 1
                values = (size, "—", "—", "Pominięto")
                detail = str(exc)
            except Exception as exc:
                errors += 1
                values = (size, "—", "—", "Błąd")
                detail = "Nie można odczytać obrazu. Plik może być uszkodzony lub w nieobsługiwanym formacie."
                if not isinstance(exc, UnidentifiedImageError):
                    detail = str(exc) or type(exc).__name__
            self.events.put(("result", row, index, values, detail))
        self.events.put(("done", saved, skipped, errors, total_before, total_after))

    def poll(self):
        while True:
            try:
                kind, *data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "current":
                row, size, index, total = data
                self.tree.item(row, values=(size, "—", "—", "Przetwarzanie"))
                self.status.set(f"Przetwarzanie zdjęcia {index} z {total}…")
            elif kind == "result":
                row, index, values, detail = data
                self.tree.item(row, values=values)
                self.details[row] = detail
                self.progress.configure(value=index)
                self.show_detail()
            else:
                saved, skipped, errors, before, after = data
                totals = f"Zapisano {saved}  ·  Pominięto {skipped}  ·  Błędy {errors}"
                if saved:
                    totals += f"  ·  {file_size(before)} → {file_size(after)}"
                self.status.set(totals)
                self.busy = False
                self.refresh()
        if self.busy:
            self.root.after(60, self.poll)

    def close(self):
        if self.busy:
            self.status.set("Zaczekaj, aż zakończy się zapis zdjęć.")
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Resizer(root)
    root.mainloop()
