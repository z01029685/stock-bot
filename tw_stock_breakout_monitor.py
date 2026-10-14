#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
台股「量價配合 + 均線多頭 + 回檔後突破前高第一根」自動監控腳本
=============================================================================
【核心選股與監控邏輯】
1. 突破前高第一根 (First Breakout Bar):
   - 在設定的回溯區間 (如 20~60 天) 內鎖定波段前高 (Swing High)。
   - 必須經歷至少 N 天 (預設 3 天以上) 的回檔/橫盤整理。
   - 前一日收盤價 < 前波高點 (尚未突破)。
   - 今日收盤價 > 前波高點 (首度站上前高，精確捕捉第一根)。
2. 量價配合 (Volume-Price Confirmation):
   - 當日為實體紅 K (收盤價 > 開盤價) 且收漲。
   - 當日成交量顯著放大，大於 5 日均量 (5MA Vol) 的 1.5 倍以上 (排除無量虛漲)。
3. 均線多頭/支撐 (Moving Average Alignment):
   - 股價站上 20MA (月線) 與 60MA (季線)。
   - 5MA > 20MA (短均線維持多頭架構或翻揚向上)。

【使用方式】
1. 安裝必要套件:
   pip install yfinance pandas tabulate requests
2. 執行指令範例:
   - 立即掃描預設焦點股:       python tw_stock_breakout_monitor.py
   - 指定股票代號掃描:         python tw_stock_breakout_monitor.py --stocks 2330 2317 2454
   - 模擬驗證模式 (無須網路):   python tw_stock_breakout_monitor.py --demo
   - 定時每日盤後自動執行:     python tw_stock_breakout_monitor.py --schedule 14:00
