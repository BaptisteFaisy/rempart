"""Seed data and database initialization for ShopLite demo application."""

import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    item TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

USERS: list[tuple[str, str, str]] = [
    ("usr-alice", "Alice Martin", "alice@example.com"),
    ("usr-bob", "Bob Dupont", "bob@example.com"),
    ("usr-charlie", "Charlie Durand", "charlie@example.com"),
]

ORDERS: list[tuple[str, str, str, float, str, str]] = [
    ("ord-101", "usr-alice", "Wireless Mouse", 29.99, "delivered", "2026-11-01T10:00:00Z"),
    ("ord-102", "usr-alice", "USB-C Hub", 49.50, "shipped", "2026-11-03T14:30:00Z"),
    ("ord-201", "usr-bob", "Mechanical Keyboard", 119.00, "delivered", "2026-11-02T11:15:00Z"),
    ("ord-202", "usr-bob", "Laptop Stand", 35.00, "processing", "2026-11-05T09:00:00Z"),
    ("ord-301", "usr-charlie", "Noise-Cancelling Headphones", 199.90, "delivered", "2026-11-04T16:45:00Z"),
    ("ord-302", "usr-charlie", "Desk Pad", 22.00, "shipped", "2026-11-06T12:00:00Z"),
]


def init_db(conn: sqlite3.Connection) -> None:
    """Apply schema and insert initial fixture rows."""
    cursor = conn.cursor()
    cursor.executescript(SCHEMA)
    cursor.executemany("INSERT INTO users VALUES (?, ?, ?);", USERS)
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?);", ORDERS)
    conn.commit()


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    """Format sqlite rows into dictionaries indexed by column name."""
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row, strict=False))
