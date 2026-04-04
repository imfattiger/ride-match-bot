import os
import re
import json
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
    FollowEvent, URIAction
)

# --- 1. 基礎設定 ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
ADMIN_LINE_ID = os.getenv('ADMIN_LINE_ID', '')

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
    "基隆市": 1, "台北市": 2, "新北市": 3, "桃園市": 4, "新竹市": 5, "新竹縣": 5.2,
    "苗栗縣": 6, "台中市": 7, "彰化縣": 8, "南投縣": 9, "雲林縣": 10, "嘉義市": 11,
    "嘉義縣": 11.2, "台南市": 12, "高雄市": 13, "屏東縣": 14, "宜蘭縣": 15, "花蓮縣": 16, "台東縣": 17
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
    },
    "桃園市": {
        "北": ["龜山區", "林口區", "蘆竹區"],
        "市區": ["桃園區", "中壢區", "八德區", "平鎮區"],
        "南": ["楊梅區", "新屋區", "觀音區"],
        "東": ["大溪區", "復興區"]
    }
}

def get_district_cluster(city, dist):
    groups = DISTRICT_GROUPS.get(city)
    if not groups:
        return city  # 無分群定義的城市：同市即視為同群
    for cluster_name, districts in groups.items():
        if dist in districts:
            return cluster_name
    return city  # 找不到分群：fallback 整個城市

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

# --- Schema 版本遷移表 ---
# 每筆格式：(version, pg_sql, sqlite_sql)
# sqlite_sql=None 代表與 pg_sql 相同（或 SQLite 不需要此步驟）
# 新增欄位/表格時，在此 list 末尾加一筆並遞增版本號
SCHEMA_MIGRATIONS = [
    # v1 基礎表
    (1,
     "CREATE TABLE IF NOT EXISTS matches (id SERIAL PRIMARY KEY, user_id TEXT, user_type TEXT, time_info TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT, line_id TEXT DEFAULT '', status TEXT DEFAULT 'active', expires_at TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, user_type TEXT, time_info TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, way_point TEXT, p_count TEXT, fee TEXT, flexible TEXT, prefs TEXT, line_id TEXT DEFAULT '', status TEXT DEFAULT 'active', expires_at TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
    (2,
     "CREATE TABLE IF NOT EXISTS user_state (user_id TEXT PRIMARY KEY, current_type TEXT, temp_time TEXT, s_city TEXT, s_dist TEXT, e_city TEXT, e_dist TEXT, temp_way TEXT, temp_count TEXT, temp_fee TEXT, temp_flex TEXT, temp_prefs TEXT, temp_line_id TEXT, step TEXT, agreed_terms INTEGER DEFAULT 0)",
     None),
    (3,
     "CREATE TABLE IF NOT EXISTS ratings (id SERIAL PRIMARY KEY, rater_id TEXT, ratee_id TEXT, match_id INTEGER, score INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE IF NOT EXISTS ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, rater_id TEXT, ratee_id TEXT, match_id INTEGER, score INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
    (4,
     "CREATE TABLE IF NOT EXISTS pairs (id SERIAL PRIMARY KEY, uid_a TEXT, match_id_a INTEGER, uid_b TEXT, match_id_b INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE IF NOT EXISTS pairs (id INTEGER PRIMARY KEY AUTOINCREMENT, uid_a TEXT, match_id_a INTEGER, uid_b TEXT, match_id_b INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
    (5,
     "CREATE TABLE IF NOT EXISTS blocked_users (user_id TEXT PRIMARY KEY, reason TEXT, blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     None),
    (6,
     "CREATE TABLE IF NOT EXISTS push_log (id SERIAL PRIMARY KEY, month_key TEXT, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE IF NOT EXISTS push_log (id INTEGER PRIMARY KEY AUTOINCREMENT, month_key TEXT, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
    # v7-10 欄位補齊（既有 DB 遷移）
    (7,  "ALTER TABLE matches ADD COLUMN IF NOT EXISTS line_id TEXT DEFAULT ''",
         "ALTER TABLE matches ADD COLUMN line_id TEXT DEFAULT ''"),
    (8,  "ALTER TABLE matches ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
         "ALTER TABLE matches ADD COLUMN status TEXT DEFAULT 'active'"),
    (9,  "ALTER TABLE matches ADD COLUMN IF NOT EXISTS expires_at TEXT",
         "ALTER TABLE matches ADD COLUMN expires_at TEXT"),
    (10, "ALTER TABLE matches ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0",
         "ALTER TABLE matches ADD COLUMN view_count INTEGER DEFAULT 0"),
    (11, "ALTER TABLE matches ADD COLUMN IF NOT EXISTS reminded_at TEXT",
         "ALTER TABLE matches ADD COLUMN reminded_at TEXT"),
    (12, "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS temp_line_id TEXT",
         "ALTER TABLE user_state ADD COLUMN temp_line_id TEXT"),
    (13, "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS temp_expire TEXT",
         "ALTER TABLE user_state ADD COLUMN temp_expire TEXT"),
    (14, "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS agreed_terms INTEGER DEFAULT 0",
         "ALTER TABLE user_state ADD COLUMN agreed_terms INTEGER DEFAULT 0"),
    (15, "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS rater_id TEXT",
         "ALTER TABLE ratings ADD COLUMN rater_id TEXT"),
    (16, "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS ratee_id TEXT",
         "ALTER TABLE ratings ADD COLUMN ratee_id TEXT"),
    # v17-19 索引 & pending_pushes
    (17, "CREATE UNIQUE INDEX IF NOT EXISTS ratings_rater_match ON ratings(match_id, rater_id)", None),
    (18, "CREATE UNIQUE INDEX IF NOT EXISTS matches_no_dup ON matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist) WHERE status = 'active'",
         "CREATE UNIQUE INDEX IF NOT EXISTS matches_no_dup ON matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist)"),
    (19,
     "CREATE TABLE IF NOT EXISTS pending_pushes (id SERIAL PRIMARY KEY, user_id TEXT, message_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
     "CREATE TABLE IF NOT EXISTS pending_pushes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, message_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
    (20, "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS notify_on_match INTEGER DEFAULT 1",
         "ALTER TABLE user_state ADD COLUMN notify_on_match INTEGER DEFAULT 1"),
]
SCHEMA_VERSION = SCHEMA_MIGRATIONS[-1][0]  # 目前最新版本號

def init_db():
    conn = get_db()
    c = conn.cursor()
    # 確保 schema_version table 存在
    if USE_PG:
        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    else:
        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    conn.commit()
    # 讀取當前版本（無資料 = 0，全新 DB 或尚未版控）
    c.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = c.fetchone()
    current_version = row[0] if row else 0
    if current_version >= SCHEMA_VERSION:
        conn.close()
        return
    # 只跑比當前版本新的遷移
    for ver, pg_sql, sqlite_sql in SCHEMA_MIGRATIONS:
        if ver <= current_version:
            continue
        sql = pg_sql if USE_PG else (sqlite_sql if sqlite_sql is not None else pg_sql)
        try:
            c.execute(sql)
            conn.commit()
        except Exception as e:
            logging.warning(f"Migration v{ver} skipped: {e}")
            try:
                if USE_PG:
                    conn._conn.rollback()  # 清除 aborted transaction state
            except:
                pass
    # 更新版本號
    if USE_PG:
        c.execute("DELETE FROM schema_version")
        c.execute("INSERT INTO schema_version (version) VALUES (%s)", (SCHEMA_VERSION,))
    else:
        c.execute("DELETE FROM schema_version")
        c.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
    conn.close()

def get_user_rating(conn, user_id):
    """回傳 (avg_score, count)，無資料回傳 (None, 0)"""
    row = conn.execute(q(
        "SELECT AVG(score), COUNT(id) FROM ratings WHERE ratee_id = ?"
    ), (user_id,)).fetchone()
    if row and row[1] and int(row[1]) > 0:
        return round(float(row[0]), 1), int(row[1])
    return None, 0

def is_blocked(uid):
    try:
        conn = get_db()
        try:
            row = conn.execute(q("SELECT user_id FROM blocked_users WHERE user_id = ?"), (uid,)).fetchone()
        finally:
            conn.close()
        return bool(row)
    except:
        return False

_flush_last = {}  # uid -> last flush timestamp，避免每次訊息都觸發 DB query

def flush_pending_pushes(uid):
    """補送之前推播失敗的通知，成功後刪除。靜默執行，不影響主流程。"""
    try:
        conn = get_db()
        try:
            rows = conn.execute(q(
                "SELECT id, message_json FROM pending_pushes WHERE user_id = ? ORDER BY id LIMIT 5"
            ), (uid,)).fetchall()
        finally:
            conn.close()
        for row_id, msg_json in rows:
            try:
                msgs_data = json.loads(msg_json)
                from linebot.models import SendMessage
                rebuilt = [FlexSendMessage.new_from_json_dict(m) if m.get('type') == 'flex' else TextSendMessage(text=m.get('text', '')) for m in msgs_data]
                line_bot_api.push_message(uid, rebuilt)
                # 成功則刪除
                _dc = get_db()
                try:
                    _dc.execute(q("DELETE FROM pending_pushes WHERE id = ?"), (row_id,))
                    _dc.commit()
                finally:
                    _dc.close()
            except:
                pass  # 仍然失敗就等下次
    except:
        pass

_last_clean_ts = 0

def clean_expired_matches():
    global _last_clean_ts
    if time.time() - _last_clean_ts < 300:  # 最多每 5 分鐘跑一次
        return
    _last_clean_ts = time.time()
    try:
        conn = get_db()
        try:
            now = datetime.now().strftime("%Y-%m-%dT%H:%M")
            conn.execute(q("DELETE FROM matches WHERE status = 'active' AND (expires_at < ? OR time_info < ?)"), (now, now))
            # 清除超過 7 天的 pending_pushes（對方已取消訂閱或長期未互動）
            if USE_PG:
                conn.execute(q("DELETE FROM pending_pushes WHERE created_at < NOW() - INTERVAL '7 days'"))
            else:
                conn.execute("DELETE FROM pending_pushes WHERE created_at < datetime('now', '-7 days')")
            conn.commit()
        finally:
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

def is_notify_enabled(user_id):
    """查詢使用者是否開啟配對通知（預設開啟）"""
    try:
        _nc = get_db()
        try:
            row = _nc.execute(q("SELECT notify_on_match FROM user_state WHERE user_id = ?"), (user_id,)).fetchone()
        finally:
            _nc.close()
        return (row[0] if row and row[0] is not None else 1) == 1
    except:
        return True  # 查不到時預設送出


def safe_push(user_id, messages):
    try:
        line_bot_api.push_message(user_id, messages)
        _store_log("push_ok", f"uid={user_id[:10]}...")
        try:
            month_key = datetime.now().strftime("%Y-%m")
            _lc = get_db()
            try:
                _lc.execute(q("INSERT INTO push_log (month_key) VALUES (?)"), (month_key,))
                _lc.commit()
            finally:
                _lc.close()
        except:
            pass
    except Exception as e:
        logging.error(f"Push to {user_id} failed: {e}")
        _store_log("push_fail", str(e))
        # 推播失敗補救：存入 pending_pushes，讓使用者下次互動時補送
        try:
            if isinstance(messages, list):
                msgs_data = [m.as_json_dict() for m in messages]
            else:
                msgs_data = [messages.as_json_dict()]
            _pc = get_db()
            try:
                _pc.execute(q("INSERT INTO pending_pushes (user_id, message_json) VALUES (?, ?)"),
                            (user_id, json.dumps(msgs_data, ensure_ascii=False)))
                _pc.commit()
            finally:
                _pc.close()
        except Exception as pe:
            logging.error(f"Failed to save pending push: {pe}")

# --- 4. Dauding 貼文解析 ---
# 支援格式：Dauding 共乘平台的標準發文格式
_CITY_ALIAS = {
    "臺北市": "台北市", "臺中市": "台中市", "臺南市": "台南市", "臺東縣": "台東縣",
    "台北": "台北市", "新北": "新北市", "桃園": "桃園市", "新竹": "新竹市",
    "台中": "台中市", "彰化": "彰化縣", "南投": "南投縣", "雲林": "雲林縣",
    "嘉義": "嘉義市", "台南": "台南市", "高雄": "高雄市", "屏東": "屏東縣",
    "宜蘭": "宜蘭縣", "花蓮": "花蓮縣", "台東": "台東縣", "基隆": "基隆市",
    "苗栗": "苗栗縣",
}

def _normalize_city(raw):
    raw = raw.strip().lstrip("#")
    return _CITY_ALIAS.get(raw, raw)

def parse_dauding(text):
    """
    解析 Dauding 共乘貼文，回傳 dict 或 None（格式不符）。
    回傳欄位：user_type, p_count, s_city, e_city, way_point,
              fee, prefs, pickup, dropoff, time_range_start, time_range_end
    """
    lines = text.strip().splitlines()
    result = {}

    # 判斷是提供還是徵求
    first = lines[0] if lines else ""
    if "徵求" in first or "搭" in first:
        result["user_type"] = "seeker"
    elif "提供" in first or "載" in first or "開車" in first:
        result["user_type"] = "driver"
    else:
        return None  # 無法判斷身份 → 不是 Dauding 格式

    # 人數
    m = re.search(r'人數(\d+)', first) or re.search(r'(\d+)\s*位', first) or re.search(r'最多\s*(\d+)', first)
    result["p_count"] = m.group(1) if m else "1"

    for line in lines:
        line = line.strip()

        # 時間
        if "共乘時間" in line or "時間" in line:
            # 抓日期
            dm = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', line)
            # 抓時間範圍
            tm = re.search(r'(\d{3,4})\s*[-~～]\s*(\d{3,4})', line)
            if dm:
                y, mo, d = dm.group(1), dm.group(2).zfill(2), dm.group(3).zfill(2)
                if tm:
                    def _fmt(t):
                        t = t.zfill(4)
                        return f"{t[:2]}:{t[2:]}"
                    result["time_range_start"] = f"{y}-{mo}-{d}T{_fmt(tm.group(1))}"
                    result["time_range_end"]   = f"{y}-{mo}-{d}T{_fmt(tm.group(2))}"
                else:
                    result["time_range_start"] = f"{y}-{mo}-{d}T00:00"
                    result["time_range_end"]   = None

        # 路線
        elif "行程路線" in line or "路線" in line:
            rm = re.search(r'[#＃]?([^\s#＃=＝>➔→]+)\s*[=＝>➔→]+\s*[#＃]?([^\s#＃/(（]+)', line)
            if rm:
                result["s_city"] = _normalize_city(rm.group(1))
                result["e_city"] = _normalize_city(rm.group(2))

        # 上車地點
        elif "上車" in line and "是否" not in line:
            m2 = re.search(r'[：:]\s*[#＃]?(.+?)(?:\s*/|$)', line)
            if m2:
                val = m2.group(1).strip().lstrip("#＃")
                if val and val != "自輸入":
                    result["pickup"] = val

        # 下車地點
        elif "下車" in line and "是否" not in line:
            m2 = re.search(r'[：:]\s*[#＃]?(.+?)(?:\s*/|$)', line)
            if m2:
                val = m2.group(1).strip().lstrip("#＃")
                if val and val != "自輸入":
                    result["dropoff"] = val

        # 中途
        elif "中途" in line:
            if re.search(r'[：:]\s*是|接受', line):
                result["way_point_type"] = "接受中途"
            else:
                result["way_point_type"] = "僅限起迄"

        # 費用
        elif "費用" in line or "分攤" in line or "收費" in line:
            m2 = re.search(r'[：:]\s*[#＃]?(.+?)(?:\s*/|$)', line)
            if m2:
                val = m2.group(1).strip().lstrip("#＃")
                if val and val != "自輸入":
                    result["fee"] = val

    # way_point 組合（中途類型 + 上下車地點）
    wtype = result.pop("way_point_type", "接受中途")
    pickup  = result.pop("pickup", "")
    dropoff = result.pop("dropoff", "")
    wp_parts = [wtype]
    if pickup:  wp_parts.append(f"上車:{pickup}")
    if dropoff: wp_parts.append(f"下車:{dropoff}")
    result["way_point"] = "|".join(wp_parts)

    # 必填欄位檢查
    if not result.get("s_city") or not result.get("e_city"):
        return None

    return result


def get_dauding_confirm_flex(parsed, uid):
    """Dauding 解析後的確認卡片，讓使用者選時間後一鍵發布"""
    ut = parsed.get("user_type", "driver")
    main_color = "#00b900" if ut == "driver" else "#1e90ff"
    role_text = "載客/貨（提供座位）" if ut == "driver" else "搭車/寄物（徵求座位）"
    sc = parsed.get("s_city", "")
    ec = parsed.get("e_city", "")
    pc = parsed.get("p_count", "1")
    fee = parsed.get("fee", "（待填寫）")
    wp = parsed.get("way_point", "接受中途")
    tr_start = parsed.get("time_range_start", "")
    tr_end   = parsed.get("time_range_end", "")

    # 顯示用時間文字
    if tr_start and tr_end:
        time_display = f"{tr_start[5:10].replace('-','/')} {tr_start[11:]} ～ {tr_end[11:]}"
    elif tr_start:
        time_display = f"{tr_start[5:10].replace('-','/')} {tr_start[11:]}"
    else:
        time_display = "（請選擇）"

    # way_point 顯示
    wp_parts = wp.split("|")
    wp_display = wp_parts[0]
    if len(wp_parts) > 1:
        wp_display += "  " + "  ".join(wp_parts[1:])

    # 存 parsed 資料供後續 postback 取用（序列化成 json 存 user_state）
    import json as _json
    parsed_json = _json.dumps(parsed, ensure_ascii=False)

    bubble = {
        "type": "bubble",
        "header": {"type": "box", "layout": "vertical", "backgroundColor": main_color,
            "contents": [
                {"type": "text", "text": "📋 從 Dauding 匯入行程", "weight": "bold", "color": "#FFFFFF", "size": "sm"},
                {"type": "text", "text": "確認以下資訊，選好時間後發布", "color": "#FFFFFFBB", "size": "xs", "margin": "xs"}
            ]},
        "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "身份", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": role_text, "color": "#333333", "size": "sm", "flex": 5, "wrap": True}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": f"{sc} ➔ {ec}", "color": "#333333", "size": "sm", "flex": 5}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": time_display, "color": "#333333", "size": "sm", "flex": 5, "wrap": True}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "人數", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": f"{pc}人", "color": "#333333", "size": "sm", "flex": 5}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "費用", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": fee, "color": "#333333", "size": "sm", "flex": 5, "wrap": True}]},
            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                {"type": "text", "text": "中途", "color": "#aaaaaa", "size": "sm", "flex": 2},
                {"type": "text", "text": wp_display, "color": "#333333", "size": "sm", "flex": 5, "wrap": True}]},
            {"type": "text", "text": "⚠️ 系統只比對縣市，精確地點顯示在配對通知供對方參考", "size": "xxs", "color": "#aaaaaa", "margin": "md", "wrap": True}
        ]},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "button", "style": "primary", "height": "sm", "color": main_color,
             "action": {"type": "datetimepicker", "label": "🕒 選擇出發時間後發布",
                        "data": f"action=dauding_publish&parsed={quote(parsed_json, safe='')}",
                        "mode": "datetime",
                        "min": datetime.now().strftime("%Y-%m-%dT%H:%M")}},
            {"type": "button", "style": "link", "height": "sm", "color": "#999999",
             "action": {"type": "message", "label": "✖ 取消，自行填寫", "text": "我要載客/貨" if ut == "driver" else "我要搭車/寄物"}}
        ]}
    }
    return FlexSendMessage(alt_text="從 Dauding 匯入行程確認", contents=bubble)


