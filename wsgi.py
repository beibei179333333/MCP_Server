"""WSGI entry point for production hosts (gunicorn wsgi:app)."""
from group_export.webapp import create_app

app = create_app()
