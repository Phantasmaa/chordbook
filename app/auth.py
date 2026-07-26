"""
Authentication for Chordbook.

Reads the SAME `usuarios` table that pennypath (mis-finanzas) writes to
in `/root/finanzas/finanzas.db`. The chordbook_db (songs + setlists) is
a SEPARATE database; this module only touches the shared users table.

No registration endpoint — users come from the pennypath registration
form. No password reset either (same).

Why reuse the table? Single source of truth: if you change your password
in finanzas, it changes in chordbook. If you delete a user in finanzas,
they lose access here too. No duplicate accounts.
"""
import os
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint, current_app, redirect, render_template,
    request, url_for, jsonify,
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, DeclarativeBase
from werkzeug.security import check_password_hash


# ─── Shared users DB (pennypath-owned SQLite file) ────────────────────────
# This is the same path pennypath uses for FINANZAS_DB. We open it in
# read-write mode and the users table is well-known.
SHARED_USERS_DB = Path(os.environ.get(
    "FINANZAS_DB", "/root/finanzas/finanzas.db"
))


class Base(DeclarativeBase):
    pass


class User(UserMixin, Base):
    """Mirror of pennypath's `usuarios` table. Read-only from chordbook's
    side — pennypath owns it, we never INSERT/UPDATE/DELETE here."""
    __tablename__ = "usuarios"

    id            = __import__("sqlalchemy").Column(__import__("sqlalchemy").Integer, primary_key=True)
    username      = __import__("sqlalchemy").Column(__import__("sqlalchemy").String(80),  unique=True, nullable=False)
    password_hash = __import__("sqlalchemy").Column(__import__("sqlalchemy").String(200), nullable=False)
    nombre        = __import__("sqlalchemy").Column(__import__("sqlalchemy").String(100))
    email         = __import__("sqlalchemy").Column(__import__("sqlalchemy").String(120))
    is_admin      = __import__("sqlalchemy").Column(__import__("sqlalchemy").Boolean, nullable=False, default=False)
    created_at    = __import__("sqlalchemy").Column(__import__("sqlalchemy").DateTime)


# Build a SQLAlchemy engine + scoped session bound to the shared users DB
_users_engine = create_engine(
    f"sqlite:///{SHARED_USERS_DB}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
_UsersSession = scoped_session(sessionmaker(bind=_users_engine, autoflush=False, autocommit=False))


def _get_user(uid: int):
    return _UsersSession().get(User, int(uid))


auth_bp = Blueprint("auth", __name__)


# ─── Public API ───────────────────────────────────────────────────────────

def admin_required(fn):
    """Decorator: 403 unless logged in AND is_admin."""
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not getattr(current_user, "is_admin", False):
            return ("Forbidden", 403)
        return fn(*args, **kwargs)
    return _wrapped


def init_login(app):
    """Wire Flask-Login into the chordbook app."""
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(uid):
        return _get_user(uid)

    @login_manager.unauthorized_handler
    def _unauth():
        if request.path.startswith("/api/"):
            return jsonify(error="no_autorizado", redirect="/login"), 401
        return redirect(url_for("auth.login", next=request.path))

    # Close the per-thread users session at teardown
    @app.teardown_appcontext
    def _close_users_session(exception=None):
        _UsersSession.remove()


# ─── Routes ───────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = _UsersSession().query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True, duration=timedelta(days=90))
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/whoami")
def whoami():
    if not current_user.is_authenticated:
        return jsonify(authenticated=False), 401
    return jsonify(
        authenticated=True,
        id=current_user.id,
        username=current_user.username,
        nombre=current_user.nombre,
        is_admin=bool(getattr(current_user, "is_admin", False)),
    )
