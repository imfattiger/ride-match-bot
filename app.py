import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 資料庫增加 status 紀錄使用者最後按下的按鈕
def init_db():
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    # 儲存行程的表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_type TEXT,
            time_info TEXT,
            start_point TEXT,
            end_point TEXT
        )
    ''')
    # 儲存使用者目前狀態的表 (司機或需求者)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY,
            current_type TEXT
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

def find_match(user_id, user_type, start_p, end_p):
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    opposite_type = 'seeker' if user_type == 'driver' else 'driver'
    # 尋找相反身份且路線一致的最新一筆
    cursor.execute('''
        SELECT user_id FROM matches 
        WHERE user_type = ? AND start_point = ? AND end_point = ? AND user_id != ?
        ORDER BY id DESC LIMIT 1
    ''', (opposite_type, start_p, end_p, user_id))
    match = cursor.fetchone()
    conn.close()
    return match[0] if match else None

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # 1. 當點擊選單按鈕，更新並紀錄該使用者的身份
    if msg == "我要載客/貨":
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type) VALUES (?, ?)', (user_id, 'driver'))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚕 您現在是【司機】狀態。\n請輸入：時間,起點,終點"))
        return

    if msg == "我要搭車/寄物":
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type) VALUES (?, ?)', (user_id, 'seeker'))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🙋 您現在是【需求者】狀態。\n請輸入：時間,起點,終點"))
        return

    # 2. 處理資料輸入
    if "," in msg or "，" in msg:
        try:
            # 取得該使用者目前的身份
            conn = sqlite3.connect('ridematch.db')
            cursor = conn.cursor()
            cursor.execute('SELECT current_type FROM user_state WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            u_type = res[0] if res else 'seeker' # 沒按按鈕預設為 seeker

            clean_msg = msg.replace("，", ",")
            parts = clean_msg.split(",")
            time_p, start_p, end_p = parts[0].strip(), parts[1].strip(), parts[2].strip()
            
            # 存入行程表
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, start_point, end_point) VALUES (?, ?, ?, ?, ?)', 
                           (user_id, u_type, time_p, start_p, end_p))
            conn.commit()
            
            # 執行媒合
            match_user_id = find_match(user_id, u_type, start_p, end_p)
            conn.close()

            if match_user_id:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 媒合成功！已找到對應夥伴。\n路線：{start_p} -> {end_p}\n系統已向對方發送通知。"))
                # 推送給對方
                line_bot_api.push_message(match_user_id, TextSendMessage(text=f"🔔 媒合通知！有人剛發布了從 {start_p} 到 {end_p} 的行程，與您的需求相符！"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已記錄行程，正在等待合適的夥伴出現..."))
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="格式錯誤。請確保為：時間,起點,終點"))
    
    elif msg == "媒合規則":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="目前推廣中，完全免費！"))
