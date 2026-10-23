from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ==========================================
# WHATSAPP TOKENS HARDCODED (Taake reply 100% aaye)
# ==========================================
HARD_TOKEN = "EAAh2AYg1ZArEBS4g4KmM8hSYlqQE9CRuSVhJNZCFO1N7gEkUokQe7o8yT9J2ZBGP7ZC9NYNGduk9931cxzK0ZAZB2uIq43S0BvtpEPEhAG4BgVZAdpeNoBaVenhpLgCT6cnUdGdo9efUEfJdJLsi0W8kZA2bUjEZAYVVRqHaHumFeE2xteVFb8ZB23RrMZBZA93KgMMYggZDZD"
HARD_ID = "1443823042139151"

# ==========================================
# ENVIRONMENT VARIABLES SE READ KARNA
# ==========================================
ENV_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
ENV_ID = os.environ.get("PHONE_NUMBER_ID", "")
ENV_DEEP = os.environ.get("DEEPSEEK_API_KEY", "")
ENV_TWELVE = os.environ.get("TWELVEDATA_API_KEY", "")

def send_hardcoded_whatsapp(to, text):
    url = f"https://graph.facebook.com/v20.0/{HARD_ID}/messages"
    headers = {"Authorization": f"Bearer {HARD_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("SEND ERROR:", e)

@app.route('/', methods=['GET'])
def home():
    return "Alive", 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == "my_secret_forex_bot_123":
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
                                
                                # YEH RENDER SE READ KI HUI VALUES HAIN
                                report = "🔍 **VARIABLES CHECK**\n\n"
                                report += f"Token starts with: `{ENV_TOKEN[:10]}`\n"
                                report += f"Token length: `{len(ENV_TOKEN)}`\n\n"
                                report += f"ID starts with: `{ENV_ID[:5]}`\n"
                                report += f"ID length: `{len(ENV_ID)}`\n\n"
                                report += f"DeepSeek starts with: `{ENV_DEEP[:5]}`\n"
                                report += f"TwelveData starts with: `{ENV_TWELVE[:5]}`"
                                
                                send_hardcoded_whatsapp(user_number, report)
                                
        except Exception as e:
            print("CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
