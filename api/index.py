"""
J4PG Deck Studio - Vercel Serverless API
Format Flask WSGI — requis par @vercel/python
"""

from flask import Flask, request, jsonify, send_file
import os
import sys
import json
import io
import base64
import tempfile

app = Flask(__name__)

# Ajouter le répertoire api/ au sys.path pour les imports internes
sys.path.insert(0, os.path.dirname(__file__))


@app.route('/api/generate', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'J4PG Deck Studio API',
        'version': '2.0',
        'message': 'API opérationnelle — POST /api/generate pour générer un deck'
    })


@app.route('/api/generate', methods=['POST'])
def generate_deck():
    """
    Génère un deck PPTX à partir des données JSON.

    Body JSON attendu :
    {
        "template": "top20" | "top12",   // optionnel, défaut "top20"
        "data": { ...tags... },
        "images": { "SHAPE_NAME": "<base64>" },  // optionnel
        "s3_kpi_vals": [[val, target], ...],     // optionnel, 8 tuples
        "s4_force_pcts": [p1, p2, p3],           // optionnel
        "s4_axe_pcts": [p1, p2, p3]             // optionnel
    }
    """
    try:
        # Parse JSON body
        body = request.get_json(force=True)
        if not body:
            return jsonify({'error': 'Corps JSON requis'}), 400

        template_name = body.get('template', 'top20')
        data = body.get('data', {})
        images_b64 = body.get('images', {})
        s3_kpi_vals = body.get('s3_kpi_vals', None)
        s4_force_pcts = body.get('s4_force_pcts', None)
        s4_axe_pcts = body.get('s4_axe_pcts', None)

        # Résolution du chemin template
        base_dir = os.path.dirname(os.path.dirname(__file__))
        template_filename = f'master_{template_name}.pptx'
        template_path = os.path.join(base_dir, 'templates', template_filename)

        if not os.path.exists(template_path):
            return jsonify({
                'error': f'Template introuvable : {template_filename}',
                'searched_at': template_path
            }), 404

        # Décoder les images base64
        images = {}
        for shape_name, b64_str in images_b64.items():
            if b64_str:
                images[shape_name] = base64.b64decode(b64_str)

        # Import lazy du fill_engine
        from fill_engine import fill_deck

        # Générer dans un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
            tmp_path = tmp.name

        fill_deck(
            template_path=template_path,
            data=data,
            images=images,
            output_path=tmp_path,
            s3_kpi_vals=s3_kpi_vals,
            s4_force_pcts=s4_force_pcts,
            s4_axe_pcts=s4_axe_pcts
        )

        # Lire le fichier généré et le retourner
        with open(tmp_path, 'rb') as f:
            pptx_bytes = f.read()
        os.unlink(tmp_path)

        # Nom du fichier de sortie
        player_name = data.get('NOM_UPPER', 'Joueur').replace(' ', '_')
        output_filename = f'J4PG_{player_name}_{template_name}.pptx'

        return send_file(
            io.BytesIO(pptx_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            as_attachment=True,
            download_name=output_filename
        )

    except ImportError as e:
        return jsonify({
            'error': 'Erreur import fill_engine',
            'details': str(e)
        }), 500
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'type': type(e).__name__,
            'trace': traceback.format_exc()
        }), 500


@app.route('/', methods=['GET'])
def root():
    return jsonify({'message': 'J4PG Deck Studio API', 'docs': '/api/generate'})
