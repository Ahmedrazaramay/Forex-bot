from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ==========================================
# KEYS SE SPACES HATANA (.strip() ka jadu)
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()

def send_whatsapp_message(to, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: Tokens missing or empty!")
        return
        
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        # Yahan hum response print karenge taake logs mein error dikhe
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print("META RESPONSE:", res.text)
    except Exception as e:
        print("SEND ERROR:", e)

@app.route('/', methods=['GET'])
def home():
    return "Alive", 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        return "Forbidden", 403

    elif request.method == 'POST':
        data = request.json
        try:
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        value = change.get('value', {})
                        if 'messages' in value:
                            msg = value['messages'][0]
                            if msg['type'] == 'text':
                                user_number = msg['from']
                                user_message = msg['text']['body'].strip()
                                
                                # 1. Check if variables are loaded
                                if not DEEPSEEK_API_KEY or not TWELVEDATA_API_KEY:
                                    send_whatsapp_message(user_number, "❌ ERROR: API Keys missing in Render Env!")
                                    return "OK", 200

                                # 2. Send a quick Ack
                                send_whatsapp_message(user_number, "⏳ APIs checked. Fetching data...")
                                
                                # (Baqi ka data aur AI logic yahan aayega jab yeh test pass ho jaye)
                                
        except Exception as e:
            print(f"WEBHOOK CRASH: {e}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
