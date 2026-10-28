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
ORACLE_CLEAR_URL = "http://141.145.158.62:5000/clear_alerts"
MY_WHATSAPP_NUMBER = "923003212360" 

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
# GITHUB RAG & IMAGE FETCHING
# ==========================================
def fetch_course_materials():
    global course_cache
    if course_cache: return course_cache

    print("Fetching Breakout Strategy Materials from GitHub...")
    
    # 1. Fetch Transcript Text
    text_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/breakout_strategy.txt"
    try:
        res = requests.get(text_url, timeout=10)
        rules_text = res.text if res.status_code == 200 else "No rules found."
    except:
        rules_text = "Error fetching rules."

    # 2. Fetch Uploaded Screenshots (Exact names from your GitHub)
    ss_names = [
        "Screenshot_20261028-124622.jpg",
        "Screenshot_20261028-124807.jpg"
    ]
    
    ss_images = []
    for name in ss_names:
        url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{name}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                ss_images.append(base64.b64encode(res.content).decode('utf-8'))
        except:
            pass

    course_cache = {"rules": rules_text, "images": ss_images}
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
# DATA FETCHING
# ==========================================
def fetch_market_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]
    
    timeframes = {"H4": "4h", "M15": "15min"}
    data_dict = {}
    live_text = ""
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
                
                if tf_code == "15min": current_price = df['Close'].iloc[-1]
                
                live_text += f"--- {tf_name} ---\n"
                for c in res['values'][:15]:
                    live_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"
            else:
                return None, None, f"API_ERROR: {res.get('message', str(res))}"
        except Exception as e:
            return None, None, f"API_ERROR: {str(e)}"
            
    return data_dict, current_price, live_text

# ==========================================
# CHART FUNCTIONS
# ==========================================
def create_chart_from_df(df, symbol, timeframe):
    chart_path = f"/tmp/{symbol.replace('/', '')}_{timeframe}.jpg"
    title = f"{symbol} - {timeframe.upper()}"
    mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', savefig=dict(fname=chart_path, bbox_inches='tight'))
    plt.close('all') 
    return chart_path

def generate_final_chart_from_df(df, pair, ai_data):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]

    entry_val = float(ai_data['entry']) if ai_data.get('entry') else None
    sl_val = float(ai_data['sl']) if ai_data.get('sl') else None
    tp_val = float(ai_data['tp']) if ai_data.get('tp') else None
    alert_val = float(ai_data['alert_level']) if ai_data.get('alert_level') else None

    chart_path = f"/tmp/{symbol.replace('/', '')}_final.jpg"
    title = f"{symbol} - M15 Entry Chart"
    
    fig, axlist = mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', returnfig=True)
    ax = axlist[0]

    if entry_val: ax.axhline(entry_val, color='b', linestyle='-', linewidth=1.5, label='Entry')
    if sl_val: ax.axhline(sl_val, color='r', linestyle='--', linewidth=1.5, label='SL')
    if tp_val: ax.axhline(tp_val, color='g', linestyle='--', linewidth=1.5, label='TP')
    if alert_val: ax.axhline(alert_val, color='y', linestyle='-', linewidth=2.0, label='Alert')

    fig.savefig(chart_path, bbox_inches='tight')
    plt.close(fig) 
    return chart_path

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

