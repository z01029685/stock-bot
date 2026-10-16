#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
台股「四大經典強勢突破型態」全自動極速監控腳本
=============================================================================
【四大突破型態演算法】
1. 【回檔突破前高第一根】 (Pullback Breakout Bar 1):
   - 40 天波段高點後，至少回檔整理 3 天以上。
   - 昨日收盤價 < 前高，今日收盤價 > 前高 (首根站上)。
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
2. 【疑似圓弧底突破第一根】 (Rounding Bottom Breakout Bar 1):
   - 打底時間約 1 個月 (20~30 個交易日)，形成圓弧狀凹底。
   - 碗底深度 >= 4%，均線走平糾結翻揚。
   - 昨日收盤價仍在碗緣頸線之下，今日出量長紅首度站上頸線。
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
3. 【疑似頭肩底「破切」第一根】 (Head & Shoulders Bottom Breakout of Neckline):
   - 打底時間約 1 個月 (20~30 個交易日)。
   - 完整三底架構：左肩 L1、頭部最低點 Head、右肩低點 L2 (右肩明顯高於頭部，不破底)。
   - 兩次反彈高點：左肩反彈高點 P1 與頭部反彈高點 P2 相連形成「頸線切線」。
   - 昨日收盤仍在切線之下，今日首度帶量長紅「破切站上切線」！
   - 放量 1.5 倍 5MA + 實體紅 K + 站上月線與季線。
4. 【5/10/20MA 均線糾結突破第一根】 (MA Squeeze & Breakout Bar 1) [全新新增]:
   - 5 日線 (5MA)、10 日線 (10MA)、20 日線 (20MA) 極致糾結壓縮 (三線差幅 <= 2.0%)。
   - 今日帶量收實體紅 K，股價同時強勢站上 5MA、10MA、20MA，均線開始形成多頭向上發散！
   - 支援與上述底型複合觸發 (例如「頭肩底破切 + 均線糾結突破」，高勝率雙重共振)。

【執行模式】
- 預設模式 (極速推薦): python tw_stock_breakout_monitor.py
  (自動多執行緒掃描台股前 220 大高流動性與熱門成長主力股)
- 全市場大掃描:       python tw_stock_breakout_monitor.py --market all
  (自動連線證交所名冊，掃描全台股 1,800+ 檔上市櫃普通股)
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
    "min_volume_shares": 300,    # 每日最低成交張數 (過濾低於 300 張之冷門股)

    # 均線糾結參數設定
    "ma_squeeze_threshold_pct": 2.0, # 5MA/10MA/20MA 最大與最小差幅門檻 (預設 2.0% 以內視為極致糾結)

    # 各型態特定時間參數 (打底約 1 個月)
    "base_lookback_days": 28,    # 圓弧底與頭肩底打底觀察天數 (約 1 個月，20~30天)
    "swing_high_window": 40,     # 回檔突破前高的回溯天數 (40天)
    "min_pullback_bars": 3,      # 前高回檔最少天數 (3天)

    # 超時防卡死參數
    "ticker_timeout_sec": 3.0,   # 單檔行情抓取超時上限 (秒)
    "max_scan_total_sec": 240,   # 全程掃描最長執行時間 (秒，預設 4 分鐘自動收尾)
    
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
def fetch_all_market_stock_codes() -> List[Tuple[str, str]]:
    """
    從台灣證交所 (TWSE) 官方清單自動爬取全台股所有上市與上櫃股票代號及名稱
    """
    print("[資料更新] 正在連線台灣證券交易所 (TWSE) 抓取名冊...")
    all_stocks = []
    modes = [(2, "上市"), (4, "上櫃")]
    
    for mode_id, market_type in modes:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode_id}"
        try:
            resp = requests.get(url, timeout=8)
            resp.encoding = 'big5'
            if resp.status_code == 200:
                matches = re.findall(r'(\d{4})[\s\u3000]+([^\s<"]+)', resp.text)
                for code, name in matches:
                    if len(code) == 4 and code.isdigit() and not code.startswith("00"):
                        suffix = ".TW" if mode_id == 2 else ".TWO"
                        all_stocks.append((f"{code}{suffix}", f"{code} {name}"))
        except Exception:
            continue

    unique_stocks = []
    seen = set()
    for sym, label in all_stocks:
        if sym not in seen:
            seen.add(sym)
            unique_stocks.append((sym, label))
            
    print(f"[名冊完成] 取得有效普通股共 {len(unique_stocks)} 檔！")
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
# 核心模組 2：四大經典型態檢驗演算法
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
    """型態 2：疑似圓弧底 (U型底) 突破第一根"""
    lookback = config["base_lookback_days"]
    if len(df) < lookback + 10:
        return False, {}

    sub_df = df.iloc[-(lookback + 2) : -1]
    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    left_part = sub_df.iloc[: int(len(sub_df) * 0.35)]
    mid_part = sub_df.iloc[int(len(sub_df) * 0.2) : int(len(sub_df) * 0.8)]

    left_high = left_part['High'].max()
    mid_low = mid_part['Low'].min()

    bowl_depth = (left_high - mid_low) / left_high * 100
    if bowl_depth < 4.0:
        return False, {}

    neckline = left_high
    is_first_break = yesterday['Close'] < neckline and today['Close'] > neckline

    if is_first_break:
        return True, {
            "name": "圓弧底突破",
            "key_price": round(float(neckline), 2),
            "detail": f"打底{lookback}天(深{bowl_depth:.1f}%)首度越過碗緣"
        }
    return False, {}


