from flask import Flask, request
import requests
import os

app = Flask(__name__)

# DIRECT TOKENS (Taake koi env variable ka masla na ho)
WHATSAPP_TOKEN = "EAAh2AYg1ZArEBS4g4KmM8hSYlqQE9CRuSVhJNZCFO1N7gEkUokQe7o8yT9J2ZBGP7ZC9NYNGduk9931cxzK0ZAZB2uIq43S0BvtpEPEhAG4BgVZAdpeNoBaVenhpLgCT6cnUdGdo9efUEfJdJLsi0W8kZA2bUjEZAYVVRqHaHumFeE2xteVFb8ZB23RrMZBZA93KgMMYggZDZD"
PHONE_NUMBER_ID = "1443823042139151"
VERIFY_TOKEN = "my_secret_forex_bot_123"

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    try:
        # Yahan hum Meta ka jawab check karenge
        response = requests.post(url, headers=headers, json=payload)
        return response.text
    except Exception as e:
        return f"SEND_EXCEPTION: {str(e)}"

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
                                
                                # Seedha reply bhejne ki koshish
                                reply_text = f"Aapne bheja: {user_message}"
                                meta_response = send_whatsapp_message(user_number, reply_text)
                                
                                # META KA JAWAB WAPIS WHATSAPP PAR BHEJENGE (Taake error pata chale)
                                # (Yeh ek backup message hai jo bot ki taraf se aayega)
                                if "error" in meta_response:
                                    send_whatsapp_message(user_number, f"META ERROR: {meta_response}")
                                    
        except Exception as e:
            # Agar code crash ho, to error message bhejo
            try:
                send_whatsapp_message(user_number, f"CODE CRASH: {str(e)}")
            except:
                pass
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
