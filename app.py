import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 1. 設定 LINE API ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 初始化資料庫 (增加 user_type 欄位) ---
def init_db():
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_type TEXT, -- 'driver' 或 'seeker'
            time_info TEXT,
            start_point TEXT,
            end_point TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 3. 媒合邏輯函數 ---
def find_match(user_id, user_type, start_p, end_p):
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    
    # 找尋：起點終點相同、身份相反、且不是自己
    opposite_type = 'seeker' if user_type == 'driver' else 'driver'
    cursor.execute('''
        SELECT user_id FROM matches 
        WHERE user_type = ? AND start_point = ? AND end_point = ? AND user_id != ?
        ORDER BY id DESC LIMIT 1
    ''', (opposite_type, start_p, end_p, user_id))
    
    match = cursor.fetchone()
    conn.close()
    return match[0] if match else None

# --- 4. 處理訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 判斷身份
    if msg == "我要載客/貨":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚕 您是【司機/載貨方】\n請輸入：時間,起點,終點\n(例如：0320 1400,台北,台中)"))
        return

    if msg == "我要搭車/寄物":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🙋 您是【需求方】\n請輸入：時間,起點,終點\n(例如：0320 1400,台北,台中)"))
        return

    # B. 處理輸入資料並進行媒合
    if "," in msg or "，" in msg:
        try:
            clean_msg = msg.replace("，", ",")
            parts = clean_msg.split(",")
            time_p, start_p, end_p = parts[0].strip(), parts[1].strip(), parts[2].strip()
            
            # 這裡簡單判斷：若訊息前有觸發詞則記錄身份（這部分未來可用 State 管理，目前先假設最近一筆）
            # 為了測試方便，我們這版直接根據輸入格式儲存，並嘗試媒合
            # 假設：我們讓使用者輸入時多帶一個字，或預設邏輯
            
            # --- 測試邏輯：我們暫定這封訊息是 seeker (需求者) ---
            u_type = 'seeker' # 實際上應由前一個按鈕狀態決定
            
            conn = sqlite3.connect('ridematch.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, start_point, end_point) VALUES (?, ?, ?, ?, ?)', 
                           (user_id, u_type, time_p, start_p, end_p))
            conn.commit()
            conn.close()

            # 執行媒合比對
            match_user_id = find_match(user_id, u_type, start_p, end_p)
            
            if match_user_id:
                # 通知當前使用者
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 媒合成功！已找到對應夥伴。\n路線：{start_p} -> {end_p}\n系統已向對方發送通知。"))
                
                # 主動推送訊息給對方 (Push Message)
                line_bot_api.push_message(match_user_id, TextSendMessage(text=f"🔔 媒合通知！有人剛發布了從 {start_p} 到 {end_p} 的行程，與您的需求相符！"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已記錄行程，正在等待合適的夥伴出現..."))
                
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="格式錯誤或系統忙碌中。"))

    elif msg == "媒合規則":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="【RideMatch 規則】\n目前免費媒合！找幫忙者未來預計收取 60~100 元配對金。"))
