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

# --- 2. 資料庫初始化 ---
def init_db():
    conn = sqlite3.connect('ridematch_v7.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible TEXT, prefs TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT, temp_flex TEXT, temp_prefs TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 3. 快速回覆選單 (大類導向) ---
def get_main_cat_menu(text_prefix=""):
    items = [
        QuickReplyButton(action=MessageAction(label="🚗 行程/地點", text="類別:行程")),
        QuickReplyButton(action=MessageAction(label="💰 費用相關", text="類別:費用")),
        QuickReplyButton(action=MessageAction(label="🚬 環境規範", text="類別:環境")),
        QuickReplyButton(action=MessageAction(label="💬 乘車氛圍", text="類別:氛圍")),
        QuickReplyButton(action=MessageAction(label="🚀 好了，發布！", text="最終確認發布"))
    ]
    return TextSendMessage(text=f"{text_prefix}請選擇欲加入的標籤分類：", quick_reply=QuickReply(items=items))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 4. 處理 Postback (時間選擇) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == "select_time":
        t = event.postback.params['datetime']
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ? WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        
        cities = ["台北市", "新北市", "桃園市", "台中市", "高雄市"]
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 時間設定成功！請選擇【縣市】", quick_reply=QuickReply(items=btns)))

# --- 5. 核心邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 啟動身分選擇
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_prefs) VALUES (?, ?, ?)', (user_id, ut, ""))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選擇出發日期時間：",
            quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))])
        ))

    # B. 縣市 -> 行政區
    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v7.db')
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
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_dist = ? WHERE user_id = ?', (d, user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對？(容許時間地點微調)", quick_reply=QuickReply(items=btns)))

    # D. 彈性 -> 啟動「Dauding 標籤循環系統」
    elif msg.startswith("彈性:"):
        f = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (f, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu("最後一步：自定義您的行程規範。\n"))

    # E. 根據類別展示對應卡片 (拆分 Dauding 的 37+ 選項)
    elif msg.startswith("類別:"):
        cat = msg.split(":")[1]
        cols = []
        if cat == "行程":
            cols = [
                CarouselColumn(title='行程規範(1)', text='基本服務', actions=[
                    MessageAction(label='提供包裹服務', text='規範:提供包裹服務'),
                    MessageAction(label='上下車可討論', text='規範:上下車可討論'),
                    MessageAction(label='順路為主', text='規範:順路為主')
                ]),
                CarouselColumn(title='行程規範(2)', text='目的地與寵物', actions=[
                    MessageAction(label='送至目的地', text='規範:可以送至目的地'),
                    MessageAction(label='可停等休息站', text='規範:可停等休息站'),
                    MessageAction(label='寵物需裝籠', text='規範:寵物需裝籠')
                ]),
                CarouselColumn(title='行程規範(3)', text='限制', actions=[
                    MessageAction(label='謝絕寵物', text='規範:謝絕寵物'),
                    MessageAction(label='有大型行李先告知', text='規範:大型行李告知'),
                    MessageAction(label='務必準時', text='規範:務必準時')
                ])
            ]
        elif cat == "費用":
            cols = [
                CarouselColumn(title='費用細節', text='收費與折扣', actions=[
                    MessageAction(label='不接受議價', text='規範:不接受議價'),
                    MessageAction(label='接受轉帳', text='規範:接受轉帳'),
                    MessageAction(label='自備零錢', text='規範:自備零錢')
                ]),
                CarouselColumn(title='特別減免', text='公益與身分', actions=[
                    MessageAction(label='學生/低收減免', text='規範:學生低收減免'),
                    MessageAction(label='捐款抵費用', text='規範:捐款抵費用'),
                    MessageAction(label='寵物免收費', text='規範:寵物免收費')
                ])
            ]
        elif cat == "環境":
            cols = [
                CarouselColumn(title='車內環境', text='氣味與規範', actions=[
                    MessageAction(label='全程禁菸酒', text='規範:全程禁菸酒'),
                    MessageAction(label='無菸無檳榔駕駛', text='規範:無菸無檳榔'),
                    MessageAction(label='車內乾淨', text='規範:車內乾淨')
                ]),
                CarouselColumn(title='駕駛安全', text='行車風格', actions=[
                    MessageAction(label='拒絕超速', text='規範:拒絕超速'),
                    MessageAction(label='無快車駕駛', text='規範:無快車駕駛'),
                    MessageAction(label='投保乘客險', text='規範:投保乘客險')
                ])
            ]
        elif cat == "氛圍":
            cols = [
                CarouselColumn(title='乘車氛圍', text='社交互動', actions=[
                    MessageAction(label='可聊天', text='規範:可聊天'),
                    MessageAction(label='不聊天', text='規範:不聊天'),
                    MessageAction(label='可睡覺聽音樂', text='規範:可睡覺聽音樂')
                ]),
                CarouselColumn(title='長期/其他', text='特殊需求', actions=[
                    MessageAction(label='長期通勤需求', text='規範:長期通勤'),
                    MessageAction(label='後座僅坐2人', text='規範:後座僅坐2人'),
                    MessageAction(label='無不良坐姿', text='規範:無不良坐姿')
                ])
            ]
        
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='選擇規範', template=CarouselTemplate(columns=cols)))

    # F. 標籤選擇完成 -> 彈回分類選單
    elif msg.startswith("規範:"):
        pref = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('SELECT temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        p_str = cursor.fetchone()[0] or ""
        if pref not in p_str:
            p_str += f"{pref}, "
            cursor.execute('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?', (p_str, user_id))
            conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu(f"✅ 已選：{pref}\n標籤清單：{p_str}\n"))

    # G. 最終發布
    elif msg == "最終確認發布":
        conn = sqlite3.connect('ridematch_v7.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_city, temp_dist, temp_flex, temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        if res:
            ut, tt, ct, dt, fx, ps = res
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, city, district, flexible, prefs) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                           (user_id, ut, tt, ct, dt, fx, ps))
            conn.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🚀 專業行程發布成功！\n\n身分：{ut}\n時間：{tt.replace('T', ' ')}\n路線：{ct}{dt}\n彈性：{fx}\n標籤：{ps}\n\n正在為您搜尋標籤符合度最高的對象..."))
        conn.close()

if __name__ == "__main__":
    app.run()
