import json
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
MESSAGES_FILE = BASE_DIR / "messages.jsonl"

# static_folder="public" + static_url_path="" means styles.css, main.js,
# favicon.svg are served from the site root, so the HTML links work unchanged.
app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_TYPES = {
    "Custom website design",
    "Responsive website",
    "Landing page",
    "Website redesign",
    "HTML/CSS development",
    "Other",
}


@app.route("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


def save_message(data: dict) -> None:
    """Append the message to messages.jsonl (one JSON object per line)."""
    record = {**data, "received_at": datetime.now(timezone.utc).isoformat()}
    with MESSAGES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def send_email(data: dict) -> bool:
    """Send the message to your inbox if SMTP settings are configured."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    to_addr = os.getenv("MAIL_TO", user)
    if not (host and user and password and to_addr):
        return False

    msg = EmailMessage()
    msg["Subject"] = f"New portfolio enquiry: {data['project_type']}"
    msg["From"] = user
    msg["To"] = to_addr
    msg["Reply-To"] = data["email"]
    msg.set_content(
        f"Name: {data['name']}\n"
        f"Email: {data['email']}\n"
        f"Project type: {data['project_type']}\n\n"
        f"{data['message']}\n"
    )

    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
    return True


@app.route("/api/contact", methods=["POST"])
def contact():
    # Accept both JSON and normal form data
    payload = request.get_json(silent=True) or request.form

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    project_type = (payload.get("project-type") or payload.get("project_type") or "").strip()
    message = (payload.get("message") or "").strip()

    errors = {}
    if len(name) < 2:
        errors["name"] = "Please enter your name."
    if not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."
    if project_type not in ALLOWED_TYPES:
        errors["project-type"] = "Please select a project type."
    if len(message) < 10:
        errors["message"] = "Please write a little more about your project."
    if len(message) > 5000:
        errors["message"] = "Message is too long."

    if errors:
        return jsonify(ok=False, errors=errors), 400

    data = {
        "name": name,
        "email": email,
        "project_type": project_type,
        "message": message,
    }

    try:
        save_message(data)
    except OSError:
        app.logger.exception("Could not save message")
        return jsonify(ok=False, error="Could not save your message."), 500

    try:
        send_email(data)
    except Exception:
        # Message is already saved, so don't fail the visitor's request
        app.logger.exception("Email sending failed")

    return jsonify(ok=True, message="Thanks! Your message has been sent.")


@app.errorhandler(404)
def not_found(_):
    return send_from_directory(PUBLIC_DIR, "index.html"), 404


if __name__ == "__main__":
 app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", port=5000)