import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 1. 設定 LINE API 金鑰 ---
# 請確保你在 Render 的 Environment Variables 已經設定好這兩項
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 初始化資料庫 ---
def init_db():
    # Render 免費版重啟時此檔案會重置，前期開發測試 OK
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_type TEXT,
            travel_info TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 3. 接收 LINE 訊號的入口 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 4. 處理訊息邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 處理「我要載客/貨」 (對應圖文選單按鈕 1)
    if msg == "我要載客/貨":
        reply = "🚕 您好！請輸入您的日程資訊（格式：時間,起點,終點）\n例如：0320 1400,台北,台中"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    # B. 處理「我要搭車/寄物」 (對應圖文選單按鈕 2)
    elif msg == "我要搭車/寄物":
        reply = "📦 您好！請輸入您的需求資訊（格式：時間,起點,終點）\n例如：0320 1500,台北,台中"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    # C. 處理「我的行程」 (對應圖文選單按鈕 3)
    elif msg == "我的行程":
        # 這裡之後可以寫從資料庫撈取資料的邏輯
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="目前功能開發中，稍後將開放查詢您的記錄！"))

    # D. 處理「媒合規則」 (對應圖文選單按鈕 4)
    elif msg == "媒合規則":
        rule_text = "【RideMatch 規則】\n1. 目前為推廣期，媒合完全免費。\n2. 未來將針對『找幫忙的人』收取配對金（載人100元/貨物60元）。\n3. 請確認行程資訊準確以便媒合。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=rule_text))

    # E. 處理資料輸入 (當訊息包含逗號時，視為行程輸入)
    elif "," in msg or "，" in msg:
        try:
            # 取代全形逗號
            clean_msg = msg.replace("，", ",")
            conn = sqlite3.connect('ridematch.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO matches (user_id, travel_info) VALUES (?, ?)', (user_id, clean_msg))
            conn.commit()
            conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已收到您的資訊！系統正在為您尋找合適的夥伴..."))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="輸入儲存失敗，請檢查格式是否正確。"))

    # F. 預設回覆
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請點擊下方選單開始使用 RideMatch 服務！"))

if __name__ == "__main__":
    app.run()
