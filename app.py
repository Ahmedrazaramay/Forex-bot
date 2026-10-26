from flask import Flask, request
import requests
import os
import threading
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import mplfinance as mpf
import matplotlib.pyplot as plt
import re
import time
from datetime import datetime

app = Flask(__name__)

# ==========================================
# SECURE KEYS
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()

ORACLE_API_URL = "http://141.145.158.62:5000/set_alert"

# ==========================================
# DUPLICATE FILTER STORAGE
# ==========================================
_processed_messages = {}

def is_duplicate(msg_id):
    if not msg_id:
        return False
    now = time.time()
    # Purge old messages (older than 5 minutes)
    for k in list(_processed_messages.keys()):
        if now - _processed_messages[k] > 300:
            del _processed_messages[k]
            
    if msg_id in _processed_messages:
        return True
        
    _processed_messages[msg_id] = now
    return False

# ==========================================
# WHATSAPP FUNCTIONS
# ==========================================
def send_whatsapp_text(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("SEND TEXT ERROR:", e)

def send_whatsapp_image(to, image_path, caption):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': open(image_path, 'rb')}
    data = {'messaging_product': 'whatsapp', 'type': 'image/jpeg'}
    
    try:
        upload_res = requests.post(url, headers=headers, files=files, data=data, timeout=20).json()
        if 'id' not in upload_res:
            return f"❌ Meta Upload Error: {upload_res}"
        
        media_id = upload_res['id']
        msg_url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        msg_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"id": media_id, "caption": caption}
        }
        requests.post(msg_url, headers=msg_headers, json=payload, timeout=10)
        return "SUCCESS"
    except Exception as e:
        return f"❌ Image Send Exception: {str(e)}"

