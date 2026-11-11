import os
import sys

# Ensure app-a is importable in tests
app_a_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if app_a_dir not in sys.path:
    sys.path.insert(0, app_a_dir)
