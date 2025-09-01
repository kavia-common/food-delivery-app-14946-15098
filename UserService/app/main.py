import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import uuid

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, validator
import sqlite3
import bcrypt
import jwt

# Configuration via ENV (do not hardcode secrets)
JWT_SECRET = os.getenv("USER_SERVICE_JWT_SECRET", "CHANGE_ME_DEV_ONLY")
JWT_ISSUER = os.getenv("USER_SERVICE_JWT_ISSUER", "user-service")
ACCESS_TOKEN_EXPIRES_MIN = int(os.getenv("USER_SERVICE_ACCESS_TOKEN_MIN", "30"))
REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("USER_SERVICE_REFRESH_TOKEN_DAYS", "7"))
DATABASE_URL = os.getenv("USER_SERVICE_DB_PATH", "users.db")

# Database Utilities
def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'customer',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS addresses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                label TEXT,
                line1 TEXT NOT NULL,
                line2 TEXT,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                postal_code TEXT NOT NULL,
                country TEXT NOT NULL,
                lat REAL,
                lng REAL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

# Pydantic Models to align with openapi/user.yaml

class GeoPoint(BaseModel):
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")

class Address(BaseModel):
    id: Optional[str] = Field(None, description="Address ID")
    label: Optional[str] = None
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postalCode: str
    country: str
    location: Optional[GeoPoint] = None

    @validator("postalCode")
    def ensure_postal_code(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("postalCode must be provided")
        return v

class User(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = Field("customer", description="User role")
    addresses: Optional[List[Address]] = []
    createdAt: datetime
    updatedAt: datetime

class UserRegistrationRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthToken(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = Field("Bearer", description="Token type")
    expiresIn: int = Field(..., description="Access token expiration in seconds")

class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    addresses: Optional[List[Address]] = None

# Security
bearer_scheme = HTTPBearer(auto_error=False)

# PUBLIC_INTERFACE
def create_access_token(sub: str, role: str) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MIN)
    payload = {
        "iss": JWT_ISSUER,
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

# PUBLIC_INTERFACE
def create_refresh_token(sub: str) -> str:
    """Create a signed JWT refresh token."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
    payload = {
        "iss": JWT_ISSUER,
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# DB Access Helpers
def row_to_user(row: sqlite3.Row, conn: sqlite3.Connection) -> User:
    # Fetch addresses for user
    addr_rows = conn.execute(
        "SELECT * FROM addresses WHERE user_id = ?", (row["id"],)
    ).fetchall()
    addresses: List[Address] = []
    for a in addr_rows:
        location = None
        if a["lat"] is not None and a["lng"] is not None:
            location = GeoPoint(lat=a["lat"], lng=a["lng"])
        addresses.append(
            Address(
                id=a["id"],
                label=a["label"],
                line1=a["line1"],
                line2=a["line2"],
                city=a["city"],
                state=a["state"],
                postalCode=a["postal_code"],
                country=a["country"],
                location=location,
            )
        )
    return User(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        phone=row["phone"],
        role=row["role"],
        addresses=addresses,
        createdAt=datetime.fromisoformat(row["created_at"]),
        updatedAt=datetime.fromisoformat(row["updated_at"]),
    )

def save_addresses(conn: sqlite3.Connection, user_id: str, addresses: Optional[List[Address]]):
    conn.execute("DELETE FROM addresses WHERE user_id = ?", (user_id,))
    if not addresses:
        return
    for addr in addresses:
        addr_id = addr.id or str(uuid.uuid4())
        lat = addr.location.lat if addr.location else None
        lng = addr.location.lng if addr.location else None
        conn.execute(
            """
            INSERT INTO addresses (id, user_id, label, line1, line2, city, state, postal_code, country, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                addr_id,
                user_id,
                addr.label,
                addr.line1,
                addr.line2,
                addr.city,
                addr.state,
                addr.postalCode,
                addr.country,
                lat,
                lng,
            ),
        )

# Dependency to get current user from Authorization header
async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = credentials.credentials
    payload = verify_token(token, expected_type="access")
    user_id = payload.get("sub")
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return row_to_user(row, conn)
    finally:
        conn.close()

# FastAPI app initialization
app = FastAPI(
    title="User Service API",
    description="Manages user registration, authentication, profile, MFA, and account recovery.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Auth", "description": "Authentication endpoints"},
        {"name": "Users", "description": "User profile endpoints"},
    ],
)

# CORS (liberal defaults for dev; configure via env for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("USER_SERVICE_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    init_db()

# Routes
@app.post("/auth/register", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Auth"], summary="Register new user")
def register_user(payload: UserRegistrationRequest):
    """
    Register a new user with email and password.
    - email: unique, required
    - password: min 8 characters
    Returns the created user object (without password).
    """
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (str(payload.email).lower(),)).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, name, phone, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                str(payload.email).lower(),
                get_password_hash(payload.password),
                payload.name,
                payload.phone,
                "customer",
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return row_to_user(row, conn)
    finally:
        conn.close()

@app.post("/auth/login", response_model=AuthToken, tags=["Auth"], summary="Login with email and password")
def login(payload: LoginRequest):
    """
    Authenticate a user and obtain access/refresh tokens.
    - Validates email/password using bcrypt.
    - Issues JWT access and refresh tokens (HS256).
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (str(payload.email).lower(),)).fetchone()
        if not row or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        access = create_access_token(row["id"], role=row["role"])
        refresh = create_refresh_token(row["id"])
        return AuthToken(
            accessToken=access,
            refreshToken=refresh,
            tokenType="Bearer",
            expiresIn=ACCESS_TOKEN_EXPIRES_MIN * 60,
        )
    finally:
        conn.close()

class RefreshRequest(BaseModel):
    refreshToken: str

@app.post("/auth/refresh", response_model=AuthToken, tags=["Auth"], summary="Refresh access token")
def refresh_token(body: RefreshRequest):
    """
    Refresh the access token using a valid refresh token.
    - No authentication header required (security: []).
    - Validates refresh token and issues a new access and refresh token.
    """
    payload = verify_token(body.refreshToken, expected_type="refresh")
    user_id = payload.get("sub")
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        access = create_access_token(row["id"], role=row["role"])
        refresh = create_refresh_token(row["id"])
        return AuthToken(
            accessToken=access,
            refreshToken=refresh,
            tokenType="Bearer",
            expiresIn=ACCESS_TOKEN_EXPIRES_MIN * 60,
        )
    finally:
        conn.close()

@app.get("/users/me", response_model=User, tags=["Users"], summary="Get current user")
def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the current authenticated user's profile.
    - Requires a valid Bearer access token.
    """
    return current_user

@app.patch("/users/me", response_model=User, tags=["Users"], summary="Update current user")
def update_me(payload: UserUpdateRequest, current_user: User = Depends(get_current_user)):
    """
    Update current authenticated user's profile fields.
    - Allows updating name, phone, and addresses.
    - Replaces addresses with provided list.
    """
    conn = get_db()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        if payload.name is not None or payload.phone is not None:
            conn.execute(
                """
                UPDATE users SET
                    name = COALESCE(?, name),
                    phone = COALESCE(?, phone),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.phone,
                    now_iso,
                    current_user.id,
                ),
            )
        if payload.addresses is not None:
            save_addresses(conn, current_user.id, payload.addresses)
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
        return row_to_user(row, conn)
    finally:
        conn.close()

# PUBLIC_INTERFACE
@app.get("/openapi.json", include_in_schema=False)
def custom_openapi():
    """Serve FastAPI-generated OpenAPI JSON."""
    return app.openapi()