# --- 4. Flex 卡片建構 ---
def get_publish_confirm_flex(res_data, match_id):
    ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid = res_data
    main_color = "#00b900" if ut == 'driver' else "#1e90ff"
    ps_text = ps.strip().rstrip(",") if ps else "（未選）"
    role_label = "載客/貨" if ut == "driver" else "搭車/寄物"
    share_text = f"【sun car 順咖媒合】{role_label}徵求 🚗\n\n📍 {sc}{sd} ➔ {ec}{ed}\n🕒 {tt.replace('T', ' ')}\n👤 {pc}人・費用：{fe}\n\n有要同方向的嗎？加 LINE Bot「sun car 順咖媒合」一起揪行程！"
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

def get_main_cat_menu():
    def _rows(items):
        """每排2個，奇數最後一個撐滿整排"""
        result = []
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            if len(pair) == 2:
                result.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": lbl, "text": f"規範:{txt}"}}
                    for lbl, txt in pair
                ]})
            else:
                lbl, txt = pair[0]
                result.append({"type": "button", "style": "secondary", "height": "sm",
                                "action": {"type": "message", "label": lbl, "text": f"規範:{txt}"}})
        return result
    def _bubble(title, items):
        return {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
                "backgroundColor": "#444441"
            },
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": _rows(items)},
            "footer": {"type": "box", "layout": "vertical", "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                 "action": {"type": "message", "label": "🚀 直接發布", "text": "最終確認發布"}}
            ]}
        }
    bubbles = [
        _bubble("🚗 車內規定", [
            ("禁菸禁檳榔", "全程禁菸禁檳榔"), ("禁止飲食", "禁止飲食"),
            ("可飲水", "可飲水"), ("保持整潔", "請保持車內整潔"),
            ("行車記錄器", "有行車記錄器"), ("兒童座椅", "車內有兒童座椅"),
            ("寵物裝籠", "寵物需裝籠推車"), ("謝絕寵物", "謝絕寵物"),
            ("依司機安排", "座位依司機安排"),
        ]),
        _bubble("💬 乘車風格", [
            ("歡迎聊天", "歡迎聊天"), ("安靜為主", "安靜為主"),
            ("可睡覺聽歌", "可睡覺聽歌"), ("歡迎攜伴", "歡迎攜伴同行"),
            ("可帶外食", "可帶外食上車"), ("限同性乘客", "限同性乘客"),
        ]),
        _bubble("🛣️ 路線偏好", [
            ("順路為主", "順路為主"), ("接受繞路", "接受繞路接送"),
            ("討論上下車", "可討論上下車點"), ("走交流道", "高速交流道為主"),
            ("可停休息站", "可停休息站"), ("依司機路線", "依司機路線為準"),
            ("回程順載", "回程願意順載"), ("固定通勤", "固定通勤路線"),
            ("長期通勤", "長期通勤歡迎"),
        ]),
        _bubble("💰 付款細節", [
            ("不接受議價", "不接受議價"), ("轉帳現金", "轉帳現金皆可"),
            ("自備零錢", "請自備零錢"), ("先付後乘", "先付後乘"),
            ("到達付款", "到達後付款"), ("可開收據", "可開收據"),
            ("學生減免", "學生低收減免"), ("寵物免費", "寵物不另收費"),
            ("捐款抵費", "捐款抵費用"),
        ]),
        _bubble("📦 行李與安全", [
            ("行李請告知", "大型行李請告知"), ("行李限一件", "行李限一件"),
            ("拒超重行李", "不接受超重行李"), ("可寄小包裹", "可寄送小型包裹"),
            ("務必準時", "務必準時"), ("身分驗證", "需身分驗證乘車"),
            ("穩健駕駛", "穩健駕駛風格"), ("乘客責任險", "投保乘客責任險"),
            ("全程定位", "全程開啟定位"),
        ]),
    ]
    return FlexSendMessage(alt_text="設定特殊需求", contents={"type": "carousel", "contents": bubbles})

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
            "contents": [{"type": "text", "text": "行程細節（依序點選）",
                          "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
            "backgroundColor": "#444441"
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                {"type": "text", "text": "中途上下車", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "接受中途", "text": "中途:接受"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "僅起迄點", "text": "中途:僅限起迄"}}
                ]},
                {"type": "separator"},
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
                {"type": "text", "text": "乘客費用（你期望的收費方式）", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "議價", "text": "費用:私訊議價"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "飲料", "text": "費用:請喝飲料"}}
                ]},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "公益", "text": "費用:免費公益"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "免費", "text": "費用:免費"}}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "刊登天數（到期自動下架，預設3天）", "size": "sm", "color": "#888780"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "1天", "text": "有效:1"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "3天", "text": "有效:3"}},
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "message", "label": "7天", "text": "有效:7"}}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "時間彈性（點此進入下一步 ↓）", "size": "sm", "color": "#1D9E75", "weight": "bold"},
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


