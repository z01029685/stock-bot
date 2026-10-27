#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
台股「五大經典強勢起漲型態」全自動極速監控腳本 (全標的完整推播版)
=============================================================================
【五大起漲型態演算法】
1. 【回檔突破前高第一根】 (Pullback Breakout Bar 1):
   - 40 天波段高點後，至少回檔整理 3 天以上。
   - 昨日收盤價 < 前高，今日收盤價 > 前高 (首根站上)。
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
2. 【疑似圓弧底突破第一根】 (Rounding Bottom Breakout Bar 1):
   - 打底時間約 1 個月 (20~30 個交易日)，形成圓弧狀凹底。
   - 碗底深度 >= 4%，均線走平翻揚。
   - 昨日收盤價仍在碗緣頸線之下，今日出量長紅首度站上頸線。
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
3. 【疑似頭肩底「破切」第一根】 (Head & Shoulders Bottom Breakout of Neckline):
   - 打底時間約 1 個月 (20~30 個交易日)。
   - 完整三底架構：左肩 L1、頭部最低點 Head、右肩低點 L2 (右肩明顯高於頭部，不破底)。
   - 兩次反彈高點：左肩反彈高點 P1 與頭部反彈高點 P2 相連形成「頸線切線」。
   - 昨日收盤仍在切線之下，今日首度帶量長紅「破切站上切線」！
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
4. 【5/10/20MA 均線糾結突破第一根】 (MA Squeeze & Breakout Bar 1):
   - 5 日線 (5MA)、10 日線 (10MA)、20 日線 (20MA) 極致糾結壓縮 (三線差幅 <= 2.0%)。
   - 今日帶量收實體紅 K，股價同時強勢站上 5MA、10MA、20MA，均線開始形成多頭向上發散！
5. 【回後買上漲（破5T後重新站上第一根）】 (Pullback & Reclaim 5MA Bar 1):
   - 強勢多頭格局：20MA > 60MA 且股價站穩 20MA 月線。
   - 強勢短洗盤：前 1~3 天回檔跌破 5T 均線 (昨日收盤價 < 5MA)，但守穩在月線 20MA 之上。
   - 今日重新站回 5T：今日收實體紅 K (漲幅>=1.5%)，收盤價首度重新站上 5T 線！

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
    "vol_multiplier": 1.5,       # 突破日成交量需大於 5 日均量的 1.5 倍 (型態1~4)
    "require_red_candle": True,  # 必須收實體紅 K (Close > Open)
    "require_above_ma20": True,  # 股價必須站上 20MA (月線)
    "require_above_ma60": True,  # 股價必須站上 60MA (季線)
    "min_volume_shares": 500,    # 每日最低成交張數 (500 張)

    # 均線糾結參數設定
    "ma_squeeze_threshold_pct": 2.0, # 5MA/10MA/20MA 差幅門檻 (2.0% 以內視為極致糾結)

    # 「回後買上漲」精準過濾參數
    "reclaim_5ma_max_pullback_bars": 3, # 跌破 5MA 的回檔天數必須在 3 天以內
    "reclaim_5ma_min_gain_pct": 1.5,    # 今日站回 5T 之紅 K 漲幅至少 1.5% 以上
    "reclaim_5ma_vol_ratio": 1.2,       # 今日成交量至少為 5MA 均量的 1.2 倍

    # 各型態特定時間參數 (依用戶需求精準錨定 40 天波段大底，當日漲幅不設限，以 6277 宏正為唯一黃金標準)
    "min_base_lookback_days": 35, # 最小打底觀察天數 (精準錨定 40 天波段，35~52天，排除 28 天以內之過短整理如 3305)
    "max_base_lookback_days": 52, # 最大打底觀察天數 (約 2.5 個月，完美鎖定 6277 宏正 40 天大底)
    "min_bowl_depth_pct": 11.0,   # 圓弧底最低深度門檻 (提高至 11.0%，以 6277 深 14.8% 為標準，徹底排除 2207 深 7.7% 與 2353 深 5.3%)
    "max_rounding_right_pullback_pct": 3.8, # 右碗壁最大容許二次回檔幅度 (3.8%，排除如 3305 右側短期二次回檔破壞圓弧形態)
    "max_upper_shadow_pct": 50.0, # 上影線佔振幅最高上限 (50.0%，漲停直接放行，排除如 3305 留 82% 爆量長上影滯漲)
    "base_lookback_days": 40,    # 基準打底觀察天數 (以 40 天為最佳核心)
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

    # 1. 代號長度與格式：必須為嚴格 4 碼純數字
    if not (len(code) == 4 and code.isdigit()):
        return False

    # 2. 排除 ETF (00 開頭)、ETN (01/02 開頭)、TDR (91 開頭)
    if code.startswith(("00", "01", "02", "91")):
        return False

    # 3. 排除可轉債 (CB) 關鍵字
    if any(kw in name for kw in ["債", "CB", "可轉", "轉換公司債", "公司債"]):
        return False

    # 4. 排除權證關鍵字 (認購權證、認售權證、牛熊證、展延權證)
    if any(kw in name for kw in ["權證", "認購", "認售", "牛證", "熊證", "展延", "購", "售", "牛", "熊"]):
        return False

    # 5. 排除特別股關鍵字 (保留「力特」、「特力」等普通股，僅排除真正的特別股)
    if any(kw in name for kw in ["特別股", "甲特", "乙特", "丙特", "丁特", "戊特"]):
        return False
    if name.endswith("特") and name not in ["力特"]:
        return False

    return True


