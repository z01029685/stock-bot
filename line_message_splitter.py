#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
LINE 官方帳號 500 字長度限制智慧切割與多泡泡廣播發送模組 (line_message_splitter.py)
=============================================================================
【問題背景】
LINE 官方帳號的單一文字訊息泡泡（Text Bubble）有字數長度限制（或超過時排版極長難以閱讀）。
如果一次篩選出的股票很多，將全部內容塞在同一則訊息會導致發送失敗或內容被截斷。

【最佳解決方案】
LINE Messaging API 允許在「單次請求（Single Request）」中夾帶最多 5 個訊息物件（Message Objects）：
    payload = {
        "messages": [
            {"type": "text", "text": "第 1 頁（第 1~4 檔）..."},
            {"type": "text", "text": "第 2 頁（第 5~8 檔）..."}
        ]
    }
【重要計費優勢】
LINE 官方帳號規定：一次請求內夾帶最多 5 個泡泡，在官方後台「依然只算扣 1 則訊息額度」！
完全不會因為切成多個泡泡而額外扣費！
=============================================================================
"""

from typing import List, Dict, Any

def split_stock_alerts_into_line_bubbles(
    hits: List[Dict[str, Any]],
    today_date_str: str = "",
    max_chars_per_bubble: int = 450,
    max_bubbles: int = 4
) -> List[Dict[str, str]]:
    """
    將股票突破清單智慧切割為多個不超過 450 字的 LINE 文字泡泡。
    
    :param hits: 命中股票資料清單
    :param today_date_str: 當日日期字串 (例如 "2026/10/16")
    :param max_chars_per_bubble: 每個泡泡最大字數 (預設 450 字，安全避開 500 字上限)
    :param max_bubbles: 最大泡泡數量 (LINE API 限制上限為 5 個，預設最多分 4 個)
    :return: LINE Messaging API 所需的 messages 陣列格式
    """
    if not hits:
        return []

    # 1. 精煉單檔股票字串排版 (每檔控制在約 40~55 字)
    formatted_items = []
    for h in hits[:15]: # 實戰中最精華的前 15 檔
        symbol = h.get("symbol", "")
        name = h.get("name", "")
        close = h.get("close", 0)
        pct = h.get("change_pct", 0)
        patterns = h.get("matched_patterns", "")
        vol = h.get("vol_ratio", 0)
        detail = h.get("pattern_details", "")
        
        item_text = (
            f"▶ {symbol} {name} {close} ({pct:+.2f}%)\n"
            f"  型態: {patterns} | 量比: {vol}x\n"
            f"  重點: {detail}"
        )
        formatted_items.append(item_text)

    # 2. 智慧組裝文字泡泡
    bubbles = []
    header = f"🔥【台股型態精選】({today_date_str})\n共篩選出 {len(hits)} 檔強勢起漲/轉強標的："
    current_bubble_lines = [header, "-----------------------------"]
    current_length = len(header) + 32

    for item in formatted_items:
        item_len = len(item) + 4
        # 若累積字數超過上限，且尚未達到泡泡總數限制，則開立新泡泡
        if (current_length + item_len > max_chars_per_bubble) and (len(bubbles) < max_bubbles - 1):
            bubbles.append("\n\n".join(current_bubble_lines))
            current_bubble_lines = [item]
            current_length = item_len
        else:
            current_bubble_lines.append(item)
            current_length += item_len

    if current_bubble_lines and len(bubbles) < max_bubbles:
        bubbles.append("\n\n".join(current_bubble_lines))

    # 3. 轉成 LINE Messaging API 規格
    return [{"type": "text", "text": b} for b in bubbles]


if __name__ == "__main__":
    # 模擬 8 檔股票測試切分效果
    sample_hits = [
        {
            "symbol": f"233{i}",
            "name": f"精選股{i}",
            "close": 120 + i * 2,
            "change_pct": 2.5 + i * 0.4,
            "vol_ratio": 1.6,
            "matched_patterns": "【回後買上漲】",
            "pattern_details": "守穩月線，今紅K放量重返5T線"
        }
        for i in range(8)
    ]
    
    bubbles = split_stock_alerts_into_line_bubbles(sample_hits, "2026/10/16")
    print(f"成功切分為 {len(bubbles)} 個訊息泡泡：")
    for idx, b in enumerate(bubbles, 1):
        print(f"\n[泡泡 {idx}] (字數: {len(b['text'])})")
        print(b["text"])