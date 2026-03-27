import os
import sqlite3
import logging
import threading
import requests
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, quote
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction, FlexSendMessage,
    DatetimePickerAction, PostbackEvent, PostbackAction,
    TemplateSendMessage, CarouselTemplate, CarouselColumn,
    FollowEvent
)

# --- 1. 基礎設定 ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 全台灣行政區數據 ---
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

# --- 同縣市區域分群（Item 8）---
DISTRICT_GROUPS = {
    "台北市": {
        "東區": ["信義區", "大安區", "松山區", "南港區", "內湖區"],
        "中區": ["中正區", "中山區", "大同區", "萬華區"],
        "北區": ["北投區", "士林區"],
        "南區": ["文山區"]
    },
    "新北市": {
        "西北": ["三重區", "蘆洲區", "新莊區", "五股區", "泰山區"],
        "西南": ["板橋區", "中和區", "永和區", "土城區", "樹林區"],
        "東南": ["新店區"],
        "東北": ["汐止區", "淡水區"]
    },
    "台中市": {
        "市區": ["西屯區", "北屯區", "南屯區", "東區", "南區", "西區", "北區"],
        "外圍": ["大里區", "太平區", "豐原區", "沙鹿區", "清水區"]
    },
    "高雄市": {
        "北區": ["左營區", "楠梓區", "岡山區"],
        "中區": ["三民區", "鼓山區", "新興區"],
        "南區": ["前鎮區", "苓雅區", "小港區"],
        "東區": ["鳳山區"],
        "外圍": ["旗山區"]
    },
    "台南市": {
        "市區": ["東區", "北區", "南區", "中西區", "安平區"],
        "外圍": ["永康區", "安南區", "仁德區", "歸仁區"]
    }
}

def get_district_cluster(city, dist):
    groups = DISTRICT_GROUPS.get(city)
    if not groups:
        return dist
    for cluster_name, districts in groups.items():
        if dist in districts:
            return cluster_name
    return dist

# --- 3. 資料庫（支援 PostgreSQL + SQLite 雙模式）---
DB_NAME = 'ridematch_v15.db'
USE_PG = bool(os.getenv('DATABASE_URL'))

_pg_pool = None

if USE_PG:
    import psycopg2
    from psycopg2 import pool as _pg_pool_mod

def _ensure_pool():
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = _pg_pool_mod.ThreadedConnectionPool(1, 5, os.getenv('DATABASE_URL'))
    return _pg_pool

class _PGWrapper:
    """讓 psycopg2 connection 支援 sqlite3 的 conn.execute() 介面，並自動歸還連線池"""
    def __init__(self, conn, pool):
        self._conn = conn
        self._cur = None
        self._pool = pool

    def execute(self, sql, params=None):
        self._cur = self._conn.cursor()
        if params is not None:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        return self

    def fetchone(self):
        return self._cur.fetchone() if self._cur else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur else []

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._cur:
            try: self._cur.close()
            except: pass
        try: self._pool.putconn(self._conn)
        except: pass

    def cursor(self):
        return self._conn.cursor()

    @property
    def lastrowid(self):
        return self._cur.lastrowid if self._cur else None

def get_db():
    if USE_PG:
        pool = _ensure_pool()
        return _PGWrapper(pool.getconn(), pool)
    return sqlite3.connect(DB_NAME)

def q(sql):
    if USE_PG:
        return sql.replace('?', '%s')
    return sql

