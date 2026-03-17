import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction, PostbackAction, 
    DatetimePickerAction, PostbackEvent
)

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

def init_db():
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, start_point TEXT, end_point TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_start TEXT)''')
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

# --- 處理點選按鈕後的隱藏資料 (Postback) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    conn = sqlite3.connect('ridematch.db')
    cursor = conn.cursor()

    if data == "select_time":
        selected_time = event.postback.params['datetime']
        cursor.execute('UPDATE user_state SET temp_time = ? WHERE user_id = ?', (selected_time, user_id))
        conn.commit()
        # 下一步：詢問起點 (使用快速回覆列出熱門城市)
        cities = ["台北", "新竹", "台中", "台南", "高雄"]
        items = [QuickReplyButton(action=MessageAction(label=c, text=f"起點:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 請選擇或輸入【起點】", quick_reply=QuickReply(items=items)))
    
    conn.close()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # 1. 初始選擇身分
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        u_type = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type) VALUES (?, ?)', (user_id, u_type))
        conn.commit()
        conn.close()
        
        # 彈出時間選擇器
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"您目前的身份是：{'司機' if u_type=='driver' else '需求方'}\n請選擇出發日期與時間：",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=DatetimePickerAction(label="選擇時間", data="select_time", mode="datetime"))
            ])
        ))

    # 2. 處理起點輸入
    elif msg.startswith("起點:"):
        start_p = msg.split(":")[1]
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_start = ? WHERE user_id = ?', (start_p, user_id))
        conn.commit()
        conn.close()
        
        cities = ["台北", "新竹", "台中", "台南", "高雄"]
        items = [QuickReplyButton(action=MessageAction(label=c, text=f"終點:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已設定起點：{start_p}\n📍 請選擇或輸入【終點】", quick_reply=QuickReply(items=items)))

    # 3. 處理終點輸入並完成紀錄
    elif msg.startswith("終點:"):
        end_p = msg.split(":")[1]
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_start FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        
        if res:
            u_type, t_time, s_start = res
            # 存入正式行程表
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, start_point, end_point) VALUES (?, ?, ?, ?, ?)', 
                           (user_id, u_type, t_time, s_start, end_p))
            conn.commit()
            
            # 執行媒合
            opposite_type = 'seeker' if u_type == 'driver' else 'driver'
            cursor.execute('SELECT user_id FROM matches WHERE user_type=? AND start_point=? AND end_point=? AND user_id!=? ORDER BY id DESC LIMIT 1', 
                           (opposite_type, s_start, end_p, user_id))
            match = cursor.fetchone()
            
            if match:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 媒合成功！\n路線：{s_start} -> {end_p}\n時間：{t_time}\n已通知對方！"))
                line_bot_api.push_message(match[0], TextSendMessage(text=f"🔔 媒合通知！有人剛發布了從 {s_start} 到 {end_p} 的行程，時間為 {t_time}，與您相符！"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已幫您發布行程，正在搜尋夥伴中..."))
        conn.close()

if __name__ == "__main__":
    app.run()
