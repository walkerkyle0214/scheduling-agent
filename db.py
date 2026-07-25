"""
SQLite-backed mock CRM for the Summit Air agent.

Single service area (no counties): one shared pool of technicians and slots. The
schedule is pre-loaded with a realistic backlog — near-term days are mostly
booked, later days open up — so booking is not trivial.

The DB file lives next to this module (summit_air.db). Call init_db() at startup;
reseed() wipes and refills it (used by /admin/reset). Connections are opened
per-operation so they're safe across FastAPI's worker threads.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).with_name("summit_air.db")

WINDOWS = ["8:00-10:00 AM", "10:00 AM-12:00 PM", "1:00-3:00 PM", "3:00-5:00 PM"]
WINDOW_ORDER = {w: i for i, w in enumerate(WINDOWS)}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE technicians (
    id TEXT PRIMARY KEY, name TEXT, skills TEXT
);
CREATE TABLE customers (
    phone TEXT PRIMARY KEY, name TEXT, address TEXT,
    property_type TEXT, notes TEXT
);
CREATE TABLE service_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_phone TEXT, date TEXT, service TEXT
);
CREATE TABLE slots (
    id TEXT PRIMARY KEY, date TEXT, day_of_week TEXT, window TEXT,
    window_order INTEGER, technician_id TEXT,
    technician_name TEXT, booked INTEGER DEFAULT 0
);
CREATE TABLE bookings (
    booking_id TEXT PRIMARY KEY, name TEXT, phone TEXT, address TEXT,
    property_type TEXT, service_type TEXT, issue_description TEXT,
    urgency TEXT, slot_id TEXT, preferred_window TEXT,
    scheduled_date TEXT, scheduled_day TEXT, scheduled_window TEXT,
    technician_name TEXT, created_at TEXT
);
CREATE TABLE priority_queue (
    priority_id TEXT PRIMARY KEY, name TEXT, phone TEXT, address TEXT,
    property_type TEXT, reason TEXT, details TEXT, level TEXT, created_at TEXT
);
"""

TECHNICIANS = [
    ("tech_01", "Marcus Reed", "hvac,furnace,ac"),
    ("tech_02", "Dana Whitfield", "hvac,furnace,ac"),
    ("tech_03", "Luis Ortega", "hvac,commercial,ac"),
    ("tech_04", "Priya Nair", "hvac,furnace,maintenance"),
]

# Fake existing customers used to populate the pre-booked backlog so the
# bookings table reads like a real day's schedule.
BACKLOG_CUSTOMERS = [
    ("Tom Alvarez", "17 Birch Court", "residential", "AC not cooling"),
    ("Greenfield Elementary", "900 School Rd", "commercial", "Rooftop unit PM"),
    ("Nadia Hassan", "233 Willow Way", "residential", "Furnace tune-up"),
    ("Cortez Auto Body", "45 Industrial Pkwy", "commercial", "No cooling in office"),
    ("Bill Trainor", "78 Sunset Dr", "residential", "Annual maintenance"),
    ("Hilltop Cafe", "12 Market St", "commercial", "Walk-in cooler check"),
    ("Renee Park", "560 Meadow Ln", "residential", "Thermostat replacement"),
    ("Dockside Storage", "301 Harbor Blvd", "commercial", "Quarterly PM"),
]


def _seed(conn: sqlite3.Connection) -> None:
    today = date.today()

    conn.executemany(
        "INSERT INTO technicians (id, name, skills) VALUES (?,?,?)",
        TECHNICIANS,
    )

    # Two known customers so lookup_customer returns real hits.
    conn.executemany(
        "INSERT INTO customers (phone, name, address, property_type, notes) VALUES (?,?,?,?,?)",
        [
            ("+15551234567", "Eleanor Davies", "412 Oakhurst Lane, Millbrook",
             "residential", "84-year-old homeowner. Furnace serviced last winter."),
            ("+15559876543", "Bridgeport Dental Group", "88 Commerce Blvd, Suite 200",
             "commercial", "Rooftop package units x3. Service contract customer."),
        ],
    )
    conn.executemany(
        "INSERT INTO service_history (customer_phone, date, service) VALUES (?,?,?)",
        [
            ("+15551234567", str(today - timedelta(days=210)), "Annual furnace maintenance"),
            ("+15559876543", str(today - timedelta(days=95)), "Quarterly commercial PM"),
            ("+15559876543", str(today - timedelta(days=280)), "Compressor replacement"),
        ],
    )

    # Generate slots for the next 7 days: one slot per technician per window.
    # Booking density is front-loaded — soon days nearly full, later days open —
    # which is what makes the agent work to find a time.
    density_by_offset = {1: 0.90, 2: 0.85, 3: 0.65, 4: 0.55, 5: 0.35, 6: 0.30, 7: 0.25}
    backlog_i = 0
    slot_n = 0
    for day_offset in range(1, 8):
        d = today + timedelta(days=day_offset)
        density = density_by_offset[day_offset]
        for window in WINDOWS:
            for tech in TECHNICIANS:
                slot_n += 1
                booked = ((slot_n * 7 + day_offset) % 100) < int(density * 100)
                conn.execute(
                    "INSERT INTO slots (id, date, day_of_week, window, window_order, technician_id, technician_name, booked) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f"slot_{slot_n:03d}", str(d), d.strftime("%A"), window,
                     WINDOW_ORDER[window], tech[0], tech[1], 1 if booked else 0),
                )
                if booked:
                    cust = BACKLOG_CUSTOMERS[backlog_i % len(BACKLOG_CUSTOMERS)]
                    backlog_i += 1
                    conn.execute(
                        "INSERT INTO bookings (booking_id, name, phone, address, property_type, service_type, "
                        "issue_description, urgency, slot_id, preferred_window, scheduled_date, scheduled_day, "
                        "scheduled_window, technician_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (f"BK-SEED{slot_n:03d}", cust[0], "", cust[1], cust[2],
                         cust[3], cust[3], "routine", f"slot_{slot_n:03d}", None,
                         str(d), d.strftime("%A"), window, tech[1],
                         datetime.utcnow().isoformat() + "Z"),
                    )
    conn.commit()


def init_db() -> None:
    """Create + seed the DB only if it doesn't exist yet."""
    if DB_PATH.exists():
        return
    reseed()


def reseed() -> None:
    """Wipe and rebuild the DB from scratch (used by /admin/reset)."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _seed(conn)
    finally:
        conn.close()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
