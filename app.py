from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

# ==========================================
# SMART KEY CLEANER (Spaces, newlines aur quotes saaf karne ke liye)
# ==========================================
def clean_env(var_name):
    val = os.environ.get(var_name, "")
    if not val:
        return ""
    # Sirf letters, numbers, aur valid symbols rakhega, spaces aur newlines hata dega
    return re.sub(r'\s+', '', val).replace('"', '').replace("'", "")

WHATSAPP_TOKEN = clean_env("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = clean_env("PHONE_NUMBER_ID")
VERIFY_TOKEN = "my_secret_forex_bot_123"
DEEPSEEK_API_KEY = clean_env("DEEPSEEK_API_KEY")
TWELVEDATA_API_KEY = clean_env("TWELVEDATA_API_KEY")

def send_whatsapp_message(to, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: Tokens missing!")
        return
        
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print("META RESPONSE:", res.text) # Logs mein asli error dikhega
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
        user_number = None
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
                                
                                # Check agar environment variable sahi load hua hai
                                if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
                                    return "OK", 200
                                
                                # 1. Immediate Echo Test
                                send_whatsapp_message(user_number, f"System Active.\nAapne likha: {user_message}\nToken length: {len(WHATSAPP_TOKEN)}")
                                
        except Exception as e:
            print("CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
