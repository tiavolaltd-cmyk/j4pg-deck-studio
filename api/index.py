import sys
import os

# Add api directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import and expose the handler
from generate import handler as _handler

# Explicitly define handler at module level for Vercel to find it
handler = _handler
