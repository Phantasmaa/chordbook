"""
Authentication for Chordbook.

Two modes:
  1. SSO mode (default in production, behind nginx): nginx already validated
     the phantasmaa_auth cookie and forwarded X-Phantasmaa-User-Id /
     X-Phantasmaa-Username / X-Phantasmaa-Is-Admin headers. We auto-login
     that user on every request.
  2. Standalone mode (dev / direct access without nginx): local /login page
     is shown, password verified against the same `usuarios` table that
     pennypath (mis-finanzas) owns in /root/finanzas/finanzas.db.

Single source of truth: if you change your password in finanzas, it
changes in chordbook. If you delete a user in finanzas, they lose
access here too. No duplicate accounts.

The phantasmaa_auth cookie is set by the central SSO service
(/root/phantasmaa-auth/) which runs on :8200, exposed via nginx on :8100.
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
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from werkzeug.security import check_password_hash


# ─── Shared users DB (pennypath-owned SQLite file) ────────────────────────
SHARED_USERS_DB = Path(os.environ.get(
    "FINANZAS_DB", "/root/finanzas/finanzas.db"
))


Base = declarative_base()


class User(UserMixin, Base):
    """Mirror of pennypath's `usuarios` table. Read-only from chordbook's
    side — pennypath owns it, we never INSERT/UPDATE/DELETE here."""
    __tablename__ = "usuarios"

    id            = Column(Integer, primary_key=True)
    username      = Column(String(80),  unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    nombre        = Column(String(100))
    email         = Column(String(120))
    is_admin      = Column(Boolean, nullable=False, default=False)
    created_at    = Column(DateTime)


_users_engine = create_engine(
    f"sqlite:///{SHARED_USERS_DB}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
_UsersSession = scoped_session(sessionmaker(bind=_users_engine, autoflush=False, autocommit=False))


def _get_user(uid: int):
    return _UsersSession().get(User, int(uid))


def _sso_mode() -> bool:
    """True if the request came through nginx with SSO headers attached.
    Detected by the presence of X-Phantasmaa-User-Id header."""
    return bool(request.headers.get("X-Phantasmaa-User-Id"))


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
    """Wire Flask-Login into the chordbook app + handle SSO auto-login."""
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

    # SSO auto-login: if nginx already validated the cookie and forwarded
    # X-Phantasmaa-User-Id, mark that user as logged in for this request.
    # We register this as a before_request that runs early — but only sets
    # the user if not already authed, so explicit local logins still work.
    @app.before_request
    def _maybe_sso_login():
        if current_user.is_authenticated:
            return None
        sso_user_id = request.headers.get("X-Phantasmaa-User-Id")
        if not sso_user_id:
            return None
        try:
            uid = int(sso_user_id)
        except ValueError:
            return None
        user = _get_user(uid)
        if user:
            login_user(user, fresh=False)

    @app.teardown_appcontext
    def _close_users_session(exception=None):
        _UsersSession.remove()


# ─── Routes ───────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # In SSO mode, nginx already redirected unauthenticated users to the
    # central SSO login. If we land here in SSO mode, the SSO already
    # authenticated the user — just bounce them to the original target.
    if _sso_mode() and current_user.is_authenticated:
        return redirect(request.args.get("next") or url_for("index"))

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
    # In SSO mode, redirect to central SSO logout so the global cookie
    # is cleared. In standalone mode, just local logout.
    if _sso_mode():
        sso_host = request.host  # chordbook host
        # Build the SSO logout URL using the chordbook host's scheme/port
        # We assume SSO is on port 8100 of the same VPS.
        sso_url = "http://127.0.0.1:8100/logout?next=http://" + sso_host + "/"
        logout_user()
        return redirect(sso_url)
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
        sso_mode=_sso_mode(),
    )
