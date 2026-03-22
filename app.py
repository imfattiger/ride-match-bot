import os
import sqlite3
import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qsl
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction,FlexSendMessage,
    DatetimePickerAction, PostbackEvent,PostbackAction,
    TemplateSendMessage, CarouselTemplate, CarouselColumn
)

# 啟動紀錄模式
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# --- 1. 基礎設定與環境變數 ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 全台灣行政區數據 (完整版) ---
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

CITY_WEIGHTS = {
    "基隆市": 1, "台北市": 2, "新北市": 3, "桃園市": 4, "新竹縣": 5, "新竹市": 5, 
    "苗栗縣": 6, "台中市": 7, "彰化縣": 8, "南投縣": 9, "雲林縣": 10, "嘉義縣": 11, 
    "嘉義市": 11, "台南市": 12, "高雄市": 13, "屏東縣": 14, "宜蘭縣": 15, "花蓮縣": 16, "台東縣": 17
}

# --- 3. 資料庫與清理機制 ---
DB_NAME = 'ridematch_v15.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_state (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, temp_way TEXT, temp_count TEXT, temp_fee TEXT, temp_flex TEXT, temp_prefs TEXT, step TEXT)''')
    conn.commit()
    conn.close()

def clean_expired_matches():
    try:
        conn = sqlite3.connect(DB_NAME)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        conn.execute('DELETE FROM matches WHERE time_info < ?', (yesterday,))
        conn.commit(); conn.close()
    except: pass

init_db()
def get_publish_confirm_flex(res_data, match_id):
    ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps = res_data
    main_color = "#00b900" if ut == 'driver' else "#1e90ff" # 司機綠/乘客藍
    
    bubble = {
      "type": "bubble",
      "header": {
        "type": "box", "layout": "vertical", "contents": [
          {"type": "text", "text": "✨ 行程發布成功", "weight": "bold", "color": "#FFFFFF", "size": "sm"}
        ], "backgroundColor": main_color
      },
      "body": {
        "type": "box", "layout": "vertical", "contents": [
          {"type": "text", "text": f"{'🚗 載客模式' if ut=='driver' else '🙋 搭車模式'}", "weight": "bold", "size": "xl", "margin": "md"},
          {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
              {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
              {"type": "text", "text": tt.replace("T", " "), "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
            ]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
              {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 1},
              {"type": "text", "text": f"{sc}{sd} ➔ {ec}{ed}", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
            ]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
              {"type": "text", "text": "詳情", "color": "#aaaaaa", "size": "sm", "flex": 1},
              {"type": "text", "text": f"{pc}人 | {fe} | {wy}", "wrap": True, "color": "#666666", "size": "sm", "flex": 5}
            ]}
          ]}
        ]
      },
      "footer": {
        "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
          {"type": "button", "style": "link", "height": "sm", "action": {
            "type": "postback", "label": "❌ 撤回/刪除此行程", "data": f"action=delete&id={match_id}"
          }, "color": "#ff4b4b"}
        ]
      }
    }
    return FlexSendMessage(alt_text="行程發布成功", contents=bubble)
# --- 4. 輔助工具介面 ---
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

