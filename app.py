import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 設定 LINE API
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 初始化資料庫
def init_db():
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    # 建立表格：記錄用戶類型、時間、起點、終點
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_type TEXT, -- 'driver' (司機) 或 'seeker' (找幫忙)
            item_type TEXT, -- 'person' (載人) 或 'cargo' (貨物)
            travel_time TEXT,
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # 簡易邏輯：如果使用者輸入「我要載客」，就觸發流程
    if "載客" in msg or "送貨" in msg:
        reply = "【測試模式】請輸入您的日程，格式如下：\n日期時間,起點,終點\n例如：0320 1400,台北,台中"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    
    elif "," in msg:
        try:
            # 簡單拆解使用者輸入的資訊
            data = msg.split(",")
            conn = sqlite3.connect('ridematch.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO matches (user_id, travel_time, start_point, end_point) VALUES (?, ?, ?, ?)', 
                           (user_id, data[0], data[1], data[2]))
            conn.commit()
            conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已幫您記錄日程，正在搜尋匹配對象..."))
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="格式錯誤，請再試一次。"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="歡迎來到 RideMatch！\n輸入『我要載客』或『我要送貨』開始測試。"))
if __name__ == "__main__":
    app.run()
