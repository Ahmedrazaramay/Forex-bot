from flask import Flask, request, jsonify
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
import base64
import json
from datetime import datetime

app = Flask(__name__)

# ==========================================
# SECURE KEYS
# ==========================================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_forex_bot_123").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()

ORACLE_API_URL = "http://141.145.158.62:5000/set_alert"
MY_WHATSAPP_NUMBER = "923003212360" 

# ==========================================
# DUPLICATE FILTER STORAGE
# ==========================================
_processed_messages = {}

def is_duplicate(msg_id):
    if not msg_id:
        return False
    now = time.time()
    for k in list(_processed_messages.keys()):
        if now - _processed_messages[k] > 300:
            del _processed_messages[k]
            
    if msg_id in _processed_messages:
        return True
        
    _processed_messages[msg_id] = now
    return False

# ==========================================
# CACHE STORAGE
# ==========================================
data_cache = {}
CACHE_EXPIRY = 300

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
def generate_basic_chart(pair):
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

        chart_path = f"/tmp/{symbol.replace('/', '')}_basic.jpg"
        title = f"{symbol} - 5M"
        
        mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', 
                 savefig=dict(fname=chart_path, bbox_inches='tight'))
        plt.close('all') 
        return chart_path
    except Exception as e:
        return f"❌ Chart Exception: {str(e)}"

def generate_final_chart(pair, ai_text, current_price):
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

        entry_val = sl_val = tp_val = alert_val = zone_top = zone_bottom = None
        zone_name = "POI"
        
        entry_match = re.search(r"Entry[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        sl_match = re.search(r"SL[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        tp_match = re.search(r"TP[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        alert_match = re.search(r"Alert Level[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        zone_top_match = re.search(r"Zone Top[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        zone_bottom_match = re.search(r"Zone Bottom[:\s*]*([\d\.]+)", ai_text, re.IGNORECASE)
        zone_name_match = re.search(r"Zone Name[:\s*]*([A-Za-z]+)", ai_text, re.IGNORECASE)

        if entry_match: entry_val = float(entry_match.group(1))
        if sl_match: sl_val = float(sl_match.group(1))
        if tp_match: tp_val = float(tp_match.group(1))
        if alert_match: alert_val = float(alert_match.group(1))
        if zone_top_match: zone_top = float(zone_top_match.group(1))
        if zone_bottom_match: zone_bottom = float(zone_bottom_match.group(1))
        if zone_name_match: zone_name = zone_name_match.group(1).upper()

        chart_path = f"/tmp/{symbol.replace('/', '')}_chart.jpg"
        title = f"{symbol} - 5M"
        
        fig, axlist = mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', returnfig=True)
        ax = axlist[0]

        if entry_val: ax.axhline(entry_val, color='b', linestyle='-', linewidth=1.5, label='Entry')
        if sl_val: ax.axhline(sl_val, color='r', linestyle='--', linewidth=1.5, label='SL')
        if tp_val: ax.axhline(tp_val, color='g', linestyle='--', linewidth=1.5, label='TP')

        if zone_top and zone_bottom:
            # Draw the shaded rectangle
            ax.axhspan(zone_bottom, zone_top, color='yellow', alpha=0.3)
            ax.axhline(zone_top, color='orange', linestyle='-', linewidth=1)
            ax.axhline(zone_bottom, color='orange', linestyle='-', linewidth=1)
            
            # Add Text Label inside the rectangle
            y_center = (zone_top + zone_bottom) / 2
            x_pos = len(df) - 2  # Position text near the right side of the chart
            
            ax.text(x_pos, y_center, f" {zone_name} ", 
                    fontsize=12, color='black', fontweight='bold', 
                    bbox=dict(facecolor='yellow', alpha=0.8, edgecolor='orange', boxstyle='round,pad=0.3'),
                    verticalalignment='center', horizontalalignment='right')
            
        elif alert_val:
            ax.axhline(alert_val, color='y', linestyle='-', linewidth=2.0, label='Alert Level')

        fig.savefig(chart_path, bbox_inches='tight')
        plt.close(fig) 
        return chart_path
    except Exception as e:
        return f"❌ Chart Exception: {str(e)}"

def get_gemini_analysis(image_path, live_data, current_price, pair):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

    prompt = f"""
    You are a strict SMC/ICT Forex Day Trading Bot.
    Analyze the attached chart image along with the data provided.
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
    🎯 Zone Top: [Price of FVG/OB top]
    🎯 Zone Bottom: [Price of FVG/OB bottom]
    🎯 Zone Name: [Write only FVG or OB]
    """

    models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_string}}
                ]
            }],
            "generationConfig": {"temperature": 0.0}
        }

        for attempt in range(3):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=60).json()
                
                if 'error' in res and res['error'].get('code') == 503:
                    print(f"{model_name} busy. Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                
                if 'candidates' in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                
                break
                
            except Exception as e:
                print(f"Error with {model_name}: {str(e)}")
                time.sleep(2)
    
    return "GEMINI ERROR: Google ke saare models abhi busy hain. Thori dair baad koshish karein."

def get_live_data(pair):
    global data_cache
    
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]

    now = time.time()
    if symbol in data_cache:
        cached_time, cached_data, cached_price = data_cache[symbol]
        if now - cached_time < CACHE_EXPIRY:
            return cached_data, cached_price
    
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
                err_msg = res.get('message', str(res))
                return f"API_ERROR: {err_msg}", None
        except Exception as e:
            return f"API_ERROR: {str(e)}", None
            
    data_cache[symbol] = (now, data_text, current_price)
    return data_text, current_price