# --- 5. 核心匹配演算法 (結合權重與彈性時間) ---
def find_matches_v15(user_id, utype, t_info, sc, sd, ec, ed, flex, way_point, p_count):
    target_type = 'seeker' if utype == 'driver' else 'driver'
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. 時間彈性計算
    try:
        base_t = datetime.strptime(t_info, "%Y-%m-%dT%H:%M")
        buffer = 4 if "願意" in flex else 1
        s_range = (base_t - timedelta(hours=buffer)).strftime("%Y-%m-%dT%H:%M")
        e_range = (base_t + timedelta(hours=buffer)).strftime("%Y-%m-%dT%H:%M")
    except:
        s_range, e_range = t_info, t_info

    # 2. 方向性與權重
    s_w, e_w = CITY_WEIGHTS.get(sc, 0), CITY_WEIGHTS.get(ec, 0)
    user_direction = 1 if e_w > s_w else (-1 if e_w < s_w else 0)
    
    # 3. 基礎查詢 (類型、時間、非本人)
    query = "SELECT user_id, time_info, s_city, s_dist, e_city, e_dist, fee, way_point, p_count FROM matches WHERE user_type = ? AND user_id != ? AND time_info BETWEEN ? AND ?"
    params = [target_type, user_id, s_range, e_range]
    
    c.execute(query, params)
    raw_res = c.fetchall()
    
    final_matches = []
    user_p = int(p_count) # 當前發布者的人數需求/供給

    for m in raw_res:
        m_uid, m_time, m_sc, m_sd, m_ec, m_ed, m_fee, m_way, m_pc = m
        m_s_w, m_e_w = CITY_WEIGHTS.get(m_sc, 0), CITY_WEIGHTS.get(m_ec, 0)
        match_direction = 1 if m_e_w > m_s_w else (-1 if m_e_w < m_s_w else 0)
        match_p = int(m_pc)

        # A. 方向檢查：必須同向
        if user_direction != match_direction:
            continue
            
        # B. 人數檢查：如果是司機發布，找人少的乘客；如果是乘客發布，找人多的司機
        if utype == 'driver' and user_p < match_p: continue # 司機位子不夠
        if utype == 'seeker' and user_p > match_p: continue # 司機位子不夠

        # C. 站點檢查 (包含中途邏輯)
        # 司機 = D, 乘客 = S
        is_match = False
        if utype == 'driver':
            d_s_w, d_e_w = s_w, e_w
            s_s_w, s_e_w = m_s_w, m_e_w
            d_way = way_point
        else:
            d_s_w, d_e_w = m_s_w, m_e_w
            s_s_w, s_e_w = s_w, e_w
            d_way = m_way

        # 如果司機接受中途：乘客的起迄權重必須在司機權重範圍內
        if "接受" in d_way:
            if user_direction == 1: # 南下 (權重增加)
                if d_s_w <= s_s_w and s_e_w <= d_e_w: is_match = True
            else: # 北上 (權重減少)
                if d_s_w >= s_s_w and s_e_w >= d_e_w: is_match = True
        else:
            # 不接受中途：起訖縣市必須完全一樣
            if sc == m_sc and ec == m_ec: is_match = True
        
        if is_match:
            final_matches.append(m)
            
    conn.close()
    return final_matches[:5]
    
    # 4. 【核心升級】過濾掉「反方向」的行程
    final_matches = []
    for m in raw_res:
        m_s_w, m_e_w = CITY_WEIGHTS.get(m[2], 0), CITY_WEIGHTS.get(m[4], 0)
        match_direction = 1 if m_e_w > m_s_w else (-1 if m_e_w < m_s_w else 0)
        
        # 只有方向相同 (或者都是同縣市) 才加入匹配清單
        if user_direction == match_direction:
            final_matches.append(m)
            
    conn.close()
    return final_matches[:5] # 回傳前 5 筆
# --- 6. 事件流程處理 ---

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return 'OK'

