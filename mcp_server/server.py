"""
AOWLYF_AI — Impact Lab / Innov8 Hub MCP server

Exposes the local Postgres-backed platform as tools Claude can call directly
(via Claude Desktop, Claude Code, or the API). This is a starting skeleton —
each tool below does real DB work but the permission checks are intentionally
explicit and centralized so they're easy to audit and extend.

Run:
    pip install -r requirements.txt
    python server.py

Then point Claude Desktop at it (see docs/claude_desktop_config.json.example).
"""

import json
import os
import uuid
from datetime import date
from typing import Optional

import asyncpg
from mcp.server.fastmcp import FastMCP

DATABASE_URL = os.environ["DATABASE_URL"]

mcp = FastMCP("aowlyf-ai")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


async def get_staff(conn, staff_id: str) -> asyncpg.Record:
    row = await conn.fetchrow("SELECT * FROM staff WHERE id = $1", staff_id)
    if not row:
        raise ValueError(f"Unknown staff_id: {staff_id}")
    return row


def is_admin(staff_row) -> bool:
    return staff_row["role"] == "admin"


# ----------------------------------------------------------------------------
# READ TOOLS
# ----------------------------------------------------------------------------

@mcp.tool()
async def list_labs() -> list[dict]:
    """List all labs and service departments in the Impact Lab / Innov8 Hub."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, kind, description FROM labs ORDER BY name")
        return [dict(r) for r in rows]


@mcp.tool()
async def list_projects(acting_as: str, lab_id: Optional[str] = None) -> list[dict]:
    """
    List projects visible to `acting_as` (a staff id).
    Admins see everything. Everyone else sees only projects in their own lab,
    or projects they are a member of.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if is_admin(actor):
            query = "SELECT * FROM projects WHERE ($1::uuid IS NULL OR lab_id = $1) ORDER BY start_date"
            rows = await conn.fetch(query, lab_id)
        else:
            query = """
                SELECT DISTINCT p.* FROM projects p
                LEFT JOIN project_members pm ON pm.project_id = p.id
                WHERE (p.lab_id = $1 OR pm.staff_id = $2)
                  AND ($3::uuid IS NULL OR p.lab_id = $3)
                ORDER BY p.start_date
            """
            rows = await conn.fetch(query, actor["lab_id"], actor["id"], lab_id)
        return [dict(r) for r in rows]


@mcp.tool()
async def get_project_timeline(acting_as: str, project_id: str) -> list[dict]:
    """Return all tasks (with dates/progress) for a project, for Gantt rendering."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if not is_admin(actor):
            member = await conn.fetchrow(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND staff_id = $2",
                project_id, actor["id"],
            )
            if not member:
                raise PermissionError("Not a member of this project.")
        rows = await conn.fetch(
            """SELECT id, title, assignee_id, start_date, end_date, progress_pct,
                      status, depends_on
               FROM tasks WHERE project_id = $1 ORDER BY start_date""",
            project_id,
        )
        return [dict(r) for r in rows]


@mcp.tool()
async def list_concerns(acting_as: str, status: Optional[str] = None) -> list[dict]:
    """Admin-only: list staff concerns/feedback, optionally filtered by status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if not is_admin(actor):
            raise PermissionError("Only the admin can list all concerns.")
        rows = await conn.fetch(
            "SELECT * FROM concerns WHERE ($1::text IS NULL OR status = $1) ORDER BY created_at DESC",
            status,
        )
        return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# WRITE TOOLS
# ----------------------------------------------------------------------------

@mcp.tool()
async def create_task(
    acting_as: str, project_id: str, title: str, assignee_id: str,
    start_date: str, end_date: str, description: str = "",
) -> dict:
    """Create a task on a project. Caller must be admin or a member of the project."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if not is_admin(actor):
            member = await conn.fetchrow(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND staff_id = $2",
                project_id, actor["id"],
            )
            if not member:
                raise PermissionError("Not a member of this project.")
        row = await conn.fetchrow(
            """INSERT INTO tasks (project_id, title, description, assignee_id, start_date, end_date)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            project_id, title, description, assignee_id, date.fromisoformat(start_date), date.fromisoformat(end_date),
        )
        return dict(row)


@mcp.tool()
async def add_project_member(acting_as: str, project_id: str, staff_id: str, role_on_team: str = "contributor") -> dict:
    """
    Add someone to a project team.
    ONLY the admin, or a staff member explicitly flagged
    `can_grant_team_membership = TRUE` by the admin, may call this.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if not (is_admin(actor) or actor["can_grant_team_membership"]):
            raise PermissionError("You are not permitted to add people to project teams.")
        row = await conn.fetchrow(
            """INSERT INTO project_members (project_id, staff_id, role_on_team, added_by)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (project_id, staff_id) DO UPDATE SET role_on_team = EXCLUDED.role_on_team
               RETURNING *""",
            project_id, staff_id, role_on_team, actor["id"],
        )
        await conn.execute(
            """INSERT INTO audit_log (actor_id, action, target_type, target_id, detail)
               VALUES ($1, 'grant_project_membership', 'project_members', $2, $3)""",
            actor["id"], project_id, json.dumps({"staff_id": staff_id, "role_on_team": role_on_team}),
        )
        return dict(row)


@mcp.tool()
async def log_concern(acting_as: str, category: str, message: str, project_id: Optional[str] = None) -> dict:
    """Any staff member files a concern/feedback item, routed to the admin queue."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        row = await conn.fetchrow(
            """INSERT INTO concerns (raised_by, project_id, category, message)
               VALUES ($1, $2, $3, $4) RETURNING *""",
            actor["id"], project_id, category, message,
        )
        return dict(row)


@mcp.tool()
async def resolve_concern(acting_as: str, concern_id: str, admin_response: str) -> dict:
    """Admin-only: respond to and close out a concern."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        actor = await get_staff(conn, acting_as)
        if not is_admin(actor):
            raise PermissionError("Only the admin can resolve concerns.")
        row = await conn.fetchrow(
            """UPDATE concerns SET admin_response = $1, status = 'resolved', resolved_at = now()
               WHERE id = $2 RETURNING *""",
            admin_response, concern_id,
        )
        return dict(row)


if __name__ == "__main__":
    mcp.run()