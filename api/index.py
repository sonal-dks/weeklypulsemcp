"""
Vercel serverless entry: ASGI app mounted at /api (see vercel.json rewrites).

Repository root must be the Vercel project root so `phase7_ui` and `phase5_delivery` resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from phase7_ui.api import app as pulse_api

root_app = FastAPI(title="Groww Pulse Vercel", version="1.0.0")
root_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
root_app.mount("/api", pulse_api)

app = Mangum(root_app, lifespan="off")
