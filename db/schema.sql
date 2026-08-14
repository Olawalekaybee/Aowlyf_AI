-- ============================================================================
-- Impact Lab / Innov8 Hub Operations Platform — Core Schema
-- Postgres 15+
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()

-- ----------------------------------------------------------------------------
-- ORG STRUCTURE
-- ----------------------------------------------------------------------------

CREATE TABLE labs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,           -- e.g. 'Electronics', 'Software Lab'
    kind        TEXT NOT NULL DEFAULT 'lab',     -- 'lab' | 'service_department' | 'admin'
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE staff_role AS ENUM ('admin', 'lab_lead', 'staff', 'intern');

CREATE TABLE staff (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE,
    whatsapp_number TEXT,                        -- E.164 format, for reminders
    lab_id          UUID REFERENCES labs(id),
    role            staff_role NOT NULL DEFAULT 'staff',
    password_hash   TEXT NOT NULL,               -- bcrypt/argon2 hash, never plaintext
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    can_grant_team_membership BOOLEAN NOT NULL DEFAULT FALSE, -- explicit admin-set flag:
                                                                -- only TRUE for people the
                                                                -- admin has permitted to
                                                                -- add others to a project team
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- PROJECTS / R&D / PROTOTYPES / TECHNICAL PROGRAMS
-- ----------------------------------------------------------------------------

CREATE TYPE project_status AS ENUM ('proposed', 'active', 'on_hold', 'completed', 'cancelled');

CREATE TABLE projects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    lab_id       UUID REFERENCES labs(id),
    category     TEXT,                            -- 'R&D' | 'Prototype' | 'Technical Program' | 'Departmental'
    description  TEXT,
    status       project_status NOT NULL DEFAULT 'proposed',
    start_date   DATE,
    end_date     DATE,                             -- planned end, drives the Gantt chart
    created_by   UUID REFERENCES staff(id),         -- who proposed it
    approved_by  UUID REFERENCES staff(id),         -- must be admin or a permitted grantor
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Who is actually on a project team. Row can ONLY be inserted by admin or
-- someone with staff.can_grant_team_membership = TRUE — enforce this in the
-- application/MCP layer, not just here.
CREATE TABLE project_members (
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    staff_id     UUID NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    role_on_team TEXT DEFAULT 'contributor',        -- 'lead' | 'contributor' | 'reviewer'
    added_by     UUID NOT NULL REFERENCES staff(id),
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, staff_id)
);

CREATE TYPE task_status AS ENUM ('not_started', 'in_progress', 'blocked', 'done');

CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    assignee_id  UUID REFERENCES staff(id),
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,                     -- these two drive each Gantt bar
    progress_pct SMALLINT NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    status       task_status NOT NULL DEFAULT 'not_started',
    depends_on   UUID REFERENCES tasks(id),          -- optional dependency, for Gantt linking
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- CONCERNS / FEEDBACK (staff -> admin)
-- ----------------------------------------------------------------------------

CREATE TYPE concern_category AS ENUM ('project', 'work', 'procurement', 'general_update', 'internal_review');
CREATE TYPE concern_status   AS ENUM ('open', 'in_review', 'resolved');

CREATE TABLE concerns (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raised_by      UUID NOT NULL REFERENCES staff(id),
    project_id     UUID REFERENCES projects(id),      -- nullable: not all concerns are project-specific
    category       concern_category NOT NULL,
    message        TEXT NOT NULL,
    ai_suggested_response TEXT,                        -- draft generated by the agent, admin edits/approves
    admin_response TEXT,
    status         concern_status NOT NULL DEFAULT 'open',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- PROCUREMENT
-- ----------------------------------------------------------------------------

CREATE TYPE procurement_status AS ENUM ('requested', 'approved', 'ordered', 'received', 'rejected');

CREATE TABLE procurement_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_by  UUID NOT NULL REFERENCES staff(id),
    project_id    UUID REFERENCES projects(id),
    item          TEXT NOT NULL,
    quantity      INT NOT NULL DEFAULT 1,
    justification TEXT,
    status        procurement_status NOT NULL DEFAULT 'requested',
    handled_by    UUID REFERENCES staff(id),           -- procurement team member or admin
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- FOLDERS / FILE ACCESS (metadata layer over MinIO/filesystem)
-- ----------------------------------------------------------------------------

CREATE TYPE folder_scope AS ENUM ('personal', 'lab_shared', 'project_shared', 'department_general');

CREATE TABLE folders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope        folder_scope NOT NULL,
    owner_staff_id UUID REFERENCES staff(id),          -- set when scope = 'personal'
    lab_id       UUID REFERENCES labs(id),              -- set when scope = 'lab_shared'
    project_id   UUID REFERENCES projects(id),          -- set when scope = 'project_shared'
    storage_path TEXT NOT NULL UNIQUE,                  -- path/bucket-prefix on MinIO or disk
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Explicit grants for anyone given access to a folder they wouldn't otherwise see
-- (e.g. admin sharing one file/folder with someone outside the lab/project).
CREATE TABLE folder_grants (
    folder_id  UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    staff_id   UUID NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    can_write  BOOLEAN NOT NULL DEFAULT FALSE,
    granted_by UUID NOT NULL REFERENCES staff(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (folder_id, staff_id)
);

-- ----------------------------------------------------------------------------
-- NOTIFICATIONS (WhatsApp reminders, etc.)
-- ----------------------------------------------------------------------------

CREATE TYPE notification_channel AS ENUM ('whatsapp', 'email', 'in_app');
CREATE TYPE notification_status  AS ENUM ('scheduled', 'sent', 'failed');

CREATE TABLE notifications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id      UUID NOT NULL REFERENCES staff(id),
    channel       notification_channel NOT NULL DEFAULT 'whatsapp',
    related_task_id UUID REFERENCES tasks(id),
    message       TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    sent_at       TIMESTAMPTZ,
    status        notification_status NOT NULL DEFAULT 'scheduled',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- AUDIT LOG — every admin-sensitive action (team grants, folder grants,
-- concern resolutions, procurement approvals) gets logged here.
-- ----------------------------------------------------------------------------

CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id    UUID NOT NULL REFERENCES staff(id),
    action      TEXT NOT NULL,                          -- e.g. 'grant_project_membership'
    target_type TEXT NOT NULL,                           -- e.g. 'project_members'
    target_id   TEXT,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Seed the lab list from the org structure provided
-- ----------------------------------------------------------------------------

INSERT INTO labs (name, kind) VALUES
    ('Electronics', 'lab'),
    ('Embedded System and Control Lab', 'lab'),
    ('3D Lab', 'lab'),
    ('Sustainable Lab', 'lab'),
    ('Product Design Lab', 'lab'),
    ('Autonomous Robotics Lab', 'lab'),
    ('Software Lab', 'lab'),
    ('BioTech Lab', 'lab'),
    ('Simulation Lab', 'lab'),
    ('Fabrication', 'service_department'),
    ('Ecolab', 'service_department'),
    ('Procurement', 'service_department');