def check_head_and_shoulders_bottom(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """型態 3：疑似頭肩底「破切」第一根"""
    lookback = config["base_lookback_days"]
    if len(df) < lookback + 10:
        return False, {}

    sub_df = df.iloc[-(lookback + 2) : -1]
    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    n = len(sub_df)

    head_rel_idx = sub_df['Low'].values.argmin()
    head_price = sub_df['Low'].iloc[head_rel_idx]

    if head_rel_idx < int(n * 0.2) or head_rel_idx > int(n * 0.75):
        return False, {}

    left_sub = sub_df.iloc[:head_rel_idx]
    right_sub = sub_df.iloc[head_rel_idx + 1 :]

    if len(left_sub) < 3 or len(right_sub) < 3:
        return False, {}

    p1_rel_idx = left_sub['High'].values.argmax()
    p1_price = left_sub['High'].iloc[p1_rel_idx]
    l1_price = left_sub['Low'].iloc[: max(1, p1_rel_idx + 1)].min()

    p2_rel_idx = right_sub['High'].values.argmax()
    p2_price = right_sub['High'].iloc[p2_rel_idx]
    p2_global_idx = head_rel_idx + 1 + p2_rel_idx
    l2_price = right_sub['Low'].min()

    if head_price >= l1_price or head_price >= l2_price:
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

    is_broke_cut = yesterday['Close'] < neckline_yest and today['Close'] > neckline_today

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

    # 突破確認：今日收盤價站上三條均線的高點，且收實體紅 K
    above_all_mas = float(today['Close']) > max_ma

    if is_squeezed and above_all_mas:
        return True, {
            "name": "均線糾結突破",
            "key_price": round(float(max_ma), 2),
            "detail": f"5/10/20MA極致糾結(差{spread_pct:.1f}%)，今日帶量發散站上"
        }
    return False, {}


def evaluate_stock_patterns(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    """綜合檢驗四大型態，並套用量價配合與均線濾網"""
    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    today_date = today.name.strftime('%Y-%m-%d') if hasattr(today.name, 'strftime') else str(today.name)

    # 1. 基礎濾網：量價配合 (放量 1.5 倍 + 實體紅 K)
    ref_vol_ma = yesterday['Vol_MA5']
    vol_ratio = (today['Volume'] / ref_vol_ma) if ref_vol_ma > 0 else 0.0
    is_red_candle = (today['Close'] > today['Open'])
    price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
    
    vol_qualified = (vol_ratio >= config["vol_multiplier"])
    candle_qualified = is_red_candle if config["require_red_candle"] else (price_change_pct > 0)
    volume_price_ok = vol_qualified and candle_qualified

    # 2. 均線濾網：站上月線 (20MA) 與季線 (60MA)
    above_ma20 = (today['Close'] > today['MA20']) if config["require_above_ma20"] else True
    above_ma60 = (today['Close'] > today['MA60']) if (config["require_above_ma60"] and pd.notnull(today['MA60'])) else True
    ma_ok = above_ma20 and above_ma60

    # 3. 流動性濾網 (成交張數 >= 300 張)
    volume_shares = int(today['Volume'] / 1000)
    liquidity_ok = volume_shares >= config.get("min_volume_shares", 300)

    # 4. 型態檢驗 (支援四大經典型態與複合觸發)
    matched_patterns = []
    details = []
    key_prices = []

    # 型態 1: 回檔突破前高
    p1_ok, p1_info = check_pullback_breakout(df, config)
    if p1_ok:
        matched_patterns.append("【回檔突破】")
        details.append(p1_info["detail"])
        key_prices.append(f"前高 {p1_info['key_price']}")

    # 型態 2: 圓弧底突破
    p2_ok, p2_info = check_rounding_bottom(df, config)
    if p2_ok:
        matched_patterns.append("【圓弧底突破】")
        details.append(p2_info["detail"])
        key_prices.append(f"碗緣 {p2_info['key_price']}")

    # 型態 3: 頭肩底破切
    p3_ok, p3_info = check_head_and_shoulders_bottom(df, config)
    if p3_ok:
        matched_patterns.append("【頭肩底破切】")
        details.append(p3_info["detail"])
        key_prices.append(f"切線 {p3_info['key_price']}")

    # 型態 4: 5/10/20MA 均線糾結突破 (新加入)
    p4_ok, p4_info = check_ma_squeeze_breakout(df, config)
    if p4_ok:
        matched_patterns.append("【均線糾結突破】")
        details.append(p4_info["detail"])
        key_prices.append(f"糾結頂 {p4_info['key_price']}")

    is_pattern_hit = len(matched_patterns) > 0
    fully_qualified = is_pattern_hit and volume_price_ok and ma_ok and liquidity_ok

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
        "volume_price_ok": volume_price_ok,
        "ma_ok": ma_ok,
    }


# =============================================================================
# 核心模組 3：高並行高速掃描 (含超時收尾機制)
# =============================================================================
def scan_stock_worker(item: Any, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if isinstance(item, tuple):
        symbol, name = item
    else:
        symbol, name = item, item

    timeout_sec = config.get("ticker_timeout_sec", 3.0)
    df = fetch_stock_daily_data(symbol, timeout_sec=timeout_sec)
    if df is not None:
        res = evaluate_stock_patterns(df, config)
        res["symbol"] = symbol.replace(".TW", "").replace(".TWO", "")
        res["name"] = name
        return res
    return None


def execute_market_scan(stock_candidates: List[Any], config: Dict[str, Any], max_workers: int = 14) -> List[Dict[str, Any]]:
    print(f"\n[極速掃描啟動] 正以多執行緒 (Threads: {max_workers}) 掃描 {len(stock_candidates)} 檔標的...")
    results = []
    start_t = time.time()
    max_total_sec = config.get("max_scan_total_sec", 240)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_stock_worker, item, config): item for item in stock_candidates}
        done_count = 0
        total_count = len(futures)
        
        for future in as_completed(futures):
            done_count += 1
            if done_count % 25 == 0 or done_count == total_count:
                print(f"  > 掃描進度: {done_count}/{total_count} ({done_count/total_count*100:.1f}%) ...", end="\r")
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                continue

            if time.time() - start_t > max_total_sec:
                print(f"\n[保護機制] 達到預設時間上限 ({max_total_sec}秒)，平滑收尾目前已完成的 {len(results)} 檔分析結果！")
                break

    elapsed = time.time() - start_t
    print(f"\n[掃描完成] 耗時 {elapsed:.1f} 秒，成功分析 {len(results)} 檔標的！")
    return results


