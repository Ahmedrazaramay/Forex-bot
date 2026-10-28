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
import queue

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

GITHUB_USER = "Ahmedrazaramay"
GITHUB_REPO = "Forex-bot"

# ==========================================
# QUEUE SYSTEM
# ==========================================
task_queue = queue.Queue()
def worker():
    while True:
        user_number, user_message = task_queue.get()
        process_message(user_number, user_message)
        task_queue.task_done()
threading.Thread(target=worker, daemon=True).start()

# ==========================================
# DUPLICATE FILTER & FETCH RULES
# ==========================================
_processed_messages = {}
def is_duplicate(msg_id):
    if not msg_id: return False
    now = time.time()
    for k in list(_processed_messages.keys()):
        if now - _processed_messages[k] > 300: del _processed_messages[k]
    if msg_id in _processed_messages: return True
    _processed_messages[msg_id] = now
    return False

course_cache = {}
def fetch_course_rules():
    global course_cache
    if course_cache: return course_cache
    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/course_rules.json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            course_cache = res.text
            return course_cache
    except: pass
    return "{}"

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
        if 'id' not in upload_res: return f"❌ Meta Error"
        media_id = upload_res['id']
        msg_url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        msg_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
        requests.post(msg_url, headers=msg_headers, json=payload, timeout=10)
        return "SUCCESS"
    except Exception as e: return f"❌ Image Error"

# ==========================================
# DATA FETCHING (6 TIMEFRAMES)
# ==========================================
def fetch_market_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"W": "1week", "D": "1day", "H4": "4h", "H1": "1h", "M15": "15min", "M5": "5min"}
    data_dict = {}
    current_price = 0
    
    for tf_name, tf_code in timeframes.items():
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf_code}&outputsize=50&apikey={TWELVEDATA_API_KEY}"
        try:
            res = requests.get(url, timeout=10).json()
            if 'values' in res:
                df = pd.DataFrame(res['values'])
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df.set_index('datetime')
                df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'})
                df = df.astype(float).sort_index()
                data_dict[tf_code] = df
                if tf_code == "5min": current_price = df['Close'].iloc[-1]
                time.sleep(2) 
            else: return None, None, f"API_ERROR ({tf_name}): {res.get('message', str(res))}"
        except Exception as e: return None, None, f"API_ERROR ({tf_name}): {str(e)}"
            
    return data_dict, current_price, "OK"

# ==========================================
# CHART GENERATION
# ==========================================
def create_chart(df, symbol, timeframe):
    chart_path = f"/tmp/{symbol.replace('/', '')}_{timeframe}.jpg"
    mpf.plot(df.tail(30), type='candle', style='charles', title=f"{symbol} - {timeframe}", savefig=dict(fname=chart_path, bbox_inches='tight'))
    plt.close('all') 
    return chart_path

def generate_final_chart(df, pair, entry, sl, tp):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    chart_path = f"/tmp/{symbol.replace('/', '')}_final.jpg"
    fig, axlist = mpf.plot(df.tail(30), type='candle', style='charles', title=f"{symbol} - Entry", returnfig=True)
    ax = axlist[0]
    if entry: ax.axhline(entry, color='b', linestyle='-', linewidth=1.5, label='Entry')
    if sl: ax.axhline(sl, color='r', linestyle='--', linewidth=1.5, label='SL')
    if tp: ax.axhline(tp, color='g', linestyle='--', linewidth=1.5, label='TP')
    fig.savefig(chart_path, bbox_inches='tight')
    plt.close(fig) 
    return chart_path

# ==========================================
# AI ANALYSIS (PURE COURSE RULES)
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

