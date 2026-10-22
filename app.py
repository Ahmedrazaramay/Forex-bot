from flask import Flask, request
import requests
import json
import os
import re

app = Flask(__name__)

# ==========================================
# SAARI KEYS RENDER KE ENVIRONMENT SE
# ==========================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")
ORACLE_ALERT_API = os.environ.get("ORACLE_ALERT_API", "") # Agar set nahi to khali

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
"""

# 1. ROOT ROUTE (UptimeRobot ke liye - Sleep Fix)
@app.route('/', methods=['GET'])
def home():
    return "Forex Bot is Alive and Awake!", 200

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print("SEND ERROR:", str(e))

def get_live_data(pair):
    # Pair formatting
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
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
                # Agar pair galat ho ya limit khatam ho
                return None, f"DATA ERROR ({symbol}): {res.get('message', 'Unknown error')}"
        except Exception as e:
            return None, f"NETWORK ERROR: {str(e)}"
    return data_text, None

def get_ai_analysis(pair, live_data):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Pair: {pair}\nRules:\n{SMC_RULES}\nLive Data:\n{live_data}\nOutput in Roman Urdu (Bias, Direction, 1H Structure, Entry Status, Entry, SL, TP, Alert Level)."
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        res = requests.post(url, headers=headers, json=payload).json()
        if 'choices' not in res:
            return f"DEEPSEEK API ERROR: {str(res)}"
        return res['choices'][0]['message']['content']
    except Exception as e:
        return f"AI CODE ERROR: {str(e)}"

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
                                user_message = msg['text']['body'].strip()
                                msg_upper = user_message.upper()
                                
                                # 2. Pair Validation & Alert Command
                                if "ALERT" in msg_upper:
                                    # Format: ALERT GOLD 2350 ya ALERT EURUSD 1.1000
                                    parts = msg_upper.split()
                                    if len(parts) >= 3:
                                        alert_pair = parts[1]
                                        alert_price = parts[2]
                                        if ORACLE_ALERT_API:
                                            # Oracle ko bhejna
                                            try:
                                                requests.post(ORACLE_ALERT_API, json={"pair": alert_pair, "price": alert_price})
                                                send_whatsapp_message(user_number, f"✅ Alert set for {alert_pair} at {alert_price}. Oracle is watching.")
                                            except:
                                                send_whatsapp_message(user_number, f"❌ Oracle API connect nahi ho rahi. Please check Render settings.")
                                        else:
                                            send_whatsapp_message(user_number, f"⚠️ Alert set karne ke liye Oracle API link set nahi hai.")
                                    else:
                                        send_whatsapp_message(user_number, "Format galat hai. Aise likhein: ALERT GOLD 2350")
                                    return "OK", 200
                                
                                # 3. Valid Pair Check (Hi, Hello ko filter karne ke liye)
                                valid_pairs = ["GOLD", "XAU", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "BTCUSD", "US30", "OIL"]
                                # Agar user ne seedha pair likha hai (jaise EURUSD) ya common word hai
                                is_pair = any(p in msg_upper for p in valid_pairs) or (len(msg_upper) == 6 and msg_upper.isalpha())
                                
                                if not is_pair:
                                    send_whatsapp_message(user_number, "Bhai koi valid pair likhein (jaise GOLD, EURUSD, GBPUSD) ya Alert lagane ke liye 'ALERT GOLD 2350' likhein.")
                                    return "OK", 200
                                
                                # Default to Gold if just "GOLD" is sent
                                pair = "XAU/USD" if "GOLD" in msg_upper or "XAU" in msg_upper else msg_upper
                                
                                live_data, error = get_live_data(pair)
                                if error:
                                    send_whatsapp_message(user_number, error)
                                    return "OK", 200
                                
                                analysis = get_ai_analysis(pair, live_data)
                                send_whatsapp_message(user_number, analysis)
        except Exception as e:
            print(f"WEBHOOK ERROR: {e}")
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
