from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ==========================================
# SAARI KEYS RENDER KE ENVIRONMENT SE (100% SECURE)
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")

SMC_RULES = """
You are a strict SMC/ICT Forex Day Trading Bot. 
Analyze based ONLY on these rules:
1. Setup: 1H POI -> 5M Entry.
2. Bias: Monthly/Weekly/Daily (Bada timeframe jeetega).
3. POI: Order Block with FVG. Buy = Discount zone, Sell = Premium zone.
4. Entry: 1H POI Tap + 5M MSS + Displacement + Retest.
5. SL: 5M POI + buffer. TP: 1H liquidity.
6. RR: Strict 1:3. Agar 1:3 nahi ban rahi to NO TRADE.
7. If NO TRADE, provide the exact 'Alert Level' (price) to break for a valid setup.
"""

def send_whatsapp_message(to, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: WhatsApp Tokens missing in Render!")
        return
        
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("SEND ERROR:", e)

def get_live_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"W": "1week", "D": "1day", "1H": "1h", "5M": "5min"}
    data_text = ""
    
    for tf_name, tf_code in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize=3&apikey={TWELVEDATA_API_KEY}" # outputsize 5 se 3 kar diya taake data chota ho
        try:
            res = requests.get(url, timeout=10).json()
            if 'values' in res:
                data_text += f"--- {tf_name} ---\n"
                for c in res['values']:
                    data_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else:
                return f"DATA ERROR ({symbol}): {res.get('message', 'Check Pair Name')}"
        except Exception as e:
            return f"NETWORK ERROR: {str(e)}"
    return data_text

def get_ai_analysis(pair, live_data):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    # PROMPT UPDATE: Ab AI lambi kahani nahi sunayega, sirf short points dega
    prompt = f"""
    Pair: {pair}
    Live Data:\n{live_data}\n
    Follow these SMC Rules:\n{SMC_RULES}\n
    Reply in SHORT, concise Roman Urdu bullet points. Do NOT write long paragraphs.
    Exactly use this format:
    * Bias: [Bullish/Bearish]
    * Direction: [Buy/Sell]
    * Status: [ENTRY / NO TRADE]
    * Entry: [Price or N/A]
    * SL: [Price or N/A]
    * TP: [Price or N/A]
    * Alert Level: [Price if NO TRADE, otherwise N/A]
    """
    
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30).json()
        if 'choices' not in res:
            return f"DEEPSEEK ERROR: {str(res)}"
        return res['choices'][0]['message']['content']
    except Exception as e:
        return f"AI CODE ERROR: {str(e)}"

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
                                user_message = msg['text']['body'].strip().upper()
                                
                                pair = "XAU/USD" if "GOLD" in user_message or "XAU" in user_message else user_message
                                
                                if len(pair) < 3:
                                    send_whatsapp_message(user_number, "Bhai valid pair likhein (jaise GOLD, EURUSD).")
                                    return "OK", 200
                                
                                live_data = get_live_data(pair)
                                if live_data.startswith("DATA ERROR") or live_data.startswith("NETWORK ERROR"):
                                    send_whatsapp_message(user_number, live_data)
                                    return "OK", 200
                                    
                                analysis = get_ai_analysis(pair, live_data)
                                send_whatsapp_message(user_number, analysis)
        except Exception as e:
            print(f"WEBHOOK CRASH: {e}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
