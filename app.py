from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

VERIFY_TOKEN = "my_secret_forex_bot_123"
WHATSAPP_TOKEN = "EAAh2AYg1ZArEBS4g4KmM8hSYlqQE9CRuSVhJNZCFO1N7gEkUokQe7o8yT9J2ZBGP7ZC9NYNGduk9931cxzK0ZAZB2uIq43S0BvtpEPEhAG4BgVZAdpeNoBaVenhpLgCT6cnUdGdo9efUEfJdJLsi0W8kZA2bUjEZAYVVRqHaHumFeE2xteVFb8ZB23RrMZBZA93KgMMYggZDZD"
PHONE_NUMBER_ID = "1443823042139151"

# DeepSeek key
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-2e97b226d171455fbcdf56164cc6974e")

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=payload)

def get_ai_analysis(user_message):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Analyze based on SMC rules: {user_message}. Give a short answer in Roman Urdu."
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    try:
        res = requests.post(url, headers=headers, json=payload).json()
        
        # Agar response mein choices nahi hain, to asli error wapis bhej do
        if 'choices' not in res:
            return f"ASLI ERROR: {str(res)}"
            
        return res['choices'][0]['message']['content']
    except Exception as e:
        return f"CODE ERROR: {str(e)}"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        else:
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
                                user_message = msg['text']['body']
                                user_number = msg['from']
                                
                                # AI se analysis
                                analysis = get_ai_analysis(user_message)
                                
                                # Reply bhejna
                                send_whatsapp_message(user_number, analysis)
        except Exception as e:
            pass
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
