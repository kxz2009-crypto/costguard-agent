"""Connector registry — P0 connectors live here as modules."""

from ..connector_base import Connector  # re-export for typing convenience

__all__ = ["Connector"]
