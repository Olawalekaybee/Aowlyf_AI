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

import json
import os
from datetime import date, datetime, timedelta, timezone
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


class ProjectCreate(BaseModel):
    name: str
    lab_id: str
    category: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ProjectStatusUpdate(BaseModel):
    status: str


class TaskCreate(BaseModel):
    title: str
    assignee_id: Optional[str] = None
    start_date: str
    end_date: str
    description: Optional[str] = None


class MemberAdd(BaseModel):
    staff_id: str
    role_on_team: str = "contributor"


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
        "can_grant_team_membership": staff["can_grant_team_membership"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def can_manage_team(current: dict) -> bool:
    return current["role"] == "admin" or current.get("can_grant_team_membership")


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
                "can_grant_team_membership": row["can_grant_team_membership"],
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


@app.get("/staff")
async def list_staff(current: dict = Depends(get_current_staff)):
    """For assignee/member pickers. Admins see everyone; everyone else
    sees only their own lab, same visibility rule as everywhere else."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if current["role"] == "admin":
            rows = await conn.fetch(
                "SELECT id, full_name, role, lab_id FROM staff WHERE is_active = TRUE ORDER BY full_name"
            )
        else:
            rows = await conn.fetch(
                "SELECT id, full_name, role, lab_id FROM staff WHERE is_active = TRUE AND lab_id = $1 ORDER BY full_name",
                current["lab_id"],
            )
        return [dict(r) for r in rows]


@app.post("/projects")
async def create_project(body: ProjectCreate, current: dict = Depends(get_current_staff)):
    """Anyone can propose a project. Admin-created projects go straight to
    'active'; everyone else's start as 'proposed' until an admin activates
    them — team ADDITIONS are still admin/permitted-only, separately, via
    /projects/{id}/members."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        is_admin = current["role"] == "admin"
        row = await conn.fetchrow(
            """INSERT INTO projects (name, lab_id, category, description, status, start_date, end_date, created_by, approved_by)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            body.name,
            body.lab_id,
            body.category,
            body.description,
            "active" if is_admin else "proposed",
            date.fromisoformat(body.start_date) if body.start_date else None,
            date.fromisoformat(body.end_date) if body.end_date else None,
            current["sub"],
            current["sub"] if is_admin else None,
        )
        return dict(row)


@app.patch("/projects/{project_id}")
async def update_project_status(
    project_id: str, body: ProjectStatusUpdate, current: dict = Depends(get_current_staff)
):
    if current["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the admin can change a project's status")
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE projects SET status = $1, approved_by = $2, updated_at = now() WHERE id = $3 RETURNING *",
            body.status,
            current["sub"],
            project_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        return dict(row)


@app.post("/projects/{project_id}/members")
async def add_member(project_id: str, body: MemberAdd, current: dict = Depends(get_current_staff)):
    if not can_manage_team(current):
        raise HTTPException(status_code=403, detail="You're not permitted to add people to project teams")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """INSERT INTO project_members (project_id, staff_id, role_on_team, added_by)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (project_id, staff_id) DO UPDATE SET role_on_team = EXCLUDED.role_on_team
               RETURNING *""",
            project_id,
            body.staff_id,
            body.role_on_team,
            current["sub"],
        )
        await conn.execute(
            """INSERT INTO audit_log (actor_id, action, target_type, target_id, detail)
               VALUES ($1, 'grant_project_membership', 'project_members', $2, $3)""",
            current["sub"],
            project_id,
            json.dumps({"staff_id": body.staff_id, "role_on_team": body.role_on_team}),
        )
        return dict(row)


@app.get("/projects/{project_id}/members")
async def list_members(project_id: str, current: dict = Depends(get_current_staff)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT pm.staff_id, pm.role_on_team, s.full_name
               FROM project_members pm JOIN staff s ON s.id = pm.staff_id
               WHERE pm.project_id = $1 ORDER BY s.full_name""",
            project_id,
        )
        return [dict(r) for r in rows]


@app.post("/projects/{project_id}/tasks")
async def create_task_rest(project_id: str, body: TaskCreate, current: dict = Depends(get_current_staff)):
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
        row = await conn.fetchrow(
            """INSERT INTO tasks (project_id, title, description, assignee_id, start_date, end_date)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            project_id,
            body.title,
            body.description,
            body.assignee_id,
            date.fromisoformat(body.start_date),
            date.fromisoformat(body.end_date),
        )
        task = dict(row)
        await manager.broadcast(
            {
                "type": "task_created",
                "task_id": str(task["id"]),
                "project_id": str(task["project_id"]),
            }
        )
        return task


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