#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
台股「五大經典強勢起漲型態」全自動極速監控腳本 (全標的完整推播版)
=============================================================================
【五大起漲型態演算法】（已移除圓弧底與均線糾結，精煉保留實戰五大強勢型態）
1. 【回檔突破前高第一根】 (Pullback Breakout Bar 1):
   - 40 天波段高點後，至少回檔整理 3 天以上。
   - 昨日收盤價 < 前高，今日收盤價 > 前高 (首根站上)。
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
2. 【回後買上漲（破5T後重新站上第一根）】 (Pullback & Reclaim 5MA Bar 1):
   - 強勢多頭格局：20MA > 60MA 且股價站穩 20MA 月線。
   - 強勢短洗盤：前 1~3 天回檔跌破 5T 均線 (昨日收盤價 < 5MA)，但守穩在月線 20MA 之上。
   - 今日重新站回 5T：今日收實體紅 K (漲幅>=1.5%)，收盤價首度重新站上 5T 線！
3. 【疑似頭肩底「破切」第一根】 (Head & Shoulders Bottom Breakout of Neckline):
   - 打底時間約 1 個月 (28 個交易日)。
   - 完整三底架構：左肩 L1、頭部最低點 Head、右肩低點 L2 (右肩明顯高於頭部，不破底)。
   - 兩次反彈高點：左肩反彈高點 P1 與頭部反彈高點 P2 相連形成「頸線切線」。
   - 昨日收盤仍在切線之下，今日首度帶量長紅「破切站上切線」！
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
4. 【跳空缺口 D+3 守穩】 (Breakaway Gap Held for D+3):
   - D 日（3 個交易日前）向上跳空開高（D 日最低價 > D-1 日最高價，不限缺口幅度），且 D 日帶量 >= 1.5 倍 5MA。
   - D+1、D+2、D+3 連續 3 個交易日「收盤價」皆守穩在缺口下緣之上（不補缺口；盤中下影線回測不計）。
   - 今日股價維持在月線與季線之上。
5. 【布林壓縮開口突破】 (Bollinger Band Squeeze & Breakout Bar 1):
   - 20 日布林通道頻寬收斂至近 60 日極窄區間（頻寬 <= 12% 且在近 60 日最窄 1.3 倍以內）。
   - 昨日收盤價仍在布林上軌之下，今日帶量收實體紅 K 首度突破布林上軌，且通道開口張開。

