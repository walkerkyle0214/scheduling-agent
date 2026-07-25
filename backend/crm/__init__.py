"""
CRM backend factory.

Select the scheduling backend with the CRM_BACKEND env var:
    CRM_BACKEND=mock          -> SQLite mock (default; used for dev + demo)
    CRM_BACKEND=servicetitan  -> live ServiceTitan adapter (needs ST_* creds)

The webhook talks only to the CRMBackend interface, so swapping backends never
touches the tools, prompt, or Vapi assistant.
"""

from __future__ import annotations

import os

from .base import CRMBackend


def get_backend() -> CRMBackend:
    choice = os.environ.get("CRM_BACKEND", "mock").lower()
    if choice == "servicetitan":
        from .servicetitan import ServiceTitanCRM
        backend: CRMBackend = ServiceTitanCRM()
    else:
        from .mock import MockCRM
        backend = MockCRM()
    backend.init()
    return backend
