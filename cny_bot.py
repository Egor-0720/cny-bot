import time
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, time as dt_time
from threading import Thread
from collections import deque

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = "173362390"
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

THRESHOLD = 0.4
CHECK_INTERVAL = 5

price_history = deque()
last_alert_global = 0
first_hit_time = {}

def send(msg):
    try:
        requests.post(URL, data={"chat_id": CHAT_ID, "text": msg})
        print(f"Отправлено: {msg}")
    except Exception as e:
        print(f"Ошибка: {e}")

def get_price():
    try:
        url = "https://iss.moex.com/iss/engines/currency/markets/selt/securities/CNYRUB_TOM.json"
        data = requests.get(url, timeout=10).json()
        price = data['marketdata']['data'][0][12]
        return float(price)
    except Exception as e:
        print(f"Ошибка получения цены: {e}")
        return None

def check_movement(current_price, current_time):
    results = []
    
    for timestamp, old_price in price_history:
        seconds_ago = current_time - timestamp
        minutes_ago = seconds_ago / 60
        
        if 2 <= minutes_ago <= 15:
            change = ((current_price - old_price) / old_price) * 100
            
            if abs(change) >= THRESHOLD:
                results.append((minutes_ago, change, seconds_ago))
    
    if not results:
        return None, None, None
    
    fastest = min(results, key=lambda x: x[2])
    return fastest[0], fastest[1], fastest[2]

def is_weekend():
    return datetime.now().weekday() >= 5

def is_working_hours():
    now = datetime.now().time()
    start = dt_time(9, 0)
    end = dt_time(18, 0)
    return start <= now <= end

def monitor():
    global last_alert_global
    
    send("📊 Бот CNYRUB_TOM запущен")
    send("⏰ Работает: будни 9:00-18:00")
    send("🎯 Порог: 0.4% | Интервал: 2-15 минут")
    
    while True:
        if is_weekend():
            time.sleep(3600)
            continue
        
        if not is_working_hours():
            time.sleep(60)
            continue
        
        current_price = get_price()
        if current_price is None:
            time.sleep(CHECK_INTERVAL)
            continue
        
        current_time = time.time()
        price_history.append((current_time, current_price))
        
        if current_time - last_alert_global < 30:
            time.sleep(CHECK_INTERVAL)
            continue
        
        interval, change, seconds = check_movement(current_price, current_time)
        
        if interval is not None:
            direction = "🚀 ВВЕРХ" if change > 0 else "📉 ВНИЗ"
            abs_change = abs(change)
            minutes_int = int(seconds // 60)
            seconds_int = int(seconds % 60)
            
            msg = f"{direction} {abs_change:.2f}% за {minutes_int} мин {seconds_int} сек!\n💰 CNYRUB_TOM = {current_price}"
            
            send(msg)
            last_alert_global = current_time
            time.sleep(10)
        
        cutoff = current_time - 16 * 60
        while price_history and price_history[0][0] < cutoff:
            price_history.popleft()
        
        time.sleep(CHECK_INTERVAL)

def http_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, format, *args):
            pass
    server = HTTPServer(('0.0.0.0', 8080), Handler)
    server.serve_forever()

thread = Thread(target=http_server, daemon=True)
thread.start()
monitor()
