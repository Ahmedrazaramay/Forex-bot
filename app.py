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
    return "Bot Live - DeepSeek Ready"

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
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            msg = entry["messages"][0]
            from_number = msg["from"]
            text = msg["text"]["body"]
            upper_text = text.upper()

            if "GOLD" in upper_text or "XAU" in upper_text or "EURUSD" in upper_text:
                # DeepSeek Call
                ds_url = "https://api.deepseek.com/v1/chat/completions"
                ds_headers = {
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json"
                }
                ds_payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional Gold XAUUSD forex signal provider. Give concise signal with BUY/SELL, Entry Price, SL, TP1, TP2, TP3. Keep it short."},
                        {"role": "user", "content": f"Give live trading signal for {text}. Current gold price around."}
                    ]
                }
                r = requests.post(ds_url, headers=ds_headers, json=ds_payload, timeout=30)
                if r.status_code == 200:
                    ai_reply = r.json()["choices"][0]["message"]["content"]
                else:
                    ai_reply = f"DeepSeek Error {r.status_code}: Check API Key. Details: {r.text[:300]}"
            else:
                ai_reply = f"Send GOLD or XAUUSD to get signal. You said: {text}"

            # Send WhatsApp Reply
            wa_url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
            wa_headers = {
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
            wa_payload = {
                "messaging_product": "whatsapp",
                "to": from_number,
                "text": {"body": ai_reply}
            }
            requests.post(wa_url, headers=wa_headers, json=wa_payload)

    except Exception as e:
        print(f"Error: {e}")
    
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
