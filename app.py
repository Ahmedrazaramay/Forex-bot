import os
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

@app.route("/", methods=["GET"])
def home():
    return "Bot Live"

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            msg = entry["messages"][0]
            from_number = msg["from"]
            text = msg["text"]["body"].upper()
            
            if "GOLD" in text or "XAU" in text:
                # DeepSeek se signal lo
                headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a Gold (XAUUSD) signal expert. Give BUY/SELL with Entry, SL, TP1 TP2 TP3 in short format. No extra explanation."},
                        {"role": "user", "content": f"Give me live XAUUSD signal for {text}"}
                    ]
                }
                r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
                ai_reply = r.json()["choices"][0]["message"]["content"]
            else:
                ai_reply = f"Send GOLD or XAUUSD to get signal. You said: {text}"

            url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
            headers2 = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
            payload2 = {"messaging_product": "whatsapp", "to": from_number, "text": {"body": ai_reply}}
            requests.post(url, headers=headers2, json=payload2)
    except Exception as e:
        print(f"Error: {e}")
    return "OK", 200
