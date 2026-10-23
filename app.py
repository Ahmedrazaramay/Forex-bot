from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ==========================================
# 100% SECURE (Saari keys Render se)
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print("META RESPONSE:", res.text) # Logs mein dikhega
    except Exception as e:
        print("SEND ERROR:", e)

def get_live_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"W": "1week", "D": "1day", "1H": "1h", "5M": "5min"}
    data_text = ""
    current_price = 0
    
    for tf_name, tf_code in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize=2&apikey={TWELVEDATA_API_KEY}"
        try:
            res = requests.get(url, timeout=10).json()
            if 'values' in res:
                if tf_code == "5min":
                    current_price = res['values'][0]['close']
                data_text += f"--- {tf_name} ---\n"
                for c in res['values']:
                    data_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else:
                return None, f"TWELVEDATA ERROR: {res.get('message', 'Pair galat hai')}"
        except Exception as e:
            return None, f"DATA NETWORK ERROR: {str(e)}"
    return data_text, current_price

def get_ai_analysis(pair, live_data, current_price):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"Pair: {pair}\nCurrent Price: {current_price}\nData:\n{live_data}\nGive output in Roman Urdu bullet points: Bias, Direction, Status, Entry, SL, TP, Alert Level."
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30).json()
        if 'choices' not in res:
            return f"DEEPSEEK ERROR: {str(res)}"
        return res['choices'][0]['message']['content']
    except Exception as e:
        return f"AI NETWORK ERROR: {str(e)}"

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
                                user_message = msg['text']['body'].strip().upper()
                                
                                # 1. IMMEDIATE ACK (Check if WhatsApp sending works)
                                send_whatsapp_message(user_number, "⏳ Checking APIs, please wait...")
                                
                                if not DEEPSEEK_API_KEY or not TWELVEDATA_API_KEY:
                                    send_whatsapp_message(user_number, f"❌ ERROR: Keys missing in Render!\nDeepSeek: {bool(DEEPSEEK_API_KEY)}\nTwelveData: {bool(TWELVEDATA_API_KEY)}")
                                    return "OK", 200

                                pair = "XAU/USD" if "GOLD" in user_message or "XAU" in user_message else user_message
                                
                                if len(pair) < 4:
                                    send_whatsapp_message(user_number, "Bhai valid pair likhein.")
                                    return "OK", 200
                                
                                # 2. FETCH DATA
                                live_data, current_price = get_live_data(pair)
                                if not live_data:
                                    send_whatsapp_message(user_number, current_price) # Error message
                                    return "OK", 200
                                    
                                # 3. AI ANALYSIS
                                analysis = get_ai_analysis(pair, live_data, current_price)
                                send_whatsapp_message(user_number, analysis)
                                
        except Exception as e:
            if user_number:
                send_whatsapp_message(user_number, f"SYSTEM CRASH: {str(e)}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
