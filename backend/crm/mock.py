"""
MockCRM — SQLite-backed implementation of CRMBackend.

This is the default backend (CRM_BACKEND=mock). It holds all the real business
logic for the four tools, backed by the disposable SQLite file in db.py, which is
pre-loaded with a realistic backlog of appointments so booking isn't trivial.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import db
from .base import CRMBackend

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Stated to the agent so it can quote real hours when a caller asks for a time
# outside them (e.g. 6 AM). Matches the four seeded windows.
BUSINESS_HOURS = ("We schedule 8:00 AM to 5:00 PM, in four windows: 8-10 AM, "
                  "10 AM-12 PM, 1-3 PM, and 3-5 PM. No earlier, later, or overnight slots.")


def _digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _extract_day(text: str | None) -> str | None:
    t = (text or "").lower()
    for d in _DAYS:
        if d in t:
            return d
    return None


def _extract_iso(text: str | None) -> str | None:
    m = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
    return m.group(0) if m else None


def _canonical_window(text: str | None) -> str | None:
    """Map free-text time ('1-3pm', '1pm', 'afternoon', '1:00-3:00 PM') to one of
    the four canonical windows, so the agent doesn't need the opaque slot_id."""
    t = (text or "").lower()
    for w in db.WINDOWS:
        if w.lower() in t:
            return w
    pm = ("pm" in t) or ("afternoon" in t) or ("evening" in t) or ("noon" in t)
    m = re.search(r"(\d{1,2})", t)
    if m:
        h = int(m.group(1))
        if h in (8, 9):
            return db.WINDOWS[0]
        if h in (10, 11):
            return db.WINDOWS[1]
        if h == 12:
            return db.WINDOWS[2] if pm else db.WINDOWS[1]
        if h in (1, 2, 13, 14):
            return db.WINDOWS[2]
        if h in (3, 4, 5, 15, 16, 17):
            return db.WINDOWS[3]
    if "morning" in t:
        return db.WINDOWS[0]
    if "afternoon" in t:
        return db.WINDOWS[2]
    if "evening" in t:
        return db.WINDOWS[3]
    return None


def _match_open_slot(conn, date_text: str | None, window_text: str | None):
    """Resolve a caller's requested day+time to a currently OPEN slot.

    Returns (status, slot|None) where status is:
      'underspecified' — couldn't pin down both a day/date AND a window
      'unavailable'    — that day/time is not an open slot (incl. impossible dates)
      'ok'             — slot is the open slot to book
    Strict by design: an out-of-range or made-up date ('January 1') matches no
    slot and comes back 'unavailable', never a silent substitution.
    """
    day = _extract_day(date_text)
    iso = _extract_iso(date_text)
    win = _canonical_window(window_text)
    if not (day or iso) or not win:
        return "underspecified", None

    rows = [dict(r) for r in conn.execute("SELECT * FROM slots WHERE booked = 0").fetchall()]
    if iso:
        rows = [s for s in rows if s["date"] == iso]
    elif day:
        rows = [s for s in rows if s["day_of_week"].lower() == day]
    rows = [s for s in rows if s["window"] == win]
    rows.sort(key=lambda s: (s["date"], s["window_order"]))
    return ("ok", rows[0]) if rows else ("unavailable", None)


