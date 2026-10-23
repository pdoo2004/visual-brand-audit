"""ASGI entry point: `uvicorn brandlens.api.main:app`."""

from brandlens.api.app import create_app

app = create_app()