def get_gemini_analysis(materials, chart_h4_path, chart_m15_path, current_price, pair, live_data):
    with open(chart_h4_path, "rb") as f: encoded_h4 = base64.b64encode(f.read()).decode('utf-8')
    with open(chart_m15_path, "rb") as f: encoded_m15 = base64.b64encode(f.read()).decode('utf-8')

    prompt = f"""
    You are an expert Breakout Trader. Analyze the live charts for {pair} (Current Price: {current_price}).
    
    --- YOUR REFERENCE MATERIALS ---
    1. TEXT RULES: \n{materials['rules']}\n
    2. UPLOADED IMAGES: These are your course's Screenshots showing how to mark levels and take breakout entries.
    
    --- LIVE CHARTS TO ANALYZE ---
    - Live H4 Chart (Look for Structure/Minor Levels)
    - Live M15 Chart (Look for Breakout Entry)
    
    Additional Data: \n{live_data}\n

    Follow the exact visual method shown in the uploaded Screenshots. If the live chart looks like the course examples, give an ENTRY. Otherwise, NO TRADE.
    IMPORTANT: If Status is ENTRY, calculate TP based on EXACTLY 1:3 Risk Reward.
    
    You MUST respond with a valid JSON object ONLY. Do not include markdown formatting or backticks.
    The JSON must have exactly these keys:
    {{
      "report": "1 short line about market movement",
      "trend": "Bullish or Bearish",
      "status": "ENTRY or NO TRADE",
      "reason": "1 short reason in Roman Urdu matching the course logic",
      "entry": "Price or null",
      "sl": "Price or null",
      "tp": "Price or null",
      "alert_level": "Price or null"
    }}
    """

    models_to_try = get_available_gemini_models()
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        
        # Prepare parts (Prompt + H4 + M15 + Uploaded SS)
        parts = [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": encoded_h4}},
            {"inline_data": {"mime_type": "image/jpeg", "data": encoded_m15}}
        ]
        
        for img in materials['images']:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img}})

        payload = {
            "contents": [{"parts": parts}],
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

# ==========================================
# MAIN PROCESS LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper().strip()
        
        if "CLEAR" in msg_upper or "DELETE" in msg_upper or "RESET" in msg_upper:
            try:
                response = requests.post(ORACLE_CLEAR_URL, timeout=10)
                if response.status_code == 200: send_whatsapp_text(user_number, "✅ Saare purane alerts delete ho gaye hain!")
                else: send_whatsapp_text(user_number, "❌ Oracle Error.")
            except Exception as e: send_whatsapp_text(user_number, f"❌ Oracle Connection Failed.")
            return

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
                        else: send_whatsapp_text(user_number, f"❌ Oracle Error.")
                    except Exception as e: send_whatsapp_text(user_number, f"❌ Oracle Connection Failed.")
                return
            else:
                send_whatsapp_text(user_number, "Format: ALERT GOLD 4050 and 4080"); return

        greetings = ["HELLO", "HI", "HEY", "SALAM", "ASSALAM", "AO", "START", "BOSS"]
        if msg_upper in greetings:
            send_whatsapp_text(user_number, "Boss, main bilkul ready hoon! 🚀\nAap mujhe koi bhi pair likh kar bhejien (jaise: XAUUSD, EURUSD, GOLD) taake main course SS aur rules ke sath analysis shuru karoon. 😎")
            return

        valid_keywords = ["XAU", "GOLD", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "BTC"]
        if not any(keyword in msg_upper for keyword in valid_keywords):
            send_whatsapp_text(user_number, "Bhai, valid pair likhein (e.g., EURUSD, XAUUSD, BTCUSD)."); return

        pair = "XAU/USD" if "GOLD" in msg_upper or "XAU" in msg_upper else msg_upper
        send_whatsapp_text(user_number, "⏳ Analysis aur Chart ban raha hai, please wait...")
        
        materials = fetch_course_materials()
        data_dict, current_price, live_data = fetch_market_data(pair)
        
        if not data_dict:
            send_whatsapp_text(user_number, f"❌ Data Error for {pair}: {live_data}"); return
            
        symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
        if "/" not in symbol and len(symbol) == 6: symbol = symbol[:3] + "/" + symbol[3:]
        
        chart_h4 = create_chart_from_df(data_dict["4h"], symbol, "4h")
        chart_m15 = create_chart_from_df(data_dict["15min"], symbol, "15min")
        
        ai_data = get_gemini_analysis(materials, chart_h4, chart_m15, current_price, pair, live_data)
        
        for c in [chart_h4, chart_m15]: os.remove(c)
        
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
            
        final_chart_path = generate_final_chart_from_df(data_dict["15min"], pair, ai_data)
        
        message = f"🪙 {pair}\n📍 Current: {current_price}\n📝 Report: {ai_data.get('report', 'N/A')}\n"
        message += f"📈 Trend: {ai_data.get('trend', 'N/A')}\n"
        
        if ai_data.get('status') == 'ENTRY':
            message += f"✅ Status: ENTRY\n💡 Reason: {ai_data.get('reason', 'N/A')}\n"
            message += f"🎯 Entry: {ai_data.get('entry')}\n🛑 SL: {ai_data.get('sl')}\n💰 TP: {ai_data.get('tp')}\n⚖️ RR: 1:3\n"
        else:
            message += f"🚫 Status: NO TRADE\n💡 Reason: {ai_data.get('reason', 'N/A')}\n🎯 Alert Level: {ai_data.get('alert_level')}\n"

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
