from flask import Flask, request
import requests
import os

app = Flask(__name__)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = "my_secret_forex_bot_123"

def send_msg(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("ERROR:", e)

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
                                user_message = msg['text']['body']
                                
                                # SIRF ECHO TEST (Bina AI ke)
                                token_check = WHATSAPP_TOKEN[:10] if WHATSAPP_TOKEN else "MISSING"
                                send_msg(user_number, f"Echo: {user_message}\nToken: {token_check}...")
        except Exception as e:
            print("CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
