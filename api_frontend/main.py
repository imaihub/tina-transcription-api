"""
Transcription API — test frontend

Serves the static HTML frontend and exposes a /config endpoint so the page
knows which API URL to call.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8001")
API_KEY = os.getenv("API_KEY", "")

app = FastAPI(title="Transcription Frontend")


@app.get("/config")
def config():
    """Return runtime configuration consumed by the frontend."""
    return {"api_url": API_URL, "api_key": API_KEY}


# Serve static files — mount last so /config is not shadowed
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
