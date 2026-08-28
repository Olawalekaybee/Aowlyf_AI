
# AOWLYF_AI — Impact Lab / Innov8 Hub Ops Platform (DGX Spark + Claude)

A private, locally-run agentic system for managing every lab, project, staff
member, folder, timeline, concern, and procurement request across the Impact
Lab and Innov8 Hub — with Claude as the conversational/agentic front end and
the DGX Spark as the private, always-on backend.

## 1. Architecture overview

```
                         ┌─────────────────────────┐
                         │   You, via Claude        │
                         │  (Desktop / Code / API)  │
                         └────────────┬─────────────┘
                                      │ MCP (tools)
                         ┌────────────▼─────────────┐
                         │   mcp_server/server.py    │   <- runs on DGX Spark
                         │  (role-checked tool calls)│
                         └────────────┬─────────────┘
              ┌───────────────┬───────┴────────┬────────────────┐
              ▼               ▼                ▼                ▼
        ┌──────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
        │ Postgres │   │   MinIO    │   │   Qdrant   │   │   Ollama   │
        │ (system  │   │ (per-user/ │   │  (RAG over │   │ (local LLM,│
        │ of record)│  │ per-lab    │   │  lab docs) │   │ private    │
        │           │  │ folders)   │   │            │   │ inference) │
        └──────────┘   └────────────┘   └────────────┘   └────────────┘
                                      │
                              ┌───────▼────────┐
                              │  Redis queue     │──► Twilio WhatsApp API
                              │ (reminders/jobs)  │    (Phase 4)
                              └────────────────┘
```

