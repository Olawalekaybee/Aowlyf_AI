"""
AOWLYF_AI: generate ready-to-send WhatsApp login messages

Reads staff_credentials_DO_NOT_COMMIT.csv (produced by provision_staff.py)
and prints one message per person with their login link, email, and
initial password, ready to copy and paste into an individual WhatsApp
chat. This does not send anything automatically, that is Phase 4.

Usage:
    python generate_login_messages.py staff_credentials_DO_NOT_COMMIT.csv --url http://192.168.1.164:5173
"""

import argparse
import csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument(
        "--url",
        default="http://localhost:5173",
        help="Dashboard address staff should open, use the Spark's LAN IP for real distribution",
    )
    args = parser.parse_args()

    sent_count = 0
    skipped_count = 0

    with open(args.csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            full_name = row["full_name"].strip()
            email = row["email"].strip()
            password = row["initial_password"].strip()

            if not email or "not set" in email.lower():
                print(f"--- Skipped {full_name}, no email on file yet ---\n")
                skipped_count += 1
                continue

            message = (
                f"Hi {full_name}, your AOWLYF_AI account is ready.\n"
                f"Login link: {args.url}\n"
                f"Email: {email}\n"
                f"Temporary password: {password}\n"
                f"Please log in and choose your own password once you are in."
            )
            print(f"--- {full_name} ({email}) ---")
            print(message)
            print()
            sent_count += 1

    print(f"Generated {sent_count} message(s), skipped {skipped_count} with no email on file.")


if __name__ == "__main__":
    main()