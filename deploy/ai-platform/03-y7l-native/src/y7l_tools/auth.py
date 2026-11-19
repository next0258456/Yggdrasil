"""Zero-Trust 10h JWT Auth, PBKDF2 verification, Redis session store, and 2-tier Kill-Switch."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

import jwt
import redis

from y7l_tools.config import Settings


class AuthError(Exception):
    """Base authentication/authorization failure."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def hash_password(password: str, salt: str | None = None, iterations: int = 200_000) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256."""
    effective_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        effective_salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${effective_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify plaintext password against stored PBKDF2-HMAC-SHA256 digest."""
    try:
        scheme, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
    except ValueError:
        return False

    candidate_hex = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate_hex, expected_hex)


class SessionStore:
    """Redis session backend with transparent in-memory fallback when Redis is unreachable."""

    def __init__(self, redis_url: str = "") -> None:
        self._memory: dict[str, tuple[str, float | None]] = {}
        self._user_chats: dict[str, set[str]] = {}
        self._redis: redis.Redis | None = None
        if redis_url.strip():
            try:
                client = redis.Redis.from_url(
                    redis_url.strip(),
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @staticmethod
    def _session_key(chat_user_id: str) -> str:
        return f"y7l:session:{chat_user_id}"

    @staticmethod
    def _user_index_key(username: str) -> str:
        return f"y7l:user_sessions:{username}"

    def set_session(self, chat_user_id: str, username: str, token: str, ttl_seconds: int) -> None:
        key = self._session_key(chat_user_id)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl_seconds, token)
                idx_key = self._user_index_key(username)
                self._redis.sadd(idx_key, chat_user_id)
                self._redis.expire(idx_key, ttl_seconds)
                return
            except Exception:
                pass
        expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None
        self._memory[key] = (token, expires_at)
        self._user_chats.setdefault(username, set()).add(chat_user_id)

    def get_session(self, chat_user_id: str) -> str | None:
        key = self._session_key(chat_user_id)
        if self._redis is not None:
            try:
                return self._redis.get(key)
            except Exception:
                pass
        entry = self._memory.get(key)
        if entry is None:
            return None
        token, expires_at = entry
        if expires_at is not None and time.time() >= expires_at:
            self._memory.pop(key, None)
            return None
        return token

    def delete_session(self, chat_user_id: str) -> bool:
        key = self._session_key(chat_user_id)
        deleted = False
        if self._redis is not None:
            try:
                deleted = bool(self._redis.delete(key))
            except Exception:
                deleted = False
        if key in self._memory:
            self._memory.pop(key, None)
            deleted = True
        for chats in self._user_chats.values():
            chats.discard(chat_user_id)
        return deleted

    def delete_user_sessions(self, username: str) -> int:
        count = 0
        if self._redis is not None:
            try:
                idx_key = self._user_index_key(username)
                chat_ids = list(self._redis.smembers(idx_key))
                for cid in chat_ids:
                    if self._redis.delete(self._session_key(cid)):
                        count += 1
                self._redis.delete(idx_key)
            except Exception:
                pass
        mem_chats = list(self._user_chats.pop(username, set()))
        for cid in mem_chats:
            if self._memory.pop(self._session_key(cid), None) is not None:
                count += 1
        return count


class AuthService:
    """Manages IAM user records, 10h JWT issuance/verification, and 2-tier Kill-Switch."""

    def __init__(self, settings: Settings, session_store: SessionStore | None = None) -> None:
        self.settings = settings
        self.session_store = session_store or SessionStore(settings.redis_url)

    @property
    def iam_file(self) -> Path:
        return self.settings.data_path / "sample_iam_users.json"

    def _load_users(self) -> list[dict[str, Any]]:
        if not self.iam_file.exists():
            return []
        payload = json.loads(self.iam_file.read_text(encoding="utf-8"))
        users = payload.get("users", [])
        return users if isinstance(users, list) else []

    def _save_users(self, users: list[dict[str, Any]]) -> None:
        self.iam_file.parent.mkdir(parents=True, exist_ok=True)
        self.iam_file.write_text(
            json.dumps({"users": users}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_user(self, username: str) -> dict[str, Any] | None:
        target = username.strip()
        for user in self._load_users():
            if user.get("username") == target:
                return user
        return None

    def issue_token(self, user: dict[str, Any]) -> str:
        now = int(time.time())
        ttl = self.settings.jwt_ttl_seconds
        claims = {
            "sub": user["username"],
            "username": user["username"],
            "department": user.get("department", "general"),
            "region": user.get("region", "North"),
            "role": user.get("role", "sales"),
            "iat": now,
            "exp": now + ttl,
        }
        return jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")

    def login(self, username: str, password: str, chat_user_id: str | None = None) -> dict[str, Any]:
        user = self.get_user(username)
        if user is None or not verify_password(password, str(user.get("password_hash", ""))):
            raise AuthError("Sai tên đăng nhập hoặc mật khẩu.", status_code=401)
        if not bool(user.get("is_active", False)):
            raise AuthError("Tài khoản đã bị khóa (Inactive).", status_code=403)

        token = self.issue_token(user)
        if chat_user_id:
            self.session_store.set_session(
                chat_user_id=chat_user_id.strip(),
                username=user["username"],
                token=token,
                ttl_seconds=self.settings.jwt_ttl_seconds,
            )

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": self.settings.jwt_ttl_seconds,
            "user": {
                "username": user["username"],
                "department": user.get("department", "general"),
                "region": user.get("region", "North"),
                "role": user.get("role", "sales"),
                "is_active": True,
            },
        }

    def verify_token(self, token: str) -> dict[str, Any]:
        if not token:
            raise AuthError("Thiếu JWT xác thực.", status_code=401)
        try:
            claims = jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Phiên đăng nhập JWT đã hết hạn.", status_code=401) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("JWT không hợp lệ.", status_code=401) from exc

        username = str(claims.get("username") or claims.get("sub") or "")
        user = self.get_user(username)
        if user is None or not bool(user.get("is_active", False)):
            raise AuthError("Tài khoản đã bị thu hồi quyền hoặc không hoạt động.", status_code=403)
        return claims

    def revoke_session(self, chat_user_id: str) -> dict[str, Any]:
        """Tier-1 Kill-Switch: wipe active chat session JWT without deactivating IAM user."""
        revoked = self.session_store.delete_session(chat_user_id.strip())
        return {
            "tier": 1,
            "action": "revoke_session",
            "chat_user_id": chat_user_id.strip(),
            "session_removed": revoked,
        }

    def deactivate_user(self, username: str, chat_user_id: str | None = None) -> dict[str, Any]:
        """Tier-2 Kill-Switch: set user is_active=False and purge any active chat sessions."""
        users = self._load_users()
        found = False
        for user in users:
            if user.get("username") == username.strip():
                user["is_active"] = False
                found = True
                break
        if not found:
            raise AuthError(f"Không tìm thấy nhân sự: {username}", status_code=404)

        self._save_users(users)
        removed_count = self.session_store.delete_user_sessions(username.strip())
        if chat_user_id:
            if self.session_store.delete_session(chat_user_id.strip()):
                removed_count += 1

        return {
            "tier": 2,
            "action": "deactivate_user",
            "username": username.strip(),
            "is_active": False,
            "sessions_purged": removed_count,
        }

    def provision_user(
        self,
        username: str,
        password: str | None,
        department: str,
        region: str,
        role: str = "sales",
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create or update an IAM user from HR Master Sheet sync."""
        users = self._load_users()
        clean_username = username.strip()
        existing = next((u for u in users if u.get("username") == clean_username), None)

        if existing is not None:
            existing["department"] = department
            existing["region"] = region
            existing["role"] = role
            existing["is_active"] = is_active
            if password:
                existing["password_hash"] = hash_password(password)
            status = "updated"
        else:
            effective_pw = password or secrets.token_urlsafe(12)
            users.append(
                {
                    "username": clean_username,
                    "password_hash": hash_password(effective_pw),
                    "department": department,
                    "region": region,
                    "role": role,
                    "is_active": is_active,
                }
            )
            status = "created"

        self._save_users(users)
        if not is_active:
            self.session_store.delete_user_sessions(clean_username)

        return {
            "status": status,
            "username": clean_username,
            "department": department,
            "region": region,
            "role": role,
            "is_active": is_active,
        }