# ==========================================
# CHART & AI FUNCTIONS
# ==========================================
def generate_chart(pair, ai_text, current_price):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
        
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=40&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if 'values' not in res:
            return f"❌ Chart Data Error: {res}"

        df = pd.DataFrame(res['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
        df = df.astype(float).sort_index()

        entry_val = sl_val = tp_val = None
        entry_match = re.search(r"Entry[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        sl_match = re.search(r"SL[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        tp_match = re.search(r"TP[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)

        if entry_match: entry_val = float(entry_match.group(1))
        if sl_match: sl_val = float(sl_match.group(1))
        if tp_match: tp_val = float(tp_match.group(1))

        hlines = []
        if entry_val: hlines.append(dict(hlines=entry_val, colors='b', linestyle='-', linewidths=1.5))
        if sl_val: hlines.append(dict(hlines=sl_val, colors='r', linestyle='--', linewidths=1.5))
        if tp_val: hlines.append(dict(hlines=tp_val, colors='g', linestyle='--', linewidths=1.5))

        chart_path = f"/tmp/{symbol.replace('/', '')}_chart.jpg"
        title = f"{symbol} - 5M"
        
        plot_kwargs = dict(type='candle', style='charles', title=title, ylabel='Price', 
                           savefig=dict(fname=chart_path, bbox_inches='tight'))
        if hlines:
            plot_kwargs['hlines'] = hlines

        mpf.plot(df, **plot_kwargs)
        
        plt.close('all') 
        return chart_path
    except Exception as e:
        return f"❌ Chart Exception: {str(e)}"

def get_ai_analysis(pair, live_data, current_price):
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are a strict SMC/ICT Forex Day Trading Bot.
    Pair: {pair}
    Current Price: {current_price}
    Live Data:\n{live_data}\n
    
    Output EXACTLY in this format (No intro, No outro):
    
    🪙 {pair}
    📍 Current: {current_price}
    📝 Report: [1 short line about market movement]
    [📈 or 📉] Trend: [Bullish/Bearish] (Weekly + Daily)
    📊 1H: [Bullish/Bearish/Consolidation]
    [✅ or 🚫] Status: [ENTRY / NO TRADE]
    💡 Reason: [1 short SMC reason in Roman Urdu]
    
    (If Status is ENTRY):
    🎯 Entry: [Price]
    🛑 SL: [Price]
    💰 TP: [Price]
    ⚖️ RR: 1:3
    
    (If Status is NO TRADE):
    🎯 Alert Level: [Price]
    """
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=45).json()
        return res['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"AI ERROR: {str(e)}"

def get_live_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"W": ("1week", 20), "D": ("1day", 20), "1H": ("1h", 60), "5M": ("5min", 60)}
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
                return None, None
        except:
            return None, None
    return data_text, current_price

# ==========================================
# MAIN PROCESS LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper().strip()
        
        # Alert Logic
        if "ALERT" in msg_upper:
            parts = msg_upper.split()
            price_level = None
            pair = "XAU/USD"
            
            for part in parts:
                try:
                    price_level = float(part)
                except ValueError:
                    if len(part) >= 3 and part != "ALERT":
                        pair = part
            
            if price_level:
                try:
                    oracle_payload = {"symbol": pair, "price": price_level}
                    response = requests.post(ORACLE_API_URL, json=oracle_payload, timeout=10)
                    if response.status_code == 200:
                        send_whatsapp_text(user_number, f"✅ Alert set on Oracle for {pair} at {price_level}!")
                    else:
                        send_whatsapp_text(user_number, f"❌ Oracle Error.")
                except Exception as e:
                    send_whatsapp_text(user_number, f"❌ Oracle Connection Failed.")
                return
            else:
                send_whatsapp_text(user_number, "Format: ALERT GOLD 4050")
                return

        # Friendly Greeting Filter
        greetings = ["HELLO", "HI", "HEY", "SALAM", "ASSALAM", "AO", "START", "BOSS"]
        if msg_upper in greetings:
            send_whatsapp_text(user_number, "Boss, main bilkul ready hoon! 🚀\nAap mujhe koi bhi pair likh kar bhejien (jaise: XAUUSD, EURUSD, GOLD) taake main analysis shuru karoon. 😎")
            return

        # Basic Pair Validation (Fixes the "Hello" bug for random words)
        valid_keywords = ["XAU", "GOLD", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
        if not any(keyword in msg_upper for keyword in valid_keywords):
            send_whatsapp_text(user_number, "Bhai, yeh kya likh diya? 😅\nMain sirf currency pairs samajhta hoon. Koi valid pair likhein (e.g., EURUSD, XAUUSD, GOLD).")
            return

        pair = "XAU/USD" if "GOLD" in msg_upper or "XAU" in msg_upper else msg_upper
        
        send_whatsapp_text(user_number, "⏳ Analysis aur Chart ban raha hai, please wait...")
        
        live_data, current_price = get_live_data(pair)
        if not live_data:
            send_whatsapp_text(user_number, f"❌ Data not available for {pair}")
            return
            
        analysis = get_ai_analysis(pair, live_data, current_price)
        
        chart_path = generate_chart(pair, analysis, current_price)
        
        if chart_path.startswith("❌"):
            send_whatsapp_text(user_number, analysis)
            send_whatsapp_text(user_number, chart_path)
        else:
            status = send_whatsapp_image(user_number, chart_path, analysis)
            if status != "SUCCESS":
                send_whatsapp_text(user_number, analysis)
                send_whatsapp_text(user_number, status)
            os.remove(chart_path) 
        
    except Exception as e:
        send_whatsapp_text(user_number, f"SYSTEM ERROR: {str(e)}")

# ==========================================
# ROUTES (WEBHOOK & PING)
# ==========================================
@app.route('/ping', methods=['GET'])
def ping():
    return "Alive", 200

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
                            msg_id = msg.get('id')
                            
                            # Duplicate Check
                            if is_duplicate(msg_id):
                                continue # Ignore duplicate message
                                
                            if msg['type'] == 'text':
                                user_number = msg['from']
                                user_message = msg['text']['body'].strip()
                                thread = threading.Thread(target=process_message, args=(user_number, user_message))
                                thread.start()
        except Exception as e:
            print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
