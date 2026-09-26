"""Compatibility entrypoint for installed scripts and python -m aixsecurity."""
from .entrypoints.cli import main

__all__ = ['main']
