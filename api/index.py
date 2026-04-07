import sys
import os

# Add the api directory to the path so we can import generate
sys.path.insert(0, os.path.dirname(__file__))

from generate import handler

__all__ = ['handler']
