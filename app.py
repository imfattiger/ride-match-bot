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

# --- API 設定 ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 資料庫初始化 (統一使用 v10) ---
def init_db():
    conn = sqlite3.connect('ridematch_v10.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         city TEXT, district TEXT, flexible TEXT, prefs TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, temp_city TEXT, temp_dist TEXT, temp_flex TEXT, temp_prefs TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 全台縣市與行政區數據 ---
CITY_DATA = {
    "北部": ["台北市", "新北市", "基隆市", "桃園市", "新竹縣", "新竹市"],
    "中部": ["苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣"],
    "南部": ["嘉義縣", "嘉義市", "台南市", "高雄市", "屏東縣"],
    "東部": ["宜蘭縣", "花蓮縣", "台東縣"]
}

DISTRICT_DATA = {
    "台北市": ["信義區", "大安區", "內湖區", "北投區", "中正區", "萬華區", "中山區", "松山區", "大同區", "南港區", "文山區", "士林區"],
    "新北市": ["板橋區", "三重區", "中和區", "永和區", "新莊區", "淡水區", "新店區", "土城區", "蘆洲區", "汐止區", "樹林區"],
    "桃園市": ["桃園區", "中壢區", "平鎮區", "八德區", "楊梅區", "蘆竹區", "龜山區", "龍潭區", "大溪區", "觀音區"],
    "台中市": ["西屯區", "北屯區", "南屯區", "東區", "南區", "西區", "北區", "大里區", "太平區", "豐原區", "沙鹿區"],
    "高雄市": ["左營區", "三民區", "新興區", "前鎮區", "苓雅區", "鼓山區", "鳳山區", "楠梓區", "小港區", "左營區"]
    # 其餘縣市可依此類推增加
}

# --- 輔助函數：主選單 ---
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

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == "select_time":
        t = event.postback.params['datetime']
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ? WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        
        cols = [
            CarouselColumn(title='🗺️ 出發地點', text='請選擇區域', actions=[
                MessageAction(label='北部 (北北基桃竹)', text='區域:北部'),
                MessageAction(label='中部 (苗中彰投雲)', text='區域:中部'),
                MessageAction(label='南部 (嘉南高屏)', text='區域:南部')
            ]),
            CarouselColumn(title='🗺️ 出發地點', text='其他區域', actions=[
                MessageAction(label='東部 (宜花東)', text='區域:東部'),
                MessageAction(label='離島', text='區域:離島'),
                MessageAction(label='重新選擇時間', text='我要載客/貨')
            ])
        ]
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='選擇地區', template=CarouselTemplate(columns=cols)))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 啟動
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_prefs) VALUES (?, ?, ?)', (user_id, ut, ""))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選擇日期時間：",
            quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))])
        ))

    # B. 區域 -> 縣市
    elif msg.startswith("區域:"):
        area = msg.split(":")[1]
        cities = CITY_DATA.get(area, ["台北市"])
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已選 {area}，請選擇縣市：", quick_reply=QuickReply(items=btns)))

    # C. 縣市 -> 行政區
    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_city = ? WHERE user_id = ?', (c, user_id))
        conn.commit()
        conn.close()
        dists = DISTRICT_DATA.get(c, ["市中心"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"行政區:{d}")) for d in dists[:13]]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    # D. 行政區 -> 彈性
    elif msg.startswith("行政區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_dist = ? WHERE user_id = ?', (d, user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對？", quick_reply=QuickReply(items=btns)))

    # E. 彈性 -> 選單
    elif msg.startswith("彈性:"):
        f = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (f, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu("最後一步：自定義規範。\n"))

    # F. 規範大類展示 (Carousel)
    elif msg.startswith("類別:"):
        cat = msg.split(":")[1]
        cols = []
        if cat == "行程":
            cols = [
                CarouselColumn(title='行程規範(1)', text='服務與討論', actions=[
                    MessageAction(label='提供包裹服務', text='規範:提供包裹服務'),
                    MessageAction(label='上下車可討論', text='規範:上下車可討論'),
                    MessageAction(label='順路為主', text='規範:順路為主')
                ]),
                CarouselColumn(title='行程規範(2)', text='目的與寵物', actions=[
                    MessageAction(label='可以送至目的地', text='規範:可以送至目的地'),
                    MessageAction(label='可停等休息站', text='規範:可停等休息站'),
                    MessageAction(label='寵物需裝籠', text='規範:寵物需裝籠')
                ]),
                CarouselColumn(title='行程規範(3)', text='駕駛安排', actions=[
                    MessageAction(label='不接受指定時間', text='規範:不接受指定時間'),
                    MessageAction(label='依照駕駛安排座', text='規範:依照駕駛安排座'),
                    MessageAction(label='依照駕駛路線', text='規範:依照駕駛路線')
                ]),
                CarouselColumn(title='行程規範(4)', text='其他限制', actions=[
                    MessageAction(label='謝絕寵物', text='規範:謝絕寵物'),
                    MessageAction(label='大型行李告知', text='規範:大型行李告知'),
                    MessageAction(label='務必準時', text='規範:務必準時')
                ])
            ]
        elif cat == "費用":
            cols = [
                CarouselColumn(title='費用細節', text='付款與議價', actions=[
                    MessageAction(label='不接受議價', text='規範:不接受議價'),
                    MessageAction(label='接受轉帳', text='規範:接受轉帳'),
                    MessageAction(label='自備零錢', text='規範:自備零錢')
                ]),
                CarouselColumn(title='優惠減免', text='公益與身分', actions=[
                    MessageAction(label='學生低收減免', text='規範:學生低收減免'),
                    MessageAction(label='捐款抵費用', text='規範:捐款抵費用'),
                    MessageAction(label='寵物免收費', text='規範:寵物免收費')
                ])
            ]
        elif cat == "環境":
            cols = [
                CarouselColumn(title='環境(1)', text='菸酒與整潔', actions=[
                    MessageAction(label='全程禁菸酒', text='規範:全程禁菸酒'),
                    MessageAction(label='無菸無檳榔', text='規範:無菸無檳榔'),
                    MessageAction(label='車內乾淨', text='規範:車內乾淨')
                ]),
                CarouselColumn(title='環境(2)', text='飲食與防疫', actions=[
                    MessageAction(label='口罩可飲水', text='規範:口罩可飲水'),
                    MessageAction(label='禁食', text='規範:禁食'),
                    MessageAction(label='消毒自備', text='規範:消毒自備')
                ]),
                CarouselColumn(title='環境(3)', text='行李寵物', actions=[
                    MessageAction(label='有大型行李箱', text='規範:大型行李箱'),
                    MessageAction(label='寵物推車提籠', text='規範:寵物推車提籠'),
                    MessageAction(label='寵物酌收費', text='規範:寵物酌收費')
                ]),
                CarouselColumn(title='安全', text='行車風格', actions=[
                    MessageAction(label='拒絕超速', text='規範:拒絕超速'),
                    MessageAction(label='無快車駕駛', text='規範:無快車駕駛'),
                    MessageAction(label='投保乘客險', text='規範:投保乘客險')
                ])
            ]
        elif cat == "氛圍":
            cols = [
                CarouselColumn(title='氛圍', text='社交互動', actions=[
                    MessageAction(label='可聊天', text='規範:可聊天'),
                    MessageAction(label='不聊天', text='規範:不聊天'),
                    MessageAction(label='可睡覺聽歌', text='規範:可睡覺聽歌')
                ]),
                CarouselColumn(title='特殊', text='需求與長期', actions=[
                    MessageAction(label='長期通勤', text='規範:長期通勤'),
                    MessageAction(label='後座限2人', text='規範:後座限2人'),
                    MessageAction(label='無不良坐姿', text='規範:無不良坐姿')
                ])
            ]
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='選擇規範', template=CarouselTemplate(columns=cols)))

    # G. 儲存標籤並循環
    elif msg.startswith("規範:"):
        pref = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('SELECT temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        p_str = res[0] if res and res[0] else ""
        if pref not in p_str:
            p_str += f"{pref}, "
            cursor.execute('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?', (p_str, user_id))
            conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu(f"✅ 已選：{pref}\n標籤：{p_str}\n"))

    # H. 最終發布
    elif msg == "最終確認發布":
        conn = sqlite3.connect('ridematch_v10.db')
        cursor = conn.cursor()
        cursor.execute('SELECT current_type, temp_time, temp_city, temp_dist, temp_flex, temp_prefs FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        if res:
            ut, tt, ct, dt, fx, ps = res
            cursor.execute('INSERT INTO matches (user_id, user_type, time_info, city, district, flexible, prefs) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                           (user_id, ut, tt, ct, dt, fx, ps))
            conn.commit()
            summary = f"🚀 發布成功！\n身分：{ut}\n時間：{tt}\n路線：{ct}{dt}\n標籤：{ps}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=summary))
        conn.close()

if __name__ == "__main__":
    app.run()