=============================================================================
"""

import os
import sys
import time
import argparse
import datetime
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

# 嘗試載入選用庫 (若使用者本機未安裝會提供友善提示)
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
# 系統預設參數設定
# =============================================================================
DEFAULT_CONFIG = {
"line_channel_access_token": "9ipOm1j5q30aCiczxs4aVEWmOeGTvUa4UF4W6Tj0O3EKW7VUpqQQPrCUmoyzRpfFDWvqtjGKzjOPTI+W6gZQhXObM9nw+xvRPCZ+8tabcneFntw+VwRIqCKh6nBljUFIeA11il0D24qHH7NxQLK/TwdB04t89/1O/w1cDnyilFU=",
"line_user_id": "U5d37c903cbc9e6442aa86bde5e830125",
    # 技術指標參數
    "lookback_window": 40,       # 尋找前波高點的回溯交易日數 (建議 20 ~ 60 天)
    "min_pullback_bars": 3,      # 前高出現後，至突破前至少需回檔/整理的天數
    "vol_multiplier": 1.5,       # 突破日成交量需大於 5 日均量的倍數 (預設 1.5 倍)
    "require_red_candle": True,  # 必須收實體紅 K (Close > Open)
    "require_above_ma20": True,  # 股價必須站上 20MA (月線)
    "require_above_ma60": True,  # 股價必須站上 60MA (季線，若資料足夠)
    "require_ma5_gt_ma20": True, # 5MA > 20MA (短期多頭架構)
    
    # 預設追蹤台股清單 (上市/上櫃熱門標的)
    "watchlist": [
        "2330",  # 台積電
        "2317",  # 鴻海
        "2454",  # 聯發科
        "2382",  # 廣達
        "3231",  # 緯創
        "2376",  # 技嘉
        "2603",  # 長榮
        "2609",  # 陽明
        "3035",  # 智原
        "3443",  # 創意
        "3661",  # 世芯-KY
        "6669",  # 緯穎
        "6274",  # 台燿
    ],
    
    # LINE / Discord 通知設定 (填入 Token 或 Webhook URL 即可啟用)
    "line_channel_access_token": "9ipOm1j5q30aCiczxs4aVEWmOeGTvUa4UF4W6Tj0O3EKW7VUpqQQPrCUmoyzRpfFDWvqtjGKzjOPTI+W6gZQhXObM9nw+xvRPCZ+8tabcneFntw+VwRIqCKh6nBljUFIeA11il0D24qHH7NxQLK/TwdB04t89/1O/w1cDnyilFU=",     # e.g., "YOUR_LINE_NOTIFY_TOKEN"
    "discord_webhook_url": "",   # e.g., "https://discord.com/api/webhooks/..."
}


# =============================================================================
# 核心模組 1：資料取得 (支援 yfinance 與 離線模擬資料)
# =============================================================================
def fetch_tw_stock_data(symbol: str, days: int = 150) -> Optional[pd.DataFrame]:
    """
    抓取台股日 K 線歷史資料 (自動適配上市 .TW 與上櫃 .TWO 代號)
    """
    if not HAS_YFINANCE:
        print("[警告] 尚未安裝 yfinance 套件。請執行: pip install yfinance")
        return None

    clean_symbol = symbol.strip().upper().replace(".TW", "").replace(".TWO", "")
    
    # 優先嘗試上市 (.TW)，若無資料則嘗試上櫃 (.TWO)
    candidates = [f"{clean_symbol}.TW", f"{clean_symbol}.TWO"]
    df = None
    
    for ticker in candidates:
        try:
            # 抓取大約 6 個月資料以確保足夠計算 60MA
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if not hist.empty and len(hist) >= 30:
                df = hist
                break
        except Exception:
            continue
            
    if df is None or df.empty:
        return None

    # 欄位正規化
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.dropna(inplace=True)
    return df


def generate_demo_dataset() -> Dict[str, Tuple[str, pd.DataFrame]]:
    """
    生成 5 種具代表性的模擬盤勢情境，供使用者免聯網測試與邏輯驗證:
    1. 2330: 【完全符合】回檔 12 天後，今日首度出量長紅突破波段前高
    2. 2317: 【量能不足】突破前高，但成交量未達 5MA 的 1.5 倍
    3. 2454: 【非第一根】昨日已突破前高，今日為第二根續漲
    4. 2382: 【帶量但未破】帶量長紅，但收盤價仍在前高壓制之下
    5. 2603: 【均線空頭】雖破高但均線處於空頭且跌破 20MA
    """
    np.random.seed(101)
    dates = pd.date_range(end=datetime.date.today(), periods=80, freq='B')
    
    scenarios = {}
    
    # --- 情境 1: 完美符合 (2330) ---
    c1 = np.linspace(80, 100, 45).tolist() # 前波高點 100 在第 45 天
    c1 += np.linspace(95, 88, 15).tolist() # 回檔至 88
    c1 += np.linspace(89, 97, 19).tolist() # 橫盤整理，昨日收 97 (未破 100)
    c1.append(105.0)                       # 今日長紅突破 105 (> 100 前高)
    h1 = [c + 1.0 for c in c1]; h1[44] = 100.5; h1[-1] = 106.0
    l1 = [c - 1.0 for c in c1]
    o1 = [c - 0.5 for c in c1]; o1[-1] = 98.0 # 開 98 收 105 (實體紅 K)
    v1 = [4000 for _ in range(79)]
    v1.append(11000) # 成交量暴增 2.75 倍
    df1 = pd.DataFrame({'Open': o1, 'High': h1, 'Low': l1, 'Close': c1, 'Volume': v1}, index=dates)
    scenarios["2330"] = ("台積電 (完美突破第一根)", df1)

    # --- 情境 2: 量能不足 (2317) ---
    c2 = list(c1)
    v2 = [4000 for _ in range(80)] # 量能平平，未放量
    df2 = pd.DataFrame({'Open': o1, 'High': h1, 'Low': l1, 'Close': c2, 'Volume': v2}, index=dates)
    scenarios["2317"] = ("鴻海 (突破但未放量)", df2)

    # --- 情境 3: 非第一根 (2454) ---
    c3 = list(c1)
    c3[-2] = 103.0 # 昨日收盤 103 已經突破 100 前高，今日是第二根
    df3 = pd.DataFrame({'Open': o1, 'High': h1, 'Low': l1, 'Close': c3, 'Volume': v1}, index=dates)
    scenarios["2454"] = ("聯發科 (已是第二根，非首度突破)", df3)

    # --- 情境 4: 帶量但尚未突破 (2382) ---
    c4 = list(c1)
    c4[-1] = 99.0 # 今日收 99，仍低於前高 100.5
    df4 = pd.DataFrame({'Open': o1, 'High': h1, 'Low': l1, 'Close': c4, 'Volume': v1}, index=dates)
    scenarios["2382"] = ("廣達 (帶量逼近但未過高)", df4)

    # --- 情境 5: 破高但均線走空 (2603) ---
    c5 = np.linspace(140, 90, 79).tolist()
    c5.append(98.0) # 今日跌深反彈碰前高，但均線在極度空頭向下
    h5 = [c + 1.0 for c in c5]; h5[-1] = 99.0
    l5 = [c - 1.0 for c in c5]
    o5 = [c - 0.5 for c in c5]
    v5 = [3000 for _ in range(79)] + [8000]
    df5 = pd.DataFrame({'Open': o5, 'High': h5, 'Low': l5, 'Close': c5, 'Volume': v5}, index=dates)
    scenarios["2603"] = ("長榮 (均線架構偏空)", df5)

    return scenarios


# =============================================================================
# 核心模組 2：形態辨識與技術指標檢驗演算法
# =============================================================================
def check_stock_breakout_pattern(
    df: pd.DataFrame, 
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    核心演算法：檢查是否符合「回檔後突破前高第一根 + 量價配合 + 均線多頭」
    """
    min_bars_needed = max(config["lookback_window"] + 15, 65)
    if len(df) < min_bars_needed:
        return {
            "qualified": False, 
            "status": "略過", 
            "detail": f"歷史 K 棒不足 ({len(df)} < {min_bars_needed})"
        }

    # 1. 計算均線與成交量指標
    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    today_date = today.name.strftime('%Y-%m-%d') if hasattr(today.name, 'strftime') else str(today.name)

    # 2. 定位前波高點 (Swing High)
    # 取今天之前 lookback_window 內的資料 (排除今天與昨天，以確保有足夠回檔與突破空間)
    window = config["lookback_window"]
    search_window = df.iloc[-(window + 2) : -2]
    
    # 尋找區間最高價
    swing_high = search_window['High'].max()
    swing_high_idx = search_window['High'].idxmax()
    swing_high_date = swing_high_idx.strftime('%Y-%m-%d') if hasattr(swing_high_idx, 'strftime') else str(swing_high_idx)

    # 計算自前高到昨日為止經歷了幾根 K 棒
    bars_since_peak = len(df.loc[swing_high_idx : yesterday.name]) - 1

    # 3. 條件檢驗 A: 回檔整理檢驗 (避免連續創高或無回檔直接噴發)
    has_pullback = bars_since_peak >= config["min_pullback_bars"]

    # 4. 條件檢驗 B: 突破前高「第一根」檢驗
    # 昨日收盤價 < 前高，且今日收盤價 > 前高
    prev_under_high = yesterday['Close'] < swing_high
    today_over_high = today['Close'] > swing_high
    is_first_breakout = prev_under_high and today_over_high

    # 5. 條件檢驗 C: 量價配合檢驗
    ref_vol_ma = yesterday['Vol_MA5'] # 參考昨日 5 日均量
    vol_ratio = (today['Volume'] / ref_vol_ma) if ref_vol_ma > 0 else 0.0
    is_red_candle = (today['Close'] > today['Open'])
    price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
    
    vol_qualified = (vol_ratio >= config["vol_multiplier"])
    candle_qualified = is_red_candle if config["require_red_candle"] else (price_change_pct > 0)
    volume_price_match = vol_qualified and candle_qualified

    # 6. 條件檢驗 D: 均線架構檢驗
    above_ma20 = (today['Close'] > today['MA20']) if config["require_above_ma20"] else True
    above_ma60 = (today['Close'] > today['MA60']) if (config["require_above_ma60"] and pd.notnull(today['MA60'])) else True
    ma_bullish = (today['MA5'] > today['MA20']) if config["require_ma5_gt_ma20"] else True
    ma_qualified = above_ma20 and above_ma60 and ma_bullish

    # 綜合判定
    fully_qualified = (has_pullback and is_first_breakout and volume_price_match and ma_qualified)

    # 狀態標記與診斷說明
    checklist = []
    if is_first_breakout and has_pullback:
        checklist.append("突破第一根✓")
    elif not prev_under_high and today_over_high:
        checklist.append("非首度突破(已連續突破)✗")
    elif not today_over_high:
        checklist.append("尚未收過前高✗")
    else:
        checklist.append("回檔不足✗")

    if volume_price_match:
        checklist.append(f"放量紅K({vol_ratio:.1f}x)✓")
    else:
        checklist.append(f"量價未達標({vol_ratio:.1f}x)✗")

    if ma_qualified:
        checklist.append("均線多頭✓")
    else:
        checklist.append("均線偏弱✗")

    return {
        "qualified": fully_qualified,
        "date": today_date,
        "close": round(float(today['Close']), 2),
        "change_pct": round(float(price_change_pct), 2),
        "swing_high": round(float(swing_high), 2),
        "swing_high_date": swing_high_date,
        "pullback_bars": bars_since_peak,
        "is_first_breakout": is_first_breakout,
        "vol_ratio": round(float(vol_ratio), 2),
        "volume_price_match": volume_price_match,
        "ma_qualified": ma_qualified,
        "status_summary": " / ".join(checklist)
    }


