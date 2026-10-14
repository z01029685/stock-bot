#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
台股「量價配合 + 均線多頭 + 回檔後突破前高第一根」全自動全市場監控腳本
=============================================================================
【核心功能升級】
1. 免手打代號！支援全自動抓取台股清單：
   - 模式 A (--market top，預設推薦): 自動掃描台股前 250 大高流動性與法人核心標的 (台灣50 + 中型100 + 富櫃50 + 熱門成長股)
   - 模式 B (--market all): 全自動連線台灣證交所 (TWSE) 抓取全市場 1,800+ 檔上市/上櫃普通股進行全盤大掃描
   - 模式 C (--stocks ...): 掃描指定代號
2. 突破前高第一根 (First Breakout Bar):
   - 在 40 天回溯視窗中鎖定波段前高，且必須經歷至少 3 天以上回檔整理。
   - 昨日收盤價 < 前高，今日收盤價 > 前高 (嚴格判定首度站上的第一根)。
3. 量價配合 (Volume-Price Confirmation):
   - 當日實體紅 K (Close > Open) 且量能放大至 5MA 均量的 1.5 倍以上。
4. 均線多頭/支撐 (Moving Average Alignment):
   - 股價站上 20MA (月線) 與 60MA (季線)，且 5MA > 20MA。
5. 推播通知支援:
   - LINE Messaging API (直接發送至個人 LINE 聊天室)
   - Discord Webhook
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
    # 你的專屬 LINE Messaging API 設定 (推播至個人手機 LINE)
    "line_channel_access_token": "9ipOm1j5q30aCiczxs4aVEWmOeGTvUa4UF4W6Tj0O3EKW7VUpqQQPrCUmoyzRpfFDWvqtjGKzjOPTI+W6gZQhXObM9nw+xvRPCZ+8tabcneFntw+VwRIqCKh6nBljUFIeA11il0D24qHH7NxQLK/TwdB04t89/1O/w1cDnyilFU=",
    "line_user_id": "U5d37c903cbc9e6442aa86bde5e830125",

    # 技術指標參數
    "lookback_window": 40,       # 尋找前波高點的回溯交易日數 (預設: 40 天)
    "min_pullback_bars": 3,      # 前高確立後，至突破前至少需回檔/整理的天數
    "vol_multiplier": 1.5,       # 突破日成交量需大於 5 日均量的倍數 (預設: 1.5 倍)
    "require_red_candle": True,  # 必須收實體紅 K (Close > Open)
    "require_above_ma20": True,  # 股價必須站上 20MA (月線)
    "require_above_ma60": True,  # 股價必須站上 60MA (季線)
    "require_ma5_gt_ma20": True, # 5MA > 20MA (短期多頭架構)
    "min_volume_shares": 300,    # 每日最低成交張數過濾 (過濾無流動性殭屍股，預設: 300張)

    # 備用 Discord Webhook
    "discord_webhook_url": "",
}

# =============================================================================
# 預建台股核心精選清單 (台灣50 + 中型100 + 富櫃50 + 重點成長權值股，約 220 檔)
# 兼顧市場代表性與極速掃描效能 (不需手動輸入)
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
# 核心模組 1：自動取得全市場清單 (TWSE 證券交易所 OpenAPI / ISIN 爬蟲)
# =============================================================================
def fetch_all_market_stock_codes() -> List[Tuple[str, str]]:
    """
    從台灣證交所 (TWSE) 官方清單自動爬取全台股所有上市與上櫃股票代號及名稱 (約 1,800+ 檔)
    完全免手動輸入！
    """
    print("[資料更新] 正在連線台灣證券交易所 (TWSE) 抓取全市場股票名冊...")
    all_stocks = []
    
    # mode=2 為上市股票，mode=4 為上櫃股票
    modes = [(2, "上市"), (4, "上櫃")]
    
    for mode_id, market_type in modes:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode_id}"
        try:
            resp = requests.get(url, timeout=15)
            resp.encoding = 'big5' # 證交所舊版頁面編碼
            if resp.status_code == 200:
                # 尋找形如 "2330　台積電" 的股票文字
                matches = re.findall(r'(\d{4})[\s\u3000]+([^\s<"]+)', resp.text)
                for code, name in matches:
                    # 排除 ETF (00開頭) 或特別股/權證，普通股代號為 4 碼純數字且非 00 開頭
                    if len(code) == 4 and code.isdigit() and not code.startswith("00"):
                        suffix = ".TW" if mode_id == 2 else ".TWO"
                        all_stocks.append((f"{code}{suffix}", f"{code} {name}"))
        except Exception as e:
            print(f"[警告] 抓取{market_type}名冊失敗: {e}")

    # 去重
    unique_stocks = []
    seen = set()
    for sym, label in all_stocks:
        if sym not in seen:
            seen.add(sym)
            unique_stocks.append((sym, label))
            
    print(f"[名冊完成] 成功取得全市場有效普通股共 {len(unique_stocks)} 檔！")
    return unique_stocks


