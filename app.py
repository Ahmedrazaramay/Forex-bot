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

# GitHub Repo Info
GITHUB_USER = "Ahmedrazaramay"
GITHUB_REPO = "Forex-bot"

# ==========================================
# DUPLICATE FILTER & CACHE STORAGE
# ==========================================
_processed_messages = {}
data_cache = {}
CACHE_EXPIRY = 300
course_cache = {}

def is_duplicate(msg_id):
    if not msg_id: return False
    now = time.time()
    for k in list(_processed_messages.keys()):
        if now - _processed_messages[k] > 300: del _processed_messages[k]
    if msg_id in _processed_messages: return True
    _processed_messages[msg_id] = now
    return False

# ==========================================
# GITHUB RAG FUNCTIONS
# ==========================================
def fetch_course_rules():
    global course_cache
    if course_cache: return course_cache

    print("Fetching Course Transcripts from GitHub...")
    rules = {"macro": "", "structure": "", "entry": ""}
    
    for i in [1, 2]:
        url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/course_video_{i}.txt"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200: rules["macro"] += res.text + "\n\n"
        except: pass

    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/course_video_3.txt"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200: rules["structure"] += res.text + "\n\n"
    except: pass

    for i in range(4, 11):
        url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/course_video_{i}.txt"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200: rules["entry"] += res.text + "\n\n"
        except: pass

    course_cache = rules
    return course_cache