# =============================================================================
# 核心模組 4：報表輸出與 LINE 官方帳號公開廣播
# =============================================================================
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
    print(f"  台股強勢底部突破掃描報告 (掃描總數: {len(results)} 檔 | 命中突破: {len(hits)} 檔)")
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
        today_date = datetime.date.today().strftime("%Y/%m/%d")
        msg_lines = [
            f"🔥【台股型態突破精選】({today_date})",
            f"共篩選出 {len(hits)} 檔「放量紅K + 站上月季線」強勢突破標的：",
            "-----------------------------"
        ]
        for h in hits[:10]:
            msg_lines.append(
                f"▶ {h['symbol']} {h.get('name', '')}\n"
                f"  現價: {h['close']} ({h['change_pct']:+.2f}%) | 放量: {h['vol_ratio']}倍\n"
                f"  型態: {h['matched_patterns']}\n"
                f"  價位: {h['key_prices']}\n"
                f"  說明: {h['pattern_details']}\n"
            )
        alert_text = "\n".join(msg_lines)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }

        if is_broadcast:
            print("\n[LINE 官方帳號] 正在進行【全員公開廣播推播 (Broadcast)】...")
            url = "https://api.line.me/v2/bot/message/broadcast"
            payload = {"messages": [{"type": "text", "text": alert_text}]}
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    print("✓ [廣播成功] 訊息已公開推播給所有加官方帳號好友的用戶！")
                else:
                    print(f"✗ [廣播失敗] 狀態碼: {resp.status_code}, 原因: {resp.text}")
            except Exception as e:
                print(f"✗ [連線異常] {e}")

        elif line_uid:
            print("\n[LINE 私訊] 正在發送至指定 User ID...")
            url = "https://api.line.me/v2/bot/message/push"
            payload = {"to": line_uid, "messages": [{"type": "text", "text": alert_text}]}
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    print("✓ [私訊成功] LINE 訊息已送達個人手機！")
                else:
                    print(f"✗ [私訊失敗] 狀態碼: {resp.status_code}, 原因: {resp.text}")
            except Exception as e:
                print(f"✗ [連線異常] {e}")

    elif not hits:
        print("\n[通知] 今日掃描無符合四大強勢型態之標的，不發送推播干擾。")


# =============================================================================
# CLI 命令列進入點
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="台股四大強勢突破型態全自動監控工具")
    parser.add_argument("--market", choices=["top", "all", "custom"], default="top", 
                        help="掃描範圍: top (精選龍頭與熱門約220檔，預設最快), all (全台股1800+檔), custom (自選)")
    parser.add_argument("--stocks", nargs="+", help="指定自選代號 (如: 2330 2317 6274)")
    parser.add_argument("--threads", type=int, default=14, help="平行掃描執行緒數量 (預設: 14)")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()

    if args.stocks:
        candidates = [(s, s) for s in args.stocks]
    elif args.market == "all":
        candidates = fetch_all_market_stock_codes()
    else:
        print(f"[市場範圍] 自動載入台股核心龍頭與高動能精選清單 (共 {len(CORE_TW_STOCKS)} 檔)...")
        candidates = [(s, s) for s in CORE_TW_STOCKS]

    results = execute_market_scan(candidates, config, max_workers=args.threads)
    print_and_notify_results(results, config)


if __name__ == "__main__":
    main()