@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    # --- 關鍵修正：先定義 data 變數 ---
    data = event.postback.data 
    
    if data == "select_time":
        t = event.postback.params['datetime']
        conn = sqlite3.connect(DB_NAME)
        conn.execute('UPDATE user_state SET temp_time = ?, step = "START" WHERE user_id = ?', (t, uid))
        conn.commit(); conn.close()
        line_bot_api.reply_message(event.reply_token, get_area_carousel("📍 第一步：選擇【出發地】區域"))
        
    # --- 這裡原本因為找不到 data 會報錯，現在修好了 ---
    elif data.startswith("action=delete"):
        # 解析 data 內容
        params = dict(parse_qsl(data))
        match_id = params.get('id')
        
        conn = sqlite3.connect(DB_NAME)
        # 安全檢查：同時比對 id 與 user_id
        conn.execute('DELETE FROM matches WHERE id = ? AND user_id = ?', (match_id, uid))
        conn.commit(); conn.close()
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 已成功刪除行程 (編號: {match_id})"))
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    uid = event.source.user_id

    if msg == "我的行程":
        conn = sqlite3.connect(DB_NAME)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        # 找出該用戶尚未過期的行程
        my_matches = conn.execute(
            'SELECT id, time_info, s_city, s_dist, e_city, e_dist, user_type FROM matches WHERE user_id = ? AND time_info >= ? ORDER BY time_info ASC LIMIT 10', 
            (uid, now)
        ).fetchall()
        conn.close()

        if not my_matches:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 您目前沒有生效中的行程。"))
        else:
            cols = []
            for m in my_matches:
                m_id, t_info, sc, sd, ec, ed, utype = m
                role = "🚗 載客/貨" if utype == 'driver' else "🙋 搭車/寄物"
                cols.append(CarouselColumn(
                    title=f"{role} | {t_info[5:16]}",
                    text=f"📍 {sc}{sd} ➔ {ec}{ed}",
                    actions=[
                        PostbackAction(label='❌ 刪除此行程', data=f"action=delete&id={m_id}")
                    ]
                ))
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text="📋 以下是您的近期行程："),
                TemplateSendMessage(alt_text="行程管理", template=CarouselTemplate(columns=cols))
            ])
        return # 處理完「我的行程」就結束，不用跑後面的邏輯

    elif msg == "媒合規則":
        rules = (
            "⚖️ 【媒合規則說明】\n\n"
            "1. 時段匹配：根據您的彈性選擇，搜尋前後 1~4 小時內的行程。\n"
            "2. 路線匹配：起訖點縣市必須一致。司機若開啟「接受中途」，系統會增加媒合機會。\n"
            "3. 自動通知：新行程符合條件時，系統會主動推播通知雙方。\n"
            "4. 過期機制：行程時間超過 24 小時後將自動隱藏。"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=rules))
        return

    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        clean_expired_matches()
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = sqlite3.connect(DB_NAME)
        conn.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_prefs) VALUES (?, ?, ?)', (uid, ut, ""))
        conn.commit(); conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🕒 請選擇日期時間：", quick_reply=QuickReply(items=[QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))])))

    elif msg.startswith("區域:"):
        area = msg.split(":")[1]
        cities = CITY_DATA.get(area, [])
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已選 {area}，請選擇縣市：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = sqlite3.connect(DB_NAME); res = conn.execute('SELECT step FROM user_state WHERE user_id = ?', (uid,)).fetchone()
        step = res[0] if res else "START"
        col = "s_city" if step == "START" else "e_city"
        conn.execute(f'UPDATE user_state SET {col} = ? WHERE user_id = ?', (c, uid))
        conn.commit(); conn.close()
        dists = DISTRICT_DATA.get(c, ["市中心"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"區:{d}")) for d in dists[:13]]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("區:"):
        d = msg.split(":")[1]
        conn = sqlite3.connect(DB_NAME); res = conn.execute('SELECT step FROM user_state WHERE user_id = ?', (uid,)).fetchone()
        step = res[0] if res else "START"
        if step == "START":
            conn.execute('UPDATE user_state SET s_dist = ?, step = "END" WHERE user_id = ?', (d, uid))
            conn.commit(); conn.close()
            line_bot_api.reply_message(event.reply_token, get_area_carousel("🏁 第二步：選擇【目的地】區域"))
        else:
            conn.execute('UPDATE user_state SET e_dist = ? WHERE user_id = ?', (d, uid))
            conn.commit(); conn.close()
            btns = [
                QuickReplyButton(action=MessageAction(label="✅ 接受中途", text="中途:接受")),
                QuickReplyButton(action=MessageAction(label="❌ 僅限起迄", text="中途:僅限起迄")),
                QuickReplyButton(action=MessageAction(label="🛣️ 交流道可", text="中途:限交流道"))
            ]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否接受中途上下車？", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("中途:"):
        conn = sqlite3.connect(DB_NAME); conn.execute('UPDATE user_state SET temp_way = ? WHERE user_id = ?', (msg.split(":")[1], uid)); conn.commit(); conn.close()
        btns = [QuickReplyButton(action=MessageAction(label=f"{i}人", text=f"人數:{i}")) for i in range(1, 5)]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請選擇人數：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("人數:"):
        conn = sqlite3.connect(DB_NAME); conn.execute('UPDATE user_state SET temp_count = ? WHERE user_id = ?', (msg.split(":")[1], uid)); conn.commit(); conn.close()
        btns = [
            QuickReplyButton(action=MessageAction(label="💰 私訊議價", text="費用:私訊議價")),
            QuickReplyButton(action=MessageAction(label="☕ 咖啡飲料", text="費用:請喝飲料")),
            QuickReplyButton(action=MessageAction(label="💵 固定金額", text="費用:固定金額")),
            QuickReplyButton(action=MessageAction(label="🆓 免費公益", text="費用:免費公益"))
        ]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="分攤方式：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("費用:"):
        conn = sqlite3.connect(DB_NAME); conn.execute('UPDATE user_state SET temp_fee = ? WHERE user_id = ?', (msg.split(":")[1], uid)); conn.commit(); conn.close()
        btns = [QuickReplyButton(action=MessageAction(label="願意彈性", text="彈性:願意彈性")), QuickReplyButton(action=MessageAction(label="不願意", text="彈性:不願意"))]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="是否願意彈性比對時間(±4hr)？", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("彈性:"):
        conn = sqlite3.connect(DB_NAME); conn.execute('UPDATE user_state SET temp_flex = ? WHERE user_id = ?', (msg.split(":")[1], uid)); conn.commit(); conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu("最後一步：自定義規範。"))

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

    elif msg.startswith("規範:"):
        p = msg.split(":")[1]
        conn = sqlite3.connect(DB_NAME); res = conn.execute('SELECT temp_prefs FROM user_state WHERE user_id = ?', (uid,)).fetchone()
        p_str = (res[0] if res and res[0] else "") + f"{p}, "
        conn.execute('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?', (p_str, uid))
        conn.commit(); conn.close()
        line_bot_api.reply_message(event.reply_token, get_main_cat_menu(f"✅ 已選：{p}\n目前標籤：{p_str}"))

    elif msg == "最終確認發布":
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute('SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs FROM user_state WHERE user_id = ?', (uid,)).fetchone()
        
        if not res: 
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 找不到暫存資料，請重新開始。"))
            return
            
        # 1. 存入正式表並取得自動生成的 ID
        cursor = conn.cursor()
        cursor.execute('INSERT INTO matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (uid, *res))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 2. 執行強化後的匹配邏輯 (注意這裡傳入了最後一個參數 pc)
        ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps = res
        m_list = find_matches_v15(uid, ut, tt, sc, sd, ec, ed, fx, wy, pc) # <--- 修改這行
        
        # 3. 準備回覆內容
        # 第一個回覆：專業的 Flex 卡片
        output = [get_publish_confirm_flex(res, new_id)]
        
        # 第二個回覆：匹配結果
        if m_list:
            match_text = "🎯 偵測到同向匹配！\n"
            for m in m_list:
                match_text += f"━━━━━━━━━━━━━━━\n🕙 {m[1][5:16]}\n📍 {m[2]}{m[3]} ➔ {m[4]}{m[5]}\n💰 {m[6]}\n"
                # 通知對方 (這裡也可以考慮換成卡片，我們先用簡潔文字)
                try:
                    line_bot_api.push_message(m[0], TextSendMessage(text=f"🔔 順路通知！\n有人發布了與您方向相同的行程：\n{sc}{sd} ➔ {ec}{ed}\n趕快點擊「我的行程」查看詳情！"))
                except: pass
            output.append(TextSendMessage(text=match_text))
        else:
            output.append(TextSendMessage(text="🔎 目前暫無同向行程，系統將持續監控。"))
            
        line_bot_api.reply_message(event.reply_token, output)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
