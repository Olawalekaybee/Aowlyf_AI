-- AOWLYF_AI — optional demo data so you can see the Gantt dashboard working
-- right away, before real projects exist. Safe to run once; re-running
-- creates a second demo project rather than erroring.
--
-- Run:
--   docker exec -i aowlyf-ai-postgres psql -U impactlab -d impactlab < seed_demo_project.sql

DO $$
DECLARE
    v_lab_id UUID;
    v_project_id UUID;
    v_staff_id UUID;
BEGIN
    SELECT id INTO v_lab_id FROM labs WHERE name = 'Electronics' LIMIT 1;
    SELECT id INTO v_staff_id FROM staff WHERE role != 'admin' AND lab_id = v_lab_id LIMIT 1;

    INSERT INTO projects (name, lab_id, category, description, status, start_date, end_date, created_by)
    VALUES (
        'Sensor Array Prototype',
        v_lab_id,
        'Prototype',
        'Demo project seeded to preview the Gantt dashboard.',
        'active',
        CURRENT_DATE - INTERVAL '5 days',
        CURRENT_DATE + INTERVAL '25 days',
        v_staff_id
    )
    RETURNING id INTO v_project_id;

    IF v_staff_id IS NOT NULL THEN
        INSERT INTO project_members (project_id, staff_id, role_on_team, added_by)
        VALUES (v_project_id, v_staff_id, 'lead', v_staff_id);
    END IF;

    INSERT INTO tasks (project_id, title, assignee_id, start_date, end_date, progress_pct, status) VALUES
        (v_project_id, 'Requirements & component sourcing', v_staff_id, CURRENT_DATE - INTERVAL '5 days', CURRENT_DATE + INTERVAL '2 days', 100, 'done'),
        (v_project_id, 'PCB schematic design', v_staff_id, CURRENT_DATE, CURRENT_DATE + INTERVAL '10 days', 55, 'in_progress'),
        (v_project_id, 'Firmware sensor drivers', v_staff_id, CURRENT_DATE + INTERVAL '5 days', CURRENT_DATE + INTERVAL '18 days', 15, 'in_progress'),
        (v_project_id, 'Enclosure fabrication', v_staff_id, CURRENT_DATE + INTERVAL '15 days', CURRENT_DATE + INTERVAL '22 days', 0, 'not_started'),
        (v_project_id, 'Waiting on calibration rig', v_staff_id, CURRENT_DATE + INTERVAL '8 days', CURRENT_DATE + INTERVAL '12 days', 20, 'blocked');
END $$;