# ==========================================
# WHATSAPP FUNCTIONS
# ==========================================
def send_whatsapp_text(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try: requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e: print("SEND TEXT ERROR:", e)

def send_whatsapp_image(to, image_path, caption=""):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': open(image_path, 'rb')}
    data = {'messaging_product': 'whatsapp', 'type': 'image/jpeg'}
    try:
        upload_res = requests.post(url, headers=headers, files=files, data=data, timeout=20).json()
        if 'id' not in upload_res: return f"❌ Meta Upload Error: {upload_res}"
        
        media_id = upload_res['id']
        msg_url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        msg_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
        requests.post(msg_url, headers=msg_headers, json=payload, timeout=10)
        return "SUCCESS"
    except Exception as e: return f"❌ Image Send Exception: {str(e)}"

# ==========================================
# CHART FUNCTIONS
# ==========================================
def generate_chart(pair, timeframe, output_size=40):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]
        
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={timeframe}&outputsize={output_size}&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if 'values' not in res: 
            return f"❌ Chart Data Error: {res}"

        df = pd.DataFrame(res['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
        df = df.astype(float).sort_index()

        chart_path = f"/tmp/{symbol.replace('/', '')}_{timeframe}.jpg"
        title = f"{symbol} - {timeframe.upper()}"
        
        mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', savefig=dict(fname=chart_path, bbox_inches='tight'))
        plt.close('all') 
        return chart_path
    except Exception as e: 
        return f"❌ Chart Exception: {str(e)}"

def generate_final_chart(pair, ai_data, current_price):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]
        
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=40&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        
        # FIX: Yahan check lagaya hai taake 'values' error na aaye
        if 'values' not in res:
            return f"❌ Final Chart Data Error (API Limit?): {res}"
            
        df = pd.DataFrame(res['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
        df = df.astype(float).sort_index()

        entry_val = float(ai_data['entry']) if ai_data.get('entry') else None
        sl_val = float(ai_data['sl']) if ai_data.get('sl') else None
        tp_val = float(ai_data['tp']) if ai_data.get('tp') else None
        alert_val = float(ai_data['alert_level']) if ai_data.get('alert_level') else None
        zone_top = float(ai_data['zone_top']) if ai_data.get('zone_top') else None
        zone_bottom = float(ai_data['zone_bottom']) if ai_data.get('zone_bottom') else None
        zone_name = str(ai_data['zone_name']).upper() if ai_data.get('zone_name') else "POI"

        chart_path = f"/tmp/{symbol.replace('/', '')}_final.jpg"
        title = f"{symbol} - 5M Entry Chart"
        
        fig, axlist = mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', returnfig=True)
        ax = axlist[0]

        if entry_val: ax.axhline(entry_val, color='b', linestyle='-', linewidth=1.5, label='Entry')
        if sl_val: ax.axhline(sl_val, color='r', linestyle='--', linewidth=1.5, label='SL')
        if tp_val: ax.axhline(tp_val, color='g', linestyle='--', linewidth=1.5, label='TP')

        if zone_top and zone_bottom:
            ax.axhspan(zone_bottom, zone_top, color='yellow', alpha=0.3)
            ax.axhline(zone_top, color='orange', linestyle='-', linewidth=1)
            ax.axhline(zone_bottom, color='orange', linestyle='-', linewidth=1)
            
            y_center = (zone_top + zone_bottom) / 2
            x_pos = len(df) - 2
            
            ax.text(x_pos, y_center, f" {zone_name} ", fontsize=12, color='black', fontweight='bold', 
                    bbox=dict(facecolor='yellow', alpha=0.8, edgecolor='orange', boxstyle='round,pad=0.3'),
                    verticalalignment='center', horizontalalignment='right')
            
        elif alert_val:
            ax.axhline(alert_val, color='y', linestyle='-', linewidth=2.0, label='Alert Level')

        fig.savefig(chart_path, bbox_inches='tight')
        plt.close(fig) 
        return chart_path
    except Exception as e: 
        return f"❌ Chart Exception: {str(e)}"

# ==========================================
# AI ANALYSIS FUNCTION
# ==========================================
def get_available_gemini_models():
    valid_models = []
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if 'models' in res:
            for m in res['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    name = m['name'].replace('models/', '')
                    if 'flash' in name or 'pro' in name: valid_models.append(name)
            valid_models.sort(reverse=True)
    except: pass
    if not valid_models: valid_models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    return valid_models

def get_gemini_analysis(weekly, daily, h1, m5, current_price, pair, live_data):
    rules = fetch_course_rules()
    
    with open(weekly, "rb") as f: encoded_weekly = base64.b64encode(f.read()).decode('utf-8')
    with open(daily, "rb") as f: encoded_daily = base64.b64encode(f.read()).decode('utf-8')
    with open(h1, "rb") as f: encoded_h1 = base64.b64encode(f.read()).decode('utf-8')
    with open(m5, "rb") as f: encoded_m5 = base64.b64encode(f.read()).decode('utf-8')

    prompt = f"""
    You are an expert SMC/ICT Forex Trader. Analyze the provided charts for {pair} (Current Price: {current_price}).
    
    IMAGE ORDER:
    - Image 1: WEEKLY Chart
    - Image 2: DAILY Chart
    - Image 3: 1H Chart
    - Image 4: 5M Chart
    
    --- COURSE RULES (FOLLOW THESE STRICTLY) ---
    
    [MACRO BIAS RULES - Apply to Weekly & Daily Charts]
    {rules['macro']}
    
    [1H STRUCTURE RULES - Apply to 1H Chart]
    {rules['structure']}
    
    [ENTRY RULES - Apply to 1H & 5M Charts]
    {rules['entry']}
    
    ---------------------------------------------
    Additional Data: \n{live_data}\n

    IMPORTANT: If Status is ENTRY, calculate TP based on EXACTLY 1:3 Risk Reward.
    
    You MUST respond with a valid JSON object ONLY. Do not include markdown formatting or backticks.
    The JSON must have exactly these keys:
    {{
      "report": "1 short line about market movement",
      "trend": "Weekly/Daily Bias (e.g. Bullish)",
      "h1": "1H Trend (e.g. Bearish/Consolidation)",
      "status": "ENTRY or NO TRADE",
      "reason": "1 short SMC reason in Roman Urdu",
      "entry": "Price or null",
      "sl": "Price or null",
      "tp": "Price or null",
      "alert_level": "Price or null",
      "zone_top": "Price or null",
      "zone_bottom": "Price or null",
      "zone_name": "FVG or OB or null"
    }}
    """

    models_to_try = get_available_gemini_models()
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_weekly}},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_daily}},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_h1}},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_m5}}
                ]
            }],
            "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}
        }

        for attempt in range(2):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=90).json() 
                if 'error' in res and res['error'].get('code') == 503:
                    time.sleep(1); break 
                if 'candidates' in res:
                    text = res['candidates'][0]['content']['parts'][0]['text'].strip()
                    return json.loads(text.replace('```json', '').replace('```', '').strip())
                break 
            except Exception as e:
                print(f"Error with {model_name}: {str(e)}")
                time.sleep(1)
    return None

