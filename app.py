from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

VERIFY_TOKEN = "my_secret_forex_bot_123"
WHATSAPP_TOKEN = "EAAGZAyg2ArEB8s4kM6hSylQe9Q5RuVhJNZCF01N7gEkUkQe7o8yT9JZZBGp7ZC9WN6dukK93lcxzxKOZAZB2Uq435GBvtyP"
PHONE_NUMBER_ID = "1443820342139151"
DEEPSEEK_API_KEY = "sk-2e79b22d6d171455fbcdf56164cc6974e"

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

def get_ai_analysis(pair):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Analyze {pair} based on SMC rules (1H POI to 5M entry, strict 1:3 RR). Give a short answer in Roman Urdu"
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    try:
        res = requests.post(url, headers=headers, json=payload).json()
        return res['choices'][0]['message']['content']
    except:
        return "Bhai AI abhi busy hai, thori der baad try karein."

@app.route('/webhook', methods=['GET', 'POST', 'HEAD'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Forbidden", 403

    if request.method == 'HEAD':
        return "", 200

    if request.method == 'POST':
        data = request.get_json()
        try:
            if data['object'] == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        value = change.get('value', {})
                        if 'messages' in value:
                            msg = value['messages'][0]
                            if msg['type'] == 'text':
                                user_message = msg['text']['body']
                                user_number = msg['from']
                                analysis = get_ai_analysis(user_message)
                                send_whatsapp_message(user_number, analysis)
        except Exception as e:
            print(f"Error: {e}")
        
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