def fetch_all_market_stock_codes() -> List[Tuple[str, str]]:
    """
    從台灣證交所 (TWSE) 官方清單自動爬取全台股所有上市與上櫃股票代號及名稱。
    【多層防護機制】：
    1. 分區過濾：精確定位 HTML 表格中的「股票」區段，略過「特別股」、「可轉換公司債」、「認購(售)權證」等。
    2. 正則邊界：使用前後邊界 (?<![0-9a-zA-Z])\d{4}(?![0-9a-zA-Z])，防止 5 碼可轉債或 6 碼權證被誤截後 4 碼。
    3. 語意過濾：調用 is_strictly_common_stock()，徹底杜絕可轉債、權證、特別股。
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

                # 備用保險機制 (若分區標籤異常，使用嚴格邊界與 is_strictly_common_stock 雙重檢核)
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


def check_rounding_bottom(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    型態 2：疑似圓弧底 (U型底/碗公底) 突破第一根
    【以 6277 宏正為標準範例之嚴格圓弧底演算法】：
    1. 打底天數：自動在 20 ~ 48 天 (約 1~2.5 個月) 區間自適應搜尋最佳對稱碗型 (如 6277 打底 40 天)。
    2. 碗深深度：以 6277 (深 14.8%) 為標準範例，要求深度 >= 10.0%，嚴格剔除 3027 盛達 (深 8.4%) 與 6165 浪凡 (深 4.9%) 等扁平橫盤。
    3. 中間腹地下凹：中間 50% 均價必須實質低於左碗緣至少 4.5%，確保為真深凹碗底而非箱型震盪。
    4. 均線糾結互斥：若短期三線極致糾結 (差幅 <= 1.8%) 且深度小於 13%，歸類為【均線糾結突破】，不誤判為圓弧底。
    """
    min_lookback = config.get("min_base_lookback_days", 35)
    max_lookback = config.get("max_base_lookback_days", 52)
    min_depth = config.get("min_bowl_depth_pct", 11.0)

    if len(df) < min_lookback + 10:
        return False, {}

    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    # 計算均線糾結幅度
    ma5 = today['MA5'] if 'MA5' in today and pd.notnull(today['MA5']) else df['Close'].tail(5).mean()
    ma10 = today['MA10'] if 'MA10' in today and pd.notnull(today['MA10']) else df['Close'].tail(10).mean()
    ma20 = today['MA20'] if 'MA20' in today and pd.notnull(today['MA20']) else df['Close'].tail(20).mean()
    mas = [float(ma5), float(ma10), float(ma20)]
    ma_spread_pct = (max(mas) - min(mas)) / min(mas) * 100.0 if min(mas) > 0 else 99.0

    best_match = None
    best_score = -1.0

    for lookback in range(min_lookback, min(len(df) - 5, max_lookback + 1)):
        sub_df = df.iloc[-(lookback + 2) : -1]
        n = len(sub_df)
        if n < min_lookback:
            continue

        # 左碗緣：觀察視窗前 30% 區間的最高點
        left_len = max(3, int(n * 0.30))
        left_part = sub_df.iloc[:left_len]
        left_high = float(left_part['High'].max())

        # 碗底：整個打底視窗內的最低點
        min_low = float(sub_df['Low'].min())
        min_low_rel_idx = int(sub_df['Low'].values.argmin())

        # 碗底必須落在中間 20% ~ 80% 的合理腹地 (避免單邊暴跌或暴漲)
        if not (int(n * 0.20) <= min_low_rel_idx <= int(n * 0.80)):
            continue

        # 1. 碗深深度門檻 (嚴格 >= 10.0%，以 6277 宏正 14.8% 為標準，排除 3027 盛達 8.4%)
        bowl_depth = (left_high - min_low) / left_high * 100.0
        if bowl_depth < min_depth:
            continue

        # 2. 中間腹地實質下凹檢驗 (中間 50% 均價必須比左緣低至少 4.5%，非水平漂浮)
        mid_part = sub_df.iloc[int(n * 0.25) : int(n * 0.75)]
        mid_mean_price = float(mid_part['Close'].mean())
        if (left_high - mid_mean_price) / left_high * 100.0 < 4.5:
            continue

        # 3. 排除極致狹幅均線糾結橫盤 (若均線糾結 <= 1.8% 且深度 < 13.0%，屬於箱型橫盤，非圓弧底)
        if ma_spread_pct <= 1.8 and bowl_depth < 13.0:
            continue

        # 4. 確認左碗緣為前期具代表性的波段高點 (不能低於左半側其他高點)
        if left_high < float(sub_df['High'].iloc[:min_low_rel_idx].max()) * 0.98:
            continue

        # 5. 右碗壁平滑爬升檢驗 (右側不可有顯著短期二次回檔，如昇貿 3305 中途二次回檔 > 3.8%)
        # 真正的圓弧底 (如 6277 宏正) 從碗底爬升回頸線是一氣呵成的平滑圓弧；若中途有顯著回檔，屬於【回檔突破】，非圓弧底！
        right_half = sub_df.iloc[min_low_rel_idx :]
        if len(right_half) >= 5:
            right_closes = right_half['Close'].values
            running_max = np.maximum.accumulate(right_closes)
            max_pullback_pct = float(np.max((running_max - right_closes) / running_max * 100.0))
            max_allowed_pullback = config.get("max_rounding_right_pullback_pct", 3.8)
            if max_pullback_pct > max_allowed_pullback:
                continue

        # 6. 碗身天花板嚴格檢驗：左碗緣頸線必須是整段打底期間 (至昨日為止) 的最高天花板
        # 碗內 (從左碗緣後至昨日) 所有收盤價絕不能曾高於頸線！若曾收過頸線，代表為水平箱型上下刷洗 (如 2207 和泰車 5 天前早已收過 550)，絕非首度突破！
        bowl_body = sub_df.iloc[left_len : -1]
        if len(bowl_body) > 0 and float(bowl_body['Close'].max()) >= left_high * 0.998:
            continue

        neckline = left_high
        # 突破第一根條件校準 (依用戶指定：整理40天最好，當日漲幅不設限、漲停放行，但嚴格排除長上影倒貨與第2根追高)：
        # 1. 突破時效性：昨日收盤價必須在頸線之下，今日才首度越過頸線 (排除昨日已漲停突破之第2根)
        is_first_break_timing = (float(yesterday['Close']) < neckline) and (float(today['Close']) > neckline)
        # 昨日漲幅不得大於 4.0% (避免昨日已大漲突破，今天跑來蹭突破)
        yest_gain_pct = ((float(yesterday['Close']) - float(df.iloc[-3]['Close'])) / float(df.iloc[-3]['Close'])) * 100.0 if len(df) >= 3 else 0.0
        not_second_bar = yest_gain_pct < 4.0

        # 2. 當日漲幅不設限：只要收實體紅 K (Close > Open 且 Close > 昨收)，漲停 (+9.9%~10%) 完全放行！
        is_red_k = (float(today['Close']) > float(today['Open'])) and (float(today['Close']) > float(yesterday['Close']))

        # 3. 避免爆量滯漲長上影線：上影線不可超過振幅 50% (漲停無上影線直接通過，排除 3305 這種留 82% 上影之出貨線)
        today_range = float(today['High']) - float(today['Low'])
        upper_shadow = float(today['High']) - max(float(today['Open']), float(today['Close']))
        upper_shadow_ratio = (upper_shadow / today_range * 100.0) if today_range > 0 else 0.0
        max_shadow = config.get("max_upper_shadow_pct", 50.0)
        candle_quality_ok = is_red_k and (upper_shadow_ratio <= max_shadow)

        is_first_break = is_first_break_timing and not_second_bar and candle_quality_ok

        if is_first_break:
            # 以對稱性與打底深度的綜合評分選出最佳碗型
            symmetry = 1.0 - abs((n / 2.0) - min_low_rel_idx) / (n / 2.0)
            score = bowl_depth * (1.0 + symmetry)
            if score > best_score:
                best_score = score
                best_match = (True, {
                    "name": "圓弧底突破",
                    "key_price": round(float(neckline), 2),
                    "detail": f"打底{lookback}天(深{bowl_depth:.1f}%)首度越過碗緣"
                })

    if best_match:
        return best_match
    return False, {}


