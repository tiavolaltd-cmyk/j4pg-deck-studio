"""
J4PG Deck Studio - API Vercel (MINIMAL TEST VERSION)
Testing if handler can execute at all with zero external dependencies
"""

import json
import sys
import os

def handler(request):
    """
    Minimal handler to test if Vercel can execute ANY Python code
    """
    try:
        if request.method == 'GET':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'status': 'handler_works',
                    'service': 'J4PG Minimal Test',
                    'python_version': sys.version.split()[0],
                    'message': 'If you see this, the handler is executing!'
                })
            }

        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Handler error',
                'message': str(e),
                'type': type(e).__name__
            })
        }