# --- 免責聲明 Flex 卡片 ---
def get_terms_flex():
    def _bubble(title, lines, is_last=False):
        body_contents = [{"type": "text", "text": line, "size": "xs", "color": "#333333", "wrap": True, "margin": "md"} for line in lines]
        bubble = {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": "#CC0000",
                "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF", "size": "sm"}]},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_contents}
        }
        if is_last:
            bubble["footer"] = {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": "#CC0000", "height": "sm",
                 "action": {"type": "postback", "label": "✅ 我已閱讀並同意使用條款", "data": "action=agree_terms"}},
                {"type": "text", "text": "點擊同意後即可開始使用服務", "size": "xxs", "color": "#999999", "align": "center"}
            ]}
        return bubble

    def _bubble_with_footer(title, lines, footer_contents):
        body_contents = [{"type": "text", "text": line, "size": "xs", "color": "#333333", "wrap": True, "margin": "md"} for line in lines]
        return {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": "#CC0000",
                "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF", "size": "sm"}]},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_contents},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer_contents}
        }

    bubbles = [
        _bubble("⚖️ 1/6 平台性質與法規", [
            "• sun car 順咖媒合 為「資訊媒合平台」，僅提供行程配對服務，非汽車運輸業者。",
            "• 本平台不經營、調度或管理任何運輸服務，不對使用者之間的共乘或帶貨行為進行控制或監督。",
            "• 依《公路法》第77條及《汽車運輸業管理規則》，未經許可經營汽車運輸業屬違法行為（罰鍰新台幣5萬至15萬元，得按次連續處罰）。",
            "• 本平台明確禁止任何使用者將本服務用於收費載客營業。使用者若以營利為目的反覆載客，其法律責任由使用者自行承擔。",
            "• 本平台亦適用「順路帶貨/寄物」場景，此屬一般民事委託行為，非貨運承攬業。使用者應自行確認物品合法性，嚴禁運送毒品、仿冒品、危險物品或其他違禁物，違者自負一切法律責任。"
        ]),
        _bubble("💰 2/6 費用分攤原則", [
            "• 本平台僅適用於「順路共乘」場景，費用分攤應限於油資與過路費等實際成本。",
            "• 費用不得超過該趟行程之合理成本，嚴禁以營利為目的收取費用。",
            "• 本平台不設定、建議或介入任何費用金額，所有費用由共乘雙方自行協商。",
            "• 本平台目前不經手任何金流，未來若加入付款功能將另行公告並更新條款。"
        ]),
        _bubble("🛡️ 3/6 安全與保險", [
            "• 共乘過程中的人身安全、財物安全由使用者自行評估與承擔。",
            "• 本平台不對搭乘過程中發生之任何事故、傷害、財物損失、行程延誤或取消負責。",
            "• 本平台不提供任何形式之保險保障。",
            "• 駕駛人應確認持有有效駕照、車輛已通過定期檢驗，並自行確認車輛保險是否涵蓋共乘情境（部分保險公司可能將共乘視為營業行為而拒絕理賠）。",
            "• 乘客搭乘前應自行評估風險，建議告知親友行程資訊。",
            "• 順路帶貨/寄物之物品損毀、遺失、延誤，由委託人與帶貨方自行協議解決，本平台不承擔任何賠償責任。貴重物品請自行投保或勿委託陌生人攜帶。"
        ]),
        _bubble("🔒 4/6 個人資料與隱私", [
            "• 依《個人資料保護法》，本平台蒐集使用者行程資料（路線、時間、聯絡方式）僅作為配對媒合用途。",
            "• 配對成功後，雙方可見對方公開資訊（路線、時間、LINE ID 等），使用者應妥善保護自身個資。",
            "• 嚴禁利用本平台取得之個人資料進行騷擾、詐騙、跟蹤或其他不法行為，違者將立即停權並配合司法機關調查。",
            "• 如需刪除個人資料，請輸入「刪除我的資料」，系統將立即清除您的行程與使用記錄。如有其他個資問題請透過「回報問題」聯繫。"
        ]),
        _bubble("📋 5/6 免責與爭議處理", [
            "• 使用者之間因共乘產生之任何民事、刑事糾紛，由當事人自行解決，與本平台無涉。",
            "• 本平台保留隨時修改服務條款、暫停或終止服務之權利。",
            "• 本平台保留停權違規使用者之權利，不另行通知。",
            "• 本條款之解釋與適用以中華民國法律為準據法，如有爭議以台灣台北地方法院為第一審管轄法院。",
            "• 使用本服務即表示您已詳閱並同意上述所有條款。"
        ]),
        _bubble_with_footer("👨‍💻 6/6 關於本服務", [
            "• 本服務由一位台灣開發者利用業餘時間獨立開發與維護，目前無專職客服團隊。",
            "• 遇到問題請輸入「回報問題」，開發者會盡力於 1~3 個工作天內回應，感謝包容。",
            "• 伺服器採免費方案，首次回應可能有約 30 秒冷啟動延遲，非故障。",
            "• 每次配對成功，系統會主動推播通知雙方，這會消耗 LINE 官方的每月推播額度。免費方案每月僅 200 則，平台越熱絡越快用完。額度耗盡後配對通知將無法發送。",
            "• 如果這個服務對你有幫助，歡迎小額斗內支持升級方案，讓配對通知持續正常運作 ☕"
        ], [
            {"type": "button", "style": "primary", "color": "#CC0000", "height": "sm",
             "action": {"type": "postback", "label": "✅ 我已閱讀並同意使用條款", "data": "action=agree_terms"}},
            {"type": "button", "style": "link", "height": "sm", "color": "#aaaaaa",
             "action": {"type": "uri", "label": "☕ 斗內支持開發者", "uri": "https://p.ecpay.com.tw/8C9FE97"}},
            {"type": "text", "text": "點擊同意後即可開始使用服務", "size": "xxs", "color": "#999999", "align": "center"}
        ])
    ]
    return FlexSendMessage(alt_text="【重要】使用條款與免責聲明（請詳閱後同意）", contents={"type": "carousel", "contents": bubbles})

# --- 歡迎訊息 Flex 卡片（Item 3）---
def get_welcome_flex():
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#00b900",
            "contents": [
                {"type": "text", "text": "sun car 順咖媒合", "weight": "bold", "color": "#FFFFFF", "size": "lg"},
                {"type": "text", "text": "共乘・帶貨・順路媒合，省錢又環保", "color": "#FFFFFFBB", "size": "xs", "margin": "sm"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "lg",
            "contents": [
                {"type": "text", "text": "四步驟開始使用：", "weight": "bold", "size": "md"},
                {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    {"type": "text", "text": "1️⃣ 選擇身份：載客/貨（含順路帶貨）或 搭車/寄物", "size": "sm", "wrap": True},
                    {"type": "text", "text": "2️⃣ 設定出發時間", "size": "sm"},
                    {"type": "text", "text": "3️⃣ 選擇起點與終點", "size": "sm"},
                    {"type": "text", "text": "4️⃣ 填寫細節後發布，系統自動媒合", "size": "sm", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "text", "text": "隨時輸入「我的行程」管理已發布行程\n輸入「媒合規則」了解配對邏輯\n輸入「有新配對嗎」查詢未送達通知\n輸入「關閉配對通知」停止主動推播\n輸入「幫助」重新查看本說明\n輸入「回報問題」送出建議或回饋", "size": "xs", "color": "#888888", "wrap": True}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#00b900", "height": "sm",
                 "action": {"type": "message", "label": "🚗 我要載客/貨", "text": "我要載客/貨"}},
                {"type": "button", "style": "primary", "color": "#1e90ff", "height": "sm",
                 "action": {"type": "message", "label": "🙋 我要搭車/寄物", "text": "我要搭車/寄物"}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#E07B00",
                 "action": {"type": "message", "label": "🔍 瀏覽現有行程", "text": "找行程"}},
                {"type": "button", "style": "secondary", "height": "sm",
                 "action": {"type": "message", "label": "📝 回報問題／建議", "text": "回報問題"}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#CC0000",
                 "action": {"type": "message", "label": "⚖️ 免責聲明與使用條款", "text": "免責聲明"}},
                {"type": "button", "style": "link", "height": "sm", "color": "#aaaaaa",
                 "action": {"type": "uri", "label": "☕ 斗內支持開發者", "uri": "https://p.ecpay.com.tw/8C9FE97"}}
            ]
        }
    }
    return FlexSendMessage(alt_text="歡迎使用 sun car 順咖媒合！", contents=bubble)

# --- 媒合規則 Flex 卡片（Item 4）---
def get_rules_flex():
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#444441",
            "contents": [
                {"type": "text", "text": "sun car 順咖媒合", "weight": "bold", "color": "#FFFFFF", "size": "sm"},
                {"type": "text", "text": "📋 媒合規則說明", "weight": "bold", "color": "#FFFFFFCC", "size": "md", "margin": "xs"}
            ]
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
                    {"type": "text", "text": "選 14:00 出發＋願意彈性 → 系統搜尋 10:00~18:00（前後各 4 小時）。選精確時間則只搜前後 1 小時。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "🧭 方向匹配", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "只配同方向！北→南不會配到南→北。同縣市內依區域分群配對（如台北東區只配東區附近）。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "📦 帶貨/寄物", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "發布「載客/貨」行程時可接受順路帶貨委託。費用和物品條件由雙方自行協議，請勿運送違禁品。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "🔔 自動通知＆過期", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "有人發布同向行程，系統主動推播通知雙方。行程依設定天數自動下架（最長 7 天）。", "size": "xs", "color": "#666666", "wrap": True}
                ]},
                {"type": "separator"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
                    {"type": "text", "text": "⭐ 評分系統", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "行程完成後，配對雙方可互相評分（1~5 顆星）。評分顯示在對方的行程卡片上供其他人參考。", "size": "xs", "color": "#666666", "wrap": True}
                ]}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                 "action": {"type": "message", "label": "🔍 找所有行程", "text": "找行程"}},
                {"type": "button", "style": "secondary", "height": "sm",
                 "action": {"type": "message", "label": "📖 回到使用說明", "text": "幫助"}},
                {"type": "button", "style": "link", "height": "sm", "color": "#aaaaaa",
                 "action": {"type": "uri", "label": "☕ 斗內支持開發者", "uri": "https://p.ecpay.com.tw/8C9FE97"}}
            ]
        }
    }
    return FlexSendMessage(alt_text="媒合規則說明", contents=bubble)

