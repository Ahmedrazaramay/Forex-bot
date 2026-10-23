from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

# Saari keys se spaces/newlines hatana
def clean_key(key):
    if not key: return ""
    return re.sub(r'\s+', '', key)

WHATSAPP_TOKEN = clean_key(os.environ.get("WHATSAPP_TOKEN", ""))
PHONE_NUMBER_ID = clean_key(os.environ.get("PHONE_NUMBER_ID", ""))

@app.route('/', methods=['GET'])
def home():
    return "Alive", 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return request.args.get('hub.challenge'), 200

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
                                
                                url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                                headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
                                payload = {"messaging_product": "whatsapp", "to": user_number, "type": "text", "text": {"body": "Echo Test from Env Variables!"}}
                                
                                # Meta ko request bhej kar jawab print karna
                                res = requests.post(url, headers=headers, json=payload, timeout=10)
                                print("META RESPONSE:", res.text) 
        except Exception as e:
            print("CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
