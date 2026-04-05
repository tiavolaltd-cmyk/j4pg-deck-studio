"""
J4PG Deck Studio - API Vercel
POST /api/generate
Recoit : multipart/form-data avec champs texte + fichiers images
Retourne : fichier PPTX en telechargement
"""

import json, os, sys, io, tempfile, traceback
from http.server import BaseHTTPRequestHandler
import cgi

# Ajouter le repertoire api au path pour importer fill_engine
sys.path.insert(0, os.path.dirname(__file__))
from fill_engine import fill_deck

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

TEMPLATES = {
    "top20": os.path.join(TEMPLATE_DIR, "master_top20.pptx"),
    "top12": os.path.join(TEMPLATE_DIR, "master_top12.pptx"),
}

# Mapping champ_form -> nom_shape_pptx
IMG_MAP = {
    "photo_player":   "PHOTO_PLAYER",
    "img_heatmap":    "IMG_HEATMAP",
    "img_radar_s5":   "IMG_RADAR_S5",
    "img_radar_s8":   "IMG_RADAR_S8",
    "img_map_impact": "IMG_MAP_IMPACT",
    "photo_j1":       "PHOTO_J1",
    "photo_j2":       "PHOTO_J2",
    "photo_j3":       "PHOTO_J3",
}


def parse_bar_vals(form, prefix, n, field_a="val", field_b="target"):
    """Extrait n tuples (val, target) depuis les champs de formulaire."""
    result = []
    for i in range(1, n + 1):
        a = form.getvalue(f"{prefix}_{i}_{field_a}", "0") or "0"
        b = form.getvalue(f"{prefix}_{i}_{field_b}", "1") or "1"
        try:
            result.append((float(a), float(b)))
        except ValueError:
            result.append((0.0, 1.0))
    return result


def parse_percentiles(form, prefix, n):
    """Extrait n percentiles depuis le formulaire."""
    result = []
    for i in range(1, n + 1):
        v = form.getvalue(f"{prefix}_{i}_pct", "0") or "0"
        try:
            result.append(float(v))
        except ValueError:
            result.append(0.0)
    return result


def parse_image(form, field_name):
    """Retourne bytes de l'image ou None."""
    item = form[field_name] if field_name in form else None
    if item and hasattr(item, 'file') and item.file:
        data = item.file.read()
        return data if data else None
    return None


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Health check."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "service": "J4PG Deck Studio"}).encode())

    def do_POST(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))

            # Parse multipart form
            environ = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": str(content_length),
            }
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ=environ
            )

            # Format de deck
            deck_format = form.getvalue("deck_format", "top20")
            template_path = TEMPLATES.get(deck_format, TEMPLATES["top20"])

            # Donnees texte - tous les champs string -> DATA dict (cles majuscules)
            data = {}
            for key in form.keys():
                val = form.getvalue(key)
                if val and isinstance(val, str):
                    data[key.upper()] = val

            # Barres slide 3 (val/target pour chaque KPI)
            s3_vals = parse_bar_vals(form, "s3_kpi", 8)

            # Barres slide 4 (percentiles forces et axes)
            s4_force_pcts = parse_percentiles(form, "s4_f", 3)
            s4_axe_pcts   = parse_percentiles(form, "s4_a", 3)

            # FIX: les champs s4_f_1_pct/s4_a_1_pct sont en minuscules dans le form
            # -> leur cle majuscule serait S4_F_1_PCT, mais le template attend S4_F1_PCT
            # On injecte les valeurs correctes dans data
            for i, pct in enumerate(s4_force_pcts, 1):
                data[f'S4_F{i}_PCT'] = str(int(pct))
            for i, pct in enumerate(s4_axe_pcts, 1):
                data[f'S4_A{i}_PCT'] = str(int(pct))

            # Images
            images = {}
            for form_field, shape_name in IMG_MAP.items():
                img = parse_image(form, form_field)
                if img:
                    images[shape_name] = img

            # Nom du fichier de sortie
            nom    = data.get("NOM_UPPER", "joueur").replace(" ", "_")
            prenom = data.get("PRENOM_UPPER", "").replace(" ", "_")
            saison = data.get("SAISON", "2024-25").replace("-", "")
            fmt_label = "TOP12" if deck_format == "top12" else "TOP20"
            fname  = f"J4PG_{prenom}_{nom}_{fmt_label}_{saison}.pptx"

            with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
                tmp_path = tmp.name

            pptx_bytes = None
            try:
                fill_deck(
                    template_path=template_path,
                    data=data,
                    images=images,
                    output_path=tmp_path,
                    s3_kpi_vals=s3_vals if any(v != (0, 1) for v in s3_vals) else None,
                    s4_force_pcts=s4_force_pcts if any(p > 0 for p in s4_force_pcts) else None,
                    s4_axe_pcts=s4_axe_pcts if any(p > 0 for p in s4_axe_pcts) else None,
                )
                with open(tmp_path, "rb") as f:
                    pptx_bytes = f.read()
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            # Reponse PPTX
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(pptx_bytes)))
            self.end_headers()
            self.wfile.write(pptx_bytes)

        except Exception as e:
            tb = traceback.format_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "trace": tb}).encode())

    def log_message(self, fmt, *args):
        pass
