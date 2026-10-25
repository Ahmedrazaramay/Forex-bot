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
    data = {'messaging_product': 'whatsapp', 'type': 'image/jpeg'} # Changed to JPEG for safety
    
    try:
        upload_res = requests.post(url, headers=headers, files=files, data=data, timeout=20).json()
        print("META UPLOAD RESPONSE:", upload_res)
        
        if 'id' not in upload_res:
            print("❌ UPLOAD FAILED BY META.")
            return False
        
        media_id = upload_res['id']
        msg_url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        msg_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"id": media_id, "caption": caption}
        }
        res = requests.post(msg_url, headers=msg_headers, json=payload, timeout=10)
        print("META IMAGE SEND RESPONSE:", res.text)
        return True
    except Exception as e:
        print("IMAGE SEND EXCEPTION:", e)
        return False

# ==========================================
# CHART GENERATION
# ==========================================
def generate_chart(pair, ai_text, current_price):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
        
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=40&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if 'values' not in res:
            print("CHART DATA ERROR:", res)
            return None

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

        chart_path = f"/tmp/{symbol.replace('/', '')}_chart.jpg" # Save as JPG
        title = f"{symbol} - 5M"
        
        # bbox_inches='tight' se chart cut nahi hota
        mpf.plot(df, type='candle', style='charles', title=title, ylabel='Price', 
                 hlines=hlines if hlines else None, savefig=dict(fname=chart_path, bbox_inches='tight'))
        
        plt.close('all') 
        print("CHART GENERATED SUCCESSFULLY:", chart_path)
        return chart_path
    except Exception as e:
        print("CHART EXCEPTION:", e)
        return None

# ==========================================
# AI LOGIC
# ==========================================
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
# MAIN LOGIC
# ==========================================
def process_message(user_number, user_message):
    try:
        msg_upper = user_message.upper()
        
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

        pair = "XAU/USD" if "GOLD" in msg_upper or "XAU" in msg_upper else msg_upper
        if len(pair) < 4:
            send_whatsapp_text(user_number, "Bhai valid pair likhein.")
            return
        
        send_whatsapp_text(user_number, "⏳ Analysis aur Chart ban raha hai, please wait...")
        
        live_data, current_price = get_live_data(pair)
        if not live_data:
            send_whatsapp_text(user_number, f"❌ Data not available for {pair}")
            return
            
        analysis = get_ai_analysis(pair, live_data, current_price)
        
        chart_path = generate_chart(pair, analysis, current_price)
        if chart_path:
            success = send_whatsapp_image(user_number, chart_path, analysis)
            if not success:
                print("⚠️ Image send failed, sending text only.")
                send_whatsapp_text(user_number, analysis) 
            os.remove(chart_path) 
        else:
            print("⚠️ Chart generation failed, sending text only.")
            send_whatsapp_text(user_number, analysis)
        
    except Exception as e:
        send_whatsapp_text(user_number, f"SYSTEM ERROR: {str(e)}")

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
                                user_message = msg['text']['body'].strip()
                                thread = threading.Thread(target=process_message, args=(user_number, user_message))
                                thread.start()
        except Exception as e:
            print("WEBHOOK CRASH:", e)
        return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
