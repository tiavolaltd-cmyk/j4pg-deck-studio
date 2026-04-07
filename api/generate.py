"""
J4PG Deck Studio - API Vercel (Native Serverless Handler)
POST /api/generate
Recoit : multipart/form-data avec champs texte + fichiers images
Retourne : fichier PPTX en base64
"""

import json
import base64
import os
import sys
import tempfile
import traceback

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


def parse_multipart_form(body_bytes, content_type):
    """
    Parse multipart/form-data from request body.
    Returns a dict with fields and files.
    """
    boundary = content_type.split("boundary=")[1].split(";")[0]
    boundary_bytes = f"--{boundary}".encode()

    parts = body_bytes.split(boundary_bytes)
    fields = {}
    files = {}

    for part in parts[1:]:  # Skip first empty part
        if not part.strip():
            continue

        # Split headers from body
        if b"\r\n\r\n" in part:
            headers_section, body_section = part.split(b"\r\n\r\n", 1)
        else:
            continue

        # Parse headers
        headers_text = headers_section.decode('utf-8', errors='ignore')

        # Extract field name and filename
        field_name = None
        filename = None

        if 'Content-Disposition:' in headers_text:
            disp_line = [l for l in headers_text.split('\n') if 'Content-Disposition:' in l][0]

            if 'name="' in disp_line:
                field_name = disp_line.split('name="')[1].split('"')[0]

            if 'filename="' in disp_line:
                filename = disp_line.split('filename="')[1].split('"')[0]

        # Remove trailing boundary markers
        body_data = body_section.rstrip(b'\r\n')

        if filename:
            # It's a file
            files[field_name] = {
                'filename': filename,
                'content': body_data
            }
        else:
            # It's a regular field
            try:
                fields[field_name] = body_data.decode('utf-8')
            except:
                fields[field_name] = body_data

    return fields, files


def parse_bar_vals(fields, prefix, n, field_a="val", field_b="target"):
    """Extrait n tuples (val, target) depuis les champs de formulaire."""
    result = []
    for i in range(1, n + 1):
        a = fields.get(f"{prefix}_{i}_{field_a}", "0") or "0"
        b = fields.get(f"{prefix}_{i}_{field_b}", "1") or "1"
        try:
            result.append((float(a), float(b)))
        except ValueError:
            result.append((0.0, 1.0))
    return result


def parse_percentiles(fields, prefix, n):
    """Extrait n percentiles depuis le formulaire."""
    result = []
    for i in range(1, n + 1):
        v = fields.get(f"{prefix}_{i}_pct", "0") or "0"
        try:
            result.append(float(v))
        except ValueError:
            result.append(0.0)
    return result


def handler(request):
    """
    Vercel serverless handler for PPTX deck generation.
    Handles GET (health check) and POST (deck generation) requests.
    """
    try:
        # Health check
        if request.method == 'GET':
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'status': 'ok',
                    'service': 'J4PG Deck Studio'
                })
            }

        # Handle POST request
        if request.method == 'POST':
            # Get content type and body
            content_type = request.headers.get('content-type', '').lower()
            body = request.body

            # Handle different content types
            if isinstance(body, str):
                body = body.encode('utf-8')

            # Parse form data based on content type
            if 'multipart/form-data' in content_type:
                fields, files = parse_multipart_form(body, content_type)
            else:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Only multipart/form-data supported'})
                }

            # Format de deck
            deck_format = fields.get("deck_format", "top20")
            template_path = TEMPLATES.get(deck_format, TEMPLATES["top20"])

            # Check template exists
            if not os.path.exists(template_path):
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': f'Template not found: {template_path}'})
                }

            # Donnees texte - tous les champs string -> DATA dict (cles majuscules)
            data = {}
            for key, val in fields.items():
                if val and isinstance(val, str) and not key.startswith('s3_') and not key.startswith('s4_'):
                    data[key.upper()] = val

            # Barres slide 3 (val/target pour chaque KPI)
            s3_vals = parse_bar_vals(fields, "s3_kpi", 8)

            # Barres slide 4 (percentiles forces et axes)
            s4_force_pcts = parse_percentiles(fields, "s4_f", 3)
            s4_axe_pcts   = parse_percentiles(fields, "s4_a", 3)

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
                if form_field in files:
                    images[shape_name] = files[form_field]['content']

            # Nom du fichier de sortie
            nom    = data.get("NOM_UPPER", "joueur").replace(" ", "_")
            prenom = data.get("PRENOM_UPPER", "").replace(" ", "_")
            saison = data.get("SAISON", "2024-25").replace("-", "")
            fmt_label = "TOP12" if deck_format == "top12" else "TOP20"
            fname  = f"J4PG_{prenom}_{nom}_{fmt_label}_{saison}.pptx"

            # Create temporary file for output
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

            # Encode to base64
            pptx_b64 = base64.b64encode(pptx_bytes).decode('utf-8')

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'Content-Disposition': f'attachment; filename="{fname}"',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': pptx_b64,
                'isBase64Encoded': True
            }

        # Unsupported method
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }

    except Exception as e:
        # Error handling
        tb = traceback.format_exc()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e),
                'trace': tb
            })
        }