# =============================================================================
# 核心模組 3：報表輸出與即時通知 (Console / CSV / Webhook)
# =============================================================================
def print_scan_report(results: List[Dict[str, Any]], title: str = "台股型態掃描報告"):
    """
    格式化終端機表格輸出
    """
    headers = [
        "代號", "名稱/備註", "今日收盤", "今日漲跌", 
        "前高價位", "前高日期", "整理天數", "量比(對5MA)", "首根突破", "判定結果"
    ]
    
    table_rows = []
    for r in results:
        status_flag = "🎯 命中突破" if r["qualified"] else "— 未符合"
        first_break_flag = "是 (第1根)" if r["is_first_breakout"] else "否"
        chg_str = f"{r['change_pct']:+.2f}%"
        vol_str = f"{r['vol_ratio']:.2f}倍"

        table_rows.append([
            r["symbol"],
            r.get("name", ""),
            r["close"],
            chg_str,
            r["swing_high"],
            r["swing_high_date"],
            f"{r['pullback_bars']} 天",
            vol_str,
            first_break_flag,
            status_flag
        ])

    print("\n" + "=" * 88)
    print(f"  {title} (執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 88)
    
    if HAS_TABULATE:
        print(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))
    else:
        # 簡易純文字表格
        print(f"{'代號':<6} {'收盤':<8} {'漲跌':<8} {'前高':<8} {'量比':<8} {'判定結果'}")
        for row in table_rows:
            print(f"{row[0]:<6} {row[2]:<8} {row[3]:<8} {row[4]:<8} {row[7]:<8} {row[9]}")
    
    print("=" * 88)
    
    # 匯出命中清單
    hits = [r for r in results if r["qualified"]]
    print(f"\n[掃描統計] 共掃描 {len(results)} 檔，符合「回檔突破前高第一根 + 量價配合」標的共 {len(hits)} 檔。")
    if hits:
        print("\n🔥 【強勢突破精選標的】:")
        for h in hits:
            print(f"  ▶ {h['symbol']} {h.get('name', '')}: 收盤 {h['close']} ({h['change_pct']:+.2f}%)，"
                  f"放量 {h['vol_ratio']}x 突破前高 {h['swing_high']} (前波整理 {h['pullback_bars']} 天)！")