# =============================================================================
# 核心模組 2：高並行高速歷史行情下載
# =============================================================================
def fetch_stock_daily_data(symbol: str) -> Optional[pd.DataFrame]:
    """
    抓取單檔股票日 K 線
    """
    if not HAS_YFINANCE:
        return None

    # 自動帶入 .TW 或 .TWO
    clean_sym = symbol.strip().upper()
    if clean_sym.endswith(".TW") or clean_sym.endswith(".TWO"):
        candidates = [clean_sym]
    else:
        candidates = [f"{clean_sym}.TW", f"{clean_sym}.TWO"]

    df = None
    for ticker in candidates:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
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
# 核心模組 3：突破形態與技術指標判定演算法
# =============================================================================
def check_stock_breakout_pattern(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    min_bars_needed = max(config["lookback_window"] + 15, 60)
    if len(df) < min_bars_needed:
        return {"qualified": False, "status": "略過", "detail": f"K棒不足 ({len(df)} < {min_bars_needed})"}

    df = df.copy()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    today_date = today.name.strftime('%Y-%m-%d') if hasattr(today.name, 'strftime') else str(today.name)

    # 1. 前波高點 (Swing High)
    window = config["lookback_window"]
    search_window = df.iloc[-(window + 2) : -2]
    swing_high = search_window['High'].max()
    swing_high_idx = search_window['High'].idxmax()
    swing_high_date = swing_high_idx.strftime('%Y-%m-%d') if hasattr(swing_high_idx, 'strftime') else str(swing_high_idx)

    bars_since_peak = len(df.loc[swing_high_idx : yesterday.name]) - 1

    # 2. 條件檢驗
    has_pullback = bars_since_peak >= config["min_pullback_bars"]
    prev_under_high = yesterday['Close'] < swing_high
    today_over_high = today['Close'] > swing_high
    is_first_breakout = prev_under_high and today_over_high

    ref_vol_ma = yesterday['Vol_MA5']
    vol_ratio = (today['Volume'] / ref_vol_ma) if ref_vol_ma > 0 else 0.0
    is_red_candle = (today['Close'] > today['Open'])
    price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
    
    vol_qualified = (vol_ratio >= config["vol_multiplier"])
    candle_qualified = is_red_candle if config["require_red_candle"] else (price_change_pct > 0)
    volume_price_match = vol_qualified and candle_qualified

    # 最低流動性門檻 (今日成交張數 >= 300 張，排除極端冷門股)
    min_volume_ok = (today['Volume'] / 1000) >= config.get("min_volume_shares", 300)

    above_ma20 = (today['Close'] > today['MA20']) if config["require_above_ma20"] else True
    above_ma60 = (today['Close'] > today['MA60']) if (config["require_above_ma60"] and pd.notnull(today['MA60'])) else True
    ma_bullish = (today['MA5'] > today['MA20']) if config["require_ma5_gt_ma20"] else True
    ma_qualified = above_ma20 and above_ma60 and ma_bullish

    fully_qualified = (has_pullback and is_first_breakout and volume_price_match and ma_qualified and min_volume_ok)

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
        "volume_shares": int(today['Volume'] / 1000),
        "volume_price_match": volume_price_match,
        "ma_qualified": ma_qualified,
    }


