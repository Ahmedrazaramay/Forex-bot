import os
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")

print(f"=== ENV CHECK ===")
print(f"VERIFY: {bool(VERIFY_TOKEN)}")
print(f"TOKEN: {bool(WHATSAPP_TOKEN)} {str(WHATSAPP_TOKEN)[:20] if WHATSAPP_TOKEN else 'MISSING'}")
print(f"PHONE_ID: {PHONE_NUMBER_ID}")

@app.route("/", methods=["GET"])
def home():
    return "Bot is Live"

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print(f"Incoming: {data}")
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            msg = entry["messages"][0]
            from_number = msg["from"]
            text = msg["text"]["body"]
            print(f"Message from {from_number}: {text}")

            # Simple reply for testing
            reply_text = f"GOLD Signal: BUY 4020, SL 4005, TP 4050-4070 (You said: {text})"

            url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
            headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
            payload = {
                "messaging_product": "whatsapp",
                "to": from_number,
                "text": {"body": reply_text}
            }
            r = requests.post(url, headers=headers, json=payload)
            print(f"Send reply status: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"ERROR IN WEBHOOK: {e}")
        import traceback
        traceback.print_exc()
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
