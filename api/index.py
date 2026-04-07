import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Import the actual handler function
from generate import handler as generate_handler

# Explicitly define handler at module level
# This ensures Vercel can find it when it scans the file
def handler(request):
    return generate_handler(request)
