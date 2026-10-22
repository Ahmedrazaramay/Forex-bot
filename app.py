from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

# ==========================================
# YAHAN SE SAARI KEYS RENDER SE UTHAYI JAYENGI
# ==========================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")

# AAPKE COURSE KE RULES
SMC_RULES = """
You are a strict SMC/ICT Forex Day Trading Bot. 
Analyze the provided multi-timeframe market data based ONLY on these rules:
1. Setup: 1H POI -> 5M Entry.
2. Bias: Monthly/Weekly/Daily (Bada timeframe jeetega).
3. POI: Order Block with FVG. Buy = Discount zone, Sell = Premium zone.
4. Entry Confirmation: 1H POI Tap + 5M MSS + Displacement + Retest.
5. SL: 5M entry POI ke neeche/upar + buffer.
6. TP: 1H nearest liquidity.
7. RR: SIRF 1:3 (Strict). Agar 1:3 nahi ban rahi to NO TRADE.
8. If NO TRADE, you MUST provide the exact 'Alert Level' (price) that needs to break for a valid setup.
Do not use any other indicators. Be strict.
"""

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
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"WhatsApp Error: {e}")

def get_live_data(pair):
    # Pair format fix (Gold -> XAU/USD, EURUSD -> EUR/USD)
    symbol = pair.upper().replace("GOLD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"W": "1week", "D": "1day", "1H": "1h", "5M": "5min"}
    data_text = ""
    
    for tf_name, tf_code in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize=5&apikey={TWELVEDATA_API_KEY}"
        try:
            res = requests.get(url).json()
            if 'values' in res:
                data_text += f"--- {tf_name} Candles ---\n"
                for c in res['values']:
                    data_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else:
                return None # Agar data na mile to None return kare
        except:
            return None
            
    return data_text

def get_ai_analysis(pair, live_data):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    Pair: {pair}
    Rules:\n{SMC_RULES}\n
    Live Market Data:\n{live_data}\n
    Give output exactly in this format in Roman Urdu:
    Monthly/Weekly Bias: [Bullish/Bearish]
    Daily Direction: [Bullish/Bearish]
    1H Structure: [Bullish/Bearish/Sideways]
    
    Entry Status: [BUY/SELL/NO TRADE]
    (If BUY/SELL):
    Entry: [price]
    SL: [price]
    TP: [price]
    RR: 1:3
    (If NO TRADE):
    Alert Level: [price]
    Reason: [Why no trade and why this alert level]
    """
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }
    try:
        res = requests.post(url, headers=headers, json=payload).json()
        if 'choices' not in res:
            return f"API ERROR: {str(res)}"
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
                                
                                # Guard: Bot apne aap ko reply na kare
                                if user_number == PHONE_NUMBER_ID:
                                    return "OK", 200
                                
                                # Default Pair Gold, warna jo user ne likha
                                pair = "XAU/USD" if "GOLD" in user_message.upper() or "XAU" in user_message.upper() else user_message
                                
                                live_data = get_live_data(pair)
                                if not live_data:
                                    send_whatsapp_message(user_number, f"Bhai {pair} ka data nahi mil raha. Spelling check karein (e.g. EURUSD ya GOLD).")
                                    return "OK", 200
                                    
                                analysis = get_ai_analysis(pair, live_data)
                                send_whatsapp_message(user_number, analysis)
        except Exception as e:
            print(f"Webhook Error: {e}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