# --- 被動媒合推播 Flex 卡片 ---
def get_match_notify_flex(sc, sd, ec, ed, tt, pc, fe, prefs, line_id, way_point=""):
    prefs_text = prefs.strip().rstrip(",") if prefs else "（未設定）"
    contact_contents = [{"type": "text", "text": "有人發布了與您同向的行程！", "size": "xs", "color": "#888888", "align": "center"}]
    if line_id:
        contact_contents.append({"type": "button", "style": "primary", "height": "sm", "color": "#00b900", "margin": "sm",
            "action": {"type": "uri", "label": "💬 加 LINE 聯絡", "uri": f"https://line.me/ti/p/~{line_id}"}})

    # 解析 way_point 取上下車地點（格式：接受中途|上車:XXX|下車:YYY）
    body_contents = [
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
    ]
    if way_point:
        wp_parts = way_point.split("|")
        for part in wp_parts[1:]:  # 跳過第一段「接受中途/僅限起迄」
            if ":" in part:
                label, val = part.split(":", 1)
                body_contents.append({"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                    {"type": "text", "text": label, "color": "#aaaaaa", "size": "sm", "flex": 1},
                    {"type": "text", "text": val, "color": "#555555", "size": "sm", "flex": 4, "wrap": True}]})
    body_contents.append({"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
        {"type": "text", "text": "標籤", "color": "#aaaaaa", "size": "sm", "flex": 1},
        {"type": "text", "text": prefs_text, "color": "#999999", "size": "xs", "flex": 4, "wrap": True}]})

    bubble = {
        "type": "bubble",
        "header": {"type": "box", "layout": "vertical",
            "contents": [{"type": "text", "text": "🔔 新的順路配對！", "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
            "backgroundColor": "#1D9E75"},
        "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_contents},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": contact_contents}
    }
    return FlexSendMessage(alt_text="🔔 新的順路配對！", contents=bubble)

# --- 發布核心邏輯（供 最終確認發布 和 WAIT_LINE_ID 共用）---
def do_publish(uid, reply_token):
    conn = get_db()
    try:
        res = conn.execute(q('SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, temp_expire FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        if not res:
            safe_reply(reply_token, TextSendMessage(text="⚠️ 找不到暫存資料，請重新開始。"))
            return
        ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid, exp = res
        lid = lid or ''
        expire_days = int(exp) if exp else 3
        expires_at = (datetime.now() + timedelta(days=expire_days)).strftime("%Y-%m-%dT%H:%M")

        # 發行程數量上限（最多 3 筆 active）
        active_count = conn.execute(q(
            "SELECT COUNT(*) FROM matches WHERE user_id = ? AND status = 'active'"
        ), (uid,)).fetchone()[0]
        if active_count >= 3:
            safe_reply(reply_token, TextSendMessage(
                text="⚠️ 你目前已有 3 筆生效中的行程，請先刪除舊行程後再發布新行程。\n\n輸入「我的行程」可管理現有行程。"
            ))
            return

        # 防重複發布（原子性：唯一索引 + ON CONFLICT，避免競態條件）
        cursor = conn.cursor()
        if USE_PG:
            cursor.execute(q('INSERT INTO matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs, line_id, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING id'),
                           (uid, ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid, expires_at))
            row = cursor.fetchone()
            if row is None:
                safe_reply(reply_token, TextSendMessage(text="⚠️ 您已有一筆相同的行程（相同路線與時間），請先刪除舊行程再重新發布。"))
                return
            new_id = row[0]
        else:
            cursor.execute('INSERT OR IGNORE INTO matches (user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, way_point, p_count, fee, flexible, prefs, line_id, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (uid, ut, tt, sc, sd, ec, ed, wy, pc, fe, fx, ps, lid, expires_at))
            new_id = cursor.lastrowid
            if not new_id:
                safe_reply(reply_token, TextSendMessage(text="⚠️ 您已有一筆相同的行程（相同路線與時間），請先刪除舊行程再重新發布。"))
                return
        conn.commit()
    finally:
        conn.close()

    m_list = find_matches_v15(uid, ut, tt, sc, sd, ec, ed, fx, wy, pc)
    output = [get_publish_confirm_flex(res[:12], new_id)]

    if m_list:
        match_bubbles = []
        rating_conn = get_db()
        for m in m_list:
            m_prefs_text = (m[9].strip().rstrip(",") if m[9] else "（未設定）")
            m_line_id = m[10] or ''
            avg, cnt = get_user_rating(rating_conn, m[0])
            rating_text = f"⭐ {avg}（{cnt}筆）" if avg else "暫無評分"
            if m_line_id:
                contact_btn = {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                    "action": {"type": "uri", "label": "💬 加 LINE 聯絡", "uri": f"https://line.me/ti/p/~{m_line_id}"}}
            else:
                contact_btn = {"type": "button", "style": "primary", "height": "sm", "color": "#E07B00",
                    "action": {"type": "postback", "label": "📨 通知對方留聯絡方式", "data": f"action=contact_req&to={m[0]}&route={m[2]}{m[3]}→{m[4]}{m[5]}"}}
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
                        {"type": "text", "text": "評分", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": rating_text, "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "標籤", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": m_prefs_text, "color": "#999999", "size": "xs", "flex": 4, "wrap": True}]}
                ]},
                "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    contact_btn,
                    {"type": "button", "style": "link", "height": "sm",
                     "action": {"type": "uri", "label": "☕ 支持開發者", "uri": "https://p.ecpay.com.tw/8C9FE97"},
                     "color": "#aaaaaa"}
                ]}
            })
            # 儲存配對關係
            pair_conn = get_db()
            try:
                if USE_PG:
                    pair_conn.execute(q('INSERT INTO pairs (uid_a, match_id_a, uid_b, match_id_b) VALUES (?,?,?,?)'),
                                      (uid, new_id, m[0], m[11]))
                else:
                    pair_conn.execute('INSERT OR IGNORE INTO pairs (uid_a, match_id_a, uid_b, match_id_b) VALUES (?,?,?,?)',
                                      (uid, new_id, m[0], m[11]))
                pair_conn.commit()
            finally:
                pair_conn.close()
            # 被動推播：通知既有配對者（含發布者的 LINE ID），尊重對方通知設定
            if is_notify_enabled(m[0]):
                safe_push(m[0], get_match_notify_flex(sc, sd, ec, ed, tt, pc, fe, ps, lid, wy))

        rating_conn.close()
        output.append(FlexSendMessage(alt_text="偵測到順路配對！",
            contents={"type": "carousel", "contents": match_bubbles}))
    else:
        # 查附近同方向的行程數，給使用者有感的等待資訊
        try:
            nc = get_db()
            nearby = nc.execute(q(
                "SELECT COUNT(*) FROM matches WHERE status = 'active' AND user_type = ? AND (s_city = ? OR e_city = ? OR s_city = ? OR e_city = ?)"
            ), (('seeker' if ut == 'driver' else 'driver'), sc, sc, ec, ec)).fetchone()[0]
            nc.close()
            if nearby > 0:
                hint = f"🔍 目前 {sc}→{ec} 方向有 {nearby} 筆潛在行程，系統正持續比對，有配對立即通知你！"
            else:
                hint = f"📭 目前此方向暫無行程，你的行程已發布，有人發布同向行程時會自動推播通知！"
        except:
            hint = "🔎 行程已發布，有人發布同向行程時會自動通知。"
        output.append(TextSendMessage(text=hint))

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

    if sc == ec:
        user_direction = 0  # 明確同縣市
    else:
        s_w, e_w = CITY_WEIGHTS.get(sc, 0), CITY_WEIGHTS.get(ec, 0)
        user_direction = 1 if e_w > s_w else (-1 if e_w < s_w else 0)

    c.execute(q("SELECT user_id, time_info, s_city, s_dist, e_city, e_dist, fee, way_point, p_count, prefs, line_id, id FROM matches WHERE user_type = ? AND user_id != ? AND status = 'active' AND time_info BETWEEN ? AND ?"),
              [target_type, user_id, s_range, e_range])
    raw_res = c.fetchall()

    final_matches = []
    try:
        user_p = int(str(p_count).strip().split()[0])
    except:
        user_p = 1  # 無法解析時預設 1，避免 crash 導致全部配不到

    for m in raw_res:
        m_uid, m_time, m_sc, m_sd, m_ec, m_ed, m_fee, m_way, m_pc, m_prefs, m_line_id, m_id = m
        if m_sc == m_ec:
            match_direction = 0
        else:
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

        try:
            match_p = int(str(m_pc).strip().split()[0])
        except:
            match_p = 1
        # driver.user_p = 能載幾人；seeker.user_p = 需要幾個座位
        # 配對條件：driver 能載人數 >= seeker 需要座位數
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
    # 依出發時間與用戶時間的接近度排序，最近的配對優先
    try:
        final_matches.sort(key=lambda m: abs((datetime.strptime(m[1], "%Y-%m-%dT%H:%M") - base_t).total_seconds()))
    except Exception:
        pass
    return final_matches[:5]

# --- 6. Flask 路由 ---
@app.route("/", methods=['GET', 'POST'])
def index():
    return "Bot is running!"

@app.route("/about", methods=['GET'])
def about():
    return """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sun car 順咖媒合</title>
<style>
  body{font-family:'Noto Sans TC',sans-serif;max-width:680px;margin:40px auto;padding:0 20px;color:#333;line-height:1.8}
  h1{color:#2c7a4b;font-size:1.8em;margin-bottom:4px}
  h2{color:#2c7a4b;font-size:1.1em;margin-top:32px;border-bottom:2px solid #d4edda;padding-bottom:4px}
  .subtitle{color:#666;margin-top:0;margin-bottom:28px}
  .btn{display:inline-block;background:#06c755;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin-top:8px}
  ul{padding-left:20px}
  li{margin-bottom:6px}
  .note{font-size:0.88em;color:#888;margin-top:40px;border-top:1px solid #eee;padding-top:16px}
</style>
</head>
<body>
<h1>sun car 順咖媒合</h1>
<p class="subtitle">共乘・帶貨・順路媒合，省錢又環保</p>

<p>sun car 順咖媒合 是一個台灣在地的 P2P 共乘媒合服務。<br>
透過 LINE Bot 自動配對同向行程，讓有空位的司機和需要搭車的乘客找到彼此。</p>

<h2>適合誰使用</h2>
<p>🚗 <strong>司機／貨主</strong>：長途開車有空位，順路帶人或帶貨，分攤油資過路費。<br>
🙋 <strong>乘客／寄物方</strong>：需要搭車或寄送物品，找順路的人幫忙，比計程車便宜。</p>

<h2>如何使用</h2>
<ol>
<li>加入 LINE 官方帳號</li>
<li>同意使用條款</li>
<li>選擇身份發布行程</li>
<li>系統自動配對，有結果主動通知</li>
</ol>

<h2>服務特色</h2>
<ul>
<li>自動方向配對，北→南只配北→南</li>
<li>時間彈性搜尋（前後 1～4 小時）</li>
<li>支援中途上下車</li>
<li>支援順路帶貨／寄物</li>
<li>配對成功後互評系統</li>
</ul>

<h2>開始使用</h2>
<p>LINE 官方帳號：<strong>@321nmofi</strong></p>
<a class="btn" href="https://line.me/R/ti/p/@321nmofi">加入 LINE Bot</a>
<p style="margin-top:12px;color:#666">或在 LINE 搜尋：<strong>sun car 順咖媒合</strong></p>

<h2>聯絡</h2>
<p>使用上有任何問題，請在 LINE Bot 內輸入「回報問題」。</p>

<div class="note">
<strong>免責聲明</strong><br>
本平台為資訊媒合服務，非汽車運輸業者。使用者之間的共乘行為由雙方自行負責。詳細條款請於 LINE Bot 內查閱。
</div>
</body>
</html>""", 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route("/ping", methods=['GET'])
def ping():
    """輕量 keep-alive endpoint，給 UptimeRobot / 外部監控用"""
    return "pong", 200

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

def _check_admin_token():
    """驗證請求帶有正確的 admin token（query string: ?token=xxx）"""
    expected = os.getenv('ADMIN_SECRET', '')
    if not expected:
        return True  # 未設定時不驗證（開發環境）
    return request.args.get('token') == expected

@app.route("/debug-bot", methods=['GET'])
def debug_bot():
    if not _check_admin_token():
        return {"error": "unauthorized"}, 401
    try:
        info = line_bot_api.get_bot_info()
        return {"status": "ok", "bot_name": info.display_name, "bot_id": info.user_id}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500

@app.route("/logs", methods=['GET'])
def show_logs():
    if not _check_admin_token():
        return {"error": "unauthorized"}, 401
    return {"logs": _log_store}

