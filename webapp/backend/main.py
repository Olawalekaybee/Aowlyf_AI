"""
AOWLYF_AI — Phase 3 web API

A separate, human-facing API from the MCP server. The MCP server (in
mcp_server/) is how Claude reads/writes the platform on your behalf. This
API is how staff log in directly and the Gantt dashboard gets its data —
same Postgres database, same permission rules, different front door.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Reads DATABASE_URL and JWT_SECRET from your project's .env automatically
(no need to re-export them in every terminal).
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import asyncpg
import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Load the project root .env (one level up from webapp/backend/), so you
# don't have to re-export DATABASE_URL in every new terminal.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

app = FastAPI(title="AOWLYF_AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


class LoginRequest(BaseModel):
    email: str
    password: str


class TaskUpdate(BaseModel):
    progress_pct: Optional[int] = None
    status: Optional[str] = None


class ConnectionManager:
    """Tracks connected dashboard clients so task updates can be pushed
    to everyone live, without a page refresh."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def create_token(staff: dict) -> str:
    payload = {
        "sub": str(staff["id"]),
        "role": staff["role"],
        "lab_id": str(staff["lab_id"]) if staff["lab_id"] else None,
        "full_name": staff["full_name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_staff(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@app.post("/auth/login")
async def login(body: LoginRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM staff WHERE email = $1 AND is_active = TRUE", body.email
        )
        if not row or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        token = create_token(dict(row))
        return {
            "token": token,
            "staff": {
                "id": str(row["id"]),
                "full_name": row["full_name"],
                "role": row["role"],
                "lab_id": str(row["lab_id"]) if row["lab_id"] else None,
            },
        }


@app.get("/auth/me")
async def me(current: dict = Depends(get_current_staff)):
    return current


@app.get("/labs")
async def list_labs(current: dict = Depends(get_current_staff)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, kind FROM labs ORDER BY name")
        return [dict(r) for r in rows]


@app.get("/projects")
async def list_projects(current: dict = Depends(get_current_staff)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if current["role"] == "admin":
            rows = await conn.fetch("SELECT * FROM projects ORDER BY start_date NULLS LAST")
        else:
            rows = await conn.fetch(
                """SELECT DISTINCT p.* FROM projects p
                   LEFT JOIN project_members pm ON pm.project_id = p.id
                   WHERE p.lab_id = $1 OR pm.staff_id = $2
                   ORDER BY p.start_date NULLS LAST""",
                current["lab_id"],
                current["sub"],
            )
        return [dict(r) for r in rows]


@app.get("/projects/{project_id}/tasks")
async def project_tasks(project_id: str, current: dict = Depends(get_current_staff)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if current["role"] != "admin":
            member = await conn.fetchrow(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND staff_id = $2",
                project_id,
                current["sub"],
            )
            project = await conn.fetchrow("SELECT lab_id FROM projects WHERE id = $1", project_id)
            in_lab = project and str(project["lab_id"]) == current["lab_id"]
            if not member and not in_lab:
                raise HTTPException(status_code=403, detail="Not a member of this project")
        rows = await conn.fetch(
            """SELECT t.id, t.title, t.start_date, t.end_date, t.progress_pct, t.status,
                      t.assignee_id, s.full_name AS assignee_name
               FROM tasks t
               LEFT JOIN staff s ON s.id = t.assignee_id
               WHERE t.project_id = $1 ORDER BY t.start_date""",
            project_id,
        )
        return [dict(r) for r in rows]


@app.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, current: dict = Depends(get_current_staff)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        fields, values = [], []
        if body.progress_pct is not None:
            values.append(body.progress_pct)
            fields.append(f"progress_pct = ${len(values)}")
        if body.status is not None:
            values.append(body.status)
            fields.append(f"status = ${len(values)}")
        if not fields:
            raise HTTPException(status_code=400, detail="Nothing to update")
        fields.append("updated_at = now()")
        values.append(task_id)
        query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ${len(values)} RETURNING *"
        row = await conn.fetchrow(query, *values)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        task = dict(row)
        await manager.broadcast(
            {
                "type": "task_updated",
                "task_id": str(task["id"]),
                "project_id": str(task["project_id"]),
                "progress_pct": task["progress_pct"],
                "status": task["status"],
            }
        )
        return task


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Dashboard doesn't need to send anything meaningful — this just
            # keeps the connection open so we can push updates to it.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
