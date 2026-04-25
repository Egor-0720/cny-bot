import time
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, time as dt_time
from threading import Thread
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = "173362390"
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

THRESHOLD = 0.4
CHECK_INTERVAL = 5

price_history = deque()
last_alert_global = 0

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
    for timestamp, old_price in price_history:
        seconds_ago = current_time - timestamp
        minutes_ago = seconds_ago / 60
        if 2 <= minutes_ago <= 15:
            change = ((current_price - old_price) / old_price) * 100
            if abs(change) >= THRESHOLD:
                return minutes_ago, change, seconds_ago
    return None, None, None

def is_weekend():
    return datetime.now().weekday() >= 5

def is_working_hours():
    now = datetime.now().time()
    return dt_time(9, 0) <= now <= dt_time(18, 0)

def monitor():
    global last_alert_global
    send("📊 CNY бот запущен. Работает пн-пт 9:00-18:00")
    
    while True:
        if is_weekend():
            time.sleep(3600)
            continue
        
        if not is_working_hours():
            time.sleep(60)
            continue
        
        price = get_price()
        if price is None:
            time.sleep(CHECK_INTERVAL)
            continue
        
        now = time.time()
        price_history.append((now, price))
        
        if now - last_alert_global < 30:
            time.sleep(CHECK_INTERVAL)
            continue
        
        interval, change, seconds = check_movement(price, now)
        
        if interval:
            direction = "🚀 ВВЕРХ" if change > 0 else "📉 ВНИЗ"
            msg = f"{direction} {abs(change):.2f}% за {int(seconds//60)}:{int(seconds%60)} мин\n💰 CNY = {price}"
            send(msg)
            last_alert_global = now
            time.sleep(10)
        
        cutoff = now - 16*60
        while price_history and price_history[0][0] < cutoff:
            price_history.popleft()
        
        time.sleep(CHECK_INTERVAL)

# === ВЕБ-СЕРВЕР ДЛЯ RENDER И HEALTHCHECK ДЛЯ БУДИЛЬНИКА ===
def run_web_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Эндпоинт для будильника (cron-job.org)
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return
        # Главная страница
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    
    def log_message(self, format, *args):
        pass

# Запускаем веб-сервер в фоновом потоке
Thread(target=run_web_server, daemon=True).start()

# Запускаем мониторинг
monitor()
