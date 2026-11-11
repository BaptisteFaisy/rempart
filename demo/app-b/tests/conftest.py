import sys
from pathlib import Path

# Add app root to sys.path so 'import app' works
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
