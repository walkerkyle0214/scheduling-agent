"""
CRMBackend — the interface every scheduling backend implements.

The four tool handlers in the Vapi webhook call these methods. Swapping the
underlying scheduling system (SQLite mock today, ServiceTitan tomorrow) means
writing a new subclass — nothing in the webhook, tools, or prompt changes.

Each method takes the parsed tool `arguments` dict and returns a plain dict that
is JSON-serialized straight into the tool result sent back to Vapi.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CRMBackend(ABC):
    name: str = "base"

    def init(self) -> None:
        """Optional one-time setup (create/seed a DB, warm a token cache)."""

    @abstractmethod
    def lookup_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find a customer by phone (preferred) or name."""

    @abstractmethod
    def check_availability(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return open appointment slots, optionally filtered."""

    @abstractmethod
    def create_booking(self, args: dict[str, Any]) -> dict[str, Any]:
        """Book a service call."""

    @abstractmethod
    def flag_priority(self, args: dict[str, Any]) -> dict[str, Any]:
        """Escalate an urgent / life-safety situation to dispatch."""

    # --- Admin / testing. Real backends may not support these. ---
    def admin_reset(self) -> None:
        raise NotImplementedError(f"{self.name} backend does not support admin_reset")

    def admin_state(self) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} backend does not support admin_state")

    def admin_add_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        """Register a known customer on the fly (used to demo caller-ID recognition)."""
        raise NotImplementedError(f"{self.name} backend does not support admin_add_customer")
