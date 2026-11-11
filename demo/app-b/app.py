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


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp_db.name
    tmp_db.close()
    app.config["DB_PATH"] = db_path

    if test_config:
        app.config.update(test_config)

    conn = sqlite3.connect(app.config["DB_PATH"])
    init_db(conn)
    conn.close()

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = dict_factory
        return g.db

    @app.teardown_appcontext
    def close_db(exception: Any = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok", "app": "BookWorm"})

    @app.get("/search")
    def search_books() -> Any:
        query = request.args.get("q", "")
        vuln_sqli = os.getenv("VULN_SQLI", "1") == "1"
        conn = get_db()
        cur = conn.cursor()

        if vuln_sqli:
            # VULNERABLE: raw string concatenation leads to SQL injection
            sql = f"SELECT id, title, author, price FROM books WHERE title LIKE '%{query}%'"
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            except sqlite3.OperationalError as err:
                return jsonify({"error": str(err)}), 400
        else:
            # SECURED: parameterized query
            cur.execute(
                "SELECT id, title, author, price FROM books WHERE title LIKE ?",
                (f"%{query}%",),
            )
            rows = cur.fetchall()

        return jsonify({"results": rows, "count": len(rows)})

    @app.get("/admin/users")
    def admin_users() -> Any:
        vuln_admin = os.getenv("VULN_ADMIN", "1") == "1"
        if not vuln_admin:
            # SECURED: require admin token
            token = request.headers.get("X-Admin-Token", "")
            if token != "secret-admin-token":
                return jsonify({"error": "Unauthorized"}), 401

        # VULNERABLE: leaks all users + api keys without auth
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, username, role, api_key FROM users")
        return jsonify({"users": cur.fetchall()})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8002)
