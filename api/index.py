"""
J4PG Deck Studio - Vercel Serverless API
Direct handler in index.py to avoid import issues
"""

import json
import sys
import os

def handler(request):
    """
    Main handler for Vercel serverless
    """
    try:
        if request.method == 'GET':
            # Health check - test if we can execute
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'status': 'ok',
                    'service': 'J4PG Deck Studio API',
                    'endpoint': 'GET /api/generate',
                    'message': 'Handler is running!'
                })
            }

        if request.method == 'POST':
            # Lazy import - only import when actually needed
            try:
                from generate import handler as generate_handler
                return generate_handler(request)
            except ImportError as ie:
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'Cannot import generate module',
                        'details': str(ie)
                    })
                }

        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }

    except Exception as e:
        import traceback
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': str(e),
                'type': type(e).__name__,
                'trace': traceback.format_exc()
            })
        }
