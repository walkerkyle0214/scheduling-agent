"""
ServiceTitanCRM — production adapter stub for ServiceTitan.

ServiceTitan is the industry-standard field-service platform for mid/large
HVAC/plumbing/electrical shops — the right fit for a 40-tech, multi-county
operation like Summit Air.

This adapter is deliberately a STUB: it maps each of our four tool methods to the
ServiceTitan API module that implements it, but does not make live calls, because
that requires Summit Air's own API credentials (a customer-provisioning step, not
an engineering one). The method bodies document exactly what the live
implementation does, so flipping CRM_BACKEND=servicetitan once creds exist is a
fill-in-the-blanks job, not a redesign.

Required env when going live:
    ST_CLIENT_ID, ST_CLIENT_SECRET   OAuth2 client credentials
    ST_APP_KEY                       ServiceTitan application key (ST-App-Key header)
    ST_TENANT_ID                     Summit Air's tenant id

API reference: https://developer.servicetitan.io
"""

from __future__ import annotations

import os
from typing import Any

from .base import CRMBackend

ST_AUTH_URL = "https://auth.servicetitan.io/connect/token"
ST_API_BASE = "https://api.servicetitan.io"


class ServiceTitanNotConfigured(RuntimeError):
    pass


class ServiceTitanCRM(CRMBackend):
    name = "servicetitan"

    def __init__(self) -> None:
        self.client_id = os.environ.get("ST_CLIENT_ID")
        self.client_secret = os.environ.get("ST_CLIENT_SECRET")
        self.app_key = os.environ.get("ST_APP_KEY")
        self.tenant_id = os.environ.get("ST_TENANT_ID")
        self._token: str | None = None

    def _require_creds(self) -> None:
        missing = [k for k, v in {
            "ST_CLIENT_ID": self.client_id,
            "ST_CLIENT_SECRET": self.client_secret,
            "ST_APP_KEY": self.app_key,
            "ST_TENANT_ID": self.tenant_id,
        }.items() if not v]
        if missing:
            raise ServiceTitanNotConfigured(
                "ServiceTitan backend selected but missing credentials: "
                + ", ".join(missing)
                + ". Set them or use CRM_BACKEND=mock."
            )

    def _get_token(self) -> str:
        """OAuth2 client-credentials token (cache until expiry).

        LIVE:
            POST {ST_AUTH_URL}
            data = grant_type=client_credentials, client_id, client_secret
            -> access_token; send as `Authorization: Bearer <token>` plus
               header `ST-App-Key: {app_key}` on every API call.
        """
        self._require_creds()
        raise NotImplementedError("ServiceTitan OAuth not implemented — stub.")

    # ------------------------------------------------------------------
    def lookup_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        """LIVE: CRM module — search customer/contact by phone.
            GET /crm/v2/tenant/{tenant}/customers?phone={phone}
            then GET .../locations for the service address(es) and
            GET /jpm/v2/.../jobs?customerId= for recent history.
        Return the same shape MockCRM does: {"found", "customer": {...}}.
        """
        self._require_creds()
        raise NotImplementedError("ServiceTitan lookup_customer — stub.")

    def check_availability(self, args: dict[str, Any]) -> dict[str, Any]:
        """LIVE: Capacity / Dispatch module — real bookable slots by zone.
            POST /dispatch/v2/tenant/{tenant}/capacity
            body = { startsOnOrAfter, endsOnOrBefore, businessUnitIds,
                     jobTypeId, skillBasedAvailability }
            Map the returned time windows to our {"slots":[{slot_id,date,...}]}.
        """
        self._require_creds()
        raise NotImplementedError("ServiceTitan check_availability — stub.")

    def create_booking(self, args: dict[str, Any]) -> dict[str, Any]:
        """LIVE: Scheduling module — create a booking / lead.
            POST /scheduling/v2/tenant/{tenant}/bookings
            body = { name, address, contacts:[{phone}], summary,
                     isFirstTimeClient, priority, jobTypeId }
            (or create customer + job + appointment directly via jpm/dispatch).
        Return the same {"success","booking_id","confirmation"} shape.
        """
        self._require_creds()
        raise NotImplementedError("ServiceTitan create_booking — stub.")

    def flag_priority(self, args: dict[str, Any]) -> dict[str, Any]:
        """LIVE: tag the job/booking urgent and notify dispatch.
            Set booking priority=Urgent and/or POST a task to the dispatch
            board; optionally trigger a ServiceTitan notification.
        """
        self._require_creds()
        raise NotImplementedError("ServiceTitan flag_priority — stub.")
