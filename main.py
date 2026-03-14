# main.py

import tkinter as tk
from tkinter import filedialog, messagebox
import json
import os

from extractor import extract_from_pdf
from extractor.fields import FIELDS, get_bloques, get_fields_by_bloque


# ── Colores ───────────────────────────────────────────────────────────────────

C = {
    "bg":         "#f5f5f5",
    "header_bg":  "#2c3e50",
    "header_fg":  "#ffffff",
    "ok_bg":      "#f0fff4",
    "ok_border":  "#27ae60",
    "fail_bg":    "#fff0f0",
    "fail_border":"#e74c3c",
    "unc_bg":     "#fffbf0",
    "unc_border": "#f39c12",
    "text":       "#2c3e50",
    "hint":       "#95a5a6",
    "btn_ok":     "#27ae60",
    "btn_cancel": "#95a5a6",
    "white":      "#ffffff",
    "border":     "#dcdcdc",
}


class App:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Extractor de Facturas")
        self.root.geometry("900x700")
        self.root.configure(bg=C["bg"])
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # Diccionario key → StringVar con el valor de cada campo
        self.vars: dict[str, tk.StringVar] = {
            f.key: tk.StringVar() for f in FIELDS
        }

        # Resultado de la extracción
        self.result = None

        self._build_header()
        self._build_body()
        self._build_footer()


    def run(self):
        self.root.mainloop()


    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        header = tk.Frame(self.root, bg=C["header_bg"], pady=14, padx=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text="Extractor de Facturas Eléctricas",
            bg=C["header_bg"], fg=C["header_fg"],
            font=("Arial", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.file_label = tk.Label(
            header,
            text="Ningún archivo seleccionado",
            bg=C["header_bg"], fg="#bdc3c7",
            font=("Arial", 9),
        )
        self.file_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        tk.Button(
            header,
            text="📂  Abrir PDF",
            bg="#3498db", fg=C["white"],
            font=("Arial", 9, "bold"),
            relief="flat", padx=14, pady=6,
            cursor="hand2",
            command=self._open_pdf,
        ).grid(row=0, column=1, rowspan=2, sticky="e")


    # ── Cuerpo con scroll ─────────────────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self.root, bg=C["bg"])
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(body, bg=C["bg"], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.inner = tk.Frame(self.canvas, bg=C["bg"])
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        ))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self.canvas_win, width=e.width
        ))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"
        ))

        self.inner.columnconfigure(0, weight=1)
        self._build_fields()


    def _build_fields(self):
        """Renderiza todos los campos organizados por bloque."""
        for bloque in get_bloques():
            fields = get_fields_by_bloque(bloque)
            if not fields:
                continue

            # Título de la sección
            section_header = tk.Frame(self.inner, bg=C["header_bg"], pady=5, padx=10)
            section_header.pack(fill="x", padx=10, pady=(10, 0))

            tk.Label(
                section_header,
                text=bloque.upper(),
                bg=C["header_bg"], fg=C["white"],
                font=("Arial", 8, "bold"),
            ).pack(side="left")

            # Grid de campos
            grid = tk.Frame(self.inner, bg=C["bg"])
            grid.pack(fill="x", padx=10, pady=(0, 4))
            grid.columnconfigure(0, weight=1)
            grid.columnconfigure(1, weight=1)

            for i, f in enumerate(fields):
                col = i % 2
                row = i // 2
                self._build_field(grid, f, row, col)


    def _build_field(self, parent, field, row, col):
        """Renderiza un campo individual."""
        # Estado inicial — sin extracción todavía
        frame = tk.Frame(
            parent,
            bg=C["unc_bg"],
            highlightbackground=C["unc_border"],
            highlightthickness=1,
        )
        frame.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
        frame.columnconfigure(0, weight=1)

        # Guardar referencia al frame para actualizar el color después
        self.vars[field.key]._frame = frame

        # Label
        top = tk.Frame(frame, bg=C["unc_bg"])
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        top.columnconfigure(0, weight=1)

        tk.Label(
            top,
            text=field.label_es,
            bg=C["unc_bg"], fg=C["text"],
            font=("Arial", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Ícono de estado — guardamos referencia para actualizar
        icon_lbl = tk.Label(
            top,
            text="○",
            bg=C["unc_bg"], fg=C["hint"],
            font=("Arial", 10),
        )
        icon_lbl.grid(row=0, column=1, sticky="e")
        self.vars[field.key]._icon = icon_lbl
        self.vars[field.key]._top  = top

        # Entry
        entry = tk.Entry(
            frame,
            textvariable=self.vars[field.key],
            font=("Arial", 9),
            bg=C["white"], fg=C["text"],
            relief="flat", bd=4,
        )
        entry.grid(row=1, column=0, sticky="ew", padx=8, pady=2)

        # Hint
        if field.hint:
            tk.Label(
                frame,
                text=field.hint,
                bg=C["unc_bg"], fg=C["hint"],
                font=("Arial", 7),
            ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 6))
        else:
            tk.Frame(frame, bg=C["unc_bg"], height=6).grid(row=2)

        self.vars[field.key]._hint_bg = C["unc_bg"]


    def _update_field_colors(self):
        for field in FIELDS:
            var   = self.vars[field.key]
            value = var.get().strip()

            if value:
                bg, border, icon, icon_fg = C["ok_bg"], C["ok_border"], "✓", C["ok_border"]
            else:
                bg, border, icon, icon_fg = C["fail_bg"], C["fail_border"], "✗", C["fail_border"]

            frame = var._frame
            frame.configure(bg=bg, highlightbackground=border)
            var._top.configure(bg=bg)
            var._icon.configure(bg=bg, fg=icon_fg, text=icon)

            for widget in frame.winfo_children():
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass

        self._update_footer_counter()


    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        tk.Frame(self.root, bg=C["border"], height=1).grid(row=2, column=0, sticky="ew")

        footer = tk.Frame(self.root, bg=C["bg"], pady=10, padx=14)
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        self.counter_var = tk.StringVar(value="Ningún archivo cargado")
        tk.Label(
            footer,
            textvariable=self.counter_var,
            bg=C["bg"], fg=C["hint"],
            font=("Arial", 8),
        ).grid(row=0, column=0, sticky="w")

        btn_frame = tk.Frame(footer, bg=C["bg"])
        btn_frame.grid(row=0, column=1, sticky="e")

        tk.Button(
            btn_frame,
            text="Limpiar",
            bg=C["btn_cancel"], fg=C["white"],
            font=("Arial", 9, "bold"),
            relief="flat", padx=14, pady=7,
            cursor="hand2",
            command=self._clear,
        ).pack(side="left", padx=(0, 8))

        self.btn_json = tk.Button(
            btn_frame,
            text="Generar JSON",
            bg="#bdc3c7", fg=C["white"],
            font=("Arial", 9, "bold"),
            relief="flat", padx=14, pady=7,
            cursor="hand2",
            command=self._generate_json,
            state="disabled",
        )
        self.btn_json.pack(side="left")


    def _update_footer_counter(self):
        """Actualiza el contador y activa/desactiva el botón JSON."""
        total     = len(FIELDS)
        filled    = sum(1 for f in FIELDS if self.vars[f.key].get().strip())
        required  = [f for f in FIELDS if f.required]
        req_done  = sum(1 for f in required if self.vars[f.key].get().strip())
        req_total = len(required)

        self.counter_var.set(
            f"{filled}/{total} campos rellenos   |   "
            f"{req_done}/{req_total} obligatorios"
        )

        # Botón JSON activo solo cuando todos los obligatorios están completos
        if req_done == req_total:
            self.btn_json.configure(bg=C["btn_ok"], state="normal")
        else:
            self.btn_json.configure(bg="#bdc3c7", state="disabled")


    # ── Acciones ──────────────────────────────────────────────────────────────

    def _open_pdf(self):
        path = filedialog.askopenfilename(
            title="Seleccionar factura PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")]
        )
        if not path:
            return

        self.file_label.configure(text=os.path.basename(path))

        try:
            self.result = extract_from_pdf(path)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el PDF:\n{e}")
            return

        # Rellenar campos con los valores extraídos
        for key, value in self.result.fields.items():
            if key in self.vars and value:
                self.vars[key].set(value)

        self._update_field_colors()


    def _clear(self):
        for var in self.vars.values():
            var.set("")
        self.result = None
        self.file_label.configure(text="Ningún archivo seleccionado")
        self._update_field_colors()
        self.counter_var.set("Ningún archivo cargado")
        self.btn_json.configure(bg="#bdc3c7", state="disabled")


    def _generate_json(self):
        """Genera el JSON con los valores actuales de los campos."""
        from extractor.fields import get_field

        data = {}
        for f in FIELDS:
            val = self.vars[f.key].get().strip()

            # Convertir al tipo correcto
            if not val:
                data[f.key] = None
            elif f.tipo == "float":
                try:
                    data[f.key] = float(val)
                except ValueError:
                    data[f.key] = val
            elif f.tipo == "int":
                try:
                    data[f.key] = int(val)
                except ValueError:
                    data[f.key] = val
            else:
                data[f.key] = val

        # Separar metadata de bloque_b
        metadata_keys = {"comercializadora", "distribuidora", "cups",
                        "periodo_inicio", "periodo_fin", "dias_facturados",
                        "tarifa_acceso"}

        output = {
            "metadata": {k: v for k, v in data.items() if k in metadata_keys},
            "bloque_b": {k: v for k, v in data.items() if k not in metadata_keys},
        }

        # Guardar archivo
        path = filedialog.asksaveasfilename(
            title="Guardar JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        messagebox.showinfo(
            "JSON guardado",
            f"Archivo guardado en:\n{path}"
        )


# ── Punto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().run()