@app.route("/stats", methods=['GET'])
def stats():
    if not _check_admin_token():
        return {"error": "unauthorized"}, 401
    try:
        conn = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        total_active = conn.execute(q("SELECT COUNT(*) FROM matches WHERE status = 'active'")).fetchone()[0]
        today_new = conn.execute(q("SELECT COUNT(*) FROM matches WHERE created_at::text LIKE ? "), (f"{today}%",)).fetchone()[0] if USE_PG else conn.execute("SELECT COUNT(*) FROM matches WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
        total_ratings = conn.execute(q("SELECT COUNT(*) FROM ratings")).fetchone()[0]
        avg_score_row = conn.execute(q("SELECT AVG(score) FROM ratings")).fetchone()
        avg_score = round(float(avg_score_row[0]), 2) if avg_score_row and avg_score_row[0] else 0
        conn.close()
        return {"active_trips": total_active, "today_new": today_new, "total_ratings": total_ratings, "avg_score": avg_score}
    except Exception as e:
        return {"error": str(e)}, 500

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
    uid = event.source.user_id
    conn = get_db()
    try:
        if USE_PG:
            conn.execute(q('INSERT INTO user_state (user_id) VALUES (?) ON CONFLICT (user_id) DO NOTHING'), (uid,))
        else:
            conn.execute('INSERT OR IGNORE INTO user_state (user_id) VALUES (?)', (uid,))
        conn.commit()
    finally:
        conn.close()
    safe_reply(event.reply_token, get_terms_flex())

# --- 8. Postback 處理 ---
@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    data = event.postback.data
    if not data:
        return

    # --- 單次 DB query 同時檢查封鎖 + 同意條款 ---
    try:
        _pc = get_db()
        try:
            _pb_state = _pc.execute(q("SELECT agreed_terms FROM user_state WHERE user_id = ?"), (uid,)).fetchone()
            _pb_blocked = _pc.execute(q("SELECT user_id FROM blocked_users WHERE user_id = ?"), (uid,)).fetchone()
        finally:
            _pc.close()
    except:
        _pb_state, _pb_blocked = None, None

    if _pb_blocked:
        return

    try:
        if data == "action=agree_terms":
            conn = get_db()
            try:
                if USE_PG:
                    conn.execute(q('INSERT INTO user_state (user_id, agreed_terms) VALUES (?, 1) ON CONFLICT (user_id) DO UPDATE SET agreed_terms = 1'), (uid,))
                else:
                    conn.execute('INSERT OR IGNORE INTO user_state (user_id) VALUES (?)', (uid,))
                    conn.execute('UPDATE user_state SET agreed_terms = 1 WHERE user_id = ?', (uid,))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, [
                TextSendMessage(text="✅ 感謝同意使用條款！歡迎使用 sun car 順咖媒合 🎉"),
                get_welcome_flex()
            ])
            return

        if not _pb_state or not _pb_state[0]:
            safe_reply(event.reply_token, get_terms_flex())
            return

        if data == "select_time":
            t = event.postback.params['datetime']
            if t < datetime.now().strftime("%Y-%m-%dT%H:%M"):
                safe_reply(event.reply_token, TextSendMessage(
                    text="⚠️ 出發時間不能是過去，請重新選擇：",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=DatetimePickerAction(label="🕒 重新選擇", data="select_time", mode="datetime"))
                    ])
                ))
                return
            conn = get_db()
            try:
                conn.execute(q('UPDATE user_state SET temp_time = ?, step = ? WHERE user_id = ?'), (t, "START", uid))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, get_area_carousel("📍 第一步：選擇【出發地】區域"))

        elif data.startswith("action=delete"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            try:
                conn.execute(q('DELETE FROM matches WHERE id = ? AND user_id = ?'), (match_id, uid))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"🗑️ 已成功刪除行程 (編號: {match_id})"))

        elif data.startswith("action=complete"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            try:
                conn.execute(q("UPDATE matches SET status = 'completed' WHERE id = ? AND user_id = ?"), (match_id, uid))
                conn.commit()
                pairs = conn.execute(q(
                    "SELECT uid_a, match_id_a, uid_b, match_id_b FROM pairs WHERE match_id_a = ? OR match_id_b = ?"
                ), (match_id, match_id)).fetchall()
            finally:
                conn.close()

            partners = []
            for p in pairs:
                ua, ma, ub, mb = p
                if ua == uid:
                    partners.append((ub, mb, ma))
                else:
                    partners.append((ua, ma, mb))

            if partners:
                partner_uid, partner_mid, my_mid = partners[0]
                def _rate_qr(ratee, mid):
                    return QuickReply(items=[
                        QuickReplyButton(action=PostbackAction(
                            label=f"{'⭐'*i}",
                            data=f"action=rate&ratee={ratee}&match_id={mid}&score={i}"
                        )) for i in range(1, 6)
                    ])
                safe_reply(event.reply_token, TextSendMessage(
                    text="🎉 行程完成！請為配對對象評分：",
                    quick_reply=_rate_qr(partner_uid, partner_mid)
                ))
                if is_notify_enabled(partner_uid):
                    safe_push(partner_uid, TextSendMessage(
                        text="🔔 你的配對行程已完成！請為對方評分：",
                        quick_reply=_rate_qr(uid, my_mid)
                    ))
            else:
                safe_reply(event.reply_token, TextSendMessage(text="🎉 行程已標記完成！"))

        elif data.startswith("action=rate"):
            params = dict(parse_qsl(data))
            ratee_id = params.get('ratee')
            match_id = params.get('match_id')
            score = params.get('score')
            if not ratee_id or not match_id or not score:
                safe_reply(event.reply_token, TextSendMessage(text="⚠️ 評分資料不完整。"))
                return
            if uid == ratee_id:
                safe_reply(event.reply_token, TextSendMessage(text="⚠️ 不能為自己評分。"))
                return
            conn = get_db()
            try:
                pair = conn.execute(q(
                    "SELECT id FROM pairs WHERE (uid_a = ? AND uid_b = ?) OR (uid_a = ? AND uid_b = ?)"
                ), (uid, ratee_id, ratee_id, uid)).fetchone()
                if not pair:
                    safe_reply(event.reply_token, TextSendMessage(text="⚠️ 找不到你們的配對記錄，無法評分。"))
                    return
                if USE_PG:
                    conn.execute(q(
                        'INSERT INTO ratings (rater_id, ratee_id, match_id, score) VALUES (?,?,?,?) ON CONFLICT (match_id, rater_id) DO NOTHING'
                    ), (uid, ratee_id, match_id, score))
                else:
                    conn.execute(
                        'INSERT OR IGNORE INTO ratings (rater_id, ratee_id, match_id, score) VALUES (?,?,?,?)',
                        (uid, ratee_id, match_id, score)
                    )
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"感謝評價！你給了 {'⭐' * int(score)}"))

        elif data.startswith("action=cancel"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            try:
                conn.execute(q("UPDATE matches SET status = 'cancelled' WHERE id = ? AND user_id = ?"), (match_id, uid))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(text=f"🚫 行程已取消 (編號: {match_id})"))

        elif data.startswith("action=report"):
            params = dict(parse_qsl(data))
            target_uid = params.get('uid', '')
            trip_id = params.get('trip_id', '')
            if ADMIN_LINE_ID and target_uid:
                safe_push(ADMIN_LINE_ID, TextSendMessage(
                    text=f"🚨 檢舉通報\n被檢舉用戶：{target_uid}\n行程編號：{trip_id}\n檢舉者：{uid}\n\n如需封鎖請回覆：/ban {target_uid}"
                ))
            safe_reply(event.reply_token, TextSendMessage(text="✅ 已送出檢舉，我們會盡快處理。感謝你的回報！"))

        elif data.startswith("action=edit_line_id"):
            params = dict(parse_qsl(data))
            match_id = params.get('id')
            conn = get_db()
            try:
                if USE_PG:
                    conn.execute(q('''INSERT INTO user_state (user_id, step)
                        VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET step = EXCLUDED.step'''),
                        (uid, f'EDIT_LINE_ID:{match_id}'))
                else:
                    conn.execute('INSERT OR REPLACE INTO user_state (user_id, step) VALUES (?, ?)',
                        (uid, f'EDIT_LINE_ID:{match_id}'))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(
                text="請輸入新的 LINE ID（輸入後直接送出，不需加 @）：",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="清除LINE ID", text="清除LINE ID"))
                ])
            ))

        elif data.startswith("contact_line="):
            line_id = data.split("=")[1]
            safe_reply(event.reply_token, TextSendMessage(
                text=f"💬 對方的 LINE ID：{line_id}\n\n點此加好友：https://line.me/ti/p/~{line_id}"
            ))

        elif data.startswith("action=contact_req"):
            params = dict(parse_qsl(data))
            target_uid = params.get('to', '')
            route = params.get('route', '（未知路線）')
            if target_uid:
                safe_push(target_uid, TextSendMessage(
                    text=f"👋 有人想聯絡你的行程！\n路線：{route}\n\n點下方按鈕可直接把 LINE ID 傳給對方：",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=PostbackAction(
                            label="💬 回傳我的LINE ID",
                            data=f"action=reply_line_id&to={uid}"
                        ))
                    ])
                ))
            safe_reply(event.reply_token, TextSendMessage(text="✅ 已通知對方，若對方回傳 LINE ID 你會立即收到！"))

        elif data.startswith("action=reply_line_id"):
            params = dict(parse_qsl(data))
            to_uid = params.get('to', '')
            conn = get_db()
            try:
                if USE_PG:
                    conn.execute(q('''INSERT INTO user_state (user_id, step)
                        VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET step = EXCLUDED.step'''),
                        (uid, f'SHARE_LINE_ID:{to_uid}'))
                else:
                    conn.execute('INSERT OR REPLACE INTO user_state (user_id, step) VALUES (?, ?)',
                        (uid, f'SHARE_LINE_ID:{to_uid}'))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(text="請直接輸入你的 LINE ID（如 @abc123），我們會立即傳給對方："))

        elif data.startswith("action=dauding_publish"):
            import json as _json
            from urllib.parse import unquote
            params = dict(parse_qsl(data))
            parsed_json = unquote(params.get("parsed", "{}"))
            t = event.postback.params.get('datetime', '')
            if not t or t < datetime.now().strftime("%Y-%m-%dT%H:%M"):
                safe_reply(event.reply_token, TextSendMessage(
                    text="⚠️ 出發時間不能是過去，請重新選擇：",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=DatetimePickerAction(label="🕒 重新選擇", data=data, mode="datetime"))
                    ])
                ))
                return
            try:
                parsed = _json.loads(parsed_json)
            except:
                safe_reply(event.reply_token, TextSendMessage(text="⚠️ 匯入資料解析失敗，請重新貼上 Dauding 行程。"))
                return
            ut   = parsed.get("user_type", "driver")
            sc   = parsed.get("s_city", "")
            ec   = parsed.get("e_city", "")
            pc   = parsed.get("p_count", "1")
            fee  = parsed.get("fee", "面議")
            wp   = parsed.get("way_point", "接受中途")
            # 寫入 user_state 再呼叫 do_publish
            conn = get_db()
            try:
                # Dauding 匯入不知道確切行政區，留空讓 matching 只比對縣市
                s_dist = ""
                e_dist = ""
                if USE_PG:
                    conn.execute(q('''INSERT INTO user_state
                        (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist,
                         temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step, agreed_terms)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                        ON CONFLICT (user_id) DO UPDATE SET
                        current_type=EXCLUDED.current_type, temp_time=EXCLUDED.temp_time,
                        s_city=EXCLUDED.s_city, s_dist=EXCLUDED.s_dist,
                        e_city=EXCLUDED.e_city, e_dist=EXCLUDED.e_dist,
                        temp_way=EXCLUDED.temp_way, temp_count=EXCLUDED.temp_count,
                        temp_fee=EXCLUDED.temp_fee, temp_flex=EXCLUDED.temp_flex,
                        temp_prefs=EXCLUDED.temp_prefs, temp_line_id=EXCLUDED.temp_line_id,
                        step=EXCLUDED.step'''),
                        (uid, ut, t, sc, s_dist, ec, e_dist, wp, pc, fee, "不彈性", "", "", "WAIT_LINE_ID"))
                else:
                    conn.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step, agreed_terms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
                        (uid, ut, t, sc, s_dist, ec, e_dist, wp, pc, fee, "不彈性", "", "", "WAIT_LINE_ID"))
                conn.commit()
            finally:
                conn.close()
            do_publish(uid, event.reply_token)

        elif data.startswith("action=extend"):
            params = dict(parse_qsl(data))
            match_id = params.get('id', '')
            if not match_id:
                safe_reply(event.reply_token, TextSendMessage(text="⚠️ 找不到行程編號。"))
                return
            conn = get_db()
            try:
                row = conn.execute(q("SELECT user_id, s_city, e_city, expires_at FROM matches WHERE id = ? AND status = 'active'"), (match_id,)).fetchone()
                if not row or row[0] != uid:
                    safe_reply(event.reply_token, TextSendMessage(text="⚠️ 只能延長自己的行程。"))
                    return
                _, sc, ec, old_exp = row
                try:
                    new_exp = (datetime.strptime(str(old_exp)[:16], "%Y-%m-%dT%H:%M") + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
                except:
                    new_exp = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
                conn.execute(q("UPDATE matches SET expires_at = ?, reminded_at = NULL WHERE id = ?"), (new_exp, match_id))
                conn.commit()
            finally:
                conn.close()
            safe_reply(event.reply_token, TextSendMessage(
                text=f"✅ 行程已延長 3 天！\n{sc} ➔ {ec}\n新下架時間：{new_exp[5:16]}"
            ))

    except Exception as e:
        logging.error(f"Postback error for {uid}: {e}")
        safe_reply(event.reply_token, TextSendMessage(text="⚠️ 操作發生錯誤，請重新嘗試。"))

# --- 9. 訊息處理（主邏輯）---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    uid = event.source.user_id

    # --- 單次 DB query 同時檢查封鎖狀態 + 同意條款（減少 round-trip）---
    try:
        _gc = get_db()
        try:
            _state = _gc.execute(q(
                "SELECT agreed_terms FROM user_state WHERE user_id = ?"
            ), (uid,)).fetchone()
            _blocked = _gc.execute(q(
                "SELECT user_id FROM blocked_users WHERE user_id = ?"
            ), (uid,)).fetchone()
        finally:
            _gc.close()
    except:
        _state, _blocked = None, None

    if _blocked:
        return

    if msg in ["免責聲明", "使用條款"]:
        safe_reply(event.reply_token, get_terms_flex())
        return

    if not _state or not _state[0]:
        safe_reply(event.reply_token, get_terms_flex())
        return

    # --- Dauding 貼文匯入偵測（在一般指令之前）---
    if len(msg) > 30 and ("共乘時間" in msg or "行程路線" in msg or "徵求座位" in msg or "提供座位" in msg):
        parsed = parse_dauding(msg)
        if parsed:
            safe_reply(event.reply_token, get_dauding_confirm_flex(parsed, uid))
            return

    # --- 補送失敗推播（每用戶最多每 60 秒觸發一次，避免拖慢回應）---
    if time.time() - _flush_last.get(uid, 0) > 60:
        _flush_last[uid] = time.time()
        threading.Thread(target=flush_pending_pushes, args=(uid,), daemon=True).start()

    # --- 有新配對嗎 ---
    if msg in ["有新配對嗎", "新配對", "配對通知"]:
        conn = get_db()
        try:
            cnt = conn.execute(q("SELECT COUNT(*) FROM pending_pushes WHERE user_id = ?"), (uid,)).fetchone()[0]
        finally:
            conn.close()
        if cnt > 0:
            safe_reply(event.reply_token, TextSendMessage(text=f"📬 找到 {cnt} 則待送通知，正在補送..."))
            flush_pending_pushes(uid)
        else:
            safe_reply(event.reply_token, TextSendMessage(text="✅ 目前沒有未送出的配對通知。"))
        return

    # --- 配對通知開關 ---
    if msg in ["關閉配對通知", "停止配對通知"]:
        conn = get_db()
        try:
            conn.execute(q("UPDATE user_state SET notify_on_match = 0 WHERE user_id = ?"), (uid,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(text="🔕 已關閉配對通知。\n\n有新配對時不會主動通知你，可隨時輸入「開啟配對通知」恢復。"))
        return

    if msg in ["開啟配對通知", "恢復配對通知"]:
        conn = get_db()
        try:
            conn.execute(q("UPDATE user_state SET notify_on_match = 1 WHERE user_id = ?"), (uid,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(text="🔔 已開啟配對通知。有新配對時會主動通知你。"))
        return

    # --- 我的行程 ---
    if msg == "我的行程":
        conn = get_db()
        try:
            my_matches = conn.execute(
                q("SELECT id, time_info, s_city, s_dist, e_city, e_dist, user_type, fee, line_id, view_count, expires_at FROM matches WHERE user_id = ? AND status = 'active' ORDER BY time_info DESC LIMIT 10"),
                (uid,)
            ).fetchall()
        finally:
            conn.close()

        if not my_matches:
            safe_reply(event.reply_token, TextSendMessage(text="📭 您目前沒有生效中的行程。"))
        else:
            bubbles = []
            for m in my_matches:
                m_id, t_info, sc, sd, ec, ed, utype, fee, lid, vc, exp_at = m
                role = "🚗 載客/貨" if utype == 'driver' else "🙋 搭車/寄物"
                hdr_color = "#1D9E75" if utype == 'driver' else "#1e90ff"
                lid_text = f"@{lid}" if lid else "未設定"
                vc_text = f"{vc or 0} 次"
                exp_text = str(exp_at)[5:16] if exp_at else "未知"
                bubbles.append({
                    "type": "bubble",
                    "header": {"type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": role, "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
                        "backgroundColor": hdr_color},
                    "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": f"{sc}{sd} ➔ {ec}{ed}", "color": "#333333", "size": "sm", "flex": 4, "wrap": True}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": t_info[5:16], "color": "#333333", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "費用", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": fee or "未設定", "color": "#333333", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "LINE ID", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": lid_text, "color": "#333333", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "瀏覽", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": vc_text, "color": "#888888", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                            {"type": "text", "text": "下架", "color": "#aaaaaa", "size": "sm", "flex": 1},
                            {"type": "text", "text": exp_text, "color": "#e07b00", "size": "sm", "flex": 4}]},
                    ]},
                    "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                         "action": {"type": "postback", "label": "✅ 已搭乘完成", "data": f"action=complete&id={m_id}"}},
                        {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                            {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                             "action": {"type": "postback", "label": "✏️ 改ID", "data": f"action=edit_line_id&id={m_id}"}},
                            {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                             "action": {"type": "postback", "label": "🗑️ 刪除", "data": f"action=delete&id={m_id}"}}
                        ]}
                    ]}
                })
            safe_reply(event.reply_token, FlexSendMessage(
                alt_text="我的行程",
                contents={"type": "carousel", "contents": bubbles}
            ))
        return

    # --- 媒合規則（Item 4）---
    elif msg == "媒合規則":
        safe_reply(event.reply_token, get_rules_flex())
        return

    elif msg in ["myid", "/myid", "我的id", "我的ID"]:
        safe_reply(event.reply_token, TextSendMessage(text=f"你的 LINE User ID：\n{uid}"))
        return

    # --- 幫助 / 使用說明（Item 3）---
    elif msg in ["回報問題", "建議", "意見回饋", "回饋", "feedback"]:
        conn = get_db()
        try:
            if USE_PG:
                conn.execute(q('''INSERT INTO user_state (user_id, step)
                    VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET step = EXCLUDED.step'''),
                    (uid, 'FEEDBACK'))
            else:
                conn.execute('INSERT OR REPLACE INTO user_state (user_id, step) VALUES (?, ?)', (uid, 'FEEDBACK'))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(
            text="📝 請直接輸入你的問題或建議，送出後我們會收到通知：",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="取消", text="取消回報"))
            ])
        ))
        return

    elif msg == "取消回報":
        conn = get_db()
        try:
            conn.execute(q('UPDATE user_state SET step = NULL WHERE user_id = ?'), (uid,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(text="已取消。"))
        return

    elif msg in ["幫助", "使用說明", "help"]:
        safe_reply(event.reply_token, get_welcome_flex())
        return

    elif msg == "刪除我的資料":
        conn = get_db()
        try:
            conn.execute(q("DELETE FROM matches WHERE user_id = ?"), (uid,))
            conn.execute(q("DELETE FROM user_state WHERE user_id = ?"), (uid,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(
            text="✅ 已刪除你的所有行程與使用記錄。\n\n若日後想再使用，重新加入好友即可。"
        ))
        return

    # --- 繼續填寫（Item 6）---
    elif msg == "繼續填寫":
        conn = get_db()
        try:
            res = conn.execute(q('SELECT step, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        finally:
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
        elif not wy or not pc or not fe or not fx:
            safe_reply(event.reply_token, get_detail_flex())
        else:
            safe_reply(event.reply_token, get_main_cat_menu())
        return

    elif msg == "找行程":
        bubble = {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1D9E75",
                "contents": [{"type": "text", "text": "🔍 瀏覽行程", "weight": "bold", "color": "#FFFFFF", "size": "md"}]},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                 "action": {"type": "message", "label": "🚗 找司機（我要搭車）", "text": "找類型:driver"}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#1e90ff",
                 "action": {"type": "message", "label": "🙋 找乘客（我要載人）", "text": "找類型:seeker"}},
                {"type": "button", "style": "secondary", "height": "sm",
                 "action": {"type": "message", "label": "📋 全部行程", "text": "找類型:all"}}
            ]}
        }
        safe_reply(event.reply_token, FlexSendMessage(alt_text="瀏覽行程", contents=bubble))
        return

    elif msg.startswith("找類型:"):
        ftype = msg.split(":")[1]
        label_map = {"driver": "找司機", "seeker": "找乘客", "all": "全部行程"}
        title = label_map.get(ftype, "找行程")
        bubble = {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": "#444441",
                "contents": [{"type": "text", "text": f"📍 {title} — 選擇區域", "weight": "bold", "color": "#FFFFFF", "size": "sm"}]},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1, "color": "#E07B00",
                     "action": {"type": "message", "label": "北部", "text": f"找地區:{ftype}:all:北部"}},
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1, "color": "#E07B00",
                     "action": {"type": "message", "label": "中部", "text": f"找地區:{ftype}:all:中部"}}
                ]},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1, "color": "#E07B00",
                     "action": {"type": "message", "label": "南部", "text": f"找地區:{ftype}:all:南部"}},
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1, "color": "#E07B00",
                     "action": {"type": "message", "label": "東部", "text": f"找地區:{ftype}:all:東部"}}
                ]}
            ]}
        }
        safe_reply(event.reply_token, FlexSendMessage(alt_text="選擇區域", contents=bubble))
        return

    elif msg.startswith("找地區:"):
        parts = msg.split(":")
        if len(parts) == 4:
            ftype, tfilter, area = parts[1], parts[2], parts[3]
        elif len(parts) == 3:
            ftype, area, tfilter = parts[1], parts[2], "all"
        else:
            ftype, area, tfilter = "all", parts[1], "all"
        cities = CITY_DATA.get(area, [])
        rows = []
        for i in range(0, len(cities), 2):
            pair = cities[i:i+2]
            if len(pair) == 2:
                rows.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "flex": 1, "color": "#1D9E75",
                     "action": {"type": "message", "label": c, "text": f"找縣市:{ftype}:{tfilter}:{c}"}} for c in pair
                ]})
            else:
                rows.append({"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                    "action": {"type": "message", "label": pair[0], "text": f"找縣市:{ftype}:{tfilter}:{pair[0]}"}})
        bubble = {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": "#444441",
                "contents": [{"type": "text", "text": f"🗺️ {area} — 選擇縣市", "weight": "bold", "color": "#FFFFFF", "size": "sm"}]},
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows}
        }
        safe_reply(event.reply_token, FlexSendMessage(alt_text=f"選擇{area}縣市", contents=bubble))
        return

    elif msg.startswith("找縣市:"):
        parts = msg.split(":")
        if len(parts) == 7:
            ftype, tfilter, city, sort, dir_filter, pg = parts[1], parts[2], parts[3], parts[4], parts[5], int(parts[6])
        elif len(parts) == 6:
            ftype, tfilter, city, sort, dir_filter, pg = parts[1], parts[2], parts[3], parts[4], parts[5], 0
        elif len(parts) == 5:
            ftype, tfilter, city, sort, dir_filter, pg = parts[1], parts[2], parts[3], parts[4], "any", 0
        elif len(parts) == 4:
            ftype, tfilter, city, sort, dir_filter, pg = parts[1], parts[2], parts[3], "time", "any", 0
        elif len(parts) == 3:
            ftype, city, tfilter, sort, dir_filter, pg = parts[1], parts[2], "all", "time", "any", 0
        else:
            ftype, city, tfilter, sort, dir_filter, pg = "all", parts[1], "all", "time", "any", 0
        page_size = 10
        offset = pg * page_size

        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT00:00")
        week_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT00:00")
        if tfilter == "today":
            time_cond = " AND time_info >= ? AND time_info < ?"
            time_vals = [now_str, tomorrow_str]
        elif tfilter == "week":
            time_cond = " AND time_info >= ? AND time_info < ?"
            time_vals = [now_str, week_str]
        else:
            time_cond = ""
            time_vals = []

        filter_labels = {"today": ("📌今天", "本週", "全部"), "week": ("今天", "📌本週", "全部")}.get(tfilter, ("今天", "本週", "📌全部"))
        sort_time_label = "📌 時間排序" if sort == "time" else "🕒 時間排序"
        sort_rating_label = "📌 評分優先" if sort == "rating" else "⭐ 評分優先"
        dir_from_label = "📌 從此出發" if dir_filter == "from" else "🚀 從此出發"
        dir_to_label = "📌 到此目的" if dir_filter == "to" else "🏁 到此目的"
        dir_any_label = "📌 任意方向" if dir_filter == "any" else "🔀 任意方向"
        _base = f"找縣市:{ftype}:{tfilter}:{city}:{sort}:{dir_filter}"
        qr_items = [
            QuickReplyButton(action=MessageAction(label=filter_labels[0], text=f"找縣市:{ftype}:today:{city}:{sort}:{dir_filter}:0")),
            QuickReplyButton(action=MessageAction(label=filter_labels[1], text=f"找縣市:{ftype}:week:{city}:{sort}:{dir_filter}:0")),
            QuickReplyButton(action=MessageAction(label=filter_labels[2], text=f"找縣市:{ftype}:all:{city}:{sort}:{dir_filter}:0")),
            QuickReplyButton(action=MessageAction(label=sort_time_label, text=f"找縣市:{ftype}:{tfilter}:{city}:time:{dir_filter}:0")),
            QuickReplyButton(action=MessageAction(label=sort_rating_label, text=f"找縣市:{ftype}:{tfilter}:{city}:rating:{dir_filter}:0")),
            QuickReplyButton(action=MessageAction(label=dir_from_label, text=f"找縣市:{ftype}:{tfilter}:{city}:{sort}:from:0")),
            QuickReplyButton(action=MessageAction(label=dir_to_label, text=f"找縣市:{ftype}:{tfilter}:{city}:{sort}:to:0")),
            QuickReplyButton(action=MessageAction(label=dir_any_label, text=f"找縣市:{ftype}:{tfilter}:{city}:{sort}:any:0")),
        ]
        filter_qr = QuickReply(items=qr_items)

        conn = get_db()
        try:
            if dir_filter == "from":
                dir_cond = "s_city = ?"
                dir_vals = [city]
            elif dir_filter == "to":
                dir_cond = "e_city = ?"
                dir_vals = [city]
            else:
                dir_cond = "(s_city = ? OR e_city = ?)"
                dir_vals = [city, city]
            base_cond = f"status = 'active' AND {dir_cond}{time_cond}"
            if sort == "rating":
                order_clause = "(SELECT COALESCE(AVG(score), 0) FROM ratings WHERE ratee_id = matches.user_id) DESC, time_info ASC"
            else:
                order_clause = "time_info ASC"
            if ftype == "all":
                rows = conn.execute(q(
                    f"SELECT id, user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, fee, p_count, line_id, expires_at FROM matches WHERE {base_cond} ORDER BY {order_clause} LIMIT ? OFFSET ?"
                ), dir_vals + time_vals + [page_size + 1, offset]).fetchall()
            else:
                rows = conn.execute(q(
                    f"SELECT id, user_id, user_type, time_info, s_city, s_dist, e_city, e_dist, fee, p_count, line_id, expires_at FROM matches WHERE user_type = ? AND {base_cond} ORDER BY {order_clause} LIMIT ? OFFSET ?"
                ), [ftype] + dir_vals + time_vals + [page_size + 1, offset]).fetchall()
            has_next = len(rows) > page_size
            rows = rows[:page_size]

            if not rows:
                label = {"driver": "司機", "seeker": "乘客"}.get(ftype, "")
                time_hint = {"today": "今天", "week": "本週"}.get(tfilter, "")
                dir_hint = {"from": "（從此出發）", "to": "（到此目的）"}.get(dir_filter, "")
                safe_reply(event.reply_token, TextSendMessage(
                    text=f"📭 目前 {city}{dir_hint} {time_hint}暫無{label}行程。\n換個時間範圍或方向試試！",
                    quick_reply=filter_qr
                ))
                return

            bubbles = []
            for r in rows:
                trip_id, owner_uid, utype, tinfo, sc, sd, ec, ed, fee, pc, lid, exp_at = r
                avg, cnt = get_user_rating(conn, owner_uid)
                rating_text = f"⭐ {avg}（{cnt}筆）" if avg else "暫無評分"
                icon = "🚗" if utype == 'driver' else "🙋"
                role = "司機" if utype == 'driver' else "乘客"
                hdr_color = "#1D9E75" if utype == 'driver' else "#1e90ff"
                is_own = (owner_uid == uid)
                if is_own:
                    footer_contents = [
                        {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                         "action": {"type": "postback", "label": "✅ 已搭乘完成", "data": f"action=complete&id={trip_id}"}},
                        {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                            {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                             "action": {"type": "postback", "label": "✏️ LINE ID", "data": f"action=edit_line_id&id={trip_id}"}},
                            {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                             "action": {"type": "postback", "label": "🗑️ 刪除", "data": f"action=delete&id={trip_id}"}}
                        ]}
                    ]
                elif lid:
                    footer_contents = [
                        {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                         "action": {"type": "uri", "label": "💬 加 LINE 聯絡", "uri": f"https://line.me/ti/p/~{lid}"}},
                        {"type": "button", "style": "link", "height": "sm", "color": "#ff4b4b",
                         "action": {"type": "postback", "label": "🚨 檢舉此用戶", "data": f"action=report&uid={owner_uid}&trip_id={trip_id}"}}
                    ]
                else:
                    footer_contents = [
                        {"type": "button", "style": "primary", "height": "sm", "color": "#E07B00",
                         "action": {"type": "postback", "label": "📨 通知對方留聯絡方式",
                                    "data": f"action=contact_req&to={owner_uid}&route={sc}{sd}→{ec}{ed}"}},
                        {"type": "button", "style": "link", "height": "sm", "color": "#ff4b4b",
                         "action": {"type": "postback", "label": "🚨 檢舉此用戶", "data": f"action=report&uid={owner_uid}&trip_id={trip_id}"}}
                    ]
                exp_text = str(exp_at)[5:16] if exp_at else "未知"
                body_rows = [
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "路線", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": f"{sc}{sd} ➔ {ec}{ed}", "color": "#333333", "size": "sm", "flex": 4, "wrap": True}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": tinfo[5:16], "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "費用", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": fee, "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "人數", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": f"{pc}人", "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "評分", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": rating_text, "color": "#333333", "size": "sm", "flex": 4}]},
                    {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                        {"type": "text", "text": "下架", "color": "#aaaaaa", "size": "sm", "flex": 1},
                        {"type": "text", "text": exp_text, "color": "#e07b00", "size": "sm", "flex": 4}]}
                ]
                if is_own:
                    body_rows.append({"type": "text", "text": "✏️ 這是你的行程", "size": "xxs", "color": "#aaaaaa", "align": "end"})
                bubbles.append({
                    "type": "bubble",
                    "header": {"type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": f"{icon} {role}", "weight": "bold", "color": "#FFFFFF", "size": "sm"}],
                        "backgroundColor": hdr_color},
                    "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_rows},
                    "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer_contents}
                })
            # 累加瀏覽次數
            trip_ids = [r[0] for r in rows]
            if trip_ids:
                placeholders = ','.join(['?' if not USE_PG else '%s'] * len(trip_ids))
                conn.execute(f"UPDATE matches SET view_count = view_count + 1 WHERE id IN ({placeholders})", trip_ids)
                conn.commit()
        finally:
            conn.close()
        time_hint = {"today": "今天", "week": "本週"}.get(tfilter, "全部")
        sort_hint = "⭐ 評分優先" if sort == "rating" else "🕒 時間排序"
        dir_hint = {"from": "從此出發", "to": "到此目的"}.get(dir_filter, "任意方向")
        page_label = f"第 {pg + 1} 頁" if pg > 0 else ""
        # 上下頁 QuickReply（附加在 filter_qr 前面）
        page_items = []
        if pg > 0:
            page_items.append(QuickReplyButton(action=MessageAction(label="◀ 上一頁", text=f"找縣市:{ftype}:{tfilter}:{city}:{sort}:{dir_filter}:{pg - 1}")))
        if has_next:
            page_items.append(QuickReplyButton(action=MessageAction(label="下一頁 ▶", text=f"找縣市:{ftype}:{tfilter}:{city}:{sort}:{dir_filter}:{pg + 1}")))
        paged_qr = QuickReply(items=page_items + qr_items) if page_items else filter_qr
        header_text = f"📋 {city} 行程（{time_hint}・{sort_hint}・{dir_hint}{('・' + page_label) if page_label else ''}・{len(rows)} 筆）"
        safe_reply(event.reply_token, [
            TextSendMessage(text=header_text),
            FlexSendMessage(alt_text=f"{city} 附近行程", contents={"type": "carousel", "contents": bubbles}, quick_reply=paged_qr)
        ])
        return


    # --- 管理員指令 ---
    elif msg in ["/stats", "/quota"] and uid == ADMIN_LINE_ID:
        month_key = datetime.now().strftime("%Y-%m")
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            sc = get_db()
            try:
                total_active = sc.execute(q("SELECT COUNT(*) FROM matches WHERE status = 'active'")).fetchone()[0]
                total_completed = sc.execute(q("SELECT COUNT(*) FROM matches WHERE status = 'completed'")).fetchone()[0]
                if USE_PG:
                    today_new = sc.execute(q("SELECT COUNT(*) FROM matches WHERE created_at::text LIKE ?"), (f"{today}%",)).fetchone()[0]
                else:
                    today_new = sc.execute("SELECT COUNT(*) FROM matches WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
                total_users = sc.execute(q("SELECT COUNT(*) FROM user_state WHERE agreed_terms = 1")).fetchone()[0]
                total_blocked = sc.execute(q("SELECT COUNT(*) FROM blocked_users")).fetchone()[0]
                total_ratings = sc.execute(q("SELECT COUNT(*) FROM ratings")).fetchone()[0]
                avg_row = sc.execute(q("SELECT AVG(score) FROM ratings")).fetchone()
                avg_score = round(float(avg_row[0]), 1) if avg_row and avg_row[0] else 0
                pending_cnt = sc.execute(q("SELECT COUNT(*) FROM pending_pushes")).fetchone()[0]
            finally:
                sc.close()
        except Exception as e:
            safe_reply(event.reply_token, TextSendMessage(text=f"⚠️ 無法取得統計資料：{e}"))
            return
        try:
            resp = requests.get(
                "https://api.line.me/v2/bot/message/quota/consumption",
                headers={"Authorization": f"Bearer {os.getenv('LINE_CHANNEL_ACCESS_TOKEN')}"},
                timeout=5
            )
            used = resp.json().get("totalUsage", 0)
            quota_text = f"已用 {used} / 200 則（剩 {max(0, 200 - used)}）"
        except Exception:
            quota_text = "無法取得"
        safe_reply(event.reply_token, TextSendMessage(
            text=(
                f"📊 sun car 統計 {today}\n"
                f"━━━━━━━━━━━━\n"
                f"👤 同意條款用戶：{total_users} 人\n"
                f"🚫 封鎖用戶：{total_blocked} 人\n"
                f"━━━━━━━━━━━━\n"
                f"🗓️ 今日新增行程：{today_new} 筆\n"
                f"✅ 生效中行程：{total_active} 筆\n"
                f"🏁 已完成行程：{total_completed} 筆\n"
                f"━━━━━━━━━━━━\n"
                f"⭐ 評分總數：{total_ratings} 筆（均分 {avg_score}）\n"
                f"📬 待補送通知：{pending_cnt} 則\n"
                f"━━━━━━━━━━━━\n"
                f"📤 {month_key} 推播：{quota_text}"
            )
        ))
        return

    elif msg.startswith("/info ") and uid == ADMIN_LINE_ID:
        target = msg[6:].strip()
        conn = get_db()
        try:
            is_ban = conn.execute(q("SELECT 1 FROM blocked_users WHERE user_id = ?"), (target,)).fetchone()
            state = conn.execute(q("SELECT step, agreed_terms, notify_on_match FROM user_state WHERE user_id = ?"), (target,)).fetchone()
            trips = conn.execute(q(
                "SELECT id, user_type, time_info, s_city, e_city, status FROM matches WHERE user_id = ? ORDER BY created_at DESC LIMIT 5"
            ), (target,)).fetchall()
            avg, cnt = get_user_rating(conn, target)
        finally:
            conn.close()
        lines = [f"🔍 用戶資訊：{target[:16]}..."]
        if is_ban:
            lines.append("🚫 狀態：已封鎖")
        else:
            lines.append("✅ 狀態：正常")
        if state:
            lines.append(f"📋 同意條款：{'是' if state[1] else '否'}  通知：{'開' if state[2] else '關'}")
        lines.append(f"⭐ 評分：{avg}（{cnt}筆）" if avg else "⭐ 評分：暫無")
        lines.append(f"━━ 近期行程（最多5筆）")
        if trips:
            for t in trips:
                t_id, utype, tinfo, sc, ec, status = t
                role = "🚗" if utype == "driver" else "🙋"
                lines.append(f"{role} #{t_id} {tinfo[5:16]} {sc}→{ec} [{status}]")
        else:
            lines.append("（無行程記錄）")
        lines.append(f"\n/ban {target}")
        safe_reply(event.reply_token, TextSendMessage(text="\n".join(lines)))
        return

    elif msg.startswith("/ban ") and uid == ADMIN_LINE_ID:
        target = msg[5:].strip()
        conn = get_db()
        try:
            if USE_PG:
                conn.execute(q("INSERT INTO blocked_users (user_id, reason) VALUES (?, 'admin_ban') ON CONFLICT (user_id) DO NOTHING"), (target,))
            else:
                conn.execute("INSERT OR IGNORE INTO blocked_users (user_id, reason) VALUES (?, 'admin_ban')", (target,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(text=f"✅ 已封鎖用戶：{target}"))
        return

    elif msg.startswith("/unban ") and uid == ADMIN_LINE_ID:
        target = msg[7:].strip()
        conn = get_db()
        try:
            conn.execute(q("DELETE FROM blocked_users WHERE user_id = ?"), (target,))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(text=f"✅ 已解封用戶：{target}"))
        return

    # --- 開始發布流程 ---
    if msg in ["我要載客/貨", "我要搭車/寄物"]:
        threading.Thread(target=clean_expired_matches, daemon=True).start()  # 非同步，不阻塞回應
        ut = 'driver' if "載客" in msg else 'seeker'
        conn = get_db()
        try:
            if USE_PG:
                conn.execute(q('''INSERT INTO user_state (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step)
                    VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '', NULL, 'START')
                    ON CONFLICT (user_id) DO UPDATE SET current_type=EXCLUDED.current_type,
                    temp_time=NULL, s_city=NULL, s_dist=NULL, e_city=NULL, e_dist=NULL,
                    temp_way=NULL, temp_count=NULL, temp_fee=NULL, temp_flex=NULL, temp_prefs='', temp_line_id=NULL, step='START' '''), (uid, ut))
            else:
                conn.execute('INSERT OR REPLACE INTO user_state (user_id, current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id, step) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "", NULL, "START")', (uid, ut))
            conn.commit()
        finally:
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
        try:
            res = conn.execute(q('SELECT step FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            step = res[0] if res else "START"
            col = "s_city" if step == "START" else "e_city"
            conn.execute(q(f'UPDATE user_state SET {col} = ? WHERE user_id = ?'), (c, uid))
            conn.commit()
        finally:
            conn.close()
        dists = DISTRICT_DATA.get(c, ["市中心"])
        btns = [QuickReplyButton(action=MessageAction(label=d, text=f"區:{d}")) for d in dists[:13]]
        safe_reply(event.reply_token, TextSendMessage(text=f"請選擇 {c} 的行政區：", quick_reply=QuickReply(items=btns)))

    elif msg.startswith("區:"):
        d = msg.split(":")[1]
        conn = get_db()
        try:
            res = conn.execute(q('SELECT step FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            step = res[0] if res else "START"
            if step == "START":
                conn.execute(q('UPDATE user_state SET s_dist = ?, step = ? WHERE user_id = ?'), (d, "END", uid))
            else:
                conn.execute(q('UPDATE user_state SET e_dist = ?, step = ? WHERE user_id = ?'), (d, "DONE", uid))
            conn.commit()
        finally:
            conn.close()
        if step == "START":
            safe_reply(event.reply_token, get_area_carousel("🏁 第二步：選擇【目的地】區域"))
        else:
            safe_reply(event.reply_token, [
                TextSendMessage(text="✅ 路線設定完成！\n\n接下來填寫行程細節：\n・中途：是否接受途中上下車\n・人數：最多幾位乘客\n・乘客費用：你希望的收費方式\n・刊登天數：行程在平台顯示幾天\n\n最後點「時間彈性」進入下一步 👇"),
                get_detail_flex()
            ])

    elif msg.startswith("中途:"):
        conn = get_db()
        try:
            conn.execute(q('UPDATE user_state SET temp_way = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
            conn.commit()
        finally:
            conn.close()

    elif msg.startswith("人數:"):
        conn = get_db()
        try:
            conn.execute(q('UPDATE user_state SET temp_count = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
            conn.commit()
        finally:
            conn.close()

    elif msg.startswith("費用:"):
        conn = get_db()
        try:
            conn.execute(q('UPDATE user_state SET temp_fee = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
            conn.commit()
        finally:
            conn.close()

    elif msg.startswith("有效:"):
        conn = get_db()
        try:
            conn.execute(q('UPDATE user_state SET temp_expire = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
            conn.commit()
        finally:
            conn.close()

    elif msg.startswith("彈性:"):
        conn = get_db()
        try:
            res = conn.execute(q('SELECT temp_count, temp_fee, temp_way, temp_expire FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            conn.execute(q('UPDATE user_state SET temp_flex = ? WHERE user_id = ?'), (msg.split(":")[1], uid))
            # 若中途/有效天數未選，設預設值
            if res and not res[2]:
                conn.execute(q('UPDATE user_state SET temp_way = ? WHERE user_id = ?'), ('接受', uid))
            if res and not res[3]:
                conn.execute(q('UPDATE user_state SET temp_expire = ? WHERE user_id = ?'), ('3', uid))
            conn.commit()
        finally:
            conn.close()

        pc = res[0] if res else None
        fe = res[1] if res else None

        if not pc or not fe:
            missing = []
            if not pc: missing.append("人數")
            if not fe: missing.append("費用方式")
            safe_reply(event.reply_token, TextSendMessage(
                text=f"⚠️ {'、'.join(missing)} 尚未選擇，請返回卡片補填。",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="↩ 返回設定", text="繼續填寫"))
                ])
            ))
        else:
            safe_reply(event.reply_token, get_main_cat_menu())

    elif msg.startswith("規範:"):
        p = msg.split(":")[1]
        conn = get_db()
        try:
            res = conn.execute(q('SELECT temp_prefs FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            p_str = (res[0] if res and res[0] else "") + f"{p}, "
            conn.execute(q('UPDATE user_state SET temp_prefs = ? WHERE user_id = ?'), (p_str, uid))
            conn.commit()
        finally:
            conn.close()
        safe_reply(event.reply_token, TextSendMessage(
            text=f"✅ 已加：{p}\n目前：{p_str.rstrip(', ')}",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="繼續選標籤", text="繼續選標籤")),
                QuickReplyButton(action=MessageAction(label="🚀 直接發布", text="最終確認發布"))
            ])
        ))

    elif msg == "繼續選標籤":
        safe_reply(event.reply_token, get_main_cat_menu())

    elif msg == "最終確認發布":
        conn = get_db()
        try:
            res = conn.execute(q('SELECT current_type, temp_time, s_city, s_dist, e_city, e_dist, temp_way, temp_count, temp_fee, temp_flex, temp_prefs, temp_line_id FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
        finally:
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

        # 拒絕過去時間
        if tt and tt < datetime.now().strftime("%Y-%m-%dT%H:%M"):
            safe_reply(event.reply_token, TextSendMessage(
                text="⚠️ 出發時間已過，無法發布過去的行程。\n\n請重新選擇出發時間：",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=DatetimePickerAction(label="🕒 重新選擇", data="select_time", mode="datetime"))
                ])
            ))
            return

        # 尚未填寫 LINE ID → 提示輸入（優先用上次記住的 ID）
        if lid is None:
            conn = get_db()
            try:
                conn.execute(q('UPDATE user_state SET step = ? WHERE user_id = ?'), ('WAIT_LINE_ID', uid))
                conn.commit()
                prev = conn.execute(q(
                    "SELECT line_id FROM matches WHERE user_id = ? AND line_id != '' ORDER BY created_at DESC LIMIT 1"
                ), (uid,)).fetchone()
            finally:
                conn.close()
            if prev and prev[0]:
                saved_id = prev[0]
                safe_reply(event.reply_token, TextSendMessage(
                    text=f"📱 聯絡方式設定\n\n上次使用的 LINE ID：@{saved_id}\n\n直接沿用還是重新輸入？",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label=f"沿用 @{saved_id[:10]}", text=saved_id)),
                        QuickReplyButton(action=MessageAction(label="重新輸入", text="重新輸入LINE ID")),
                        QuickReplyButton(action=MessageAction(label="跳過", text="跳過"))
                    ])
                ))
            else:
                safe_reply(event.reply_token, TextSendMessage(
                    text="📱 最後一步！輸入 LINE ID 讓配對對象能聯絡你：\n\n查看方式：LINE → 設定 → 個人檔案 → LINE ID\n（不想提供請按跳過）",
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
            try:
                res = conn.execute(q('SELECT step, current_type FROM user_state WHERE user_id = ?'), (uid,)).fetchone()
            finally:
                conn.close()
        except Exception as e:
            _store_log("fallback_db_error", str(e))
            res = None

        # 處理意見回饋
        if res and res[0] == 'FEEDBACK':
            feedback_text = msg.strip()
            conn2 = get_db()
            try:
                conn2.execute(q('UPDATE user_state SET step = NULL WHERE user_id = ?'), (uid,))
                conn2.commit()
            finally:
                conn2.close()
            if ADMIN_LINE_ID:
                safe_push(ADMIN_LINE_ID, TextSendMessage(
                    text=f"📬 用戶回饋（uid: {uid[:12]}...）\n\n{feedback_text}"
                ))
            safe_reply(event.reply_token, TextSendMessage(text="✅ 已收到！感謝你的回饋，我們會持續改善 🙏"))
            return

        # 處理編輯行程 LINE ID
        if res and res[0] and res[0].startswith('EDIT_LINE_ID:'):
            match_id = res[0].split(':', 1)[1]
            new_lid = '' if msg == '清除LINE ID' else msg.strip().lstrip('@')
            if new_lid and not re.match(r'^[a-zA-Z0-9._-]{1,30}$', new_lid):
                safe_reply(event.reply_token, TextSendMessage(
                    text="⚠️ LINE ID 格式不正確，只允許英文、數字、底線、點、連字號（最多30字元）。\n\n請重新輸入："
                ))
                return
            conn2 = get_db()
            try:
                conn2.execute(q('UPDATE matches SET line_id = ? WHERE id = ? AND user_id = ?'), (new_lid, match_id, uid))
                conn2.execute(q('UPDATE user_state SET step = NULL WHERE user_id = ?'), (uid,))
                conn2.commit()
            finally:
                conn2.close()
            result = f"已清除 LINE ID" if not new_lid else f"LINE ID 已更新為 @{new_lid}"
            safe_reply(event.reply_token, TextSendMessage(
                text=f"✅ {result}",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="📋 我的行程", text="我的行程"))
                ])
            ))
            return

        # 處理回傳 LINE ID 給詢問者
        if res and res[0] and res[0].startswith('SHARE_LINE_ID:'):
            to_uid = res[0].split(':', 1)[1]
            line_id = msg.strip().lstrip('@')
            if line_id and not re.match(r'^[a-zA-Z0-9._-]{1,30}$', line_id):
                safe_reply(event.reply_token, TextSendMessage(
                    text="⚠️ LINE ID 格式不正確，只允許英文、數字、底線、點、連字號（最多30字元）。\n\n請重新輸入："
                ))
                return
            conn2 = get_db()
            try:
                conn2.execute(q('UPDATE user_state SET step = NULL WHERE user_id = ?'), (uid,))
                conn2.commit()
            finally:
                conn2.close()
            safe_push(to_uid, TextSendMessage(
                text=f"✅ 對方回覆了 LINE ID：@{line_id}\n點此加好友：https://line.me/ti/p/~{line_id}"
            ))
            safe_reply(event.reply_token, TextSendMessage(text=f"✅ 已將你的 LINE ID（@{line_id}）傳給對方！"))
            return

        # 處理 LINE ID 輸入
        if res and res[0] == 'WAIT_LINE_ID':
            if msg == '重新輸入LINE ID':
                safe_reply(event.reply_token, TextSendMessage(
                    text="請輸入你的 LINE ID（不含 @）：",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="跳過", text="跳過"))
                    ])
                ))
                return
            line_id = '' if msg == '跳過' else msg.strip().lstrip('@')
            if line_id and not re.match(r'^[a-zA-Z0-9._-]{1,30}$', line_id):
                safe_reply(event.reply_token, TextSendMessage(
                    text="⚠️ LINE ID 格式不正確，只允許英文、數字、底線、點、連字號（最多30字元）。\n\n請重新輸入，或按跳過：",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="跳過", text="跳過"))
                    ])
                ))
                return
            conn = get_db()
            try:
                conn.execute(q('UPDATE user_state SET temp_line_id = ?, step = ? WHERE user_id = ?'), (line_id, 'DONE', uid))
                conn.commit()
            finally:
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

