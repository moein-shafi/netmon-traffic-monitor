"""
Authentication and authorization system for NetMon.
Supports JWT-based authentication with admin/user roles.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import CONFIG_DIR, SECRETS_PATH

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY_FILE = CONFIG_DIR / ".jwt_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# HTTP Bearer token
security = HTTPBearer()

# User storage (in production, use a proper database)
USERS_FILE = CONFIG_DIR / "users.json"


def get_or_create_secret_key() -> str:
    """Get or create JWT secret key."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    
    # Generate a secure random key
    key = secrets.token_urlsafe(64)
    SECRET_KEY_FILE.write_text(key)
    SECRET_KEY_FILE.chmod(0o600)  # Restrict permissions
    return key


SECRET_KEY = get_or_create_secret_key()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def load_users() -> Dict[str, Dict]:
    """Load users from disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        # Create default admin user
        default_users = {
            "admin": {
                "username": "admin",
                "hashed_password": get_password_hash("admin"),  # CHANGE THIS IN PRODUCTION!
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "active": True,
            }
        }
        save_users(default_users)
        return default_users
    
    try:
        with USERS_FILE.open("r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[auth] Failed to load users: {e}")
        return {}


def save_users(users: Dict[str, Dict]) -> None:
    """Save users to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with USERS_FILE.open("w") as f:
        json.dump(users, f, indent=2)
    USERS_FILE.chmod(0o600)  # Restrict permissions


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """Authenticate a user and return user info if valid."""
    users = load_users()
    user = users.get(username)
    
    if not user:
        return None
    
    if not user.get("active", True):
        return None
    
    if not verify_password(password, user["hashed_password"]):
        return None
    
    return {
        "username": user["username"],
        "role": user.get("role", "user"),
    }


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Get the current authenticated user from JWT token."""
    token = credentials.credentials
    payload = verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    users = load_users()
    user = users.get(username)
    
    if user is None or not user.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return {
        "username": username,
        "role": user.get("role", "user"),
    }


def require_admin(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Require admin role for access."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def create_user(username: str, password: str, role: str = "user") -> Dict:
    """Create a new user (admin only)."""
    users = load_users()
    
    if username in users:
        raise ValueError(f"User {username} already exists")
    
    if role not in ["admin", "user"]:
        raise ValueError(f"Invalid role: {role}")
    
    users[username] = {
        "username": username,
        "hashed_password": get_password_hash(password),
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    
    save_users(users)
    return {
        "username": username,
        "role": role,
        "created_at": users[username]["created_at"],
    }


def update_user_password(username: str, new_password: str) -> None:
    """Update a user's password."""
    users = load_users()
    
    if username not in users:
        raise ValueError(f"User {username} not found")
    
    users[username]["hashed_password"] = get_password_hash(new_password)
    save_users(users)


def list_users() -> List[Dict]:
    """List all users (admin only)."""
    users = load_users()
    return [
        {
            "username": username,
            "role": user.get("role", "user"),
            "created_at": user.get("created_at"),
            "active": user.get("active", True),
        }
        for username, user in users.items()
    ]

