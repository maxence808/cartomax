import http.server
import io
import json
import socketserver
import webbrowser
import threading
import os
import re
import sys
from collections import deque
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image

from plu import backend as plu_backend

PORT = 5000

def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
HTML_DIRECTORY_NAME = "html"
DEFAULT_HTML_FILE = "cartomax.html"
STYLE_DIRECTORY_NAME = "style-carte-sauv"

def sanitize_style_name(name):
    clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", str(name or "")).strip()
    clean_name = re.sub(r"\s+", " ", clean_name)
    return clean_name[:80]

def parse_hex_color(value, default=(0, 255, 0)):
    clean_value = str(value or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", clean_value):
        return default
    return tuple(int(clean_value[index:index + 2], 16) for index in (0, 2, 4))

def remove_france_export_background(image_bytes, key_color=(0, 255, 0), tolerance=55):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pixels = image.load()
    tolerance_squared = tolerance * tolerance
    width, height = image.size
    key_r, key_g, key_b = key_color

    def is_key_fringe_color(r, g, b, loose=False):
        threshold = 18 if loose else 28
        min_channel = 95 if loose else 120
        if key_g > key_r and key_g > key_b:
            return g > min_channel and g - r > threshold and g - b > threshold
        if key_r > key_g and key_b > key_g:
            return r > min_channel and b > min_channel and g < (155 if loose else 125)
        return False

    def is_key_pixel(x, y):
        r, g, b, a = pixels[x, y]
        dr = r - key_r
        dg = g - key_g
        db = b - key_b
        close_to_key = (dr * dr) + (dg * dg) + (db * db) <= tolerance_squared
        return close_to_key or is_key_fringe_color(r, g, b) or a < 250

    # First remove the green background connected to image borders. This keeps
    # useful map greens inside France while allowing aggressive edge cleanup.
    visited = bytearray(width * height)
    queue = deque()

    def enqueue(x, y):
        index = y * width + x
        if visited[index] or not is_key_pixel(x, y):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        r, g, b, _ = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
        if x > 0:
            enqueue(x - 1, y)
        if x < width - 1:
            enqueue(x + 1, y)
        if y > 0:
            enqueue(x, y - 1)
        if y < height - 1:
            enqueue(x, y + 1)

    # Then shave off remaining green antialiasing fringes touching transparency.
    for _ in range(3):
        to_clear = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                r, g, b, a = pixels[x, y]
                if a == 0:
                    continue
                key_fringe = is_key_fringe_color(r, g, b, loose=True)
                if not key_fringe:
                    continue
                touches_transparent = (
                    pixels[x - 1, y][3] == 0 or pixels[x + 1, y][3] == 0
                    or pixels[x, y - 1][3] == 0 or pixels[x, y + 1][3] == 0
                )
                if touches_transparent:
                    to_clear.append((x, y))
        if not to_clear:
            break
        for x, y in to_clear:
            r, g, b, _ = pixels[x, y]
            pixels[x, y] = (r, g, b, 0)

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Sert les fichiers depuis le dossier où se trouve le .exe ou app.py
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]

        if path == "/" or path == "":
            path = f"/{DEFAULT_HTML_FILE}"

        relative_path = os.path.normpath(unquote(path).lstrip("/\\"))
        if relative_path in ("", "."):
            relative_path = DEFAULT_HTML_FILE
        html_aliases = {
            "plu.html": "carte_plu.html",
            "base.html": "plu_base.html",
            "plu-base.html": "plu_base.html",
            "base_plu.html": "plu_base.html",
        }
        if relative_path in html_aliases:
            relative_path = html_aliases[relative_path]

        candidates = []
        if (
            os.sep not in relative_path
            and "/" not in relative_path
            and relative_path.lower().endswith(".html")
        ):
            candidates.append(os.path.join(BASE_DIR, HTML_DIRECTORY_NAME, relative_path))
        candidates.append(os.path.join(BASE_DIR, relative_path))

        for candidate in candidates:
            absolute_candidate = os.path.abspath(candidate)
            if os.path.commonpath([BASE_DIR, absolute_candidate]) != BASE_DIR:
                continue
            if os.path.exists(absolute_candidate):
                return absolute_candidate

        fallback = os.path.abspath(candidates[0])
        if os.path.commonpath([BASE_DIR, fallback]) != BASE_DIR:
            return BASE_DIR
        return fallback

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_png(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path.startswith("/api/nouveau/") or path in (
            "/api/charger-plu",
            "/api/charger-plu-nomfic",
            "/api/analyser-zone",
        ):
            try:
                payload = plu_backend.read_json_request(self)
                result = plu_backend.handle_api(path, payload)
                if result is None:
                    self.send_json(404, {"erreur": "Endpoint PLU introuvable."})
                else:
                    self.send_json(200, result)
            except Exception as error:
                self.send_json(500, {
                    "erreur": str(error),
                    "categorie_erreur": getattr(error, "categorie", "erreur_inconnue"),
                })
            return

        if path == "/api/france-transparent":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                image_bytes = self.rfile.read(content_length)
                query = parse_qs(parsed_url.query)
                key_color = parse_hex_color(query.get("keyColor", ["00ff00"])[0])
                processed = remove_france_export_background(image_bytes, key_color)
                self.send_png(200, processed)
            except Exception as error:
                self.send_json(500, {"error": str(error)})
            return

        if path != "/api/personal-style":
            self.send_json(404, {"error": "Endpoint introuvable."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            style_name = sanitize_style_name(payload.get("name"))
            style_data = payload.get("style")

            if not style_name:
                self.send_json(400, {"error": "Nom du style manquant."})
                return
            if not isinstance(style_data, dict):
                self.send_json(400, {"error": "Style invalide."})
                return

            style_dir = os.path.join(BASE_DIR, STYLE_DIRECTORY_NAME)
            os.makedirs(style_dir, exist_ok=True)
            file_path = os.path.join(style_dir, f"{style_name}.json")

            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(style_data, file, ensure_ascii=False, indent=2)

            self.send_json(200, {"name": style_name})
        except Exception as error:
            self.send_json(500, {"error": str(error)})

def open_browser():
    webbrowser.open(f"http://127.0.0.1:{PORT}")

if __name__ == "__main__":
    os.chdir(BASE_DIR)

    threading.Timer(1, open_browser).start()

    with socketserver.TCPServer(("127.0.0.1", PORT), CustomHandler) as httpd:
        print(f"Application lancée : http://127.0.0.1:{PORT}")
        print("Ferme cette fenêtre pour arrêter l'application.")
        httpd.serve_forever()
