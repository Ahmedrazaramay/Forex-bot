from flask import Flask, request
import requests
import os
import threading

app = Flask(__name__)

# ==========================================
# 100% SECURE: KEYS SIRF RENDER VARIABLES SE
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()

def send_whatsapp_message(to, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
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
    
    # UPDATED DATA SIZES: W(30), D(30), 1H(60), 5M(60)
    timeframes = {"W": ("1week", 30), "D": ("1day", 30), "1H": ("1h", 60), "5M": ("5min", 60)}
    data_text = ""
    current_price = 0
    
    for tf_name, (tf_code, tf_size) in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize={tf_size}&apikey={TWELVEDATA_API_KEY}"
        try:
            res = requests.get(url, timeout=10).json()
            if 'values' in res:
                if tf_code == "5min":
                    current_price = res['values'][0]['close']
                
                data_text += f"--- {tf_name} ---\n"
                for c in res['values']:
                    data_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else:
                return None, f"❌ Bhai, {symbol} ka data free API par available nahi hai."
        except Exception as e:
            return None, f"❌ Network error aya hai. Thori der baad try karein."
    return data_text, current_price

def get_ai_analysis(pair, live_data, current_price):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    # AAPKE RULES (AI inko andar hi andar check karega)
    master_prompt = """
    You are a strict SMC/ICT Forex Day Trading Bot.
    Analyze the following rules internally (DO NOT print these steps):
    Setup: 1H POI -> 5M Entry | RR 1:3 ONLY.
    1. Bias: Monthly/Weekly/Daily. (Conflict -> bada TF jeete).
    2. 1H POI valid = OB with FVG.
    3. 5M confirmation (all 4 required): 1H POI tap, 5M MSS, 5M Displacement, 5M Retest.
    4. SL = 5M POI ± buffer. TP = 1H nearest liquidity.
    5. RR: SIRF 1:3. Agar 1:3 nahi ban rahi to NO TRADE.
    6. Pair Behavior: Volatility check. Agar Daily range < 50 pips to NO TRADE.
    7. Agar koi bhi condition fail ho, to NO TRADE dena hai.
    
    IMPORTANT: Do NOT output Step 0, Step 1, etc. Just give the final decision.
    Use this EXACT short format:

    🪙 {pair}
    📍 Current: {current_price}
    📝 Report: [1 short line about market movement, e.g., 1H Liquidity Sweep hui ya POI tap hua]
    [📈 or 📉] Trend: [Bullish/Bearish] (Weekly + Daily)
    📊 1H: [Bullish/Bearish/Consolidation]
    [✅ or 🚫] Status: [ENTRY / NO TRADE]
    💡 Reason: [1 short SMC reason in Roman Urdu]
    """
    
    full_prompt = f"""
    {master_prompt}
    (If Status is ENTRY, output Entry/SL/TP/RR. If NO TRADE, output Alert).
    
    Data:
    Pair: {pair}
    Current Price: {current_price}
    Live Data:\n{live_data}
    """
    
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": full_prompt}], "temperature": 0.0}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=45).json()
        if 'choices' not in res:
            return f"DEEPSEEK ERROR: {str(res)}"
        return res['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"AI NETWORK ERROR: {str(e)}"

# ==========================================
# BACKGROUND PROCESS (Meta Timeout Fix)
# ==========================================
def process_message(user_number, user_message):
    try:
        greetings = ["HI", "HELLO", "HELO", "SALAM", "AO", "START", "HEY"]
        if user_message in greetings:
            send_whatsapp_message(user_number, "🤖 *Forex SMC Bot Active!*\n\nMujhe kisi bhi pair ka naam bhejein (jaise GOLD, EURUSD).")
            return
            
        pair = "XAU/USD" if "GOLD" in user_message or "XAU" in user_message else user_message
        
        if len(pair) < 4:
            send_whatsapp_message(user_number, "Bhai valid pair likhein (jaise GOLD, EURUSD).")
            return
        
        live_data, current_price = get_live_data(pair)
        if not live_data:
            send_whatsapp_message(user_number, current_price) # Error message
            return
            
        analysis = get_ai_analysis(pair, live_data, current_price)
        send_whatsapp_message(user_number, analysis)
        
    except Exception as e:
        send_whatsapp_message(user_number, f"SYSTEM ERROR: {str(e)}")

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
                                
                                # Start Background Thread
                                thread = threading.Thread(target=process_message, args=(user_number, user_message))
                                thread.start()
                                
        except Exception as e:
            print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
