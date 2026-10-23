from flask import Flask, request
import requests
import os

app = Flask(__name__)

# DIRECT WHATSAPP TOKENS (Jo abhi test mein kaam kar chuke hain)
WHATSAPP_TOKEN = "EAAh2AYg1ZArEBS4g4KmM8hSYlqQE9CRuSVhJNZCFO1N7gEkUokQe7o8yT9J2ZBGP7ZC9NYNGduk9931cxzK0ZAZB2uIq43S0BvtpEPEhAG4BgVZAdpeNoBaVenhpLgCT6cnUdGdo9efUEfJdJLsi0W8kZA2bUjEZAYVVRqHaHumFeE2xteVFb8ZB23RrMZBZA93KgMMYggZDZD"
PHONE_NUMBER_ID = "1443823042139151"
VERIFY_TOKEN = "my_secret_forex_bot_123"

# ENVIRONMENT SE KEYS
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"SEND ERROR: {e}")

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
                                
                                # 1. TWELVEDATA TEST
                                if not TWELVEDATA_API_KEY:
                                    send_whatsapp_message(user_number, "ERROR: TWELVEDATA_API_KEY Render mein nahi mili!")
                                    return "OK", 200
                                
                                td_url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVEDATA_API_KEY}"
                                td_res = requests.get(td_url).json()
                                
                                if 'price' not in td_res:
                                    send_whatsapp_message(user_number, f"TWELVEDATA ERROR: {str(td_res)}")
                                    return "OK", 200
                                
                                # 2. DEEPSEEK TEST
                                if not DEEPSEEK_API_KEY:
                                    send_whatsapp_message(user_number, "ERROR: DEEPSEEK_API_KEY Render mein nahi mili!")
                                    return "OK", 200
                                
                                ai_url = "https://api.deepseek.com/chat/completions"
                                ai_headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
                                ai_payload = {
                                    "model": "deepseek-chat",
                                    "messages": [{"role": "user", "content": f"Say 'API is working' in Urdu."}],
                                    "temperature": 0.1
                                }
                                ai_res = requests.post(ai_url, headers=ai_headers, json=ai_payload).json()
                                
                                if 'choices' not in ai_res:
                                    send_whatsapp_message(user_number, f"DEEPSEEK ERROR: {str(ai_res)}")
                                    return "OK", 200
                                
                                # AGAR DONO THEEK HAIN
                                send_whatsapp_message(user_number, f"✅ DONO API THEEK HAIN!\nTwelveData Price: {td_res['price']}\nAI Response: {ai_res['choices'][0]['message']['content']}")
                                
        except Exception as e:
            print(f"WEBHOOK ERROR: {e}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
