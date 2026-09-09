"""
AOWLYF_AI: update existing staff emails and WhatsApp numbers from a CSV

Use this when staff were originally provisioned without an email or
WhatsApp number, and you have now filled those in on staff_roster.csv.
This updates their existing record in place. Their password and account
stay exactly as they were, only the contact details change. This is what
enables login for staff who could not log in before.

Matches existing staff rows by full_name and lab, the same matching rule
provision_staff.py uses when no email is set yet. Safe to re-run, only
rows whose email actually changed get updated.

Usage:
    pip install -r requirements.txt
    export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
    python update_staff_emails.py staff_roster.csv
"""

import csv
import os
import sys

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def get_lab_id(cur, lab_name):
    cur.execute("SELECT id FROM labs WHERE name = %s", (lab_name,))
    row = cur.fetchone()
    return row[0] if row else None


def main(csv_path):
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    updated = []
    skipped = []
    already_current = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            full_name = row["full_name"].strip()
            lab_name = row["lab"].strip()
            email = row["email"].strip() or None
            whatsapp = row["whatsapp_number"].strip() or None

            if not full_name or not lab_name or not email:
                continue
            if full_name.startswith("[FILL IN"):
                continue

            lab_id = get_lab_id(cur, lab_name)
            if not lab_id:
                skipped.append(f"{full_name} (lab '{lab_name}' not found)")
                continue

            cur.execute(
                "SELECT id, email FROM staff WHERE full_name = %s AND lab_id = %s",
                (full_name, lab_id),
            )
            existing = cur.fetchone()
            if not existing:
                skipped.append(f"{full_name} (no matching staff record in this lab)")
                continue

            staff_id, current_email = existing
            if current_email == email:
                already_current += 1
                continue

            cur.execute(
                """UPDATE staff
                   SET email = %s,
                       whatsapp_number = COALESCE(%s, whatsapp_number),
                       updated_at = now()
                   WHERE id = %s""",
                (email, whatsapp, staff_id),
            )
            updated.append(full_name)

    conn.commit()
    cur.close()
    conn.close()

    print(f"Updated {len(updated)} staff record(s):")
    for name in updated:
        print(f"  - {name}")

    if already_current:
        print(f"\n{already_current} record(s) already had the correct email, no change needed.")

    if skipped:
        print(f"\nSkipped {len(skipped)} row(s):")
        for name in skipped:
            print(f"  - {name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_staff_emails.py <staff_roster.csv>")
        sys.exit(1)
    main(sys.argv[1])