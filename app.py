import os
import sqlite3
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction, 
    DatetimePickerAction, PostbackEvent
)

app = Flask(__name__)

# --- API 設定 ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 資料庫初始化 ---
def init_db():
    conn = sqlite3.connect('ridematch_v4.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible_time INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT)''')
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

# --- 處理時間選擇 ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == "select_time":
        t = event.postback.params['datetime']
        conn = sqlite3.connect('ridematch_v4.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ? WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        
        cities = ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市"]
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 時間 OK！請選縣市", quick_reply=QuickReply(items=btns)))

# --- 處理文字訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v4.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type) VALUES (?, ?)', (user_id, ut))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選日期時間：",
            quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 選擇", data="select_time", mode="datetime"))])
        ))

    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v4.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_city = ? WHERE user_id = ?', (c, user_id))
        conn.commit()
        conn.close()
        dists = ["板橋區", "新莊區", "中和區"] if c == "新北市" else ["信義區", "大安區", "內湖區"]
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"行政區:{d}")) for d in dists]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("行政區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v4.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_dist = ? WHERE user_id = ?', (d, user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:1")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:0"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對？", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("彈性:"):
        f = int(msg.split(":")[1])
        conn = sqlite3.connect('ridematch_v4.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_city, temp_dist FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        
        if res and res[1] and res[2]:
            ut, tt, ct, dt = res
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, city, district, flexible_time) VALUES (?, ?, ?, ?, ?, ?)', (user_id, ut, tt, ct, dt, f))
            conn.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 發布成功！\n路徑：{ct}{dt}\n正在媒合中..."))
        conn.close()

if __name__ == "__main__":
    app.run()