# ==========================================
# MAIN PROCESS LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper().strip()
        
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
                        send_whatsapp_text(user_number, f"✅ Alert sent to Oracle for {pair} at {price_level}!")
                    else:
                        send_whatsapp_text(user_number, f"❌ Oracle Error.")
                except Exception as e:
                    send_whatsapp_text(user_number, f"❌ Oracle Connection Failed.")
                return
            else:
                send_whatsapp_text(user_number, "Format: ALERT GOLD 4050")
                return

        greetings = ["HELLO", "HI", "HEY", "SALAM", "ASSALAM", "AO", "START", "BOSS"]
        if msg_upper in greetings:
            send_whatsapp_text(user_number, "Boss, main bilkul ready hoon! 🚀\nAap mujhe koi bhi pair likh kar bhejien (jaise: XAUUSD, EURUSD, GOLD) taake main analysis shuru karoon. 😎")
            return

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
        elif live_data.startswith("API_ERROR:"):
            send_whatsapp_text(user_number, f"❌ TwelveData Error:\n{live_data}")
            return
            
        basic_chart_path = generate_basic_chart(pair)
        if basic_chart_path.startswith("❌"):
            send_whatsapp_text(user_number, "Chart generate nahi ho saka.")
            return
            
        analysis = get_gemini_analysis(basic_chart_path, live_data, current_price, pair)
        os.remove(basic_chart_path)
        
        if analysis.startswith("GEMINI ERROR:"):
            send_whatsapp_text(user_number, analysis)
            return
            
        final_chart_path = generate_final_chart(pair, analysis, current_price)
        
        if final_chart_path.startswith("❌"):
            send_whatsapp_text(user_number, analysis)
            send_whatsapp_text(user_number, final_chart_path)
        else:
            status = send_whatsapp_image(user_number, final_chart_path, analysis)
            if status != "SUCCESS":
                send_whatsapp_text(user_number, analysis)
                send_whatsapp_text(user_number, status)
            os.remove(final_chart_path) 
        
    except Exception as e:
        send_whatsapp_text(user_number, f"SYSTEM ERROR: {str(e)}")

# ==========================================
# ROUTES
# ==========================================
@app.route('/ping', methods=['GET'])
def ping():
    return "Alive", 200

@app.route('/', methods=['GET'])
def home():
    return "Alive", 200

@app.route('/trigger_analysis', methods=['POST'])
def trigger_analysis():
    data = request.json
    symbol = data.get('symbol', 'XAU/USD')
    thread = threading.Thread(target=process_message, args=(MY_WHATSAPP_NUMBER, symbol))
    thread.start()
    return jsonify({"status": "success", "message": "Analysis started"}), 200

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
                            
                            if is_duplicate(msg_id):
                                continue 
                                
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