# --- 10. 到期提醒 ---
def reminder_thread():
    while True:
        try:
            now = datetime.now()
            remind_from = now.strftime("%Y-%m-%dT%H:%M")
            remind_to = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            conn = get_db()
            try:
                trips = conn.execute(q(
                    "SELECT id, user_id, s_city, e_city, expires_at FROM matches WHERE status = 'active' AND expires_at BETWEEN ? AND ? AND reminded_at IS NULL"
                ), (remind_from, remind_to)).fetchall()
                for trip in trips:
                    trip_id, user_id, sc, ec, exp_at = trip
                    remind_flex = {
                        "type": "bubble",
                        "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                            {"type": "text", "text": "⏰ 行程即將下架", "weight": "bold", "size": "md"},
                            {"type": "text", "text": f"{sc} ➔ {ec}", "size": "sm", "color": "#555555"},
                            {"type": "text", "text": f"下架時間：{str(exp_at)[5:16]}", "size": "sm", "color": "#e07b00"},
                        ]},
                        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                            {"type": "button", "style": "primary", "height": "sm", "color": "#1D9E75",
                             "action": {"type": "postback", "label": "📅 延長 3 天", "data": f"action=extend&id={trip_id}"}},
                            {"type": "button", "style": "secondary", "height": "sm",
                             "action": {"type": "postback", "label": "🗑️ 刪除行程", "data": f"action=delete&id={trip_id}"}}
                        ]}
                    }
                    safe_push(user_id, FlexSendMessage(alt_text=f"⏰ {sc}→{ec} 行程即將下架", contents=remind_flex))
                    conn.execute(q("UPDATE matches SET reminded_at = ? WHERE id = ?"), (remind_from, trip_id))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logging.error(f"Reminder thread error: {e}")
        time.sleep(1800)

# --- 11. Keep Alive ---
# 注意：Render free tier 進程若被殺，self-ping 也一起死。
# 建議同時設定 UptimeRobot 每 5 分鐘 ping /ping endpoint 作為外部保活。
def keep_alive():
    url = os.getenv('RENDER_EXTERNAL_URL', 'https://ride-match-bot.onrender.com') + '/ping'
    while True:
        try:
            requests.get(url, timeout=10)
            logging.info(f"Keep alive ping: {url}")
        except Exception as e:
            logging.error(f"Keep alive failed: {e}")
        time.sleep(540)  # 9 分鐘，確保 Render 15 分鐘休眠窗口內 ping 兩次

# Render 環境下在模組層級啟動 keep_alive（gunicorn 不會跑 __main__）
if os.getenv('RENDER'):
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=reminder_thread, daemon=True).start()

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=reminder_thread, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