def export_results_to_csv(results: List[Dict[str, Any]], filename: Optional[str] = None):
    """
    將掃描結果存檔為 CSV
    """
    if not filename:
        today_str = datetime.date.today().strftime("%Y%m%d")
        filename = f"tw_stock_breakout_report_{today_str}.csv"
    
    df_res = pd.DataFrame(results)
    df_res.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"[檔案匯出] 掃描結果已成功存檔至: {filename}")


def send_alerts(hits: List[Dict[str, Any]], config: Dict[str, Any]):
    """
    支援推播至 LINE Notify 或 Discord Webhook
    """
    if not hits:
        return

    msg_lines = ["【台股突破監控警示】符合量價配合突破第一根:"]
    for h in hits:
        msg_lines.append(
            f"• {h['symbol']} {h.get('name', '')}: 現價 {h['close']} ({h['change_pct']:+.2f}%) "
            f"放量 {h['vol_ratio']}x 破前高 {h['swing_high']}"
        )
    alert_text = "\n".join(msg_lines)

    # LINE Notify
    token = config.get("line_notify_token")
    if token and HAS_REQUESTS:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            data = {"message": alert_text}
            requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data, timeout=5)
            print("[推播通知] LINE Notify 警示已成功送出！")
        except Exception as e:
            print(f"[推播錯誤] LINE Notify 發送失敗: {e}")

    # Discord Webhook
    discord_url = config.get("discord_webhook_url")
    if discord_url and HAS_REQUESTS:
        try:
            payload = {"content": alert_text}
            requests.post(discord_url, json=payload, timeout=5)
            print("[推播通知] Discord 警示已成功送出！")
        except Exception as e:
            print(f"[推播錯誤] Discord Webhook 發送失敗: {e}")


