import sys
import os
from pathlib import Path

# Add the backend directory to the sys.path so Python can find the 'app' module
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
