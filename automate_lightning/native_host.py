import sys
import json
import struct
import time

# ---------------- Helpers ----------------
def send_message(message):
    """Send JSON message to Chrome extension"""
    encoded = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.flush()

def read_message():
    """Read JSON message from Chrome extension"""
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    length = struct.unpack("I", raw_length)[0]
    message = sys.stdin.buffer.read(length).decode("utf-8")
    return json.loads(message)

# ---------------- Sample User Data ----------------
users_db = {
    "101": {
        "name": "Alice Johnson",
        "dob": "01/01/2005",
        "email": "alice@example.com",
        "mobile": "9876543210",
        "username": "alice123",
        "password": "password123"
    }
}

# ---------------- Main Loop ----------------
if __name__ == "__main__":
    while True:
        msg = read_message()
        if msg is None:
            break

        # Extract URL and Telegram/user info from msg
        telegram_id = msg.get("telegram_id", "101")  # Example fallback
        url = msg.get("url")
        user_data = users_db.get(telegram_id, {})

        # Example: map input fields heuristically
        fields = []
        for selector in msg.get("fields", []):
            key = selector.get("keyword")  # optional keyword from extension
            value = user_data.get(key, "")
            if value:
                fields.append({
                    "selector": selector.get("selector"),
                    "value": value
                })

        # Build response JSON
        form_json = {
            "title": f"Autofill Profile for {url}",
            "url": url + "*",
            "fields": fields
        }

        # Send to extension
        send_message(form_json)
