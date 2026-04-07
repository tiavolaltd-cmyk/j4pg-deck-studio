"""
J4PG Deck Studio - API Flask pour Vercel
POST /api/generate
Reçoit : multipart/form-data avec champs texte + fichiers images
Retourne : fichier PPTX en téléchargement
"""

import json, os, sys, io, tempfile, traceback
from flask import Flask, request, send_file, jsonify

# Ajouter le répertoire api au path pour importer fill_engine
sys.path.insert(0, os.path.dirname(__file__))
from fill_engine import fill_deck

app = Flask(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

TEMPLATES = {
    "top20": os.path.join(TEMPLATE_DIR, "master_top20.pptx"),
    "top12": os.path.join(TEMPLATE_DIR, "master_top12.pptx"),
}

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
    result = []
    for i in range(1, n + 1):
        a = form.get(f"{prefix}_{i}_{field_a}", "0") or "0"
        b = form.get(f"{prefix}_{i}_{field_b}", "1") or "1"
        try:
            result.append((float(a), float(b)))
        except ValueError:
            result.append((0.0, 1.0))
    return result

def parse_percentiles(form, prefix, n):
    result = []
    for i in range(1, n + 1):
        v = form.get(f"{prefix}_{i}_pct", "0") or "0"
        try:
            result.append(float(v))
        except ValueError:
            result.append(0.0)
    return result

def parse_image(files, field_name):
    if field_name not in files:
        return None
    file = files[field_name]
    if file and file.filename:
        return file.read()
    return None

@app.route('/api/generate', methods=['GET', 'POST'])
def generate():
    if request.method == "GET":
        return jsonify({"status": "ok", "service": "J4PG Deck Studio"}), 200
    
    try:
        deck_format = request.form.get("deck_format", "top20")
        template_path = TEMPLATES.get(deck_format, TEMPLATES["top20"])

        data = {}
        for key in request.form.keys():
            val = request.form.get(key)
            if val and isinstance(val, str):
                data[key.upper()] = val

        s3_vals = parse_bar_vals(request.form, "s3_kpi", 8)
        s4_force_pcts = parse_percentiles(request.form, "s4_f", 3)
        s4_axe_pcts = parse_percentiles(request.form, "s4_a", 3)

        for i, pct in enumerate(s4_force_pcts, 1):
            data[f'S4_F{i}_PCT'] = str(int(pct))
        for i, pct in enumerate(s4_axe_pcts, 1):
            data[f'S4_A{i}_PCT'] = str(int(pct))

        images = {}
        for form_field, shape_name in IMG_MAP.items():
            img = parse_image(request.files, form_field)
            if img:
                images[shape_name] = img

        nom = data.get("NOM_UPPER", "joueur").replace(" ", "_")
        prenom = data.get("PRENOM_UPPER", "").replace(" ", "_")
        saison = data.get("SAISON", "2024-25").replace("-", "")
        fmt_label = "TOP12" if deck_format == "top12" else "TOP20"
        fname = f"J4PG_{prenom}_{nom}_{fmt_label}_{saison}.pptx"

        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
            tmp_path = tmp.name

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
            
            return send_file(
                io.BytesIO(pptx_bytes),
                mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                as_attachment=True,
                download_name=fname
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"error": str(e), "trace": tb}), 500

if __name__ == '__main__':
    app.run(debug=False)
