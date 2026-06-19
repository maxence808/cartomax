import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk


class SuppressionCouleursApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Supprimer des couleurs")
        self.root.geometry("1100x760")
        self.root.minsize(820, 560)

        self.image_path = ""
        self.original_image = None
        self.preview_image = None
        self.display_photo = None
        self.display_scale = 1.0
        self.display_offset = (0, 0)
        self.colors_to_remove = []
        self.pipette_active = False

        self.tolerance = tk.IntVar(value=45)
        self.status = tk.StringVar(value="Choisis une image pour commencer.")

        self._build_ui()

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0)
        main.rowconfigure(0, weight=1)

        image_frame = ttk.Frame(main)
        image_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(image_frame, bg="#202020", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._canvas_click)
        self.canvas.bind("<Configure>", lambda _event: self._refresh_preview())

        side = ttk.Frame(main, width=280)
        side.grid(row=0, column=1, sticky="ns")
        side.columnconfigure(0, weight=1)

        ttk.Button(side, text="Choisir une photo", command=self.open_image).grid(
            row=0, column=0, sticky="ew"
        )

        ttk.Label(side, text="Enlever couleur").grid(
            row=1, column=0, sticky="w", pady=(18, 6)
        )
        ttk.Button(side, text="Ajouter avec pipette", command=self.activate_pipette).grid(
            row=2, column=0, sticky="ew"
        )

        tolerance_row = ttk.Frame(side)
        tolerance_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        tolerance_row.columnconfigure(1, weight=1)
        ttk.Label(tolerance_row, text="Tolérance").grid(row=0, column=0, sticky="w")
        self.tolerance_label = ttk.Label(tolerance_row, text=str(self.tolerance.get()))
        self.tolerance_label.grid(row=0, column=2, sticky="e")
        tolerance_slider = ttk.Scale(
            tolerance_row,
            from_=0,
            to=160,
            orient="horizontal",
            variable=self.tolerance,
            command=self._tolerance_changed,
        )
        tolerance_slider.grid(row=0, column=1, sticky="ew", padx=8)

        ttk.Label(side, text="Couleurs sélectionnées").grid(
            row=4, column=0, sticky="w", pady=(18, 6)
        )
        self.colors_frame = ttk.Frame(side)
        self.colors_frame.grid(row=5, column=0, sticky="ew")
        self.colors_frame.columnconfigure(0, weight=1)

        ttk.Separator(side).grid(row=6, column=0, sticky="ew", pady=18)

        ttk.Button(side, text="Actualiser l'aperçu", command=self.apply_preview).grid(
            row=7, column=0, sticky="ew"
        )
        ttk.Button(side, text="Exporter PNG transparent", command=self.export_png).grid(
            row=8, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(side, text="Vider les couleurs", command=self.clear_colors).grid(
            row=9, column=0, sticky="ew", pady=(8, 0)
        )

        ttk.Label(side, textvariable=self.status, wraplength=260).grid(
            row=10, column=0, sticky="ew", pady=(18, 0)
        )

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Choisir une image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not path:
            return

        try:
            self.original_image = Image.open(path).convert("RGBA")
        except Exception as error:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir l'image.\n\n{error}")
            return

        self.image_path = path
        self.preview_image = self.original_image.copy()
        self.colors_to_remove.clear()
        self._render_color_list()
        self._refresh_preview()
        self.status.set("Image chargée. Clique sur Ajouter avec pipette, puis sur l'image.")

    def activate_pipette(self):
        if self.original_image is None:
            messagebox.showinfo("Image manquante", "Choisis d'abord une image.")
            return
        self.pipette_active = True
        self.canvas.configure(cursor="crosshair")
        self.status.set("Pipette active : clique sur une couleur dans l'image.")

    def _canvas_click(self, event):
        if not self.pipette_active or self.original_image is None:
            return

        image_x, image_y = self._canvas_to_image_coords(event.x, event.y)
        if image_x is None:
            return

        color = self.original_image.getpixel((image_x, image_y))[:3]
        if color not in self.colors_to_remove:
            self.colors_to_remove.append(color)
        self.pipette_active = False
        self.canvas.configure(cursor="")
        self._render_color_list()
        self.apply_preview()
        self.status.set(f"Couleur ajoutée : #{color[0]:02X}{color[1]:02X}{color[2]:02X}")

    def _canvas_to_image_coords(self, canvas_x, canvas_y):
        offset_x, offset_y = self.display_offset
        image_x = int((canvas_x - offset_x) / self.display_scale)
        image_y = int((canvas_y - offset_y) / self.display_scale)
        width, height = self.original_image.size
        if image_x < 0 or image_y < 0 or image_x >= width or image_y >= height:
            return None, None
        return image_x, image_y

    def _tolerance_changed(self, _value):
        self.tolerance_label.configure(text=str(int(self.tolerance.get())))
        if self.original_image is not None and self.colors_to_remove:
            self.apply_preview()

    def apply_preview(self):
        if self.original_image is None:
            return
        self.preview_image = self._remove_colors(self.original_image)
        self._refresh_preview()

    def _remove_colors(self, image):
        if not self.colors_to_remove:
            return image.copy()

        output = image.copy().convert("RGBA")
        pixels = output.load()
        width, height = output.size
        tolerance_squared = int(self.tolerance.get()) ** 2

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a == 0:
                    continue
                for target_r, target_g, target_b in self.colors_to_remove:
                    dr = r - target_r
                    dg = g - target_g
                    db = b - target_b
                    if (dr * dr) + (dg * dg) + (db * db) <= tolerance_squared:
                        pixels[x, y] = (r, g, b, 0)
                        break

        return output

    def _refresh_preview(self):
        self.canvas.delete("all")
        image = self.preview_image
        if image is None:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Aucune image",
                fill="#d0d0d0",
                font=("Segoe UI", 18),
            )
            return

        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        image_width, image_height = image.size
        self.display_scale = min(
            canvas_width / image_width,
            canvas_height / image_height,
            1.0,
        )
        display_width = max(1, int(image_width * self.display_scale))
        display_height = max(1, int(image_height * self.display_scale))
        self.display_offset = (
            (canvas_width - display_width) // 2,
            (canvas_height - display_height) // 2,
        )

        display = image.resize((display_width, display_height), Image.LANCZOS)
        checker = self._checkerboard(display_width, display_height)
        checker.alpha_composite(display)
        self.display_photo = ImageTk.PhotoImage(checker)

        self.canvas.create_image(
            self.display_offset[0],
            self.display_offset[1],
            image=self.display_photo,
            anchor="nw",
        )

    def _checkerboard(self, width, height):
        image = Image.new("RGBA", (width, height), "#ffffff")
        pixels = image.load()
        size = 12
        for y in range(height):
            for x in range(width):
                if ((x // size) + (y // size)) % 2:
                    pixels[x, y] = (220, 220, 220, 255)
        return image

    def _render_color_list(self):
        for child in self.colors_frame.winfo_children():
            child.destroy()

        if not self.colors_to_remove:
            ttk.Label(self.colors_frame, text="Aucune couleur").grid(
                row=0, column=0, sticky="w"
            )
            return

        for index, color in enumerate(self.colors_to_remove):
            row = ttk.Frame(self.colors_frame)
            row.grid(row=index, column=0, sticky="ew", pady=3)
            row.columnconfigure(1, weight=1)

            swatch = tk.Canvas(row, width=28, height=20, highlightthickness=1)
            swatch.grid(row=0, column=0, sticky="w")
            hex_color = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
            swatch.create_rectangle(0, 0, 28, 20, fill=hex_color, outline="")

            ttk.Label(row, text=hex_color).grid(row=0, column=1, sticky="w", padx=8)
            ttk.Button(
                row,
                text="X",
                width=3,
                command=lambda idx=index: self.remove_color(idx),
            ).grid(row=0, column=2, sticky="e")

    def remove_color(self, index):
        del self.colors_to_remove[index]
        self._render_color_list()
        self.apply_preview()

    def clear_colors(self):
        self.colors_to_remove.clear()
        self._render_color_list()
        self.apply_preview()
        self.status.set("Liste des couleurs vidée.")

    def export_png(self):
        if self.original_image is None:
            messagebox.showinfo("Image manquante", "Choisis d'abord une image.")
            return

        output_image = self._remove_colors(self.original_image)
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        default_name = f"{base_name}_transparent.png"
        path = filedialog.asksaveasfilename(
            title="Exporter le PNG",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG transparent", "*.png")],
        )
        if not path:
            return

        try:
            output_image.save(path, "PNG")
        except Exception as error:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer le PNG.\n\n{error}")
            return

        self.status.set(f"PNG exporté : {path}")
        messagebox.showinfo("Export terminé", "Le PNG transparent a été créé.")


if __name__ == "__main__":
    root = tk.Tk()
    app = SuppressionCouleursApp(root)
    root.mainloop()
