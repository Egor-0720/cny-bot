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

# НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ ОБЪЁМА
last_volume_data = {'volume': None, 'time': 0, 'price': None}
VOLUME_SPIKE_THRESHOLD = 500000      # 500,000 единиц
MINUTE_MOVE_THRESHOLD = 0.32         # 0.32% за минуту

def send(msg):
    try:
        requests.post(URL, data={"chat_id": CHAT_ID, "text": msg})
        print(f"Отправлено: {msg}")
    except Exception as e:
        print(f"Ошибка: {e}")

def get_price_and_volume():
    """Возвращает цену и объём VOLTODAY"""
    try:
        url = "https://iss.moex.com/iss/engines/currency/markets/selt/securities/CNYRUB_TOM.json"
        data = requests.get(url, timeout=10).json()
        marketdata = data['marketdata']['data'][0]
        price = marketdata[12]           # LAST
        volume_today = marketdata[16]    # VOLTODAY
        return float(price), float(volume_today)
    except Exception as e:
        print(f"Ошибка получения цены/объёма: {e}")
        return None, None

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

def send_regular_signal(change, seconds, price, interval):
    """Отправляет сигнал с градацией по скорости"""
    direction = "🚀 ВВЕРХ" if change > 0 else "📉 ВНИЗ"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    
    # Определяем тип сигнала по времени
    if interval <= 5:
        emoji = "🟢 СИЛЬНЫЙ СИГНАЛ"
        strength = "Быстрое движение"
    else:
        emoji = "🟡 БАЗОВЫЙ СИГНАЛ"
        strength = "Плавное движение"
    
    msg = f"""{emoji} {direction}
📊 {abs(change):.2f}% за {minutes} мин {secs} сек
💰 CNY = {price}
⚡ {strength}"""
    send(msg)

def send_critical_signal(price_change, volume_change, current_price):
    """Отправляет критический сигнал (объём + быстрая цена)"""
    direction = "🚀 ВВЕРХ" if price_change > 0 else "📉 ВНИЗ"
    msg = f"""🔥 КРИТИЧЕСКИЙ СИГНАЛ!
{direction} {abs(price_change):.2f}% за 1 минуту
📊 Объём за минуту: {volume_change:,.0f}
💰 CNY = {current_price}
⚡ Аномальный всплеск!"""
    send(msg)

def monitor():
    global last_alert_global
    
    send("📊 CNY бот запущен. Работает пн-пт 9:00-18:00")
    send("🛡️ Режимы: 1) Объём+1мин (🔥) 2) 2-5мин (🟢) 3) 6-15мин (🟡)")
    
    while True:
        if is_weekend():
            time.sleep(3600)
            continue
        
        if not is_working_hours():
            time.sleep(60)
            continue
        
        price, volume = get_price_and_volume()
        if price is None:
            time.sleep(CHECK_INTERVAL)
            continue
        
        now = time.time()
        
        # === ОСНОВНАЯ ЛОГИКА (2–15 минут) С ГРАДАЦИЕЙ ===
        price_history.append((now, price))
        
        if now - last_alert_global >= 30:
            interval_min, change, seconds = check_movement(price, now)
            if interval_min:
                send_regular_signal(change, seconds, price, interval_min)
                last_alert_global = now
                time.sleep(10)
        
        # === НОВАЯ ЛОГИКА: ОБЪЁМ + 1 МИНУТА ===
        if last_volume_data['volume'] is not None and volume is not None:
            # Проверяем, прошла ли минута
            if now - last_volume_data['time'] >= 60:
                # Объём за минуту
                volume_diff = volume - last_volume_data['volume']
                # Изменение цены за минуту
                if last_volume_data['price'] is not None:
                    minute_price_change = ((price - last_volume_data['price']) / last_volume_data['price']) * 100
                    
                    # Условие для критического сигнала
                    if (volume_diff >= VOLUME_SPIKE_THRESHOLD and 
                        abs(minute_price_change) >= MINUTE_MOVE_THRESHOLD):
                        send_critical_signal(minute_price_change, volume_diff, price)
                        last_alert_global = now
                        time.sleep(10)
        
        # Обновляем данные для объёмной логики
        last_volume_data['volume'] = volume
        last_volume_data['time'] = now
        last_volume_data['price'] = price
        
        # Чистим старую историю цен (16 минут)
        cutoff = now - 17*60
        while price_history and price_history[0][0] < cutoff:
            price_history.popleft()
        
        time.sleep(CHECK_INTERVAL)

# === ВЕБ-СЕРВЕР ДЛЯ RENDER И HEALTHCHECK ===
def run_web_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    
    def log_message(self, format, *args):
        pass

# Запускаем веб-сервер в фоновом потоке
Thread(target=run_web_server, daemon=True).start()

# Запускаем мониторинг
monitor()