# =============================================================================
# 核心模組 4：執行引擎與定時排程邏輯
# =============================================================================
def run_scan(stock_list: List[str], config: Dict[str, Any], is_demo: bool = False):
    """
    主掃描迴圈
    """
    results = []
    
    if is_demo:
        print("[執行模式] 正在以內建情境模擬資料執行診斷...")
        dataset = generate_demo_dataset()
        for symbol, (name, df) in dataset.items():
            res = check_stock_breakout_pattern(df, config)
            res["symbol"] = symbol
            res["name"] = name
            results.append(res)
    else:
        print(f"[執行模式] 即時連線掃描中 (共 {len(stock_list)} 檔標的)...")
        for symbol in stock_list:
            df = fetch_tw_stock_data(symbol)
            if df is not None:
                res = check_stock_breakout_pattern(df, config)
                res["symbol"] = symbol
                res["name"] = ""
                results.append(res)
            else:
                print(f"  - [{symbol}] 資料抓取失敗或代號不存在，跳過。")
            time.sleep(0.3) # 避免對 Yahoo Finance 頻繁請求

    if results:
        print_scan_report(results)
        export_results_to_csv(results)
        
        hits = [r for r in results if r["qualified"]]
        send_alerts(hits, config)
    else:
        print("[資訊] 未取得任何有效股票資料。")


def run_scheduled_daemon(stock_list: List[str], config: Dict[str, Any], target_time_str: str):
    """
    盤後定時自動排程常駐監控 (例如每天 14:00 執行)
    """
    print(f"\n[排程守護程序啟動] 每日預定執行時間: {target_time_str} (台股盤後)")
    print("按下 Ctrl + C 即可終止程序。\n")
    
    executed_today = False
    
    while True:
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        
        # 僅在平日 (週一至週五) 執行
        is_weekday = now.weekday() < 5
        
        if is_weekday and current_time_str == target_time_str and not executed_today:
            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 觸發盤後自動掃描任務！")
            run_scan(stock_list, config, is_demo=False)
            executed_today = True
            time.sleep(60) # 暫停 1 分鐘避免重複觸發
            
        # 換日後重置標記
        if current_time_str == "00:00":
            executed_today = False
            
        time.sleep(10)


# =============================================================================
# CLI 命令列進入點
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="台股回檔突破前高第一根 + 量價均線監控工具")
    parser.add_argument("--stocks", nargs="+", help="指定要掃描的台股代號 (如: 2330 2317 2454)")
    parser.add_argument("--demo", action="store_true", help="啟用免聯網情境模擬測試")
    parser.add_argument("--schedule", type=str, help="指定每日自動執行的盤後時間 (格式: HH:MM，如 14:30)")
    parser.add_argument("--window", type=int, default=40, help="尋找前波高點的回溯天數 (預設: 40)")
    parser.add_argument("--vol-mult", type=float, default=1.5, help="量能放大倍數門檻 (預設: 1.5 倍 5MA)")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    config["lookback_window"] = args.window
    config["vol_multiplier"] = args.vol_mult

    stock_list = args.stocks if args.stocks else config["watchlist"]

    if args.demo:
        run_scan(stock_list, config, is_demo=True)
    elif args.schedule:
        run_scheduled_daemon(stock_list, config, args.schedule)
    else:
        # 若未安裝 yfinance 則自動提示並切換至 demo 模式示範
        if not HAS_YFINANCE:
            print("==================================================================")
            print("【環境提示】本機尚未偵測到 yfinance 庫。")
            print("若需即時抓取台股行情，請在終端執行: pip install yfinance")
            print("現在自動為您啟動【模擬驗證模式 (Demo)】展示篩選與判定邏輯：")
            print("==================================================================")
            run_scan(stock_list, config, is_demo=True)
        else:
            run_scan(stock_list, config, is_demo=False)


if __name__ == "__main__":
    main()