def init_db():
    conn = get_db()
    c = conn.cursor()
    if USE_PG:
        c.execute('''CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY, user_id TEXT, user_type TEXT, time_info TEXT,
            s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT,
            way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT,
            line_id TEXT DEFAULT '', status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT,
            s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT,
            temp_way TEXT, temp_count TEXT, temp_fee TEXT,
            temp_flex TEXT, temp_prefs TEXT, temp_line_id TEXT, step TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ratings (
            id SERIAL PRIMARY KEY, user_id TEXT, match_id INTEGER,
            score INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        # 遷移既有資料表
        for stmt in [
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS line_id TEXT DEFAULT ''",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
            "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS temp_line_id TEXT"
        ]:
            try: c.execute(stmt)
            except: pass
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT, line_id TEXT DEFAULT '', status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_state (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, temp_way TEXT, temp_count TEXT, temp_fee TEXT, temp_flex TEXT, temp_prefs TEXT, temp_line_id TEXT, step TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, match_id INTEGER, score INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        for col in ["line_id TEXT DEFAULT ''", "status TEXT DEFAULT 'active'"]:
            try: c.execute(f'ALTER TABLE matches ADD COLUMN {col}')
            except: pass
        try: c.execute('ALTER TABLE user_state ADD COLUMN temp_line_id TEXT')
        except: pass
    conn.commit()
    conn.close()

_last_clean_ts = 0

def clean_expired_matches():
    global _last_clean_ts
    if time.time() - _last_clean_ts < 300:  # 最多每 5 分鐘跑一次
        return
    _last_clean_ts = time.time()
    try:
        conn = get_db()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        conn.execute(q('DELETE FROM matches WHERE time_info < ?'), (yesterday,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Clean expired failed: {e}")

try:
    init_db()
except Exception as e:
    logging.error(f"init_db failed (app will retry on first request): {e}")

# --- 安全包裝 LINE API（Item 6）---
_log_store = []

def _store_log(tag, msg):
    _log_store.append({"time": datetime.now().isoformat(), "tag": tag, "msg": str(msg)})
    if len(_log_store) > 30:
        _log_store.pop(0)

def safe_reply(reply_token, messages):
    try:
        line_bot_api.reply_message(reply_token, messages)
        _store_log("reply_ok", f"token={reply_token[:10]}...")
    except Exception as e:
        logging.error(f"Reply failed: {e}")
        _store_log("reply_fail", str(e))

def safe_push(user_id, messages):
    try:
        line_bot_api.push_message(user_id, messages)
        _store_log("push_ok", f"uid={user_id[:10]}...")
    except Exception as e:
        logging.error(f"Push to {user_id} failed: {e}")
        _store_log("push_fail", str(e))

# --- 4. Flex 卡片建構 ---
def get_publish_confirm_flex(res_data, match_id):
    ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid = res_data
    main_color = "#00b900" if ut == 'driver' else "#1e90ff"
    ps_text = ps.strip().rstrip(",") if ps else "（未選）"
    share_text = f"🚗 共乘徵求！\n{sc}{sd} ➔ {ec}{ed}\n🕒 {tt.replace('T', ' ')}\n👤 {pc}人 | {fe}\n\n找順路旅伴就用 RideMatch"
    share_url = f"https://line.me/R/msg/text/?{quote(share_text)}"

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
            ]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
              {"type": "text", "text": "標籤", "color": "#aaaaaa", "size": "sm", "flex": 1},
              {"type": "text", "text": ps_text, "wrap": True, "color": "#aaaaaa", "size": "xs", "flex": 5}
            ]},
            {"type": "text", "text": "＊標籤僅供對方參考，不影響媒合", "size": "xxs", "color": "#cccccc", "margin": "sm", "wrap": True}
          ]}
        ]
      },
      "footer": {
        "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
          {"type": "button", "style": "primary", "height": "sm", "color": "#42659a", "action": {
            "type": "uri", "label": "📤 分享行程給朋友", "uri": share_url
          }},
          {"type": "button", "style": "link", "height": "sm", "action": {
            "type": "postback", "label": "❌ 撤回/刪除此行程", "data": f"action=delete&id={match_id}"
          }, "color": "#ff4b4b"},
          {"type": "separator", "margin": "sm"},
          {"type": "button", "style": "link", "height": "sm", "action": {
            "type": "uri", "label": "☕ 請開發者喝杯咖啡",
            "uri": "https://p.ecpay.com.tw/8C9FE97"
          }, "color": "#aaaaaa"}
        ]
      }
    }
    return FlexSendMessage(alt_text="行程發布成功", contents=bubble)

def get_main_cat_menu(text_prefix=""):
    items = [
        QuickReplyButton(action=MessageAction(label="🛣️ 路線與行程", text="類別:路線")),
        QuickReplyButton(action=MessageAction(label="💰 費用與付款", text="類別:費用")),
        QuickReplyButton(action=MessageAction(label="🚗 車內環境", text="類別:環境")),
        QuickReplyButton(action=MessageAction(label="💬 乘車氛圍", text="類別:氛圍")),
        QuickReplyButton(action=MessageAction(label="📦 行李與安全", text="類別:行李安全")),
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

def get_detail_flex():
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [{"type": "text", "text": "行程細節（一次設定）",
                          "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
            "backgroundColor": "#444441"
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                {"type": "text", "text": "人數", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "1人", "text": "人數:1"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "2人", "text": "人數:2"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "3人", "text": "人數:3"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "4人", "text": "人數:4"}}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "費用方式", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "議價", "text": "費用:私訊議價"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "飲料", "text": "費用:請喝飲料"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "公益", "text": "費用:免費公益"}}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "時間彈性", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1,
                     "color": "#1D9E75",
                     "action": {"type": "message", "label": "彈性 ±4hr", "text": "彈性:願意彈性"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "精確時間", "text": "彈性:不願意"}}
                ]}
            ]
        }
    }
    return FlexSendMessage(alt_text="設定行程細節", contents=bubble)

# --- 歡迎訊息 Flex 卡片（Item 3）---
def get_welcome_flex():
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#00b900",
            "contents": [
                {"type": "text", "text": "RideMatch 順路媒合", "weight": "bold", "color": "#FFFFFF", "size": "lg"},
                {"type": "text", "text": "找到同方向的旅伴，省錢又環保", "color": "#FFFFFFBB", "size": "xs", "margin": "sm"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "lg",
            "contents": [
                {"type": "text", "text": "四步驟開始使用：", "weight": "bold", "size": "md"},
                {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    {"type": "text", "text": "1️⃣ 選擇身份：載客/貨 或 搭車/寄物", "size": "sm", "wrap": True},
                    {"type": "text", "text": "2️⃣ 設定出發時間", "size": "sm"},
                    {"type": "text", "text": "3️⃣ 選擇起點與終點", "size": "sm"},
                    {"type": "text", "text": "4️⃣ 填寫細節後發布，系統自動媒合", "size": "sm", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "隨時輸入「我的行程」管理已發布行程\n輸入「媒合規則」了解配對邏輯\n輸入「幫助」重新查看本說明", "size": "xs", "color": "#888888", "wrap": True}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#00b900", "height": "sm",
                 "action": {"type": "message", "label": "🚗 我要載客/貨", "text": "我要載客/貨"}},
                {"type": "button", "style": "primary", "color": "#1e90ff", "height": "sm",
                 "action": {"type": "message", "label": "🙋 我要搭車/寄物", "text": "我要搭車/寄物"}}
            ]
        }
    }
    return FlexSendMessage(alt_text="歡迎使用 RideMatch 順路媒合！", contents=bubble)

# --- 媒合規則 Flex 卡片（Item 4）---
def get_rules_flex():
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#555555",
            "contents": [{"type": "text", "text": "⚖️ 媒合規則說明", "weight": "bold", "color": "#FFFFFF", "size": "md"}]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "lg",
            "contents": [
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "🛣️ 中途上下車", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "司機從台北開到台中，你在桃園上車、新竹下車也OK！只要司機開啟「接受中途」，系統就會幫你配到順路的車。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "⏰ 時間彈性", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "你選 14:00 出發＋願意彈性 → 系統自動幫你搜尋 10:00~18:00 的行程（前後各 4 小時）。選精確時間則只搜前後 1 小時。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "🧭 方向匹配", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "只配同方向！北→南不會配到南→北的人。同縣市內則配同區域的行程。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "🔔 自動通知＆過期", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "有人發布同向行程時，系統主動推播通知雙方。行程超過 24 小時自動隱藏。", "size": "xs", "color": "#666666", "wrap": True}
                ]}
            ]
        }
    }
    return FlexSendMessage(alt_text="媒合規則說明", contents=bubble)

# --- 被動媒合推播 Flex 卡片 ---
def get_match_notify_flex(sc, sd, ec, ed, tt, pc, fe, prefs, line_id):
    prefs_text = prefs.strip().rstrip(",") if prefs else "（未設定）"
    contact_contents = [{"type": "text", "text": "有人發布了與您同向的行程！", "size": "xs", "color": "#888888", "align": "center"}]
    if line_id:
        contact_contents.append({"type": "button", "style": "primary", "height": "sm", "color": "#00b900", "margin": "sm",
            "action": {"type": "uri", "label": "💬 加 LINE 聯絡", "uri": f"https://line.me/ti/p/~{line_id}"}})
    bubble = {
        "type": "bubble",
        "header": {"type": "box", "layout": "vertical",
            "contents": [{"type": "text", "text": "🔔 新的順路配對！", "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
            "backgroundColor": "#1D9E75"},
        "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 1},
                {"type": "text", "text": f"{sc}{sd} ➔ {ec}{ed}", "color": "#333333", "size": "sm", "flex": 4, "wrap": True}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
                {"type": "text", "text": tt.replace("T", " "), "color": "#333333", "size": "sm", "flex": 4}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "費用", "color": "#aaaaaa", "size": "sm", "flex": 1},
                {"type": "text", "text": fe, "color": "#333333", "size": "sm", "flex": 4}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "人數", "color": "#aaaaaa", "size": "sm", "flex": 1},
                {"type": "text", "text": f"{pc}人", "color": "#333333", "size": "sm", "flex": 4}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "標籤", "color": "#aaaaaa", "size": "sm", "flex": 1},
                {"type": "text", "text": prefs_text, "color": "#999999", "size": "xs", "flex": 4, "wrap": True}]}
        ]},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contact_contents}
    }
    return FlexSendMessage(alt_text="🔔 新的順路配對！", contents=bubble)

# --- 發布核心邏輯（供 最終確認發布 和 WAIT_LINE_ID 共用）---
def do_publish(uid, reply_token):
    conn = get_db()
    res = conn.execute(q('SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
    if not res:
        safe_reply(reply_token, TextSendMessage(text="⚠️ 找不到暫存資料，請重新開始。"))
        conn.close()
        return
    ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid = res
    lid = lid or ''

    # 防重複發布
    existing = conn.execute(q(
        "SELECT id FROM matches WHERE user_id = ? AND user_type = ? AND time_info = ? AND s_city = ? AND s_dist = ? AND e_city = ? AND e_dist = ? AND status = 'active'"
    ), (uid, ut, tt, sc, sd, ec, ed)).fetchone()
    if existing:
        safe_reply(reply_token, TextSendMessage(text="⚠️ 您已有一筆相同的行程（相同路線與時間），請先刪除舊行程再重新發布。"))
        conn.close()
        return

    cursor = conn.cursor()
    if USE_PG:
        cursor.execute(q('INSERT INTO matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs, line_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id'),
                       (uid, ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid))
        new_id = cursor.fetchone()[0]
    else:
        cursor.execute('INSERT INTO matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs, line_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (uid, ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid))
        new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    m_list = find_matches_v15(uid, ut, tt, sc, sd, ec, ed, fx, wy, pc)
    output = [get_publish_confirm_flex(res, new_id)]

    if m_list:
        match_bubbles = []
        for m in m_list:
            m_prefs_text = (m[9].strip().rstrip(",") if m[9] else "（未設定）")
            m_line_id = m[10] or ''
            if m_line_id:
                contact_btn = {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                    "action": {"type": "uri", "label": "💬 加 LINE 聯絡", "uri": f"https://line.me/ti/p/~{m_line_id}"}}
            else:
                contact_btn = {"type": "button", "style": "secondary", "height": "sm",
                    "action": {"type": "message", "label": "對方未提供 LINE ID", "text": "幫助"}}
            match_bubbles.append({
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical",
                    "contents": [{"type": "text", "text": "🎯 順路配對", "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
                    "backgroundColor": "#1D9E75"},
                "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": m[1][5:16], "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": f"{m[2]}{m[3]} ➔ {m[4]}{m[5]}", "color": "#333333", "size": "sm", "flex": 4, "wrap": True}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "費用", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": m[6], "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "人數", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": f"{m[8]}人", "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "標籤", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": m_prefs_text, "color": "#999999", "size": "xs", "flex": 4, "wrap": True}]}
                ]},
                "footer": {"type": "box", "layout": "vertical", "contents": [contact_btn]}
            })
            # 被動推播：通知既有配對者（含發布者的 LINE ID）
            safe_push(m[0], get_match_notify_flex(sc, sd, ec, ed, tt, pc, fe, ps, lid))

        output.append(FlexSendMessage(alt_text="偵測到順路配對！",
            contents={"type": "carousel", "contents": match_bubbles}))
    else:
        output.append(TextSendMessage(text="🔎 目前暫無同向行程，系統將持續監控。"))

    safe_reply(reply_token, output)

# --- 5. 核心匹配演算法 ---
def find_matches_v15(user_id, utype, t_info, sc, sd, ec, ed, flex, way_point, p_count):
    target_type = 'seeker' if utype == 'driver' else 'driver'
    conn = get_db()
    c = conn.cursor()

    try:
        base_t = datetime.strptime(t_info, "%Y-%m-%dT%H:%M")
        buffer = 4 if "願意" in flex else 1
        s_range = (base_t - timedelta(hours=buffer)).strftime("%Y-%m-%dT%H:%M")
        e_range = (base_t + timedelta(hours=buffer)).strftime("%Y-%m-%dT%H:%M")
    except:
        s_range, e_range = t_info, t_info

    s_w, e_w = CITY_WEIGHTS.get(sc, 0), CITY_WEIGHTS.get(ec, 0)
    user_direction = 1 if e_w > s_w else (-1 if e_w < s_w else 0)

    c.execute(q("SELECT user_id, time_info, s_city, s_dist, e_city, e_dist, fee, way_point, p_count, prefs, line_id FROM matches WHERE user_type = ? AND user_id != ? AND status = 'active' AND time_info BETWEEN ? AND ?"),
              [target_type, user_id, s_range, e_range])
    raw_res = c.fetchall()

    final_matches = []
    user_p = int(p_count)

    for m in raw_res:
        m_uid, m_time, m_sc, m_sd, m_ec, m_ed, m_fee, m_way, m_pc, m_prefs = m
        m_s_w, m_e_w = CITY_WEIGHTS.get(m_sc, 0), CITY_WEIGHTS.get(m_ec, 0)
        match_direction = 1 if m_e_w > m_s_w else (-1 if m_e_w < m_s_w else 0)

        if user_direction != match_direction:
            continue

        # 同縣市：用區域分群匹配（Item 8）
        if user_direction == 0:
            if sc != m_sc or ec != m_ec:
                continue
            user_s_cluster = get_district_cluster(sc, sd)
            match_s_cluster = get_district_cluster(m_sc, m_sd)
            user_e_cluster = get_district_cluster(ec, ed)
            match_e_cluster = get_district_cluster(m_ec, m_ed)
            if user_s_cluster != match_s_cluster or user_e_cluster != match_e_cluster:
                continue

        match_p = int(m_pc)
        if utype == 'driver' and user_p < match_p:
            continue
        if utype == 'seeker' and user_p > match_p:
            continue

        # 站點檢查（中途邏輯）— 僅跨縣市時
        if user_direction != 0:
            is_match = False
            d_s_w, d_e_w = (s_w, e_w) if utype == 'driver' else (m_s_w, m_e_w)
            s_s_w, s_e_w_val = (m_s_w, m_e_w) if utype == 'driver' else (s_w, e_w)
            d_way = way_point if utype == 'driver' else m_way

            if "接受" in d_way:
                if user_direction == 1:
                    if d_s_w <= s_s_w and s_e_w_val <= d_e_w:
                        is_match = True
                else:
                    if d_s_w >= s_s_w and s_e_w_val >= d_e_w:
                        is_match = True
            else:
                if sc == m_sc and ec == m_ec:
                    is_match = True

            if not is_match:
                continue

        final_matches.append(m)

    conn.close()
    return final_matches[:5]

# --- 6. Flask 路由 ---
@app.route("/", methods=['GET', 'POST'])
def index():
    return "Bot is running!"

@app.route("/health", methods=['GET'])
def health():
    token_ok = bool(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
    secret_ok = bool(os.getenv('LINE_CHANNEL_SECRET'))
    db_ok = False
    try:
        conn = get_db()
        conn.close()
        db_ok = True
    except Exception as e:
        pass
    return {"token": token_ok, "secret": secret_ok, "db": db_ok}

@app.route("/debug-bot", methods=['GET'])
def debug_bot():
    try:
        info = line_bot_api.get_bot_info()
        return {"status": "ok", "bot_name": info.display_name, "bot_id": info.user_id}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500

@app.route("/logs", methods=['GET'])
def show_logs():
    return {"logs": _log_store}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    _store_log("webhook", f"body_len={len(body)}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        logging.error(f"Handler error: {e}", exc_info=True)
        _store_log("handler_error", str(e))
    return 'OK'

# --- 7. FollowEvent（歡迎訊息，Item 3）---
@handler.add(FollowEvent)
def handle_follow(event):
    safe_reply(event.reply_token, get_welcome_flex())

# --- 8. Postback 處理 ---
@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    data = event.postback.data
    if not data:
        return

    try:
        if data == "select_time":
            t = event.postback.params['datetime']
            conn = get_db()
            conn.execute(q('UPDATE user_state SET temp_time = ?, step = ? WHERE user_id = ?'), (t, "START", uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, get_area_carousel("📍 第一步：選擇【出發地】區域"))

        elif data.startswith("action=delete"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            conn.execute(q('DELETE FROM matches WHERE id = ? AND user_id = ?'), (match_id, uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"🗑️ 已成功刪除行程 (編號: {match_id})"))

        elif data.startswith("action=complete"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            conn.execute(q("UPDATE matches SET status = 'completed' WHERE id = ? AND user_id = ?"), (match_id, uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, TextSendMessage(
                text="🎉 恭喜完成行程！請為這趟體驗評分：",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=PostbackAction(label=f"{'⭐' * i}", data=f"action=rate&id={match_id}&score={i}"))
                    for i in range(1, 6)
                ])
            ))

        elif data.startswith("action=rate"):
            params = dict(parse_qsl(data))
            match_id, score = params.get('id'), params.get('score')
            conn = get_db()
            if USE_PG:
                conn.execute(q('INSERT INTO ratings (user_id, match_id, score) VALUES (?, ?, ?)'), (uid, match_id, score))
            else:
                conn.execute('INSERT INTO ratings (user_id, match_id, score) VALUES (?, ?, ?)', (uid, match_id, score))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"感謝評價！您給了 {'⭐' * int(score)} 的評分。"))

        elif data.startswith("action=cancel"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            conn.execute(q("UPDATE matches SET status = 'cancelled' WHERE id = ? AND user_id = ?"), (match_id, uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"🚫 行程已取消 (編號: {match_id})"))
    except Exception as e:
        logging.error(f"Postback error for {uid}: {e}")
        safe_reply(event.reply_token, TextSendMessage(text="⚠️ 操作發生錯誤，請重新嘗試。"))

# --- 9. 訊息處理（主邏輯）---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    uid = event.source.user_id

    # --- 我的行程 ---
    if msg == "我的行程":
        conn = get_db()
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        my_matches = conn.execute(
            q("SELECT id, time_info, s_city, s_dist, e_city, e_dist, user_type FROM matches WHERE user_id = ? AND status = 'active' AND time_info >= ? ORDER BY time_info ASC LIMIT 10"),
            (uid, now)
        ).fetchall()
        conn.close()

        if not my_matches:
            safe_reply(event.reply_token, TextSendMessage(text="📭 您目前沒有生效中的行程。"))
        else:
            cols = []
            for m in my_matches:
                m_id, t_info, sc, sd, ec, ed, utype = m
                role = "🚗 載客/貨" if utype == 'driver' else "🙋 搭車/寄物"
                title_str = f"{role} | {t_info[5:16]}"
                text_str = f"{sc}{sd} ➔ {ec}{ed}"
                cols.append(CarouselColumn(
                    title=title_str[:40],
                    text=text_str[:60],
                    actions=[
                        PostbackAction(label='✅ 已搭乘完成', data=f"action=complete&id={m_id}"),
                        PostbackAction(label='🚫 取消行程', data=f"action=cancel&id={m_id}"),
                        PostbackAction(label='❌ 刪除', data=f"action=delete&id={m_id}")
                    ]
                ))
            safe_reply(event.reply_token, [
                TextSendMessage(text="📋 以下是您的近期行程："),
                TemplateSendMessage(alt_text="行程管理", template=CarouselTemplate(columns=cols))
            ])
        return

    # --- 媒合規則（Item 4）---
    elif msg == "媒合規則":
        safe_reply(event.reply_token, get_rules_flex())
        return

    # --- 幫助 / 使用說明（Item 3）---
    elif msg in ["幫助", "使用說明", "help"]:
        safe_reply(event.reply_token, get_welcome_flex())
        return

    # --- 繼續填寫（Item 6）---
    elif msg == "繼續填寫":
        conn = get_db()
        res = conn.execute(q('SELECT step, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        conn.close()
        if not res:
            safe_reply(event.reply_token, TextSendMessage(text="⚠️ 找不到暫存資料，請重新開始。"))
            return
        step, ut, tt, sc, sd, ec, ed, wy, pc, fe, fx = res
        if not tt:
            safe_reply(event.reply_token, TextSendMessage(
                text="🕒 請選擇日期時間：",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))
                ])
            ))
        elif not sc or not sd:
            safe_reply(event.reply_token, get_area_carousel("📍 選擇【出發地】區域"))
        elif not ec or not ed:
            safe_reply(event.reply_token, get_area_carousel("🏁 選擇【目的地】區域"))
        elif not wy:
            btns = [
                QuickReplyButton(action=MessageAction(label="✅ 接受中途", text="中途:接受")),
                QuickReplyButton(action=MessageAction(label="❌ 僅限起迄", text="中途:僅限起迄")),
                QuickReplyButton(action=MessageAction(label="🛣️ 交流道可", text="中途:限交流道"))
            ]
            safe_reply(event.reply_token, TextSendMessage(text="是否接受中途上下車？", quick_reply=QuickReply(items=btns)))
        elif not pc or not fe or not fx:
            safe_reply(event.reply_token, get_detail_flex())
        else:
            safe_reply(event.reply_token, get_main_cat_menu("您已填完基本資料，請選擇標籤或直接發布。"))
        return

    # --- 開始發布流程 ---
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        clean_expired_matches()
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = get_db()
        if USE_PG:
            conn.execute(q('''INSERT INTO user_state (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step)
                VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '', NULL, 'START')
                ON CONFLICT (user_id) DO UPDATE SET current_type=EXCLUDED.current_type,
                temp_time=NULL, s_city=NULL, s_dist=NULL, e_city=NULL, e_dist=NULL,
                temp_way=NULL, temp_count=NULL, temp_fee=NULL, temp_flex=NULL, temp_prefs='', temp_line_id=NULL, step='START' '''), (uid, ut))
        else:
            conn.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "", NULL, "START")', (uid, ut))
        conn.commit()
        conn.close()
        safe_reply(event.reply_token, TextSendMessage(
            text="🕒 請選擇日期時間：",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=DatetimePickerAction(label="🕒 點我選擇", data="select_time", mode="datetime"))
            ])
        ))

    elif msg.startswith("區域:"):
        area = msg.split(":")[1]
        cities = CITY_DATA.get(area, [])
        btns = [QuickReplyButton(action=MessageAction(label=c, text=f"縣市:{c}")) for c in cities]
        safe_reply(event.reply_token, TextSendMessage(text=f"已選 {area}，請選擇縣市：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("縣市:"):
        c = msg.split(":")[1]
        conn = get_db()
        res = conn.execute(q('SELECT step FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        step = res[0] if res else "START"
        col = "s_city" if step == "START" else "e_city"
        conn.execute(q(f'UPDATE user_state SET {col} = ? WHERE user_id = ?'), (c, uid))
        conn.commit()
        conn.close()
        dists = DISTRICT_DATA.get(c, ["市中心"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"區:{d}")) for d in dists[:13]]
        safe_reply(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("區:"):
        d = msg.split(":")[1]
        conn = get_db()
        res = conn.execute(q('SELECT step FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        step = res[0] if res else "START"
        if step == "START":
            conn.execute(q('UPDATE user_state SET s_dist = ?, step = ? WHERE user_id = ?'), (d, "END", uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, get_area_carousel("🏁 第二步：選擇【目的地】區域"))
        else:
            conn.execute(q('UPDATE user_state SET e_dist = ?, step = ? WHERE user_id = ?'), (d, "DONE", uid))
            conn.commit()
            conn.close()
            btns = [
                QuickReplyButton(action=MessageAction(label="✅ 接受中途", text="中途:接受")),
                QuickReplyButton(action=MessageAction(label="❌ 僅限起迄", text="中途:僅限起迄")),
                QuickReplyButton(action=MessageAction(label="🛣️ 交流道可", text="中途:限交流道"))
            ]
            safe_reply(event.reply_token, TextSendMessage(text="是否接受中途上下車？", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("中途:"):
        conn = get_db()
        conn.execute(q('UPDATE user_state SET temp_way = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
        conn.commit()
        conn.close()
        safe_reply(event.reply_token, get_detail_flex())

    elif msg.startswith("人數:"):
        conn = get_db()
        conn.execute(q('UPDATE user_state SET temp_count = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
        conn.commit()
        conn.close()

    elif msg.startswith("費用:"):
        conn = get_db()
        conn.execute(q('UPDATE user_state SET temp_fee = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
        conn.commit()
        conn.close()

    elif msg.startswith("彈性:"):
        conn = get_db()
        res = conn.execute(q('SELECT temp_count, temp_fee, temp_way FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        conn.execute(q('UPDATE user_state SET temp_flex = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
        conn.commit()
        conn.close()

        pc = res[0] if res else None
        fe = res[1] if res else None
        wy = res[2] if res else ""

        if not pc or not fe:
            missing = []
            if not pc: missing.append("人數")
            if not fe: missing.append("費用方式")
            safe_reply(event.reply_token, TextSendMessage(
                text=f"⚠️ {'、'.join(missing)} 尚未選擇，請返回補填。",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="↩ 返回重選", text=f"中途:{wy}"))
                ])
            ))
        else:
            safe_reply(event.reply_token, get_main_cat_menu("最後一步：自定義規範。"))

    elif msg.startswith("類別:"):
        cat = msg.split(":")[1]
        cols = []
        if cat == "路線":
            cols = [
                CarouselColumn(title='路線(1)', text='接送與繞路', actions=[
                    MessageAction(label='順路為主', text='規範:順路為主'),
                    MessageAction(label='接受繞路接送', text='規範:接受繞路接送'),
                    MessageAction(label='可討論上下車點', text='規範:可討論上下車點')
                ]),
                CarouselColumn(title='路線(2)', text='路線安排', actions=[
                    MessageAction(label='高速交流道為主', text='規範:高速交流道為主'),
                    MessageAction(label='可停休息站', text='規範:可停休息站'),
                    MessageAction(label='依司機路線為準', text='規範:依司機路線為準')
                ]),
                CarouselColumn(title='路線(3)', text='通勤模式', actions=[
                    MessageAction(label='回程願意順載', text='規範:回程願意順載'),
                    MessageAction(label='固定通勤路線', text='規範:固定通勤路線'),
                    MessageAction(label='長期通勤歡迎', text='規範:長期通勤歡迎')
                ])
            ]
        elif cat == "費用":
            cols = [
                CarouselColumn(title='費用(1)', text='付款方式', actions=[
                    MessageAction(label='不接受議價', text='規範:不接受議價'),
                    MessageAction(label='轉帳現金皆可', text='規範:轉帳現金皆可'),
                    MessageAction(label='請自備零錢', text='規範:請自備零錢')
                ]),
                CarouselColumn(title='費用(2)', text='付款時機', actions=[
                    MessageAction(label='先付後乘', text='規範:先付後乘'),
                    MessageAction(label='到達後付款', text='規範:到達後付款'),
                    MessageAction(label='可開收據', text='規範:可開收據')
                ]),
                CarouselColumn(title='費用(3)', text='優惠減免', actions=[
                    MessageAction(label='學生低收減免', text='規範:學生低收減免'),
                    MessageAction(label='寵物不另收費', text='規範:寵物不另收費'),
                    MessageAction(label='捐款抵費用', text='規範:捐款抵費用')
                ])
            ]
        elif cat == "環境":
            cols = [
                CarouselColumn(title='環境(1)', text='菸酒飲食', actions=[
                    MessageAction(label='全程禁菸禁檳榔', text='規範:全程禁菸禁檳榔'),
                    MessageAction(label='禁止飲食', text='規範:禁止飲食'),
                    MessageAction(label='可飲水', text='規範:可飲水')
                ]),
                CarouselColumn(title='環境(2)', text='整潔與設備', actions=[
                    MessageAction(label='請保持車內整潔', text='規範:請保持車內整潔'),
                    MessageAction(label='有行車記錄器', text='規範:有行車記錄器'),
                    MessageAction(label='車內有兒童座椅', text='規範:車內有兒童座椅')
                ]),
                CarouselColumn(title='環境(3)', text='寵物規定', actions=[
                    MessageAction(label='寵物需裝籠推車', text='規範:寵物需裝籠推車'),
                    MessageAction(label='謝絕寵物', text='規範:謝絕寵物'),
                    MessageAction(label='座位依司機安排', text='規範:座位依司機安排')
                ])
            ]
        elif cat == "氛圍":
            cols = [
                CarouselColumn(title='氛圍(1)', text='互動偏好', actions=[
                    MessageAction(label='歡迎聊天', text='規範:歡迎聊天'),
                    MessageAction(label='安靜為主', text='規範:安靜為主'),
                    MessageAction(label='可睡覺聽歌', text='規範:可睡覺聽歌')
                ]),
                CarouselColumn(title='氛圍(2)', text='同行偏好', actions=[
                    MessageAction(label='歡迎攜伴同行', text='規範:歡迎攜伴同行'),
                    MessageAction(label='可帶外食上車', text='規範:可帶外食上車'),
                    MessageAction(label='限同性乘客', text='規範:限同性乘客')
                ])
            ]
        elif cat == "行李安全":
            cols = [
                CarouselColumn(title='行李(1)', text='行李規定', actions=[
                    MessageAction(label='大型行李請告知', text='規範:大型行李請告知'),
                    MessageAction(label='行李限一件', text='規範:行李限一件'),
                    MessageAction(label='不接受超重行李', text='規範:不接受超重行李')
                ]),
                CarouselColumn(title='行李(2)', text='包裹寄送', actions=[
                    MessageAction(label='可寄送小型包裹', text='規範:可寄送小型包裹'),
                    MessageAction(label='務必準時', text='規範:務必準時'),
                    MessageAction(label='需身分驗證乘車', text='規範:需身分驗證乘車')
                ]),
                CarouselColumn(title='安全', text='駕駛與保險', actions=[
                    MessageAction(label='穩健駕駛風格', text='規範:穩健駕駛風格'),
                    MessageAction(label='投保乘客責任險', text='規範:投保乘客責任險'),
                    MessageAction(label='全程開啟定位', text='規範:全程開啟定位')
                ])
            ]
        if cols:
            safe_reply(event.reply_token, TemplateSendMessage(alt_text='選擇規範', template=CarouselTemplate(columns=cols)))

    elif msg.startswith("規範:"):
        p = msg.split(":")[1]
        conn = get_db()
        res = conn.execute(q('SELECT temp_prefs FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        p_str = (res[0] if res and res[0] else "") + f"{p}, "
        conn.execute(q('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?'), (p_str, uid))
        conn.commit()
        conn.close()
        safe_reply(event.reply_token, get_main_cat_menu(f"✅ 已選：{p}\n目前標籤：{p_str}"))

    elif msg == "最終確認發布":
        conn = get_db()
        res = conn.execute(q('SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        conn.close()

        if not res:
            safe_reply(event.reply_token, TextSendMessage(text="⚠️ 找不到暫存資料，請重新開始。"))
            return

        ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid = res

        missing = []
        if not tt: missing.append("出發時間")
        if not sc or not sd: missing.append("出發地")
        if not ec or not ed: missing.append("目的地")
        if not pc: missing.append("人數")
        if not fe: missing.append("費用方式")
        if not fx: missing.append("時間彈性")

        if missing:
            safe_reply(event.reply_token, TextSendMessage(
                text=f"⚠️ 還有以下項目未填：\n" + "\n".join(f"• {m}" for m in missing) + "\n\n請返回補填後再發布。"
            ))
            return

        # 尚未填寫 LINE ID → 提示輸入
        if lid is None:
            conn = get_db()
            conn.execute(q('UPDATE user_state SET step = ? WHERE user_id = ?'), ('WAIT_LINE_ID', uid))
            conn.commit()
            conn.close()
            safe_reply(event.reply_token, TextSendMessage(
                text="📱 最後一步！請輸入您的 LINE ID，讓配對對象能聯絡您：\n\n💡 查看方式：LINE → 設定 → 個人檔案 → LINE ID\n\n如不想提供，請按「跳過」",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="跳過", text="跳過"))
                ])
            ))
            return

        do_publish(uid, event.reply_token)

    # --- 未知輸入 fallback（含 WAIT_LINE_ID 處理）---
    else:
        try:
            conn = get_db()
            res = conn.execute(q('SELECT step, current_type FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            conn.close()
        except Exception as e:
            _store_log("fallback_db_error", str(e))
            res = None

        # 處理 LINE ID 輸入
        if res and res[0] == 'WAIT_LINE_ID':
            line_id = '' if msg == '跳過' else msg.strip().lstrip('@')
            conn = get_db()
            conn.execute(q('UPDATE user_state SET temp_line_id = ?, step = ? WHERE user_id = ?'), (line_id, 'DONE', uid))
            conn.commit()
            conn.close()
            do_publish(uid, event.reply_token)
            return

        if res and res[0] and res[1]:
            items = [
                QuickReplyButton(action=MessageAction(label="繼續填寫", text="繼續填寫")),
                QuickReplyButton(action=MessageAction(label="重新開始", text="我要載客/貨" if res[1] == 'driver' else "我要搭車/寄物"))
            ]
            safe_reply(event.reply_token, TextSendMessage(
                text="🤔 不太確定您的意思，您目前有未完成的行程設定。",
                quick_reply=QuickReply(items=items)
            ))
        else:
            items = [
                QuickReplyButton(action=MessageAction(label="🚗 我要載客/貨", text="我要載客/貨")),
                QuickReplyButton(action=MessageAction(label="🙋 我要搭車/寄物", text="我要搭車/寄物")),
                QuickReplyButton(action=MessageAction(label="📋 我的行程", text="我的行程")),
                QuickReplyButton(action=MessageAction(label="❓ 使用說明", text="幫助"))
            ]
            safe_reply(event.reply_token, TextSendMessage(
                text="🤔 不太確定您的意思，請選擇以下功能：",
                quick_reply=QuickReply(items=items)
            ))

# --- 10. Keep Alive ---
def keep_alive():
    url = os.getenv('RENDER_EXTERNAL_URL', 'https://ride-match-bot.onrender.com') + '/'
    while True:
        try:
            requests.get(url, timeout=10)
            logging.info(f"Keep alive ping: {url}")
        except Exception as e:
            logging.error(f"Keep alive failed: {e}")
        time.sleep(600)

# Render 環境下在模組層級啟動 keep_alive（gunicorn 不會跑 __main__）
if os.getenv('RENDER'):
    threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
