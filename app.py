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

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 1. 資料庫初始化 (v13) ---
def init_db():
    conn = sqlite3.connect('ridematch_v13.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, 
         s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, 
         way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
        (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, 
         s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, 
         temp_way TEXT, temp_count TEXT, temp_fee TEXT,
         temp_flex TEXT, temp_prefs TEXT, step TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. 數據定義 ---
CITY_DATA = {
    "北部": ["台北市", "新北市", "基隆市", "桃園市", "新竹縣", "新竹市"],
    "中部": ["苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣"],
    "南部": ["嘉義縣", "嘉義市", "台南市", "高雄市", "屏東縣"],
    "東部": ["宜蘭縣", "花蓮縣", "台東縣"]
}

DISTRICT_DATA = {
    "台北市": ["信義區", "大安區", "內湖區", "北投區", "中正區", "萬華區", "中山區", "松山區", "大同區", "南港區", "文山區", "士林區"],
    "新北市": ["板橋區", "三重區", "中和區", "永和區", "新莊區", "淡水區", "新店區", "土城區", "蘆洲區", "汐止區", "樹林區", "五股區", "泰山區"],
    "基隆市": ["仁愛區", "信義區", "中正區", "中山區", "安樂區", "暖暖區", "七堵區"],
    "桃園市": ["桃園區", "中壢區", "平鎮區", "八德區", "楊梅區", "蘆竹區", "龜山區", "龍潭區", "大溪區", "觀音區", "新屋區"],
    "新竹市": ["東區", "北區", "香山區"],
    "新竹縣": ["竹北市", "竹東鎮", "新埔鎮", "關西鎮", "湖口鄉", "新豐鄉", "芎林鄉", "寶山鄉"],
    "苗栗縣": ["苗栗市", "頭份市", "竹南鎮", "後龍鎮", "通霄鎮", "苑裡鎮", "公館鄉"],
    "台中市": ["西屯區", "北屯區", "南屯區", "東區", "南區", "西區", "北區", "大里區", "太平區", "豐原區", "沙鹿區", "清水區"],
    "彰化縣": ["彰化市", "員林市", "和美鎮", "鹿港鎮", "溪湖鎮", "二林鎮", "福興鄉", "花壇鄉"],
    "南投縣": ["南投市", "埔里鎮", "草屯鎮", "竹山鎮", "集集鎮", "名間鄉"],
    "雲林縣": ["斗六市", "虎尾鎮", "西螺鎮", "土庫鎮", "北港鎮", "古坑鄉"],
    "嘉義市": ["東區", "西區"],
    "嘉義縣": ["太保市", "朴子市", "布袋鎮", "大林鎮", "民雄鄉", "水上鄉"],
    "台南市": ["永康區", "安南區", "東區", "北區", "南區", "安平區", "中西區", "仁德區", "歸仁區"],
    "高雄市": ["左營區", "三民區", "鳳山區", "楠梓區", "前鎮區", "苓雅區", "鼓山區", "小港區", "新興區", "旗山區", "岡山區"],
    "屏東縣": ["屏東市", "潮州鎮", "東港鎮", "恆春鎮", "萬丹鄉", "內埔鄉"],
    "宜蘭縣": ["宜蘭市", "羅東鎮", "蘇澳鎮", "頭城鎮", "礁溪鄉", "冬山鄉", "五結鄉"],
    "花蓮縣": ["花蓮市", "鳳林鎮", "玉里鎮", "新城鄉", "吉安鄉", "壽豐鄉"],
    "台東縣": ["台東市", "成功鎮", "關山鎮", "卑南鄉", "鹿野鄉"]
}

# --- 3. 輔助工具 ---
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
        CarouselColumn(title=title, text='台灣地區', actions=[
            MessageAction(label='北部', text='區域:北部'),
            MessageAction(label='中部', text='區域:中部'),
            MessageAction(label='南部', text='區域:南部')
        ]),
        CarouselColumn(title=title, text='其餘地區', actions=[
            MessageAction(label='東部', text='區域:東部'),
            MessageAction(label='重新開始', text='我要載客/貨'),
            MessageAction(label='略過直接發布', text='最終確認發布')
        ])
    ]))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
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
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_time = ?, step = "START" WHERE user_id = ?', (t, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_area_carousel("📍 第一步：選擇【出發地】區域"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id

    # A. 啟動
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect('ridematch_v13.db')
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
        cities = CITY_DATA.get(area, [])
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已選 {area}，請選縣市：", quick_reply=QuickReply(items=btns)))

    # C. 縣市 -> 行政區
    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('SELECT step FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        step = res[0] if res else "START"
        if step == "START":
            cursor.execute('UPDATE user_state SET s_city = ? WHERE user_id = ?', (c, user_id))
        else:
            cursor.execute('UPDATE user_state SET e_city = ? WHERE user_id = ?', (c, user_id))
        conn.commit()
        conn.close()
        dists = DISTRICT_DATA.get(c, ["市中心"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"區:{d}")) for d in dists[:13]]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    # D. 行政區 -> 下一步 (判斷是要選目的地還是選中途)
    elif msg.startswith("區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('SELECT step FROM user_state WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        step = res[0] if res else "START"
        if step == "START":
            cursor.execute('UPDATE user_state SET s_dist = ?, step = "END" WHERE user_id = ?', (d, user_id))
            conn.commit()
            conn.close()
            line_bot_api.reply_message(event.reply_token, get_area_carousel("🏁 第二步：選擇【目的地】區域"))
        else:
            cursor.execute('UPDATE user_state SET e_dist = ? WHERE user_id = ?', (d, user_id))
            conn.commit()
            conn.close()
            btns = [
                QuickReplyButton(action=MessageAction(label="✅ 接受中途", text="中途:接受")),
                QuickReplyButton(action=MessageAction(label="❌ 僅限起迄", text="中途:不接受")),
                QuickReplyButton(action=MessageAction(label="🛣️ 交流道可", text="中途:限交流道"))
            ]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否接受中途上下車？", quick_reply=QuickReply(items=btns)))

    # E. 中途 -> 人數
    elif msg.startswith("中途:"):
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_way = ? WHERE user_id = ?', (msg.split(":")[1], user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label=f"{i}人", text=f"人數:{i}")) for i in range(1, 5)]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請選擇人數：", quick_reply=QuickReply(items=btns)))

    # F. 人數 -> 費用
    elif msg.startswith("人數:"):
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_count = ? WHERE user_id = ?', (msg.split(":")[1], user_id))
        conn.commit()
        conn.close()
        btns = [
            QuickReplyButton(action=MessageAction(label="💰 私訊議價", text="費用:私訊議價")),
            QuickReplyButton(action=MessageAction(label="☕ 咖啡飲料", text="費用:請喝飲料")),
            QuickReplyButton(action=MessageAction(label="💵 固定金額", text="費用:面議/固定")),
            QuickReplyButton(action=MessageAction(label="🆓 免費公益", text="費用:免費"))
        ]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="分攤方式：", quick_reply=QuickReply(items=btns)))

    # G. 費用 -> 彈性
    elif msg.startswith("費用:"):
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_fee = ? WHERE user_id = ?', (msg.split(":")[1], user_id))
        conn.commit()
        conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意")), QuickReplyButton(action=MessageAction(label="不彈性", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="起終點設定完成！是否願意彈性比對？", quick_reply=QuickReply(items=btns)))

    # H. 彈性 -> 選單
    elif msg.startswith("彈性:"):
        f = msg.split(":")[1]
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (f, user_id))
        conn.commit()
        conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu("最後一步：自定義規範。"))

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
        conn = sqlite3.connect('ridematch_v13.db')
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

    # I. 最終發布
    elif msg == "最終確認發布":
        conn = sqlite3.connect('ridematch_v13.db')
        cursor = conn.cursor()
        cursor.execute('''SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, 
                          temp_way, temp_count, temp_fee, temp_flex, temp_prefs 
                          FROM user_state WHERE user_id = ?''', (user_id,))
        res = cursor.fetchone()
        if res:
            # 這裡總共 11 個欄位，對應 SQL 的 11 個問號
            cursor.execute('''INSERT INTO matches 
                (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (user_id, *res))
            conn.commit()
            ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps = res
            summary = (
                f"✨ 【共乘發布成功】 ✨\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 身分：{'🚗 司機' if ut=='driver' else '🙋 乘客'}\n"
                f"📅 時間：{tt}\n"
                f"📍 起點：{sc}{sd}\n"
                f"🏁 終點：{ec}{ed}\n"
                f"🛣️ 中途：{wy}\n"
                f"👥 人數：{pc} 人\n"
                f"💰 費用：{fe}\n"
                f"📝 規範：{ps if ps else '無'}\n"
                f"⚙️ 彈性：{fx}"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=summary))
        conn.close()

if __name__ == "__main__":
    app.run()
