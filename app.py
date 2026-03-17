import os
import sqlite3
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction, PostbackAction, 
    DatetimePickerAction, PostbackEvent
)

app = Flask(__name__)

# --- 1. 設定 LINE API ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 初始化資料庫 (使用新檔名 v3 確保乾淨) ---
def init_db():
    conn = sqlite3.connect('ridematch_v3.db')
    cursor = conn.cursor()
    # 媒合行程表
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible_time INTEGER, flexible_loc INTEGER)''')
    # 使用者暫存狀態表
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 3. 模糊媒合邏輯 ---
def find_fuzzy_match(user_id, u_type, t_time, city, dist, flex):
    try:
        conn = sqlite3.connect('ridematch_v3.db')
        cursor = conn.cursor()
        opp_type = 'seeker' if u_type == 'driver' else 'driver'
        target_dt = datetime.strptime(t_time, '%Y-%m-%dT%H:%M')
        
        cursor.execute('SELECT user_id, time_info, district, flexible_time FROM matches WHERE user_type=? AND city=? AND user_id!=?', (opp_type, city, user_id))
        candidates = cursor.fetchall()
        
        for cand_id, cand_time, cand_dist, cand_flex in candidates:
            cand_dt = datetime.strptime(cand_time, '%Y-%m-%dT%H:%M')
            time_diff = abs((target_dt - cand_dt).total_seconds() / 60)
            
            # 時間：任一方彈性則 60 分鐘，否則 30 分鐘
            time_ok = time_diff <= 60 if (flex or cand_flex) else time_diff <= 30
            # 地點：雙方彈性則同縣市，否則需同行政區
            loc_ok = True if (flex and cand_flex) else (dist == cand_dist)
            
            if time_ok and loc_ok:
                conn.close()
                return cand_id, cand_time, cand_dist
        conn.close()
    except Exception as e:
        print(f"Match Error: {e}")
    return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
