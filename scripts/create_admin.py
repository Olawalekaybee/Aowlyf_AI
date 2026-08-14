"""
AOWLYF_AI — one-time admin account bootstrap.

Run this yourself, interactively, to create the ONE account with full
platform control (sees everyone, every project, every folder; can grant
project team membership; resolves concerns; approves procurement).

Your password is never written to disk or logged — only its bcrypt hash
goes into the database.

Usage:
    export DATABASE_URL=postgresql://impactlab:changeme@localhost:5432/impactlab
    python create_admin.py
"""

import getpass
import os

import bcrypt
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    print("=== AOWLYF_AI admin account setup ===\n")
    full_name = input("Your full name: ").strip()
    email = input("Your email: ").strip()
    whatsapp = input("Your WhatsApp number (E.164, e.g. +2348012345678): ").strip()
    password = getpass.getpass("Choose an admin password: ")
    confirm = getpass.getpass("Confirm password: ")

    if not full_name or not email or not password:
        print("Name, email, and password are required. Aborting.")
        return
    if password != confirm:
        print("Passwords did not match. Aborting.")
        return
    if len(password) < 12:
        print("Use at least 12 characters for the admin password. Aborting.")
        return

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id FROM staff WHERE role = 'admin'")
    if cur.fetchone():
        confirm_dup = input(
            "An admin account already exists. Create another one anyway? [y/N]: "
        ).strip().lower()
        if confirm_dup != "y":
            print("Aborting.")
            cur.close()
            conn.close()
            return

    cur.execute(
        """INSERT INTO staff (full_name, email, whatsapp_number, role, password_hash, can_grant_team_membership)
           VALUES (%s, %s, %s, 'admin', %s, TRUE) RETURNING id""",
        (full_name, email, whatsapp, pw_hash),
    )
    staff_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    print(f"\nAdmin account created: {full_name} ({email}) — id {staff_id}")
    print("Use this account's `staff_id` as `acting_as` when calling MCP tools as admin.")


if __name__ == "__main__":
    main()
