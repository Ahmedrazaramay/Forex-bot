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
        # WhatsApp text limit (4096 chars) ko handle karne ke liye split (just in case)
        if len(text) > 4000:
            text = text[:4000] + "\n...[Message Truncated]"
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("SEND ERROR:", e)

def get_live_data(pair):
    symbol = pair.upper().replace("GOLD", "XAU/USD").replace("XAUUSD", "XAU/USD")
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]
    
    # Aapke rules ke mutabiq data size
    timeframes = {"W": ("1week", 20), "D": ("1day", 20), "1H": ("1h", 30), "5M": ("5min", 30)}
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
    
    # AAPKA DIYA HUA EXACT PROMPT
    master_prompt = """
Aap ek SMC/ICT-based forex DAY TRADING bot hain.
Setup: 1H POI → 5M Entry | RR 1:3 ONLY | Pair Behavior Aware.

STRICT RULES:

0. PAIR BEHAVIOR (har analysis se pehle):
   - Analyze pair ka behavior profile
   - Volatility, breakaway gap, gap imbalance, sessions
   - Spread check, backtest status
   - IF pair behavior incomplete → WARNING / NO TRADE

1. SIRF course (Part 1–11) ke rules use karo.
   Kuch add mat karo.

2. Analysis TOP-DOWN order mein:
   Step 0: Pair Behavior Profile
   Step 1: Bias (Monthly → Weekly → Daily)
   Step 2: Key Levels (1H POI + 1H Liquidity)
   Step 3: Entry (5M MSS + Displacement + Retest)
   Step 4: Pair-Specific Behavior Check
   Step 5: RR Calculation (1:3 only)
   Step 6: Final Decision

3. Day Trading Fix: 1H POI + 5M entry (change nahi).

4. Bias: Monthly/Weekly/Daily.
   Conflict → bada TF jeete.
   Sirf Main Bias (POI→Liquidity). Reversal avoid.

5. 1H POI valid = OB with FVG.
   Buy=Discount, Sell=Premium.

6. 5M confirmation (all 4 required):
   - 1H POI tap
   - 5M MSS (last swing break, sweep OK)
   - 5M Displacement (FVG+OB)
   - 5M last POI retest

7. SL = 5M POI ± buffer.
   TP = 1H nearest liquidity.

8. RR RULE (STRICT):
   - Sirf 1:3 RR wali entry (±0.1 tolerance)
   - IF RR != 1:3 → NO TRADE
   - TP artificially adjust nahi karna
   - Agar 1H liquidity se 1:3 nahi banti → skip

9. PAIR BEHAVIOR RULES:
   - Breakaway gap: gold=no_fill, bitcoin=fill, forex=fill
   - Gap imbalance: forex/crypto=skip, indian=apply
   - Killzones: forex/gold/crypto=yes, indian=no
   - Volatility: daily_range < 50 pips → NO TRADE
   - Spread: > SL_distance × 0.1 → NO TRADE
   - Bitcoin: expect long consolidations
   - Gold: expect clean trends
   - Forex: session-dependent

10. Avoid: Bias against, sideways, trap, invalid POI,
    incomplete confirmation, RR != 1:3, pair behavior
    mismatch.

OUTPUT FORMAT (isi order mein):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0: PAIR BEHAVIOR
Pair: [name] | Daily Range: [pips]
Volatility: HIGH/MED/LOW | 1:3 RR Feasible: YES/NO
Breakaway Gap: [fill/no fill] | Gap Imbalance: [skip/apply]
Killzones: [yes/no] | Best Session: [NY/London/Asian]
Spread Check: PASS/FAIL | Notable: [1 line]

STEP 1: BIAS
Monthly: [dir] | Weekly: [dir] | Daily: [dir]
Final Bias: [dir] | Reason: [1 line]

STEP 2: KEY LEVELS (1H)
POI Type: [type] | Zone: [price] | Valid: YES/NO
Location: Discount/Premium
TP Liquidity: [price] ([pips] away)

STEP 3: ENTRY CONFIRMATION (5M)
1H POI Tap: YES/NO
5M MSS: YES/NO
5M Displacement: YES/NO
5M Last POI Retest: YES/NO

STEP 4: PAIR BEHAVIOR CHECK
Breakaway Gap Expected: [fill/no fill]
Gap Imbalance: [skip/apply]
Session Filter: [valid/skip]
Volatility Confirm: [YES/NO]

STEP 5: RR CALCULATION
Entry: [price] | SL: [price] ([pips])
TP: [price] ([pips]) | RR: 1:X
Required: 1:3 | Status: PASS/FAIL

STEP 6: FINAL DECISION
Direction: BUY/SELL/NO TRADE
Entry: [price] | SL: [price] | TP: [price]
RR: 1:3 ✅
Confidence: HIGH/MEDIUM/LOW
Pair Context: [why this pair fits]
Reason: [2-3 lines Urdu]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AGAR pair behavior mismatch ya RR != 1:3 → NO TRADE.
SIRF confirmed + 1:3 RR + pair behavior matched
entries do. Jhooti trades nahi.
KHUD SE KUCH ADD NAHI KARNA.
    """
    
    # Data inject karna prompt ke aakhir mein
    full_prompt = f"{master_prompt}\n\n--- LIVE DATA FOR ANALYSIS ---\nPair: {pair}\nCurrent Price: {current_price}\nLive Data:\n{live_data}"
    
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": full_prompt}], "temperature": 0.0}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=45).json() # Timeout barha diya kyunke output lamba hai
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