def get_live_data(pair):
    global data_cache
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]

    now = time.time()
    if symbol in data_cache:
        cached_time, cached_data, cached_price = data_cache[symbol]
        if now - cached_time < CACHE_EXPIRY: return cached_data, cached_price
    
    timeframes = {"W": ("1week", 20), "D": ("1day", 20), "1H": ("1h", 60), "5M": ("5min", 60)}
    data_text = ""; current_price = 0
    
    for tf_name, (tf_code, tf_size) in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize={tf_size}&apikey={TWELVEDATA_API_KEY}"
        try:
            res = requests.get(url, timeout=10).json()
            if 'values' in res:
                if tf_code == "5min": current_price = res['values'][0]['close']
                data_text += f"--- {tf_name} ---\n"
                for c in res['values']: data_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else: return f"API_ERROR: {res.get('message', str(res))}", None
        except Exception as e: return f"API_ERROR: {str(e)}", None
            
    data_cache[symbol] = (now, data_text, current_price)
    return data_text, current_price

# ==========================================
# MAIN PROCESS LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper().strip()
        
        if "ALERT" in msg_upper:
            prices = re.findall(r'\b\d+(?:\.\d+)?\b', user_message)
            words = msg_upper.replace("ALERT", "").replace("AND", "").replace("SET", "").split()
            pair = "XAU/USD"
            for w in words:
                if len(w) >= 3 and not w.replace('.', '', 1).isdigit():
                    pair = w; break

            if prices:
                for price_str in prices:
                    price_level = float(price_str)
                    try:
                        oracle_payload = {"symbol": pair, "price": price_level}
                        response = requests.post(ORACLE_API_URL, json=oracle_payload, timeout=10)
                        if response.status_code == 200: send_whatsapp_text(user_number, f"✅ Alert sent to Oracle for {pair} at {price_level}!")
                        else: send_whatsapp_text(user_number, f"❌ Oracle Error for {price_level}.")
                    except Exception as e: send_whatsapp_text(user_number, f"❌ Oracle Connection Failed.")
                return
            else:
                send_whatsapp_text(user_number, "Format: ALERT GOLD 4050 and 4080"); return

        greetings = ["HELLO", "HI", "HEY", "SALAM", "ASSALAM", "AO", "START", "BOSS"]
        if msg_upper in greetings:
            send_whatsapp_text(user_number, "Boss, main bilkul ready hoon! 🚀\nAap mujhe koi bhi pair likh kar bhejien (jaise: XAUUSD, EURUSD, GOLD) taake main RAG-based 4-Chart analysis shuru karoon. 😎")
            return

        valid_keywords = ["XAU", "GOLD", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "BTC"]
        if not any(keyword in msg_upper for keyword in valid_keywords):
            send_whatsapp_text(user_number, "Bhai, valid pair likhein (e.g., EURUSD, XAUUSD, BTCUSD)."); return

        pair = "XAU/USD" if "GOLD" in msg_upper or "XAU" in msg_upper else msg_upper
        
        # MESSAGE FIXED HERE
        send_whatsapp_text(user_number, "⏳ Analysis aur Chart ban raha hai, please wait...")
        
        live_data, current_price = get_live_data(pair)
        if not live_data or live_data.startswith("API_ERROR:"):
            send_whatsapp_text(user_number, f"❌ Data Error for {pair}"); return
            
        chart_w = generate_chart(pair, "1week", 30); time.sleep(1)
        chart_d = generate_chart(pair, "1day", 40); time.sleep(1)
        chart_1h = generate_chart(pair, "1h", 50); time.sleep(1)
        chart_5m = generate_chart(pair, "5min", 50)
        
        if any(c.startswith("❌") for c in [chart_w, chart_d, chart_1h, chart_5m]):
            send_whatsapp_text(user_number, "Chart generate nahi ho saka."); return
            
        ai_data = get_gemini_analysis(chart_w, chart_d, chart_1h, chart_5m, current_price, pair, live_data)
        
        for c in [chart_w, chart_d, chart_1h, chart_5m]: os.remove(c)
        
        if not ai_data:
            send_whatsapp_text(user_number, "❌ AI busy hai ya course text parse nahi hua. Thori dair baad try karein."); return

        if ai_data.get('status') == 'ENTRY':
            try:
                e_val = float(ai_data['entry']); s_val = float(ai_data['sl']); t_val = float(ai_data['tp'])
                risk = abs(e_val - s_val); reward = abs(t_val - e_val)
                if risk > 0 and (reward / risk < 2.9 or reward / risk > 3.1):
                    ai_data['status'] = 'NO TRADE'
                    ai_data['reason'] = f"RR ghalat tha ({reward/risk:.1f}R). Sirf 1:3 allowed hai."
                    ai_data['alert_level'] = ai_data['entry']
            except: pass
            
        final_chart_path = generate_final_chart(pair, ai_data, current_price)
        
        message = f"🪙 {pair}\n📍 Current: {current_price}\n📝 Report: {ai_data.get('report', 'N/A')}\n"
        message += f"📈 Macro Trend: {ai_data.get('trend', 'N/A')}\n📊 1H: {ai_data.get('h1', 'N/A')}\n"
        
        if ai_data.get('status') == 'ENTRY':
            message += f"✅ Status: ENTRY\n💡 Reason: {ai_data.get('reason', 'N/A')}\n"
            message += f"🎯 Entry: {ai_data.get('entry')}\n🛑 SL: {ai_data.get('sl')}\n💰 TP: {ai_data.get('tp')}\n⚖️ RR: 1:3\n"
        else:
            message += f"🚫 Status: NO TRADE\n💡 Reason: {ai_data.get('reason', 'N/A')}\n🎯 Alert Level: {ai_data.get('alert_level')}\n"
            if ai_data.get('zone_name'): message += f"📦 Zone: {ai_data.get('zone_name')} ({ai_data.get('zone_bottom')} - {ai_data.get('zone_top')})\n"

        if final_chart_path.startswith("❌"):
            send_whatsapp_text(user_number, message); send_whatsapp_text(user_number, final_chart_path)
        else:
            status = send_whatsapp_image(user_number, final_chart_path, f"📊 {pair} Entry Chart")
            if status != "SUCCESS": send_whatsapp_text(user_number, status)
            else: send_whatsapp_text(user_number, message)
            os.remove(final_chart_path) 
        
    except Exception as e:
        send_whatsapp_text(user_number, f"SYSTEM ERROR: {str(e)}")

# ==========================================
# ROUTES
# ==========================================
@app.route('/ping', methods=['GET'])
def ping(): return "Alive", 200

@app.route('/', methods=['GET'])
def home(): return "Alive", 200

@app.route('/trigger_analysis', methods=['POST'])
def trigger_analysis():
    data = request.json
    symbol = data.get('symbol', 'XAU/USD')
    threading.Thread(target=process_message, args=(MY_WHATSAPP_NUMBER, symbol)).start()
    return jsonify({"status": "success", "message": "Analysis started"}), 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN: return request.args.get('hub.challenge'), 200
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
                            if is_duplicate(msg.get('id')): continue 
                            if msg['type'] == 'text':
                                threading.Thread(target=process_message, args=(msg['from'], msg['text']['body'].strip())).start()
        except Exception as e: print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
