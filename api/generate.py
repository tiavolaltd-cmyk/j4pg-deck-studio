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

# DON'T import fill_engine at module level - defer to handler execution
# This allows us to catch import errors properly

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
        # Health check - test system state
        if request.method == 'GET':
            status = {
                'status': 'ok',
                'service': 'J4PG Deck Studio',
                'templates_dir': TEMPLATE_DIR,
                'template_top20_exists': os.path.exists(TEMPLATES['top20']),
                'template_top12_exists': os.path.exists(TEMPLATES['top12']),
                'python_version': sys.version,
                'sys_path': sys.path[:3]  # First 3 paths for debugging
            }

            # Try importing fill_engine in handler context
            try:
                from fill_engine import fill_deck
                status['fill_engine_status'] = 'loaded_ok'
                status['fill_deck_callable'] = callable(fill_deck)
            except Exception as import_err:
                status['fill_engine_status'] = 'import_failed'
                status['fill_engine_error'] = str(import_err)
                status['fill_engine_error_type'] = type(import_err).__name__

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(status, indent=2)
            }

        # Handle POST request
        if request.method == 'POST':
            # Import fill_engine here, inside the handler
            from fill_engine import fill_deck

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
            data['S3_BARS'] = parse_bar_vals(fields, 's3', 8)

            # Barres slide 4 (forces et axes d'amélioration)
            data['S4_FORCES'] = parse_bar_vals(fields, 's4', 5, field_a='force_val', field_b='force_target')
            data['S4_AXES'] = parse_bar_vals(fields, 's4', 5, field_a='axe_val', field_b='axe_target')

            # Percentiles slide 5
            data['S5_PERCENTILES'] = parse_percentiles(fields, 's5', 8)

            # Images
            images = {}
            for field_name, shape_name in IMG_MAP.items():
                if field_name in files:
                    file_data = files[field_name]['content']
                    images[shape_name] = file_data

            # Generate PPTX
            with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp_file:
                tmp_path = tmp_file.name

            try:
                fill_deck(template_path, data, images, tmp_path)

                # Read and encode the generated PPTX
                with open(tmp_path, 'rb') as f:
                    pptx_bytes = f.read()

                pptx_b64 = base64.b64encode(pptx_bytes).decode('utf-8')

                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/octet-stream',
                        'Content-Disposition': 'attachment; filename="deck.pptx"',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': pptx_b64,
                    'isBase64Encoded': True
                }
            finally:
                # Cleanup
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # Unsupported method
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }

    except Exception as e:
        # Error handling - return detailed error info
        tb = traceback.format_exc()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e),
                'error_type': type(e).__name__,
                'trace': tb
            }, indent=2)
        }