def get_ai_analysis(chart_paths, rules_json, pair):
    encoded_charts = []
    for path in chart_paths:
        with open(path, "rb") as f:
            encoded_charts.append(base64.b64encode(f.read()).decode('utf-8'))

    prompt = f"""
    You are an expert Forex Trader. Analyze the live charts for {pair}.
    
    YOUR ONLY REFERENCE IS THIS COURSE JSON:
    {rules_json}
    
    LIVE CHARTS (In Order: Weekly, Daily, H4, H1, M15, M5):
    Analyze them top-down strictly based on the JSON rules.
    
    Calculate Entry, SL, and TP exactly as the JSON rules dictate.
    
    You MUST respond in JSON:
    {{
      "report": "Short report in Roman Urdu",
      "trend": "Bullish or Bearish or Ranging",
      "status": "ENTRY or NO TRADE",
      "reason": "Short reason based on JSON rules",
      "entry": "Price or null",
      "sl": "Price or null",
      "tp": "Price or null",
      "alert_level": "Price or null"
    }}
    """

    models_to_try = get_available_gemini_models()
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        parts = [{"text": prompt}]
        for enc in encoded_charts:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": enc}})
            
        payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}}
        try:
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=90).json() 
            if 'candidates' in res:
                text = res['candidates'][0]['content']['parts'][0]['text'].strip()
                return json.loads(text.replace('```json', '').replace('```', '').strip())
        except: pass
    return None

# ==========================================
# MAIN LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper().strip()
        
        if "ALERT" in msg_upper:
            prices = re.findall(r'\b\d+(?:\.\d+)?\b', user_message)
            words = msg_upper.replace("ALERT", "").replace("AND", "").replace("SET", "").split()
            pair = "XAU/USD"
            for w in words:
                if len(w) >= 3 and not w.replace('.', '', 1).isdigit(): pair = w; break

            if prices:
                for price_str in prices:
                    try:
                        requests.post(ORACLE_API_URL, json={"symbol": pair, "price": float(price_str)}, timeout=10)
                        send_whatsapp_text(user_number, f"✅ Alert sent for {pair} at {price_str}!")
                    except: send_whatsapp_text(user_number, f"❌ Oracle Error.")
                return
            
        if msg_upper in ["HELLO", "HI", "XAUUSD", "BTCUSD", "EURUSD"]:
            pair = "XAU/USD" if "XAU" in msg_upper or "GOLD" in msg_upper else msg_upper
            send_whatsapp_text(user_number, f"⏳ 6 Timeframes ka data aa raha hai. AI aapke Course JSON ke mutabiq analysis kar raha hai...")
            
            data_dict, current_price, err = fetch_market_data(pair)
            if not data_dict:
                send_whatsapp_text(user_number, f"❌ Data Error: {err}"); return
                
            symbol = pair
            chart_paths = []
            tf_order = [("1week", "W"), ("1day", "D"), ("4h", "H4"), ("1h", "H1"), ("15min", "M15"), ("5min", "M5")]
            
            for tf_code, tf_name in tf_order:
                df = data_dict[tf_code]
                chart_path = create_chart(df, symbol, tf_name)
                chart_paths.append(chart_path)
            
            # AI Analysis based on JSON Rules
            rules = fetch_course_rules()
            ai_data = get_ai_analysis(chart_paths, rules, pair)
            
            for path in chart_paths: os.remove(path)
            
            if not ai_data:
                send_whatsapp_text(user_number, "❌ AI Fail. Try again.")
                return
                
            message = f"🪙 {pair}\n📍 Current: {current_price}\n📝 Report: {ai_data.get('report', '')}\n"
            message += f"📈 Trend: {ai_data.get('trend', '')}\n"
            
            if ai_data.get('status') == 'ENTRY':
                entry = ai_data.get('entry')
                sl = ai_data.get('sl')
                tp = ai_data.get('tp')
                
                message += f"✅ Status: ENTRY\n💡 Reason: {ai_data.get('reason', '')}\n"
                message += f"🎯 Entry: {entry}\n🛑 SL: {sl}\n💰 TP: {tp}\n"
                
                final_chart = generate_final_chart(data_dict["5min"], pair, float(entry) if entry else None, float(sl) if sl else None, float(tp) if tp else None)
                send_whatsapp_image(user_number, final_chart, f"📊 {pair} Chart")
                os.remove(final_chart)
            else:
                message += f"🚫 Status: NO TRADE\n💡 Reason: {ai_data.get('reason', '')}\n🎯 Alert Level: {ai_data.get('alert_level', '')}"
                
            send_whatsapp_text(user_number, message)
            return

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
    task_queue.put((MY_WHATSAPP_NUMBER, data.get('symbol', 'XAU/USD')))
    return jsonify({"status": "success"}), 200

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
                                task_queue.put((msg['from'], msg['text']['body'].strip()))
        except Exception as e: print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
