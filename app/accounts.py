"""Caraxes accounts: simple local users, sessions, and the shared activity log.

Self-contained on purpose: it opens its own SQLite connections to the same
database file and owns the users / auth_sessions / activity tables, so the
rest of the app only calls `current_user`, `require_user`, and `log_activity`.
Passwords are salted PBKDF2 (stdlib only). This is home-LAN-grade auth, not
internet-grade: there is no HTTPS, lockout, or rate limiting.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")

_db_path: Path | None = None

AUTH_COOKIE = "caraxes_auth"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600
PBKDF2_ITERATIONS = 200_000
MAX_ACTIVITY_ROWS = 5_000

PUBLIC_PATH_PREFIXES = ("/static/", "/api/auth/")
PUBLIC_PATHS = {"/login", "/favicon.ico"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db() -> Any:
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(db_path: Path) -> None:
    global _db_path
    _db_path = db_path
    with db() as conn:
        conn.executescript(
            """
            create table if not exists users (
                id text primary key,
                username text unique not null,
                display_name text not null,
                password_hash text not null,
                created_at text not null
            );

            create table if not exists auth_sessions (
                token text primary key,
                user_id text not null references users(id) on delete cascade,
                created_at text not null,
                last_seen text not null
            );

            create table if not exists activity (
                id text primary key,
                user_id text,
                username text not null,
                kind text not null,
                detail text not null,
                path text,
                workspace text,
                created_at text not null
            );

            create index if not exists idx_activity_created on activity (created_at desc);
            create index if not exists idx_activity_path on activity (path);
            """
        )
        try:
            conn.execute("alter table chats add column user_id text")
        except sqlite3.OperationalError:
            pass


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored)


def current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            """
            select u.id, u.username, u.display_name, u.created_at
            from auth_sessions s join users u on u.id = s.user_id
            where s.token = ?
            """,
            (token,),
        ).fetchone()
        if row:
            conn.execute("update auth_sessions set last_seen = ? where token = ?", (now_iso(), token))
    return dict(row) if row else None


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def user_count() -> int:
    with db() as conn:
        return int(conn.execute("select count(*) as n from users").fetchone()["n"])


def list_users() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "select id, username, display_name, created_at from users order by created_at asc"
        ).fetchall()
    return [dict(row) for row in rows]


def log_activity(
    user: dict[str, Any] | None,
    kind: str,
    detail: str,
    path: str | None = None,
    workspace: str | None = None,
) -> None:
    try:
        with db() as conn:
            conn.execute(
                """
                insert into activity (id, user_id, username, kind, detail, path, workspace, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user.get("id") if user else None,
                    (user.get("display_name") or user.get("username")) if user else "system",
                    kind,
                    detail[:500],
                    path,
                    workspace,
                    now_iso(),
                ),
            )
            conn.execute(
                """
                delete from activity where id in (
                    select id from activity order by created_at desc limit -1 offset ?
                )
                """,
                (MAX_ACTIVITY_ROWS,),
            )
    except Exception:
        pass  # the log must never break the actual operation


def last_edit_for_path(path: str, workspace: str | None) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            """
            select username, kind, created_at from activity
            where path = ? and (? is null or workspace = ?)
              and kind in ('coder.save', 'coder.ai_write', 'coder.create')
            order by created_at desc limit 1
            """,
            (path, workspace, workspace),
        ).fetchone()
    return dict(row) if row else None


async def auth_middleware(request: Request, call_next: Any) -> Any:
    path = request.url.path
    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
        return await call_next(request)
    if current_user(request) is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not signed in"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)
    return await call_next(request)


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=4, max_length=128)
    display_name: str = Field(default="", max_length=48)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


def _start_session(response: JSONResponse, user_id: str) -> None:
    token = secrets.token_hex(32)
    with db() as conn:
        conn.execute(
            "insert into auth_sessions (token, user_id, created_at, last_seen) values (?, ?, ?, ?)",
            (token, user_id, now_iso(), now_iso()),
        )
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register")
def register(payload: RegisterIn) -> JSONResponse:
    username = payload.username.strip().lower()
    display_name = payload.display_name.strip() or payload.username.strip()
    user_id = str(uuid.uuid4())
    first_user = user_count() == 0
    try:
        with db() as conn:
            conn.execute(
                "insert into users (id, username, display_name, password_hash, created_at) values (?, ?, ?, ?, ?)",
                (user_id, username, display_name, _hash_password(payload.password), now_iso()),
            )
            if first_user:
                # The first account claims all chats created before accounts existed.
                conn.execute("update chats set user_id = ? where user_id is null", (user_id,))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="That username is already taken")
    user = {"id": user_id, "username": username, "display_name": display_name}
    log_activity(user, "auth.register", f"created the account '{display_name}'")
    response = JSONResponse({"ok": True, "user": user})
    _start_session(response, user_id)
    return response


@router.post("/auth/login")
def login(payload: LoginIn) -> JSONResponse:
    with db() as conn:
        row = conn.execute(
            "select * from users where username = ?",
            (payload.username.strip().lower(),),
        ).fetchone()
    if not row or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    user = {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}
    log_activity(user, "auth.login", "signed in")
    response = JSONResponse({"ok": True, "user": user})
    _start_session(response, row["id"])
    return response


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        with db() as conn:
            conn.execute("delete from auth_sessions where token = ?", (token,))
    response = JSONResponse({"ok": True})
    response.delete_cookie(AUTH_COOKIE, path="/")
    return response


@router.get("/auth/me")
def me(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return {"user": user, "user_count": user_count()}


@router.get("/activity")
def list_activity(
    request: Request,
    limit: int = Query(default=120, ge=1, le=500),
    kind: str = Query(default="", max_length=30),
    path: str = Query(default="", max_length=500),
) -> list[dict[str, Any]]:
    require_user(request)
    clauses = []
    params: list[Any] = []
    if kind:
        clauses.append("kind like ?")
        params.append(f"{kind}%")
    if path:
        clauses.append("path = ?")
        params.append(path)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    with db() as conn:
        rows = conn.execute(
            f"select username, kind, detail, path, workspace, created_at from activity {where} "
            "order by created_at desc limit ?",
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]