【完整全名單推播 (無截斷)】
- 不再限制只推送前幾檔！只要符合條件的股票「全部完整列出」。
- 自動依 450 字上限分拆訊息泡泡，並以每批最多 5 個泡泡自動連續發送，確保全市場命中標的 100% 送達手機！
=============================================================================
"""

import os
import sys
import time
import re
import argparse
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

# 嘗試載入選用套件
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# 系統預設參數設定 (已綁定你的專屬 LINE 設定)
# =============================================================================
DEFAULT_CONFIG = {
    # 你的專屬 LINE 官方帳號設定
    "line_channel_access_token": "9ipOm1j5q30aCiczxs4aVEWmOeGTvUa4UF4W6Tj0O3EKW7VUpqQQPrCUmoyzRpfFDWvqtjGKzjOPTI+W6gZQhXObM9nw+xvRPCZ+8tabcneFntw+VwRIqCKh6nBljUFIeA11il0D24qHH7NxQLK/TwdB04t89/1O/w1cDnyilFU=",
    
    # 公開廣播模式 (Broadcast): 廣播給所有加好友的用戶
    "line_broadcast": True,
    "line_user_id": "U5d37c903cbc9e6442aa86bde5e830125",

    # 技術面通用門檻
    "vol_multiplier": 1.5,       # 突破日成交量需大於 5 日均量的 1.5 倍
    "require_red_candle": True,  # 必須收實體紅 K (Close > Open)
    "require_above_ma20": True,  # 股價必須站上 20MA (月線)
    "require_above_ma60": True,  # 股價必須站上 60MA (季線)
    "min_volume_shares": 500,    # 每日最低成交張數 (500 張)

    # 「回後買上漲」精準過濾參數
    "reclaim_5ma_max_pullback_bars": 3, # 跌破 5MA 的回檔天數必須在 3 天以內
    "reclaim_5ma_min_gain_pct": 1.5,    # 今日站回 5T 之紅 K 漲幅至少 1.5% 以上
    "reclaim_5ma_vol_ratio": 1.2,       # 今日成交量至少為 5MA 均量的 1.2 倍

    # 「跳空缺口 D+3 守穩」參數
    "gap_hold_days": 3,          # 跳空後需守穩天數 (D+1, D+2, D+3 皆不補缺口)
    "gap_min_pct": 0.0,          # 最小跳空幅度 (0.0% = 不限幅度，只要有缺口就算)
    "gap_vol_multiplier": 1.5,   # D 日跳空當天成交量需 >= 5MA 均量的 1.5 倍

    # 「布林通道壓縮突破」參數
    "bb_period": 20,             # 布林通道均線週期 (20 日)
    "bb_std_dev": 2.0,           # 布林通道標準差倍數 (2.0)
    "bb_max_squeeze_width_pct": 12.0, # 壓縮時頻寬絕對上限 (12.0% 以內)
    "bb_squeeze_near_min_ratio": 1.30, # 昨日頻寬須在近 60 日最窄頻寬的 1.30 倍以內

    # 波段與底部形態參數
    "base_lookback_days": 28,    # 頭肩底打底觀察天數 (約 1 個月)
    "swing_high_window": 40,     # 回檔突破前高的回溯天數 (40天)
    "min_pullback_bars": 3,      # 前高回檔最少天數 (3天)

    # LINE 訊息泡泡設定
    "line_bubble_max_chars": 450,# 單個文字泡泡字數限制 (小於官方 500 字上限)

    # 超時防卡死參數
    "ticker_timeout_sec": 3.0,   # 單檔行情抓取超時上限 (秒)
    "max_scan_total_sec": 600,   # 全程掃描最長執行時間 (10 分鐘)
    
    "discord_webhook_url": "",
}

# =============================================================================
# 預建台股核心精選清單 (台灣50 + 中型100 + 富櫃50 + 重點成長權值股，約 220 檔)
# =============================================================================
CORE_TW_STOCKS = [
    # 半導體 / IC 設計 / 封測
    "2330", "2454", "2303", "3711", "2379", "3034", "3035", "3443", "3661", "6488",
    "6770", "3529", "8299", "3260", "6531", "6533", "2449", "6239", "8016", "3131",
    # AI 伺服器 / 代工 / 電腦周邊
    "2317", "2382", "3231", "2356", "6669", "2376", "2357", "2301", "2395", "3017",
    "3324", "3653", "2421", "3013", "3044", "2474", "3706", "3515", "2353", "2324",
    # PCB / 載板 / CCL
    "3037", "3189", "8046", "2368", "6274", "8358", "6213", "3042", "2383", "4958",
    # 重電 / 綠能 / 線纜
    "1519", "1503", "1504", "1513", "1514", "1609", "1605", "1618", "6806", "9958",
    # 網通 / 光通訊 / CPO
    "2345", "3450", "4977", "4979", "3363", "6442", "3163", "5388", "3081", "3491",
    # 散熱 / 機殼 / 電源
    "3017", "3324", "2421", "3653", "2308", "6282", "3008", "3406", "3376", "6124",
    # 被動元件 / 特用化學
    "2492", "2327", "2456", "6173", "4763", "1722", "1711", "4770", "4768", "4755",
    # 航運 / 散裝 / 航空
    "2603", "2609", "2615", "2605", "2606", "2637", "2618", "2610", "2634", "2646",
    # 金融保險
    "2881", "2882", "2891", "2886", "2884", "2892", "2885", "2880", "2887", "2890",
    "2883", "2801", "2834", "2888", "5880", "5876", "6005", "2855",
    # 傳產 / 塑化 / 鋼鐵 / 生技
    "1101", "1102", "1301", "1303", "1326", "6505", "2002", "2027", "2014", "9910",
    "9904", "1402", "1795", "6472", "4743", "6547", "1760", "6446", "6589", "6733",
    # 車用 / 機器人 / 自動化
    "2201", "2204", "2207", "4566", "2049", "2359", "4583", "1590", "1597", "8255",
    "2498", "3708", "4967", "6188", "2486", "2408", "3583", "5483", "6182", "3545"
]
CORE_TW_STOCKS = sorted(list(set(CORE_TW_STOCKS)))


# =============================================================================
# 核心模組 1：資料取得 (支援超時保護)
# =============================================================================
def is_strictly_common_stock(code: str, name: str) -> bool:
    """
    台股純普通股嚴格過濾器：
    1. 代號格式：必須為嚴格 4 碼純數字 (完全排除 5 碼可轉債、6 碼權證、帶英文字母特別股)。
    2. 排除非普通股代號：排除 00 開頭 (ETF)、01/02 開頭 (ETN)、91 開頭 (TDR)。
    3. 排除可轉債 (CB)：名稱包含「債」、「CB」、「可轉」、「轉換公司債」。
    4. 排除權證 (Warrants)：名稱包含「權證」、「認購」、「認售」、「牛證」、「熊證」、「展延」，或含「購/售/牛/熊」。
    5. 排除特別股：名稱包含「特別股」、「甲特」、「乙特」、「丙特」、「丁特」、「戊特」，或名稱以「特」結尾 (排除「力特」等普通股除外)。
    """
    code = str(code).strip().upper()
    name = str(name).strip()

    if not (len(code) == 4 and code.isdigit()):
        return False

    if code.startswith(("00", "01", "02", "91")):
        return False

    if any(kw in name for kw in ["債", "CB", "可轉", "轉換公司債", "公司債"]):
        return False

    if any(kw in name for kw in ["權證", "認購", "認售", "牛證", "熊證", "展延", "購", "售", "牛", "熊"]):
        return False

    if any(kw in name for kw in ["特別股", "甲特", "乙特", "丙特", "丁特", "戊特"]):
        return False
    if name.endswith("特") and name not in ["力特"]:
        return False

    return True


def fetch_all_market_stock_codes() -> List[Tuple[str, str]]:
    """
    從台灣證交所 (TWSE) 官方清單自動爬取全台股所有上市與上櫃股票代號及名稱。
    """
    print("[資料更新] 正在連線台灣證券交易所 (TWSE) 抓取名冊 (啟用普通股嚴格過濾)... ")
    all_stocks = []
    modes = [(2, "上市"), (4, "上櫃")]
    
    for mode_id, market_type in modes:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode_id}"
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = 'big5'
            if resp.status_code == 200:
                html_text = resp.text
                in_stock_section = False
                found_in_section = 0
                rows = re.split(r"<tr[^>]*>", html_text, flags=re.IGNORECASE)
                
                for row in rows:
                    b_match = re.search(r"<b[^>]*>([^<]+)</b>", row, re.IGNORECASE)
                    if b_match:
                        sec_title = b_match.group(1).strip()
                        if sec_title == "股票":
                            in_stock_section = True
                        else:
                            in_stock_section = False
                            
                    if in_stock_section:
                        cell_match = re.search(r">\s*(?<![0-9a-zA-Z])(\d{4})(?![0-9a-zA-Z])[\s　]+([^<]+?)\s*<", row)
                        if cell_match:
                            code = cell_match.group(1).strip()
                            name = cell_match.group(2).strip()
                            if is_strictly_common_stock(code, name):
                                suffix = ".TW" if mode_id == 2 else ".TWO"
                                all_stocks.append((f"{code}{suffix}", f"{code} {name}"))
                                found_in_section += 1

                if found_in_section == 0:
                    matches = re.findall(r"(?<![0-9a-zA-Z])(\d{4})(?![0-9a-zA-Z])[\s\u3000]+([^\s<\"\'\r\n]+)", html_text)
                    for code, name in matches:
                        if is_strictly_common_stock(code, name):
                            suffix = ".TW" if mode_id == 2 else ".TWO"
                            all_stocks.append((f"{code}{suffix}", f"{code} {name}"))
        except Exception as e:
            print(f"[名冊警告] {market_type} 抓取發生例外: {e}")
            continue

    unique_stocks = []
    seen = set()
    for sym, label in all_stocks:
        if sym not in seen:
            seen.add(sym)
            unique_stocks.append((sym, label))
            
    print(f"[名冊完成] 成功取得純普通股共 {len(unique_stocks)} 檔 (已完整過濾可轉債與權證)！")
    return unique_stocks


def fetch_stock_daily_data(symbol: str, timeout_sec: float = 3.0) -> Optional[pd.DataFrame]:
    """
    抓取單檔股票日 K 線 (含嚴格超時防護)
    """
    if not HAS_YFINANCE:
        return None

    clean_sym = symbol.strip().upper()
    if clean_sym.endswith(".TW") or clean_sym.endswith(".TWO"):
        candidates = [clean_sym]
    else:
        candidates = [f"{clean_sym}.TW", f"{clean_sym}.TWO"]

    df = None
    for ticker in candidates:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo", timeout=timeout_sec)
            if not hist.empty and len(hist) >= 35:
                df = hist
                break
        except Exception:
            continue

    if df is None or df.empty:
        return None

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.dropna(inplace=True)
    return df


# =============================================================================
# 核心模組 2：五大經典型態檢驗演算法
# =============================================================================

def check_pullback_breakout(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """型態 1：波段回檔突破前高第一根"""
    window = config["swing_high_window"]
    if len(df) < window + 10:
        return False, {}

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    search_window = df.iloc[-(window + 2) : -2]
    swing_high = search_window['High'].max()
    swing_high_idx = search_window['High'].idxmax()
    bars_since_peak = len(df.loc[swing_high_idx : yesterday.name]) - 1

    has_pullback = bars_since_peak >= config["min_pullback_bars"]
    is_first = yesterday['Close'] < swing_high and today['Close'] > swing_high

    if has_pullback and is_first:
        return True, {
            "name": "回檔突破前高",
            "key_price": round(float(swing_high), 2),
            "detail": f"整理 {bars_since_peak} 天首度過前高"
        }
    return False, {}


def check_head_and_shoulders_bottom(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """型態 4：疑似頭肩底「破切」第一根 (嚴格三波谷架構)"""
    lookback = config.get("base_lookback_days", 28)
    if len(df) < lookback + 10:
        return False, {}

    sub_df = df.iloc[-(lookback + 2) : -1]
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    n = len(sub_df)

    head_rel_idx = sub_df['Low'].values.argmin()
    head_price = float(sub_df['Low'].iloc[head_rel_idx])

    if head_rel_idx < int(n * 0.22) or head_rel_idx > int(n * 0.72):
        return False, {}

    left_sub = sub_df.iloc[:head_rel_idx]
    right_sub = sub_df.iloc[head_rel_idx + 1 :]

    if len(left_sub) < 3 or len(right_sub) < 3:
        return False, {}

    p1_rel_idx = left_sub['High'].values.argmax()
    p1_price = float(left_sub['High'].iloc[p1_rel_idx])
    l1_price = float(left_sub['Low'].iloc[: max(1, p1_rel_idx + 1)].min())

    p2_rel_idx = right_sub['High'].values.argmax()
    p2_price = float(right_sub['High'].iloc[p2_rel_idx])
    p2_global_idx = head_rel_idx + 1 + p2_rel_idx
    l2_price = float(right_sub['Low'].min())

    if head_price >= l1_price * 0.985 or head_price >= l2_price * 0.985:
        return False, {}
    if l2_price <= head_price:
        return False, {}

    x1 = p1_rel_idx
    x2 = p2_global_idx
    if x2 <= x1:
        return False, {}

    slope = (p2_price - p1_price) / (x2 - x1)
    neckline_yest = p1_price + slope * ((n - 1) - x1)
    neckline_today = p1_price + slope * (n - x1)

    is_broke_cut = float(yesterday['Close']) < neckline_yest and float(today['Close']) > neckline_today

    if is_broke_cut:
        return True, {
            "name": "頭肩底破切",
            "key_price": round(float(neckline_today), 2),
            "detail": f"頭部{head_price:.1f}右肩有守，今日破切站上"
        }
    return False, {}


def check_reclaim_5ma_breakout(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    型態 3：強勢股【回後買上漲】（均線多頭回檔跌破5T線，今日首度重新站上5T第一根）
    """
    if len(df) < 65:
        return False, {}

    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    uptrend_ok = (today['MA20'] > today['MA60']) and (today['Close'] > today['MA20'])
    max_pullback = config.get("reclaim_5ma_max_pullback_bars", 3)
    recent_bars = df.iloc[-(max_pullback + 1) : -1]
    under_5ma_count = sum(recent_bars['Close'] < recent_bars['MA5'])
    is_valid_pullback = (under_5ma_count >= 1) and (yesterday['Close'] < yesterday['MA5'])
    held_20ma = (recent_bars['Low'].min() >= recent_bars['MA20'].min() * 0.99)

    today_reclaim_5ma = today['Close'] > today['MA5']
    min_gain = config.get("reclaim_5ma_min_gain_pct", 1.5)
    price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
    is_red_candle = (today['Close'] > today['Open']) and (price_change_pct >= min_gain)

    ref_vol_ma = yesterday['Vol_MA5']
    vol_ratio = (today['Volume'] / ref_vol_ma) if ref_vol_ma > 0 else 0.0
    vol_reclaim_ok = (vol_ratio >= config.get("reclaim_5ma_vol_ratio", 1.2)) or (today['Volume'] >= yesterday['Volume'] * 1.1)

    if uptrend_ok and is_valid_pullback and held_20ma and today_reclaim_5ma and is_red_candle and vol_reclaim_ok:
        return True, {
            "name": "回後買上漲",
            "key_price": round(float(today['MA5']), 2),
            "detail": f"回檔守月線，紅K(+{price_change_pct:.1f}%)重返5T線"
        }
    return False, {}


