import sys
import os

# Ensure parent directory is in sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from server import RequestHandler, init_db

# Initialize DB on cold start
try:
    init_db()
except Exception as e:
    print(f"[Vercel Cold Start Init Note] {e}")

# Vercel looks for a class named `handler` inheriting from BaseHTTPRequestHandler
class handler(RequestHandler):
    pass
