import os
import sqlite3
from datetime import datetime, timedelta
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
    conn = sqlite3.connect('ridematch_v2.db')
    cursor = conn.cursor()
    # 增加彈性欄位：flexible_time (1=願意, 0=不願意), flexible_loc (1=願意, 0=不願意)
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible_time INTEGER, flexible_loc INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT, flex_t INTEGER, flex_l INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- 輔助函數：模糊媒合 ---
def find_fuzzy_match(user_id, u_type, t_time, city, dist, flex_t, flex_l):
    conn = sqlite3.connect('ridematch_v2.db')
    cursor = conn.cursor()
    opp_type = 'seeker' if u_type == 'driver' else 'driver'
    
    # 解析目標時間
    target_dt = datetime.strptime(t_time, '%Y-%m-%dT%H:%M')
    
    # 撈出所有同縣市、身份相反的潛在對象
    cursor.execute('SELECT user_id, time_info, district, flexible_time, flexible_loc FROM matches WHERE user_type=? AND city=? AND user_id!=?', (opp_type, city, user_id))
    candidates = cursor.fetchall()
    
    for cand_id, cand_time, cand_dist, cand_flex_t, cand_flex_l in candidates:
        cand_dt = datetime.strptime(cand_time, '%Y-%m-%dT%H:%M')
        
        # 1. 時間比對：如果有一方願意彈性，容許正負60分；否則正負30分
        time_diff = abs((target_dt - cand_dt).total_seconds() / 60)
        time_ok = time_diff <= 60 if (flex_t or cand_flex_t) else time_diff <= 30
        
        # 2. 地點比對：如果雙方都願意跨區，同縣市即可；否則必須行政區相同
        loc_ok = True if (flex_l and cand_flex_l) else (dist == cand_dist)
        
        if time_ok and loc_ok:
            conn.close()
            return cand_id, cand_time, cand_dist
            
    conn.close()
    return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

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
        # 選擇縣市
        cities = ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市"]
        items = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 請選擇或輸入【出發縣市】", quick_reply=QuickReply(items=items)))
    
    conn.close()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 身份選擇
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        u_type = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type) VALUES (?, ?)', (user_id, u_type))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選擇出發時間：",
            quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="選擇時間", data="select_time", mode="datetime"))])
        ))

    # B. 處理縣市 -> 帶出熱門行政區 (示例)
    elif msg.startswith("縣市:"):
        city = msg.split(":")[1]
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_city = ? WHERE user_id = ?', (city, user_id))
        conn.commit()
        conn.close()
        # 這裡僅列出部分行政區示範
        districts = ["板橋區", "新莊區", "中和區"] if city == "新北市" else ["信義區", "大安區", "內湖區"]
        items = [QuickReplyButton(action=MessageAction(label=d, text=f"行政區:{d}")) for d in districts]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已選 {city}，請選擇行政區：", quick_reply=QuickReply(items=items)))

    # C. 處理行政區 -> 詢問彈性意願
    elif msg.startswith("行政區:"):
        dist = msg.split(":")[1]
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_dist = ? WHERE user_id = ?', (dist, user_id))
        conn.commit()
        conn.close()
        items = [
            QuickReplyButton(action=MessageAction(label="時間地點皆可彈性", text="彈性:全開")),
            QuickReplyButton(action=MessageAction(label="僅限此時此地", text="彈性:全關"))
        ]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="最後一階段：您是否願意接受時間相差一小時內，或同縣市跨區配對？", quick_reply=QuickReply(items=items)))

    # D. 確認並儲存
    elif msg.startswith("彈性:"):
        flex = 1 if "全開" in msg else 0
        conn = sqlite3.connect('ridematch.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_city, temp_dist FROM user_state WHERE user_id = ?', (user_id,))
        u_type, t_time, city, dist = cursor.fetchone()
        
        # 存入資料庫
        cursor.execute('INSERT INTO matches (user_id, user_type, time_info, city, district, flexible_time, flexible_loc) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                       (user_id, u_type, t_time, city, dist, flex, flex))
        conn.commit()
        
        # 執行模糊媒合
        match_res = find_fuzzy_match(user_id, u_type, t_time, city, dist, flex, flex)
        conn.close()

        confirm_text = f"✅ 行程已發布！\n身分：{'司機' if u_type=='driver' else '乘客'}\n時間：{t_time}\n地點：{city}{dist}\n彈性：{'開啟' if flex else '關閉'}"
        
        if match_res:
            m_id, m_time, m_dist = match_res
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text=confirm_text),
                TextSendMessage(text=f"🎉 發現潛在夥伴！\n對方的預計時間：{m_time}\n地點：{city}{m_dist}\n系統已幫您連線，請稍候。")
            ])
            line_bot_api.push_message(m_id, TextSendMessage(text=f"🔔 媒合通知！有人發布了附近的行程：\n路線：{city}{dist}\n時間：{t_time}\n與您的需求相近，快來看看吧！"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=confirm_text + "\n\n正在搜尋適合的對象..."))

if __name__ == "__main__":
    app.run()