class MockCRM(CRMBackend):
    name = "mock"

    def init(self) -> None:
        db.init_db()

    # ------------------------------------------------------------------
    def lookup_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        phone = args.get("phone") or args.get("phone_number")
        name = args.get("name")

        # Guard against unresolved Vapi template vars (e.g. text-chat testing).
        if phone and "{{" in str(phone):
            phone = None

        conn = db.get_conn()
        try:
            row = None
            if phone:
                want = _digits(phone)[-10:]
                if want:
                    for r in conn.execute("SELECT * FROM customers").fetchall():
                        if _digits(r["phone"])[-10:] == want:
                            row = r
                            break
            if row is None and name:
                like = f"%{name.strip().lower()}%"
                row = conn.execute(
                    "SELECT * FROM customers WHERE LOWER(name) LIKE ?", (like,)
                ).fetchone()

            if row is None:
                return {
                    "found": False,
                    "message": "No existing customer on file. Treat as a new customer and collect their details.",
                }

            history = conn.execute(
                "SELECT date, service FROM service_history WHERE customer_phone = ? ORDER BY date DESC",
                (row["phone"],),
            ).fetchall()
            customer = {
                "name": row["name"],
                "phone": row["phone"],
                "address": row["address"],
                "property_type": row["property_type"],
                "notes": row["notes"],
                "service_history": [{"date": h["date"], "service": h["service"]} for h in history],
            }
            return {"found": True, "customer": customer}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    def check_availability(self, args: dict[str, Any]) -> dict[str, Any]:
        date_pref = args.get("date") or args.get("date_range")
        urgency = (args.get("urgency") or args.get("urgency_tier") or "routine").lower()

        conn = db.get_conn()
        try:
            rows = conn.execute("SELECT * FROM slots WHERE booked = 0").fetchall()
        finally:
            conn.close()

        all_open = sorted([dict(r) for r in rows], key=lambda s: (s["date"], s["window_order"]))
        # The real bookable horizon — so the agent can correct out-of-range dates.
        horizon = None
        if all_open:
            horizon = {"earliest": all_open[0]["date"], "latest": all_open[-1]["date"]}

        slots = list(all_open)
        if date_pref:
            dp = str(date_pref).strip().lower()
            slots = [s for s in slots if dp in s["date"] or dp in s["day_of_week"].lower()]

        if not slots:
            msg = "No open slots match that request."
            if date_pref and horizon:
                msg = (f"Nothing open for that date. We only schedule between {horizon['earliest']} "
                       f"and {horizon['latest']}. Offer the caller a real open time in that range.")
            return {"available": False, "message": msg, "scheduling_window": horizon,
                    "business_hours": BUSINESS_HOURS}

        # Dedup to distinct (date, window) times so the caller hears clean options,
        # not the same slot repeated once per available technician.
        seen: set[tuple[str, str]] = set()
        offered = []
        limit = 6 if urgency in ("urgent", "emergency", "priority", "b", "c") else 4
        for s in slots:
            key = (s["date"], s["window"])
            if key in seen:
                continue
            seen.add(key)
            offered.append({"slot_id": s["id"], "date": s["date"], "day": s["day_of_week"],
                            "window": s["window"]})
            if len(offered) >= limit:
                break
        return {"available": True, "slots": offered, "total_open": len(slots),
                "scheduling_window": horizon, "business_hours": BUSINESS_HOURS}

    # ------------------------------------------------------------------
    def create_booking(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name")
        phone = args.get("phone") or args.get("phone_number")
        address = args.get("address")
        property_type = (args.get("property_type") or "residential").lower()
        service_type = args.get("service_type") or "HVAC service"
        issue = args.get("issue_description") or args.get("issue_summary") or ""
        urgency = (args.get("urgency") or args.get("urgency_tier") or "routine").lower()
        slot_id = args.get("slot_id") or args.get("slot")
        preferred_window = args.get("preferred_window")

        if not name or not address:
            return {
                "success": False,
                "message": "Missing required booking info. Need at least the caller's name and service address.",
            }

        conn = db.get_conn()
        try:
            # Slot-authoritative: a confirmed booking must consume exactly one OPEN
            # slot. Never fabricate a confirmation for a time that isn't open.
            slot = None
            if slot_id:
                slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
                if slot is None:
                    return {"success": False,
                            "message": f"Slot {slot_id} doesn't exist. Call check_availability and offer a currently open time."}
                if slot["booked"]:
                    return {"success": False,
                            "message": "That time was just taken. Call check_availability again and offer another open slot."}
            else:
                # No slot_id — resolve the caller's requested day + time window to a
                # real OPEN slot. Rejects impossible/out-of-range dates outright.
                date_text = args.get("date") or args.get("day") or preferred_window
                window_text = args.get("window") or preferred_window
                status, slot = _match_open_slot(conn, date_text, window_text)
                if status == "underspecified":
                    return {"success": False,
                            "message": "Need a specific day and time window to book. Confirm which offered time the caller wants, or call check_availability and offer one."}
                if status == "unavailable" or slot is None:
                    return {"success": False,
                            "message": "That day/time isn't an open slot (it may be taken, or outside our schedule — we only book about a week out). Call check_availability and offer the caller a currently open day and time."}

            conn.execute("UPDATE slots SET booked = 1 WHERE id = ?", (slot["id"],))
            scheduled = {
                "date": slot["date"], "day": slot["day_of_week"],
                "window": slot["window"], "technician_name": slot["technician_name"],
            }

            booking_id = db.new_id("BK")
            conn.execute(
                "INSERT INTO bookings (booking_id, name, phone, address, property_type, service_type, "
                "issue_description, urgency, slot_id, preferred_window, scheduled_date, scheduled_day, "
                "scheduled_window, technician_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (booking_id, name, phone, address, property_type, service_type, issue, urgency,
                 slot["id"], preferred_window,
                 scheduled["date"], scheduled["day"], scheduled["window"], scheduled["technician_name"],
                 datetime.utcnow().isoformat() + "Z"),
            )
            conn.commit()
        finally:
            conn.close()

        confirm = (
            f"Booked {service_type} for {name} on {scheduled['day']} {scheduled['date']}, "
            f"{scheduled['window']}, with technician {scheduled['technician_name']}."
        )
        return {"success": True, "booking_id": booking_id, "confirmation": confirm, "scheduled": scheduled}

    # ------------------------------------------------------------------
    def flag_priority(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name")
        phone = args.get("phone") or args.get("phone_number")
        address = args.get("address")
        reason = args.get("reason") or "Unspecified urgent situation"
        details = args.get("details") or ""
        property_type = (args.get("property_type") or "residential").lower()

        blob = (reason + " " + details).lower()
        is_safety = any(w in blob for w in ("gas", "carbon monoxide", "co detector", "smoke", "burning"))

        priority_id = db.new_id("PRI")
        level = "EMERGENCY" if is_safety else "URGENT"
        conn = db.get_conn()
        try:
            conn.execute(
                "INSERT INTO priority_queue (priority_id, name, phone, address, property_type, reason, details, level, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (priority_id, name, phone, address, property_type, reason, details, level,
                 datetime.utcnow().isoformat() + "Z"),
            )
            conn.commit()
        finally:
            conn.close()

        if is_safety:
            msg = ("Flagged as EMERGENCY and pushed to the top of dispatch. "
                   "Caller should be advised on safety steps first.")
        else:
            msg = "Flagged as URGENT. Dispatch has been alerted for same-day/priority scheduling."
        return {"success": True, "priority_id": priority_id, "level": level, "message": msg}

    # ------------------------------------------------------------------
    def admin_reset(self) -> None:
        db.reseed()

    def admin_add_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        """Insert (or replace) a known customer so caller-ID lookup finds them.
        Handy right before a demo: register the caller's real number."""
        phone = args.get("phone") or args.get("phone_number")
        name = args.get("name")
        if not phone or not name:
            return {"success": False, "message": "phone and name are required."}
        address = args.get("address") or "Address on file — please confirm"
        property_type = (args.get("property_type") or "residential").lower()
        notes = args.get("notes") or "Added via admin for demo."

        conn = db.get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO customers (phone, name, address, property_type, notes) "
                "VALUES (?,?,?,?,?)",
                (phone, name, address, property_type, notes),
            )
            for h in args.get("service_history", []) or []:
                conn.execute(
                    "INSERT INTO service_history (customer_phone, date, service) VALUES (?,?,?)",
                    (phone, h.get("date", ""), h.get("service", "")),
                )
            conn.commit()
        finally:
            conn.close()
        return {"success": True, "message": f"Customer {name} registered for {phone}."}

    def admin_state(self) -> dict[str, Any]:
        conn = db.get_conn()
        try:
            customers = [dict(r) for r in conn.execute("SELECT * FROM customers").fetchall()]
            technicians = [dict(r) for r in conn.execute("SELECT * FROM technicians").fetchall()]
            open_slots = conn.execute("SELECT COUNT(*) AS n FROM slots WHERE booked = 0").fetchone()["n"]
            booked_slots = conn.execute("SELECT COUNT(*) AS n FROM slots WHERE booked = 1").fetchone()["n"]
            bookings = [dict(r) for r in conn.execute("SELECT * FROM bookings ORDER BY created_at").fetchall()]
            priority = [dict(r) for r in conn.execute("SELECT * FROM priority_queue ORDER BY created_at").fetchall()]
            slots = [dict(r) for r in conn.execute(
                "SELECT * FROM slots ORDER BY date, window_order, technician_name").fetchall()]
        finally:
            conn.close()
        return {
            "customers": customers,
            "technicians": technicians,
            "open_slots": open_slots,
            "booked_slots": booked_slots,
            "bookings": bookings,
            "priority_queue": priority,
            "slots": slots,
        }
