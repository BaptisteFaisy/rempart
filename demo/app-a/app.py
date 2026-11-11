"""ShopLite Flask application — Demo app A with intentional IDOR vulnerability."""

import os
import sqlite3
from typing import Any
from flask import Flask, g, jsonify, request
from seed import dict_factory, init_db


def is_idor_vulnerable() -> bool:
    """Return whether IDOR vulnerability is active (default 1 / True)."""
    val = os.getenv("VULN_IDOR", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def get_db(db_conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Provide an application-context SQLite connection."""
    if "db" not in g:
        if db_conn is not None:
            g.db = db_conn
        else:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = dict_factory
            init_db(conn)
            g.db = conn
    return g.db


def register_routes(app: Flask, persistent_conn: sqlite3.Connection | None = None) -> None:
    """Register endpoints for ShopLite."""

    @app.before_request
    def before_request() -> None:
        get_db(persistent_conn)

    @app.teardown_appcontext
    def teardown_db(exception: Any = None) -> None:
        db = g.pop("db", None)
        if db is not None and persistent_conn is None:
            db.close()

    @app.get("/health")
    def health() -> tuple[Any, int]:
        return jsonify({"status": "ok", "service": "shoplite", "idor_active": is_idor_vulnerable()}), 200

    @app.get("/orders")
    def list_orders() -> tuple[Any, int]:
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return jsonify({"error": "missing_user_id_header"}), 400
        cur = g.db.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id ASC", (user_id,))
        rows = cur.fetchall()
        return jsonify({"user_id": user_id, "orders": rows}), 200

    @app.get("/orders/<order_id>")
    def get_order(order_id: str) -> tuple[Any, int]:
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return jsonify({"error": "missing_user_id_header"}), 400

        cur = g.db.cursor()
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cur.fetchone()
        if order is None:
            return jsonify({"error": "not_found"}), 404

        if not is_idor_vulnerable() and order["user_id"] != user_id:
            return jsonify({"error": "forbidden", "message": "Access denied to foreign order"}), 403

        return jsonify({"order": order}), 200


def create_app(test_config: dict[str, Any] | None = None, persistent_conn: sqlite3.Connection | None = None) -> Flask:
    """Application factory for ShopLite."""
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)

    # If no custom persistent connection provided, create one per app instance
    # so in-memory SQLite tables persist across requests during the app lifecycle.
    if persistent_conn is None:
        persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
        persistent_conn.row_factory = dict_factory
        init_db(persistent_conn)

    register_routes(app, persistent_conn=persistent_conn)
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=8080)
