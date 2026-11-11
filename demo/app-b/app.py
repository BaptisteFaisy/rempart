"""BookWorm demo application (Client B) with seeded vulnerabilities.

Vulnerabilities:
- VULN_SQLI=1: SQL injection in /search?q=
- VULN_ADMIN=1: /admin/users route accessible without authentication
"""

import os
import sqlite3
import tempfile
from typing import Any
from flask import Flask, g, jsonify, request

ADMIN_TOKEN = "secret-admin-token"
BOOK_COLUMNS = "id, title, author, price"
USER_COLUMNS = "id, username, role, api_key"


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            api_key TEXT NOT NULL
        )
    """)
    cur.execute("DELETE FROM books")
    cur.execute("DELETE FROM users")
    cur.executemany(
        "INSERT INTO books (id, title, author, price) VALUES (?, ?, ?, ?)",
        [
            (1, "The Pragmatic Programmer", "Hunt & Thomas", 45.0),
            (2, "Clean Code", "Robert C. Martin", 40.0),
            (3, "Designing Data-Intensive Applications", "Martin Kleppmann", 50.0),
            (4, "Site Reliability Engineering", "Betsy Beyer", 42.0),
        ],
    )
    cur.executemany(
        "INSERT INTO users (id, username, role, api_key) VALUES (?, ?, ?, ?)",
        [
            (1, "alice", "admin", "secret-key-alice"),
            (2, "bob", "customer", "key-bob-123"),
        ],
    )
    conn.commit()


def get_db(app: Flask) -> sqlite3.Connection:
    """Return the SQLite connection bound to the current request context."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = dict_factory
    return g.db


def _configure_db(app: Flask, test_config: dict[str, Any] | None = None) -> None:
    """Point the app at a fresh temporary database and seed it."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    app.config["DB_PATH"] = tmp_db.name
    tmp_db.close()

    if test_config:
        app.config.update(test_config)

    conn = sqlite3.connect(app.config["DB_PATH"])
    init_db(conn)
    conn.close()


def _register_db_lifecycle(app: Flask) -> None:
    """Close the request-scoped connection when the context is torn down."""

    @app.teardown_appcontext
    def close_db(exception: Any = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()


def _register_health(app: Flask) -> None:
    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok", "app": "BookWorm"})


def _search_concatenated(cur: sqlite3.Cursor, query: str) -> list[dict[str, Any]]:
    """VULNERABLE: raw string concatenation leads to SQL injection."""
    sql = f"SELECT {BOOK_COLUMNS} FROM books WHERE title LIKE '%{query}%'"
    cur.execute(sql)
    return cur.fetchall()


def _search_parameterized(cur: sqlite3.Cursor, query: str) -> list[dict[str, Any]]:
    """SECURED: parameterized query."""
    cur.execute(
        f"SELECT {BOOK_COLUMNS} FROM books WHERE title LIKE ?",
        (f"%{query}%",),
    )
    return cur.fetchall()


def _register_search(app: Flask) -> None:
    """Register /search: SQL injection when VULN_SQLI=1, safe query otherwise."""

    @app.get("/search")
    def search_books() -> Any:
        query = request.args.get("q", "")
        cur = get_db(app).cursor()

        if os.getenv("VULN_SQLI", "1") == "1":
            try:
                rows = _search_concatenated(cur, query)
            except sqlite3.OperationalError as err:
                return jsonify({"error": str(err)}), 400
        else:
            rows = _search_parameterized(cur, query)

        return jsonify({"results": rows, "count": len(rows)})


def _admin_allowed() -> bool:
    """VULN_ADMIN=1 opens the route; otherwise the admin token is required."""
    if os.getenv("VULN_ADMIN", "1") == "1":
        return True
    return request.headers.get("X-Admin-Token", "") == ADMIN_TOKEN


def _register_admin(app: Flask) -> None:
    """Register /admin/users: leaks every API key when VULN_ADMIN=1."""

    @app.get("/admin/users")
    def admin_users() -> Any:
        if not _admin_allowed():
            # SECURED: require the admin token
            return jsonify({"error": "Unauthorized"}), 401

        # VULNERABLE: leaks all users + api keys without auth
        cur = get_db(app).cursor()
        cur.execute(f"SELECT {USER_COLUMNS} FROM users")
        return jsonify({"users": cur.fetchall()})


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    _configure_db(app, test_config)
    _register_db_lifecycle(app)
    _register_health(app)
    _register_search(app)
    _register_admin(app)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8002)
