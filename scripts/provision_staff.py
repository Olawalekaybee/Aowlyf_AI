"""
AOWLYF_AI — staff & folder provisioning (Phase 2)

Reads a CSV roster and, for each person:
  1. Creates a `staff` row in Postgres with a securely hashed password
     (a random one is generated for you — nothing is ever stored in
     plaintext in the database).
  2. Creates their personal folder prefix in MinIO + a matching `folders`
     row (scope='personal').
  3. Ensures their lab's shared folder exists in MinIO + `folders` row
     (scope='lab_shared') — idempotent across staff in the same lab.
  4. Writes plaintext INITIAL passwords to a local file
     (staff_credentials_DO_NOT_COMMIT.csv) so you can hand them out
     individually. Delete that file once everyone has logged in and
     changed their password.

Safe to re-run: staff already in the database are skipped — matched by
email when one is set, or by full name + lab when it isn't (so re-running
this on rows with no email yet doesn't create duplicates). Rows with a
placeholder name (starting with "[FILL IN") are skipped with a warning —
edit staff_roster.csv first.

Usage:
    pip install -r requirements.txt
    export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
    export MINIO_ENDPOINT=localhost:9000
    export MINIO_ACCESS_KEY=...
    export MINIO_SECRET_KEY=...
    python provision_staff.py staff_roster.csv
"""

import csv
import io
import os
import secrets
import sys
from pathlib import Path

import bcrypt
import psycopg2
from minio import Minio
from minio.error import S3Error

DATABASE_URL = os.environ["DATABASE_URL"]
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

BUCKET = "aowlyf-ai-folders"
CREDENTIALS_OUT = Path("staff_credentials_DO_NOT_COMMIT.csv")


def slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace(".", "")


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def get_or_create_lab(cur, lab_name: str) -> str:
    cur.execute("SELECT id FROM labs WHERE name = %s", (lab_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO labs (name, kind) VALUES (%s, 'lab') RETURNING id",
        (lab_name,),
    )
    return cur.fetchone()[0]


def ensure_minio_prefix(mc: Minio, prefix: str):
    """MinIO has no real 'folders' — write a zero-byte placeholder object
    so the prefix exists and is immediately browsable."""
    marker = f"{prefix.rstrip('/')}/.keep"
    try:
        mc.stat_object(BUCKET, marker)
    except S3Error:
        mc.put_object(BUCKET, marker, data=io.BytesIO(b""), length=0)


def ensure_folder_row(cur, scope, storage_path, owner_staff_id=None, lab_id=None):
    cur.execute("SELECT id FROM folders WHERE storage_path = %s", (storage_path,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO folders (scope, owner_staff_id, lab_id, storage_path)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (scope, owner_staff_id, lab_id, storage_path),
    )
    return cur.fetchone()[0]


def main(csv_path: str):
    mc = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
               secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)
    if not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    credentials_rows = []
    skipped = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            full_name = row["full_name"].strip()
            lab_name = row["lab"].strip()
            role = row["role"].strip() or "staff"
            email = row["email"].strip() or None
            whatsapp = row["whatsapp_number"].strip() or None

            if not full_name or not lab_name:
                continue
            if full_name.startswith("[FILL IN"):
                skipped.append(full_name)
                continue

            lab_id = get_or_create_lab(cur, lab_name)

            if email:
                cur.execute("SELECT id FROM staff WHERE email = %s", (email,))
                if cur.fetchone():
                    print(f"Skipping {full_name} — already exists ({email})")
                    continue
            else:
                # No email on file — fall back to matching on name + lab so
                # re-running this script doesn't create duplicate records.
                cur.execute(
                    "SELECT id FROM staff WHERE full_name = %s AND lab_id = %s",
                    (full_name, lab_id),
                )
                if cur.fetchone():
                    print(f"Skipping {full_name} — already exists in this lab (no email set)")
                    continue

            password = generate_password()
            pw_hash = hash_password(password)

            cur.execute(
                """INSERT INTO staff (full_name, email, whatsapp_number, lab_id, role, password_hash)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (full_name, email, whatsapp, lab_id, role, pw_hash),
            )
            staff_id = cur.fetchone()[0]

            # Personal folder — visible only to this person + admin
            personal_prefix = f"personal/{slugify(full_name)}-{staff_id}"
            ensure_minio_prefix(mc, personal_prefix)
            ensure_folder_row(cur, "personal", personal_prefix, owner_staff_id=staff_id)

            # Lab shared folder — visible to everyone in that lab + admin
            lab_prefix = f"labs/{slugify(lab_name)}/shared"
            ensure_minio_prefix(mc, lab_prefix)
            ensure_folder_row(cur, "lab_shared", lab_prefix, lab_id=lab_id)

            credentials_rows.append({
                "full_name": full_name,
                "lab": lab_name,
                "role": role,
                "email": email or "(not set — add before this person can log in)",
                "initial_password": password,
            })

            print(f"Provisioned: {full_name} ({lab_name}, {role})")

    conn.commit()
    cur.close()
    conn.close()

    if credentials_rows:
        with open(CREDENTIALS_OUT, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["full_name", "lab", "role", "email", "initial_password"]
            )
            writer.writeheader()
            writer.writerows(credentials_rows)
        print(f"\n{len(credentials_rows)} staff provisioned.")
        print(f"Initial passwords written to: {CREDENTIALS_OUT.resolve()}")
        print("Hand these out individually and securely, then DELETE this file.")

    if skipped:
        print(f"\nSkipped {len(skipped)} placeholder row(s) — fill in real names first:")
        for name in skipped:
            print(f"  - {name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python provision_staff.py <staff_roster.csv>")
        sys.exit(1)
    main(sys.argv[1])