Claude is the **reasoning and conversation layer** — you talk to it normally
("add Ann to the sensor prototype project", "what's overdue in the Software
Lab", "draft a reply to Habeeb's concern"), and it calls tools on your MCP
server to actually read/write the platform. The local LLM (Ollama) and Qdrant
handle private, always-on work that shouldn't leave the Spark — document
search, routine classification, drafting — while Claude handles the harder
reasoning and the conversational interface. Nothing here requires your lab
data to leave your hardware unless you choose to send it to Claude.

## 2. What's in this scaffold right now

| Path                                        | Purpose                                                                                                                                                              |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker-compose.yml`                      | Postgres, Redis, MinIO, Qdrant, Ollama — the whole local infra stack                                                                                                |
| `db/schema.sql`                           | Full data model: labs, staff, roles, projects, tasks, concerns, procurement, folders, notifications, audit log. Pre-seeded with your 9 labs + 3 service departments. |
| `mcp_server/server.py`                    | Working MCP server skeleton with role-checked tools (list projects, get timeline, create task, add project member, log/resolve concerns)                             |
| `docs/claude_desktop_config.json.example` | How to point Claude Desktop at your local MCP server                                                                                                                 |

This is a **real foundation**, not a mockup — the schema and permission logic
are wired to your actual org structure and rules (admin-only team grants,
per-person folders, concern routing). What's not built yet: the web UI, the
Gantt view, and WhatsApp delivery. See the roadmap below.

## 3. Your org structure, as encoded

**Labs:** Electronics, Embedded System & Control, 3D, Sustainable, Product
Design, Autonomous Robotics, Software, BioTech, Simulation.
**Service departments:** Fabrication, Ecolab, Procurement.

Staff/interns aren't seeded yet (deliberately — you should add real people via
a script or the MCP `add_staff` tool once it exists, not hardcode names into
version control). A `seed_staff.sql` template is a natural next step once
you confirm emails/WhatsApp numbers for everyone.

## 4. Permission rules, as implemented

- **Admin (you):** full visibility and control over everyone, every project,
  every folder. Every sensitive action is written to `audit_log`.
- **Everyone else:** sees their own personal folder, their lab's shared
  folder, and any project folder they're a confirmed member of — nothing
  more. Enforced in `list_projects`/`get_project_timeline` today; the same
  pattern extends to folder-serving endpoints.
- **Team assignment:** only you, or someone you've explicitly flagged
  `can_grant_team_membership = TRUE`, can add anyone to a project team
  (`add_project_member`). Everyone else gets a `PermissionError`.
- **Concerns:** any staff member can file one (`log_concern`); only you can
  see the full list or resolve one (`list_concerns`, `resolve_concern`).
  The `ai_suggested_response` column is there so an agent can draft a reply
  for your approval, not send anything unsupervised.

## 5. Setup (from a fresh DGX Spark)

```bash
# 1. Install Docker + NVIDIA Container Toolkit (for Ollama GPU access)
#    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

# 2. Configure secrets
cp .env.example .env
# edit .env with real passwords

# 3. Bring up the infra stack
docker compose up -d
# Postgres will auto-run db/schema.sql on first boot

# 4. Pull a local model into Ollama
docker exec -it impactlab-ollama ollama pull llama3.1:8b

# 5. Run the MCP server
cd mcp_server
pip install -r requirements.txt
export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
python server.py

# 6. Point Claude Desktop at it
#    copy docs/claude_desktop_config.json.example into your Claude Desktop
#    config, update the path, restart Claude Desktop
```

## 6. Roadmap — everything else, in build order

**Phase 1 — Foundation (this scaffold)**
Data model, permission logic, MCP server skeleton. ✅ done.

**Phase 2 — Staff & folder provisioning** ✅ done
See `scripts/`:

- `create_admin.py` — run this yourself, once, to create your own admin
  account. It prompts interactively (`getpass`) so your password is never
  written to disk or logged — only its bcrypt hash goes into Postgres.
- `staff_roster.csv` — pre-filled with everyone from your org structure
  (Electronics, Embedded System & Control, 3D, Sustainable, Product Design,
  Software, BioTech, Simulation, Procurement). A few rows are marked
  `[FILL IN - ...]` where I didn't have real names (Autonomous Robotics'
  two staff, Fabrication, Ecolab) — replace those before running the script.
  Emails and WhatsApp numbers are left blank for you to fill in; without an
  email a person is provisioned but can't log in yet, and without a
  WhatsApp number they won't get Phase 4 reminders.
- `provision_staff.py` — reads that CSV and, per person: creates their
  `staff` row with a randomly generated password (bcrypt-hashed in the DB,
  never stored in plaintext), creates their personal MinIO folder, and
  ensures their lab's shared folder exists. Safe to re-run — existing
  people (by email) are skipped. Writes initial passwords to
  `staff_credentials_DO_NOT_COMMIT.csv` (gitignored) for you to hand out
  individually, then delete.

Run order:

```bash
cd scripts
pip install -r requirements.txt
export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=impactlab-admin      # from your .env
export MINIO_SECRET_KEY=<your MINIO_ROOT_PASSWORD>

python create_admin.py          # you, first — full control
# edit staff_roster.csv: fill in the [FILL IN...] rows, add real emails
python provision_staff.py staff_roster.csv
```

**Note on folder enforcement:** MinIO folders are organized by prefix
(`personal/<name>-<id>/`, `labs/<lab>/shared/`) inside one bucket, and access
is enforced at the application layer — the MCP server / future file-serving
API checks the `folders`/`folder_grants` tables before returning anything,
the same way `list_projects` already checks project membership. That's
enough for this platform's purposes; if you later want defense-in-depth at
the storage layer too, MinIO supports per-prefix IAM policies as a Phase 6
hardening step.

Add a `login`/session layer (even a simple JWT-based one) next, so staff
authenticate with the password `provision_staff.py` generated for them and
that identity becomes their `acting_as` id in every tool call.

**Phase 3 — Web app: dashboard + Gantt** ✅ done
A separate, human-facing layer from the MCP server — same Postgres
database, same permission rules, different front door. Staff log in
directly with the email/password `provision_staff.py` set up for them;
Claude keeps using the MCP server exactly as before. Lives in `webapp/`:

- `webapp/backend/` — a small FastAPI app: `/auth/login` (checks the
  bcrypt password hash, issues a JWT), `/projects` and
  `/projects/{id}/tasks` (scoped the same way as the MCP tools — admins
  see everything, everyone else sees their own lab + projects they're a
  member of), and a `/ws` WebSocket that pushes task updates to every
  connected dashboard live, no page refresh needed.
- `webapp/frontend/` — a React + Vite dashboard: a login screen, a project
  list grouped by lab, and a Gantt view where each task's bar width
  animates smoothly when its progress changes (via the WebSocket push).
  Styled as a dark "engineering console" — grid background, amber signal
  color for in-progress work with a live pulse indicator, teal for done,
  red for blocked.

Run order (two terminals, alongside your existing Docker stack):

```bash
# Terminal 1 — backend
cd webapp/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# (reads DATABASE_URL and JWT_SECRET from your project .env automatically)

# Terminal 2 — frontend
cd webapp/frontend
npm install
npm run dev
# opens on http://localhost:5173
```

Log in with any staff email + the password `provision_staff.py` generated
for them (see `scripts/staff_credentials_DO_NOT_COMMIT.csv` before you
delete it). No projects exist yet fresh out of Phase 2 — either create one
via Claude/the MCP tools, or run `scripts/seed_demo_project.sql` for a
one-command demo project to see the Gantt working immediately:

```bash
docker exec -i aowlyf-ai-postgres psql -U impactlab -d impactlab < scripts/seed_demo_project.sql
```

**Not yet built:** a "create project" / "create task" UI (for now that
happens via Claude or direct MCP calls), and the General Update /
Procurement / Internal Review request forms that write into
`concerns`/`procurement_requests`.

**Phase 4 — WhatsApp reminders**
Twilio WhatsApp Business API (there's a whole Twilio skill set already
available for this — template approval, 24-hour session rules, etc.). A
worker reads `notifications` due in the next N minutes/hours and sends them,
driven off task deadlines and project milestones.

**Phase 5 — Agentic layer**

- Concern triage agent: classifies incoming concerns, drafts a suggested
  response into `ai_suggested_response` using Qdrant-retrieved project
  context, you approve/edit/send.
- Weekly digest agent: summarizes each lab's status into a report you review
  before it goes out.
- RAG over lab reports/prototypes so you (or lab leads, scoped correctly) can
  ask "what's the status of the biotech incubator project" and get a grounded
  answer instead of hunting through folders.

**Phase 6 — Hardening**
Real auth (rotate the password-hashing approach if needed, add MFA for the
admin account), backups for Postgres/MinIO, and a proper folder-serving layer
that enforces `folders`/`folder_grants` on every file read, not just at the
project level.

**Phase 3 — Login layer + Gantt dashboard** ✅ started
See `backend/` and `frontend/`:

- `backend/main.py` — a FastAPI app: `/auth/login` (email + password → JWT),
  `/me`, `/labs`, `/projects` (permission-scoped: admins see everything,
  everyone else sees their own lab + projects they're a member of),
  `/projects/{id}/tasks` (drives the Gantt), `/dashboard/summary`, and the
  `/concerns` pipeline (file one, admin lists/resolves). Same Postgres
  database as the MCP server — this is the plain-HTTP interface for the web
  dashboard, while `mcp_server/server.py` stays the interface Claude uses.
- `backend/auth.py` — bcrypt password verification + JWT issuing/checking.
- `frontend/index.html` — a single-file dashboard (React via CDN, no build
  step) with a login screen and a live-updating Gantt view — task bars
  poll every 5 seconds so progress updates show up without a manual
  refresh, and colors shift (blue → green/red) as a task's status changes.

Run order:

```bash
# Backend
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal) — serve it rather than opening the file
# directly, so the browser's fetch calls to the API behave correctly
cd ../frontend
python3 -m http.server 5500
# then open http://localhost:5500 in a browser
```

Log in with the admin account (or any provisioned staff member's email +
the initial password from `staff_credentials_DO_NOT_COMMIT.csv`) — you
should NOT be able to see other labs' projects unless you're admin.

**Not built yet:** the General Update / Procurement / Internal Review
request forms (the `/concerns` and `/procurement_requests` tables and API
support them; the UI for filing one is still to come), WhatsApp reminders,
and a "change my password" flow for staff logging in for the first time.

## 7. Immediate next decision

Phase 2 (staff/folder provisioning) or Phase 3 (the Gantt dashboard) are the
two that make this feel real day-to-day. Worth picking whichever one you'd
actually put in front of staff first.