def check_gap_hold_d3(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    型態 5：跳空缺口 D+3 守穩（三日不補缺口，以收盤價判定、盤中下影線不計）
    - D 日（hold_days 個交易日前）出現向上跳空缺口：D 日最低價 > D-1 日最高價（不限幅度，只要有缺口就算）。
    - D 日帶量上攻（D 日成交量 >= D-1 日 5 日均量的 1.5 倍，且收盤 >= 開盤與前收）。
    - D+1 至 D+3（含今日）連續 3 天「收盤價」皆嚴格守在缺口下緣（D-1 日最高價）之上，未被回補！
    """
    hold_days = config.get("gap_hold_days", 3)
    if len(df) < hold_days + 10:
        return False, {}

    day_d_prev = df.iloc[-(hold_days + 2)]  # D-1
    day_d = df.iloc[-(hold_days + 1)]       # D (跳空日)
    hold_window = df.iloc[-hold_days:]      # D+1 .. D+3 (含今日)

    prev_high = float(day_d_prev['High'])
    d_low = float(day_d['Low'])
    if prev_high <= 0 or d_low <= prev_high:
        return False, {}

    gap_pct = (d_low - prev_high) / prev_high * 100.0
    min_gap_pct = config.get("gap_min_pct", 0.0)
    if min_gap_pct > 0 and gap_pct < min_gap_pct:
        return False, {}

    # D 日須收漲且未收黑崩跌
    if float(day_d['Close']) <= float(day_d_prev['Close']) or float(day_d['Close']) < float(day_d['Open']):
        return False, {}

    # D 日跳空當天必須有量能配合
    d_prev_vol_ma5 = float(day_d_prev['Vol_MA5']) if pd.notnull(day_d_prev['Vol_MA5']) else 0.0
    if d_prev_vol_ma5 <= 0 or float(day_d['Volume']) < d_prev_vol_ma5 * config.get("gap_vol_multiplier", 1.5):
        return False, {}

    # D+1 ~ D+3 連續 3 日收盤價皆不得回補缺口 (盤中低點回測不算)
    if not (hold_window['Close'] > prev_high).all():
        return False, {}

    return True, {
        "name": "跳空缺口D+3守穩",
        "key_price": round(prev_high, 2),
        "detail": f"D日跳空{gap_pct:.1f}%，連{hold_days}日收盤守穩缺口({prev_high:.2f})不補"
    }


def check_bollinger_squeeze_breakout(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    型態 6：布林通道壓縮開口突破第一根
    - 20 日布林通道頻寬收斂至近 60 日極窄水準（<= 12% 且 <= 近 60 日最窄頻寬的 1.30 倍）。
    - 昨日收盤價仍在布林上軌之下，今日收盤首度站上布林上軌，且通道頻寬開始張開。
    """
    bb_period = config.get("bb_period", 20)
    if len(df) < bb_period + 40:
        return False, {}

    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    if pd.isnull(today['BB_Upper']) or pd.isnull(yesterday['BB_Upper']) or pd.isnull(yesterday['BB_Width']):
        return False, {}

    bb_width_yest = float(yesterday['BB_Width'])
    bb_width_today = float(today['BB_Width'])

    recent_bb_widths = df['BB_Width'].iloc[-61:-1].dropna()
    if len(recent_bb_widths) < 20:
        return False, {}

    q25_bb_width = float(recent_bb_widths.quantile(0.25))
    max_allowed_width = config.get("bb_max_squeeze_width_pct", 12.0)

    is_squeezed = (bb_width_yest <= max_allowed_width) and (bb_width_yest <= max(q25_bb_width, 5.0))
    is_first_break = (float(yesterday['Close']) <= float(yesterday['BB_Upper'])) and (float(today['Close']) > float(today['BB_Upper']))
    is_expanding = bb_width_today > bb_width_yest

    if is_squeezed and is_first_break and is_expanding:
        return True, {
            "name": "布林壓縮突破",
            "key_price": round(float(today['BB_Upper']), 2),
            "detail": f"布林頻寬壓縮至{bb_width_yest:.1f}%，今日帶量突破上軌({float(today['BB_Upper']):.2f})"
        }
    return False, {}


def evaluate_stock_patterns(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """綜合檢驗五大型態，並套用量價配合與均線濾網"""
    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    bb_period = config.get("bb_period", 20)
    bb_std_mult = config.get("bb_std_dev", 2.0)
    bb_std = df['Close'].rolling(bb_period).std(ddof=0)
    df['BB_Upper'] = df['MA20'] + bb_std_mult * bb_std
    df['BB_Lower'] = df['MA20'] - bb_std_mult * bb_std
    df['BB_Width'] = ((df['BB_Upper'] - df['BB_Lower']) / df['MA20']) * 100.0

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    today_date = today.name.strftime('%Y-%m-%d') if hasattr(today.name, 'strftime') else str(today.name)

    ref_vol_ma = yesterday['Vol_MA5']
    vol_ratio = (today['Volume'] / ref_vol_ma) if ref_vol_ma > 0 else 0.0
    is_red_candle = (today['Close'] > today['Open'])
    price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
    
    vol_qualified = (vol_ratio >= config["vol_multiplier"])
    candle_qualified = is_red_candle if config["require_red_candle"] else (price_change_pct > 0)
    standard_volume_price_ok = vol_qualified and candle_qualified

    above_ma20 = (today['Close'] > today['MA20']) if config["require_above_ma20"] else True
    above_ma60 = (today['Close'] > today['MA60']) if (config["require_above_ma60"] and pd.notnull(today['MA60'])) else True
    ma_ok = above_ma20 and above_ma60

    volume_shares = int(today['Volume'] / 1000)
    liquidity_ok = volume_shares >= config.get("min_volume_shares", 500)

    matched_patterns = []
    details = []
    key_prices = []

    # 型態 1: 回檔突破前高 (波段整理後首根突破)
    p1_ok, p1_info = check_pullback_breakout(df, config)
    if p1_ok:
        matched_patterns.append("【回檔突破】")
        details.append(p1_info["detail"])
        key_prices.append(f"前高 {p1_info['key_price']}")

    # 型態 2: 強勢股【回後買上漲】(守穩月線重返5T)
    p3_ok, p3_info = check_reclaim_5ma_breakout(df, config)
    if p3_ok:
        matched_patterns.append("【回後買上漲】")
        details.append(p3_info["detail"])
        key_prices.append(f"5T線 {p3_info['key_price']}")

    # 型態 3: 疑似頭肩底「破切」第一根
    p4_ok, p4_info = check_head_and_shoulders_bottom(df, config)
    if p4_ok:
        matched_patterns.append("【頭肩底破切】")
        details.append(p4_info["detail"])
        key_prices.append(f"切線 {p4_info['key_price']}")

    # 型態 4: 跳空缺口 D+3 守穩 (D日跳空帶量 + 連3日收盤不補缺口)
    p5_ok, p5_info = check_gap_hold_d3(df, config)
    if p5_ok:
        matched_patterns.append("【跳空缺口D+3守穩】")
        details.append(p5_info["detail"])
        key_prices.append(f"缺口緣 {p5_info['key_price']}")

    # 型態 5: 布林通道壓縮開口突破
    p6_ok, p6_info = check_bollinger_squeeze_breakout(df, config)
    if p6_ok:
        matched_patterns.append("【布林壓縮突破】")
        details.append(p6_info["detail"])
        key_prices.append(f"布林上軌 {p6_info['key_price']}")

    is_pattern_hit = len(matched_patterns) > 0
    # 「回後買上漲」與「跳空缺口D+3守穩」皆有各自專屬的量能與K棒檢驗，不強迫 D+3 當日再度爆量 1.5x
    has_self_validated_pattern = any(p in matched_patterns for p in ["【回後買上漲】", "【跳空缺口D+3守穩】"])
    is_volume_valid = standard_volume_price_ok or has_self_validated_pattern

    fully_qualified = is_pattern_hit and is_volume_valid and ma_ok and liquidity_ok

    return {
        "qualified": fully_qualified,
        "date": today_date,
        "close": round(float(today['Close']), 2),
        "change_pct": round(float(price_change_pct), 2),
        "vol_ratio": round(float(vol_ratio), 2),
        "volume_shares": volume_shares,
        "matched_patterns": " + ".join(matched_patterns) if matched_patterns else "無型態",
        "key_prices": " / ".join(key_prices) if key_prices else "—",
        "pattern_details": "；".join(details) if details else "—",
        "volume_price_ok": is_volume_valid,
        "ma_ok": ma_ok,
    }


# =============================================================================
# 核心模組 3：高並行高速掃描
# =============================================================================
def scan_stock_worker(item: Any, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if isinstance(item, tuple):
        symbol, name = item
    else:
        symbol, name = item, item

    clean_code = re.sub(r"\.(TW|TWO)$", "", str(symbol).strip().upper())
    if not is_strictly_common_stock(clean_code, str(name)):
        return None

    timeout_sec = config.get("ticker_timeout_sec", 3.0)
    df = fetch_stock_daily_data(symbol, timeout_sec=timeout_sec)
    if df is not None:
        res = evaluate_stock_patterns(df, config)
        res["symbol"] = re.sub(r"\.(TW|TWO)$", "", str(symbol).strip().upper())
        res["name"] = name
        return res
    return None


def execute_market_scan(stock_candidates: List[Any], config: Dict[str, Any], max_workers: int = 14) -> List[Dict[str, Any]]:
    print(f"\n[極速掃描啟動] 正以多執行緒 (Threads: {max_workers}) 掃描 {len(stock_candidates)} 檔標的...")
    results = []
    start_t = time.time()
    max_total_sec = config.get("max_scan_total_sec", 600)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_stock_worker, item, config): item for item in stock_candidates}
        done_count = 0
        total_count = len(futures)
        
        for future in as_completed(futures):
            done_count += 1
            if done_count % 30 == 0 or done_count == total_count:
                print(f"  > 掃描進度: {done_count}/{total_count} ({done_count/total_count*100:.1f}%) ...", end="\r")
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                continue

            if time.time() - start_t > max_total_sec:
                print(f"\n[超時防護提醒] 掃描達到 {max_total_sec} 秒上限，自動收尾匯出目前已完成之 {len(results)} 檔標的！")
                break

    elapsed = time.time() - start_t
    print(f"\n[掃描完成] 耗時 {elapsed:.1f} 秒，成功分析 {len(results)} 檔標的！")
    return results


# =============================================================================
# 核心模組 4：LINE 官方帳號全標的無截斷推播 (多泡泡自動分批發送)
# =============================================================================
def build_all_line_message_bubbles(hits: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    不限檔數！將所有符合條件的標的全部完整列出，自動分派到多個泡泡中 (每個泡泡 <= 450 字)。
    """
    if not hits:
        return []

    max_chars = config.get("line_bubble_max_chars", 450)
    today_date = datetime.date.today().strftime("%Y/%m/%d")

    formatted_items = []
    for h in hits:
        symbol = h.get("symbol", "")
        name = h.get("name", "")
        close = h.get("close", 0)
        pct = h.get("change_pct", 0)
        patterns = h.get("matched_patterns", "")
        vol = h.get("vol_ratio", 0)
        detail = h.get("pattern_details", "")
        
        item_str = f"• {symbol} {name} {close} ({pct:+.2f}%)\n  {patterns} | 量比:{vol}x ({detail})"
        formatted_items.append(item_str)

    bubbles = []
    header = f"🔥【台股型態突破全名單】({today_date})\n共篩選出 {len(hits)} 檔強勢起漲/轉強標的："
    current_bubble_lines = [header, "-----------------------------"]
    current_len = len(header) + 32

    for item in formatted_items:
        item_len = len(item) + 4
        if current_len + item_len > max_chars:
            bubbles.append("\n\n".join(current_bubble_lines))
            current_bubble_lines = [item]
            current_len = item_len
        else:
            current_bubble_lines.append(item)
            current_len += item_len

    if current_bubble_lines:
        bubbles.append("\n\n".join(current_bubble_lines))

    return [{"type": "text", "text": b} for b in bubbles]


def print_and_notify_results(results: List[Dict[str, Any]], config: Dict[str, Any]):
    hits = [r for r in results if r["qualified"]]
    hits = sorted(hits, key=lambda x: x["change_pct"], reverse=True)

    headers = ["代號", "名稱/備註", "收盤價", "今日漲跌", "命中型態", "關鍵價位", "量比(5MA)", "成交張數", "判定"]
    table_rows = []
    
    display_list = hits if hits else results[:15]
    for r in display_list:
        status_flag = "🎯 命中推薦" if r["qualified"] else "— 未符合"
        chg_str = f"{r['change_pct']:+.2f}%"
        vol_str = f"{r['vol_ratio']:.2f}x"
        table_rows.append([
            r["symbol"], r.get("name", ""), r["close"], chg_str,
            r["matched_patterns"], r["key_prices"], vol_str,
            f"{r['volume_shares']}張", status_flag
        ])

    print("\n" + "=" * 96)
    print(f"  台股強勢底部/轉強突破掃描報告 (掃描總數: {len(results)} 檔 | 命中突破: {len(hits)} 檔)")
    print("=" * 96)
    if HAS_TABULATE:
        print(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))
    else:
        for row in table_rows:
            print(row)
    print("=" * 96)

    today_str = datetime.date.today().strftime("%Y%m%d")
    csv_file = f"tw_breakout_scan_{today_str}.csv"
    pd.DataFrame(results).to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"[CSV 報告] 已匯出完整分析至: {csv_file}")

    line_token = config.get("line_channel_access_token")
    is_broadcast = config.get("line_broadcast", True)
    line_uid = config.get("line_user_id")
    
    if hits and line_token and HAS_REQUESTS:
        message_bubbles = build_all_line_message_bubbles(hits, config)
        print(f"\n[LINE 訊息建構] 已將全部 {len(hits)} 檔股票完整切分為 {len(message_bubbles)} 個短訊息泡泡！")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }

        for batch_idx in range(0, len(message_bubbles), 5):
            batch_bubbles = message_bubbles[batch_idx : batch_idx + 5]
            
            if is_broadcast:
                print(f"[LINE 官方帳號] 正在廣播發送第 {batch_idx//5 + 1} 批泡泡 ({len(batch_bubbles)} 則)...")
                url = "https://api.line.me/v2/bot/message/broadcast"
                payload = {"messages": batch_bubbles}
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=12)
                    if resp.status_code == 200:
                        print(f"✓ [廣播成功] 第 {batch_idx//5 + 1} 批已公開送達！")
                    else:
                        print(f"✗ [廣播失敗] 狀態碼: {resp.status_code}, 原因: {resp.text}")
                except Exception as e:
                    print(f"✗ [連線異常] {e}")

            elif line_uid:
                print(f"[LINE 私訊] 正在發送第 {batch_idx//5 + 1} 批泡泡至個人...")
                url = "https://api.line.me/v2/bot/message/push"
                payload = {"to": line_uid, "messages": batch_bubbles}
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=12)
                    if resp.status_code == 200:
                        print(f"✓ [私訊成功] 第 {batch_idx//5 + 1} 批已送達個人手機！")
                    else:
                        print(f"✗ [私訊失敗] 狀態碼: {resp.status_code}, 原因: {resp.text}")
                except Exception as e:
                    print(f"✗ [連線異常] {e}")

    elif not hits:
        print("\n[通知] 今日掃描無符合強勢型態之標的，不發送推播干擾。")


# =============================================================================
# CLI 命令列進入點
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="台股五大強勢突破型態全自動監控工具")
    parser.add_argument("--market", choices=["top", "all", "custom"], default="top", 
                        help="掃描範圍: top (精選龍頭與熱門約220檔，預設最快), all (全台股1800+檔), custom (自選)")
    parser.add_argument("--stocks", nargs="+", help="指定自選代號 (如: 2330 2317 6274)")
    parser.add_argument("--threads", type=int, default=14, help="平行掃描執行緒數量 (預設: 14)")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()

    if args.stocks:
        candidates = [(s, s) for s in args.stocks if is_strictly_common_stock(re.sub(r"\.(TW|TWO)$", "", s), s)]
    elif args.market == "all":
        candidates = fetch_all_market_stock_codes()
    else:
        print(f"[市場範圍] 自動載入台股核心龍頭與高動能精選清單 (共 {len(CORE_TW_STOCKS)} 檔)...")
        candidates = [(s, s) for s in CORE_TW_STOCKS]

    results = execute_market_scan(candidates, config, max_workers=args.threads)
    print_and_notify_results(results, config)


if __name__ == "__main__":
    main()