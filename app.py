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

# --- 資料庫初始化 (統一使用 v11) ---
def init_db():
    conn = sqlite3.connect('ridematch_v11.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         start_city TEXT, start_dist TEXT, end_city TEXT, end_dist TEXT, gender TEXT, flexible TEXT, prefs TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, 
         temp_scity TEXT, temp_sdist TEXT, temp_ecity TEXT, temp_edist TEXT, 
         temp_gender TEXT, temp_flex TEXT, temp_prefs TEXT, state_step TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 全台數據庫 (簡化顯示，完整邏輯已內建) ---
CITY_DATA = {
    "北部": ["台北市", "新北市", "基隆市", "桃園市", "新竹縣", "新竹市"],
    "中部": ["苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣"],
    "南部": ["嘉義縣", "嘉義市", "台南市", "高雄市", "屏東縣"],
    "東部": ["宜蘭縣", "花蓮縣", "台東縣"]
}

# 這裡我先幫你放入核心行政區，並教你系統如何自動處理「目的地」
DIST_DATA = {
    "台北市": ["信義區", "大安區", "內湖區", "北投區", "中正區", "萬華區", "中山區", "松山區", "大同區", "南港區", "文山區", "士林區"],
    "新北市": ["板橋區", "三重區", "中和區", "永和區", "新莊區", "淡水區", "新店區", "土城區", "蘆洲區", "汐止區", "樹林區"],
    "台中市": ["西屯區", "北屯區", "南屯區", "東區", "南區", "西區", "北區", "大里區", "太平區", "豐原區", "沙鹿區"],
    "桃園市": ["桃園區", "中壢區", "平鎮區", "八德區", "楊梅區", "蘆竹區", "龜山區", "龍潭區", "大溪區"],
    "高雄市": ["左營區", "三民區", "新興區", "前鎮區", "苓雅區", "鼓山區", "鳳山區", "楠梓區", "小港區", "鳳山區"]
    # 註：此處可補完 319 區，或當找不到時顯示「市中心/其他」
}

def get_main_cat_menu(text_prefix=""):
    items = [
        QuickReplyButton(action=MessageAction(label="🚗 行程/地點", text="類別:行程")),
        QuickReplyButton(action=MessageAction(label="💰 費用相關", text="類別:費用")),
        QuickReplyButton(action=MessageAction(label="🚬 環境規範", text="類別:環境")),
        QuickReplyButton(action=MessageAction(label="💬 乘車氛圍", text="類別:氛圍")),
        QuickReplyButton(action=MessageAction(label="🚀 全部選好，發布！", text="最終確認發布"))
    ]
    return TextSendMessage(text=f"{text_prefix}請選擇欲加入的標籤分類：", quick_reply=QuickReply(items=items))

def get_area_carousel(title="請選擇區域"):
    return TemplateSendMessage(alt_text=title, template=CarouselTemplate(columns=[
        CarouselColumn(title=title, text='台灣分區', actions=[
            MessageAction(label='北部 (北北基桃竹)', text='選區:北部'),
            MessageAction(label='中部 (苗中彰投雲)', text='選區:中部'),
            MessageAction(label='南部 (嘉南高屏)', text='選區:南部')
        ]),
        CarouselColumn(title=title, text='其他分區', actions=[
            MessageAction(label='東部 (宜花東)', text='選區:東部'),
            MessageAction(label='離島/重新選擇', text='我要載客/貨'),
            MessageAction(label='略過/回主選單', text="最終確認發布")
        ])
    ]))

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
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ?, state_step = "START_AREA" WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_area_carousel("📍 第一步：選擇【出發】區域"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # 1. 啟動與時間
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_prefs) VALUES (?, ?, ?)', (user_id, ut, ""))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請選擇出發日期時間：", quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))])))

    # 2. 地點選擇邏輯 (出發/目的地 循環)
    elif msg.startswith("選區:"):
        area = msg.split(":")[1]
        cities = CITY_DATA.get(area, ["台北市"])
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已選 {area}，請選擇具體縣市：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('SELECT state_step FROM user_state WHERE user_id = ?', (user_id,))
        step = cursor.fetchone()[0]
        if step == "START_AREA":
            cursor.execute('UPDATE user_state SET temp_scity = ? WHERE user_id = ?', (c, user_id))
        else:
            cursor.execute('UPDATE user_state SET temp_ecity = ? WHERE user_id = ?', (c, user_id))
        conn.commit()
        conn.close()
        dists = DIST_DATA.get(c, ["市中心", "全區", "其他"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"區:{d}")) for d in dists[:12]]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('SELECT state_step FROM user_state WHERE user_id = ?', (user_id,))
        step = cursor.fetchone()[0]
        if step == "START_AREA":
            cursor.execute('UPDATE user_state SET temp_sdist = ?, state_step = "END_AREA" WHERE user_id = ?', (d, user_id))
            conn.commit()
            conn.close()
            line_bot_api.reply_message(event.reply_token, get_area_carousel("🏁 第二步：選擇【目的地】區域"))
        else:
            cursor.execute('UPDATE user_state SET temp_edist = ? WHERE user_id = ?', (d, user_id))
            conn.commit()
            conn.close()
            # 選完目的地，進入性別選擇
            btns = [
                QuickReplyButton(action=MessageAction(label="🚺 限女性", text="性別:限女性")),
                QuickReplyButton(action=MessageAction(label="🚹 限男性", text="性別:限男性")),
                QuickReplyButton(action=MessageAction(label="🚻 不限性別", text="性別:不限"))
            ]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="第三步：請選擇對方的性別要求", quick_reply=QuickReply(items=btns)))

    # 3. 性別 -> 彈性
    elif msg.startswith("性別:"):
        g = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_gender = ? WHERE user_id = ?', (g, user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對？(容許時間地點微調)", quick_reply=QuickReply(items=btns)))

    # 4. 彈性 -> 標籤大類 (同之前邏輯)
    elif msg.startswith("彈性:"):
        f = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v11.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (f, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu("最後一步：設定標籤規範。\n"))

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
        conn = sqlite3.connect('ridematch_v11.db')
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
        conn = sqlite3.connect('ridematch_v11.db')
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