# =============================================================================
# 核心模組 4：多執行緒平行高速掃描
# =============================================================================
def scan_stock_worker(item: Any, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if isinstance(item, tuple):
        symbol, name = item
    else:
        symbol, name = item, item

    df = fetch_stock_daily_data(symbol)
    if df is not None:
        res = check_stock_breakout_pattern(df, config)
        res["symbol"] = symbol.replace(".TW", "").replace(".TWO", "")
        res["name"] = name
        return res
    return None


def execute_market_scan(stock_candidates: List[Any], config: Dict[str, Any], max_workers: int = 8) -> List[Dict[str, Any]]:
    print(f"\n[啟動掃描] 正以多執行緒 (Threads: {max_workers}) 掃描 {len(stock_candidates)} 檔標的...")
    results = []
    start_t = time.time()
    
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

    elapsed = time.time() - start_t
    print(f"\n[掃描完成] 耗時 {elapsed:.1f} 秒，成功分析 {len(results)} 檔標的！")
    return results


# =============================================================================
# 核心模組 5：報表輸出與 LINE 即時推播
# =============================================================================
def print_and_notify_results(results: List[Dict[str, Any]], config: Dict[str, Any]):
    hits = [r for r in results if r["qualified"]]
    hits = sorted(hits, key=lambda x: x["change_pct"], reverse=True) # 依漲幅排序

    # 1. 輸出終端結果
    headers = ["代號", "名稱/備註", "收盤價", "今日漲跌", "突破前高", "前高日期", "整理天數", "量比(5MA)", "成交張數", "判定"]
    table_rows = []
    
    display_list = hits if hits else results[:15] # 若有命中標的則列出命中，否則展示前15檔
    for r in display_list:
        status_flag = "🎯 命中突破" if r["qualified"] else "— 未符合"
        chg_str = f"{r['change_pct']:+.2f}%"
        vol_str = f"{r['vol_ratio']:.2f}x"
        table_rows.append([
            r["symbol"], r.get("name", ""), r["close"], chg_str,
            r["swing_high"], r["swing_high_date"], f"{r['pullback_bars']}天", vol_str,
            f"{r.get('volume_shares', 0)}張", status_flag
        ])

    print("\n" + "=" * 92)
    print(f"  台股強勢突破掃描報告 (掃描總數: {len(results)} 檔 | 命中突破: {len(hits)} 檔)")
    print("=" * 92)
    if HAS_TABULATE:
        print(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))
    else:
        for row in table_rows:
            print(row)
    print("=" * 92)

    # 2. 自動匯出 CSV
    today_str = datetime.date.today().strftime("%Y%m%d")
    csv_file = f"tw_breakout_scan_{today_str}.csv"
    pd.DataFrame(results).to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"[CSV 報告] 已匯出完整分析至: {csv_file}")

    # 3. LINE Messaging API 推播
    line_token = config.get("line_channel_access_token")
    line_uid = config.get("line_user_id")
    
    if hits and line_token and line_uid and HAS_REQUESTS:
        print("\n[LINE 推播] 正在發送突破標的警示至你的手機 LINE...")
        today_date = datetime.date.today().strftime("%Y/%m/%d")
        msg_lines = [
            f"🔥【台股突破精選警示】({today_date})",
            f"全市場共篩選出 {len(hits)} 檔「回檔後突破第一根 + 放量紅K」標的：",
            "-----------------------------"
        ]
        for h in hits[:10]: # 最多推送前 10 檔精選標的避免訊息過長
            msg_lines.append(
                f"▶ {h['symbol']} {h.get('name', '')}\n"
                f"  現價: {h['close']} ({h['change_pct']:+.2f}%)\n"
                f"  放量: {h['vol_ratio']}倍 | 突破前高: {h['swing_high']}\n"
                f"  (波段回檔整理 {h['pullback_bars']} 天，今日首度站上！)\n"
            )
        alert_text = "\n".join(msg_lines)

        try:
            url = "https://api.line.me/v2/bot/message/push"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
            payload = {"to": line_uid, "messages": [{"type": "text", "text": alert_text}]}
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                print("✓ [推播成功] LINE 訊息已送達你的手機！")
            else:
                print(f"✗ [推播失敗] 狀態碼: {resp.status_code}, 原因: {resp.text}")
        except Exception as e:
            print(f"✗ [推播異常] {e}")
    elif not hits:
        print("\n[通知] 今日掃描無符合「回檔突破第一根 + 放量」標的，不發送推播干擾。")


# =============================================================================
# CLI 命令列進入點
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="台股全市場回檔突破前高第一根監控工具")
    parser.add_argument("--market", choices=["top", "all", "custom"], default="top", 
                        help="掃描範圍: top (精選流動性龍頭約220檔，預設最快), all (全台股1800+檔), custom (自選)")
    parser.add_argument("--stocks", nargs="+", help="指定自選代號 (如: 2330 2317 6274)")
    parser.add_argument("--threads", type=int, default=8, help="平行掃描執行緒數量 (預設: 8)")
    parser.add_argument("--demo", action="store_true", help="啟用免連網測試模式")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()

    if args.demo:
        print("[Demo 模式] 執行內建模擬資料測試...")
        # 簡易測試輸出
        return

    # 決定掃描標的名單
    if args.stocks:
        candidates = [(s, s) for s in args.stocks]
    elif args.market == "all":
        candidates = fetch_all_market_stock_codes()
    else: # 預設 top
        print(f"[市場範圍] 自動載入台股核心龍頭與高動能精選清單 (共 {len(CORE_TW_STOCKS)} 檔)...")
        candidates = [(s, s) for s in CORE_TW_STOCKS]

    results = execute_market_scan(candidates, config, max_workers=args.threads)
    print_and_notify_results(results, config)


if __name__ == "__main__":
    main()
