"""
AOWLYF_AI: WhatsApp deadline reminders (Phase 4)

Two jobs in one script, meant to be run periodically, for example every
hour via cron:

  1. Scan open tasks whose deadline falls within REMINDER_WINDOW_HOURS
     and schedule a reminder notification for the assignee, if one has
     not already been scheduled or sent for that task.
  2. Send every notification that is due, and mark it sent or failed.

Sending uses the Twilio WhatsApp API. On a Twilio trial account, the
recipient must first join your sandbox by texting your join phrase to
your sandbox number, and must rejoin every 3 days.

WhatsApp requires an approved Content Template for the first
business-initiated message in a conversation, free-form text only works
as a reply within an already-open session. Set TWILIO_CONTENT_SID to
one of your sandbox's pre-approved template SIDs, find it in Twilio
Console under Messaging, Try it out, Send a WhatsApp message, then
switch to the API view after picking a template.

Important limitation: the sandbox's pre-approved templates have fixed
wording, they do not accept variables, so the actual message text sent
will be that template's own text, not your task's real title or due
date. Getting genuinely dynamic reminder text requires creating and
getting Meta approval for your own Content Template with variables,
then setting TWILIO_CONTENT_SID to that template's SID instead. Until
then, this script still tracks and confirms delivery correctly, only
the message body Twilio actually sends is generic rather than specific
to each task.

Usage:
    pip install -r requirements.txt
    export DATABASE_URL=postgresql://impactlab:changeme@localhost:5433/impactlab
    export TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    export TWILIO_AUTH_TOKEN=your_auth_token
    export TWILIO_WHATSAPP_FROM=whatsapp:+17372508034
    export TWILIO_CONTENT_SID=HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python run_whatsapp_reminders.py
"""

import os
from datetime import datetime, timedelta, timezone

import psycopg2
from twilio.rest import Client

DATABASE_URL = os.environ["DATABASE_URL"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = os.environ["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = os.environ.get("TWILIO_CONTENT_SID")

REMINDER_WINDOW_HOURS = int(os.environ.get("REMINDER_WINDOW_HOURS", "24"))


def schedule_due_reminders(conn):
    cutoff_date = (datetime.now(timezone.utc) + timedelta(hours=REMINDER_WINDOW_HOURS)).date()
    cur = conn.cursor()
    cur.execute(
        """SELECT t.id, t.title, t.end_date, t.assignee_id, s.whatsapp_number
           FROM tasks t
           JOIN staff s ON s.id = t.assignee_id
           WHERE t.status != 'done'
             AND t.assignee_id IS NOT NULL
             AND s.whatsapp_number IS NOT NULL
             AND t.end_date <= %s""",
        (cutoff_date,),
    )
    candidates = cur.fetchall()

    scheduled = []
    for task_id, title, end_date, staff_id, whatsapp_number in candidates:
        cur.execute(
            """SELECT 1 FROM notifications
               WHERE related_task_id = %s AND staff_id = %s AND status != 'failed'""",
            (task_id, staff_id),
        )
        if cur.fetchone():
            continue

        message = (
            f"Reminder: your task \"{title}\" is due on {end_date}. "
            f"Check AOWLYF_AI for details."
        )
        cur.execute(
            """INSERT INTO notifications (staff_id, channel, related_task_id, message, scheduled_for)
               VALUES (%s, 'whatsapp', %s, %s, now())""",
            (staff_id, task_id, message),
        )
        scheduled.append(title)

    conn.commit()
    cur.close()
    return scheduled


def send_due_notifications(conn, client):
    cur = conn.cursor()
    cur.execute(
        """SELECT n.id, n.message, s.whatsapp_number, s.full_name
           FROM notifications n
           JOIN staff s ON s.id = n.staff_id
           WHERE n.channel = 'whatsapp' AND n.status = 'scheduled' AND n.scheduled_for <= now()"""
    )
    due = cur.fetchall()

    sent, failed = [], []
    for notification_id, message, whatsapp_number, full_name in due:
        try:
            if TWILIO_CONTENT_SID:
                # Opens a conversation using an approved template. If the
                # template has variables of its own, pass them here with
                # content_variables instead of relying on the message text
                # generated above.
                client.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:{whatsapp_number}",
                    content_sid=TWILIO_CONTENT_SID,
                )
            else:
                # Only works as a reply within an already-open 24 hour
                # session, otherwise Twilio rejects this with a
                # ContentSid required error.
                client.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:{whatsapp_number}",
                    body=message,
                )
            cur.execute(
                "UPDATE notifications SET status = 'sent', sent_at = now() WHERE id = %s",
                (notification_id,),
            )
            sent.append(full_name)
        except Exception as exc:
            cur.execute(
                "UPDATE notifications SET status = 'failed' WHERE id = %s",
                (notification_id,),
            )
            failed.append(f"{full_name} ({exc})")

    conn.commit()
    cur.close()
    return sent, failed


def main():
    conn = psycopg2.connect(DATABASE_URL)
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    scheduled = schedule_due_reminders(conn)
    print(f"Scheduled {len(scheduled)} new reminder(s):")
    for title in scheduled:
        print(f"  - {title}")

    sent, failed = send_due_notifications(conn, client)
    print(f"\nSent {len(sent)} reminder(s):")
    for name in sent:
        print(f"  - {name}")

    if failed:
        print(f"\nFailed {len(failed)} reminder(s):")
        for detail in failed:
            print(f"  - {detail}")

    conn.close()


if __name__ == "__main__":
    main()