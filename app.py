import os
import sqlite3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction, 
    DatetimePickerAction, PostbackEvent,
    TemplateSendMessage, CarouselTemplate, CarouselColumn
)

app = Flask(__name__)

# --- 1. API 設定 ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 資料庫初始化 (v6 加入 prefs 欄位) ---
def init_db():
    conn = sqlite3.connect('ridematch_v6.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible TEXT, prefs TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT, temp_flex TEXT, temp_prefs TEXT)''')
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

# --- 3. 處理時間選擇 (Postback) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == "select_time":
        t = event.postback.params['datetime']
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ? WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        
        cities = ["台北市", "新北市", "桃園市", "台中市", "高雄市"]
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 時間設定成功！請選擇【縣市】", quick_reply=QuickReply(items=btns)))

# --- 4. 處理主要對話邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 啟動身分選擇
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_prefs) VALUES (?, ?, ?)', (user_id, ut, ""))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選擇出發日期時間：",
            quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 選擇", data="select_time", mode="datetime"))])
        ))

    # B. 縣市 -> 行政區
    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_city = ? WHERE user_id = ?', (c, user_id))
        conn.commit()
        conn.close()
        dists = ["板橋區", "新莊區", "中和區"] if c == "新北市" else ["信義區", "大安區", "內湖區"]
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"行政區:{d}")) for d in dists]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    # C. 行政區 -> 彈性
    elif msg.startswith("行政區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_dist = ? WHERE user_id = ?', (d, user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對？", quick_reply=QuickReply(items=btns)))

    # D. 彈性 -> 顯示 Dauding 式詳細規範 (Carousel)
    elif msg.startswith("彈性:"):
        f = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (f, user_id))
        conn.commit()
        conn.close()

        # 這裡彈出 Dauding 的選項卡片
        carousel = CarouselTemplate(columns=[
            CarouselColumn(
                title='🚗 行車規範', text='請選擇(可多選)',
                actions=[
                    MessageAction(label='🚭 全程禁菸', text='規範:全程禁菸'),
                    MessageAction(label='📦 提供包裹服務', text='規範:提供包裹'),
                    MessageAction(label='⏰ 務必準時', text='規範:務必準時')
                ]
            ),
            CarouselColumn(
                title='💰 費用相關', text='請選擇您的偏好',
                actions=[
                    MessageAction(label='💵 不接受議價', text='規範:不接受議價'),
                    MessageAction(label='📲 接受轉帳', text='規範:接受轉帳'),
                    MessageAction(label='🐶 寵物酌收費', text='規範:寵物酌收費')
                ]
            ),
            CarouselColumn(
                title='💬 其他細節', text='增加配對精準度',
                actions=[
                    MessageAction(label='🐾 寵物需裝籠', text='規範:寵物需裝籠'),
                    MessageAction(label='🧳 有大型行李', text='規範:有大型行李'),
                    MessageAction(label='✅ 完成並發布', text='最終確認發布')
                ]
            )
        ])
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='詳細規範', template=carousel))

    # E. 處理規範標籤 (多選)
    elif msg.startswith("規範:"):
        pref = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('SELECT temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        p_str = cursor.fetchone()[0] or ""
        if pref not in p_str:
            p_str += f"{pref}, "
            cursor.execute('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?', (p_str, user_id))
            conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"已加入標籤：{pref}\n目前已選：{p_str}\n您可繼續上方選取，或點擊下方按鈕結束。",
            quick_reply=QuickReply(items=[QuickReplyButton(action=MessageAction(label="👌 選好了，發布！", text="最終確認發布"))])
        ))

    # F. 最終發布
    elif msg == "最終確認發布":
        conn = sqlite3.connect('ridematch_v6.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_city, temp_dist, temp_flex, temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        if res:
            ut, tt, ct, dt, fx, ps = res
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, city, district, flexible, prefs) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                           (user_id, ut, tt, ct, dt, fx, ps))
            conn.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🚀 發布成功！\n身分：{ut}\n時間：{tt}\n路線：{ct}{dt}\n規範：{ps}\n\n正在自動媒合中..."))
        conn.close()

if __name__ == "__main__":
    app.run()