def check_head_and_shoulders_bottom(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """型態 3：疑似頭肩底「破切」第一根 (嚴格三波谷架構，避免與平滑圓弧底混淆)"""
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

    # 頭肩底實質檢驗：頭部深度必須比左肩和右肩更深 (至少 1.5% 以上)，避免把圓弧底碗底小波折誤判為頭部
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


def check_ma_squeeze_breakout(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """型態 4：5日、10日、20日均線極致糾結出量突破第一根"""
    today = df.iloc[-1]
    ma5 = today['MA5']
    ma10 = today['MA10']
    ma20 = today['MA20']

    if pd.isnull(ma5) or pd.isnull(ma10) or pd.isnull(ma20) or ma20 == 0:
        return False, {}

    mas = [float(ma5), float(ma10), float(ma20)]
    max_ma = max(mas)
    min_ma = min(mas)
    spread_pct = (max_ma - min_ma) / min_ma * 100.0

    threshold = config.get("ma_squeeze_threshold_pct", 2.0)
    is_squeezed = spread_pct <= threshold
    above_all_mas = float(today['Close']) > max_ma

    if is_squeezed and above_all_mas:
        return True, {
            "name": "均線糾結突破",
            "key_price": round(float(max_ma), 2),
            "detail": f"5/10/20MA極致糾結(差{spread_pct:.1f}%)，今日帶量發散站上"
        }
    return False, {}


def check_reclaim_5ma_breakout(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    型態 5：強勢股【回後買上漲】（均線多頭回檔跌破5T線，今日首度重新站上5T第一根）
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


def evaluate_stock_patterns(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """綜合檢驗五大型態，並套用量價配合與均線濾網"""
    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

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

    # 型態 2: 圓弧底突破 (優先評估底部型態，支援 20~48 天大中小碗底)
    p2_ok, p2_info = check_rounding_bottom(df, config)
    if p2_ok:
        matched_patterns.append("【圓弧底突破】")
        details.append(p2_info["detail"])
        key_prices.append(f"碗緣 {p2_info['key_price']}")

    # 型態 1: 回檔突破前高 (若同時為圓弧底，代表亦創波段前高)
    p1_ok, p1_info = check_pullback_breakout(df, config)
    if p1_ok:
        matched_patterns.append("【回檔突破】")
        details.append(p1_info["detail"])
        key_prices.append(f"前高 {p1_info['key_price']}")

    # 型態 3: 頭肩底破切 (若已是標準圓弧底，則不重複或誤判為頭肩底)
    p3_ok, p3_info = check_head_and_shoulders_bottom(df, config)
    if p3_ok and not p2_ok:
        matched_patterns.append("【頭肩底破切】")
        details.append(p3_info["detail"])
        key_prices.append(f"切線 {p3_info['key_price']}")

    # 型態 4: 5/10/20MA 均線糾結突破
    p4_ok, p4_info = check_ma_squeeze_breakout(df, config)
    if p4_ok:
        matched_patterns.append("【均線糾結突破】")
        details.append(p4_info["detail"])
        key_prices.append(f"糾結頂 {p4_info['key_price']}")

    # 型態 5: 強勢股【回後買上漲】
    p5_ok, p5_info = check_reclaim_5ma_breakout(df, config)
    if p5_ok:
        matched_patterns.append("【回後買上漲】")
        details.append(p5_info["detail"])
        key_prices.append(f"5T線 {p5_info['key_price']}")

    is_pattern_hit = len(matched_patterns) > 0
    is_volume_valid = standard_volume_price_ok or ("【回後買上漲】" in matched_patterns)

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

    # 嚴格防護過濾：確認代號與名稱為純普通股 (排除可轉債、權證、特別股)
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

    # 緊湊高密度條列格式 (每檔約 32~38 字，完整列出型態與關鍵數據)
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
        # 若加入此檔股票會超過 450 字，則開立新泡泡
        if current_len + item_len > max_chars:
            bubbles.append("\n\n".join(current_bubble_lines))
            current_bubble_lines = [item]
            current_len = item_len
        else:
            current_bubble_lines.append(item)
            current_len += item_len

    if current_bubble_lines:
        bubbles.append("\n\n".join(current_bubble_lines))

    # 包裝為 LINE Messaging API 的 messages 物件清單
    return [{"type": "text", "text": b} for b in bubbles]


def print_and_notify_results(results: List[Dict[str, Any]], config: Dict[str, Any]):
    hits = [r for r in results if r["qualified"]]
    hits = sorted(hits, key=lambda x: x["change_pct"], reverse=True)

    headers = ["代號", "名稱/備註", "收盤價", "今日漲跌", "命中型態", "關鍵價位", "量比(5MA)", "成交張數", "判定"]
    table_rows = []
    
    # 終端機表格完整列出所有命中標的！
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

    # 匯出 CSV 完整紀錄
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

        # LINE API 單次請求最多支援發送 5 個泡泡，若超過 5 個則分批次全部發送完畢，一檔不漏！
        for batch_idx in range(0, len(message_bubbles), 5):
            batch_bubbles = message_bubbles[batch_idx : batch_idx + 5]
            
            # 廣播模式 (Broadcast)
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

            # 私訊模式 (Push)
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