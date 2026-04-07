import sys
import os

# Ensure fill_engine can be imported
sys.path.insert(0, os.path.dirname(__file__))

# Import the handler from generate module
from generate import handler

# Explicitly define handler at module level for Vercel
__all__ = ['handler']
