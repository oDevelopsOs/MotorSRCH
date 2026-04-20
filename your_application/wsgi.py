"""
Compatibilidad con el Start Command por defecto de Render (Python): gunicorn your_application.wsgi
Expone `application` ASGI apuntando a la app FastAPI en api/main.py.
Gunicorn usara UvicornWorker via gunicorn.conf.py.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_API = os.path.join(_REPO, "api")
if _API not in sys.path:
    sys.path.insert(0, _API)

from main import app

application = app
