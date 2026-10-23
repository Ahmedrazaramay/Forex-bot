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
                # Simple Error Message for Invalid/Paid Pairs
                return None, f"❌ Bhai, {symbol} ka data free API par available nahi hai."
        except Exception as e:
            return None, f"❌ Network error aya hai. Thori der baad try karein."
    return data_text, current_price

def get_ai_analysis(pair, live_data, current_price):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are a strict SMC/ICT Forex Day Trading Bot.
    Pair: {pair}
    Current Price: {current_price}
    Live Data (W, D, 1H, 5M):\n{live_data}\n
    
    Instructions:
    1. Analyze strictly based on SMC rules (OB, FVG, MSS, Liquidity).
    2. For the "📝 Report" line, look at the Daily (D) data and tell me: Is the market moving from POI to Liquidity, or Liquidity to POI? And what is the nearest level (Liquidity or POI)? Write this in 1-2 short lines in Roman Urdu.
    3. If there is an entry, provide Entry, SL, TP, and a 1-line SMC Reason in Roman Urdu.
    4. If there is NO entry, provide the Alert Level (price to break) and say "Break ka intezar".
    5. Do NOT change the emojis, structure, or write any extra text.
    
    Format for ENTRY:
    🪙 {pair}
    📍 Current: {current_price}
    📝 Report: [Daily TF context: Market kahan se nikli hai, nazdeek ka level kya hai]
    [📈 or 📉] Trend: [Bullish/Bearish] (Weekly + Daily)
    📊 1H: [Bullish/Bearish/Consolidation]
    ✅ Status: ENTRY
    💡 Reason: [Short SMC reason in Roman Urdu]
    🎯 Entry: [Price]
    🛑 SL: [Price]
    💰 TP: [Price]
    ⚖️ RR: 1:3

    Format for NO TRADE:
    🪙 {pair}
    📍 Current: {current_price}
    📝 Report: [Daily TF context: Market kahan se nikli hai, nazdeek ka level kya hai]
    [📈 or 📉] Trend: [Bullish/Bearish] (Weekly + Daily)
    📊 1H: [Bullish/Bearish/Consolidation]
    🚫 Status: NO TRADE
    🎯 Alert: [Price] Break ka intezar
    """
    
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
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
                                
                                # Thread Start
                                thread = threading.Thread(target=process_message, args=(user_number, user_message))
                                thread.start()
                                
        except Exception as e:
            print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
