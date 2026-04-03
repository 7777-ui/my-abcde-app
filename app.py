import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# --- 核心策略函式 ---
def check_strategy(stock_df, market_status, mkt_bw, otc_bw):
    if len(stock_df) < 21: return "資料不足", 0
    
    # 計算技術指標
    df = stock_df.copy()
    bb = ta.bbands(df['Close'], length=20, std=2)
    df['ma20'] = ta.sma(df['Close'], length=20)
    df['ma5'] = ta.sma(df['Close'], length=5)
    df['bw'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / df['ma20'] * 100
    
    # 取得最新數據
    curr = df.iloc[-1]
    prev_ma20 = df['ma20'].iloc[-2]
    
    # 基礎濾網 (通用條件)
    slope_positive = curr['ma20'] > prev_ma20
    high_volume = (curr['Close'] * curr['Volume']) > 500000000 # 成交值 > 5億
    pct_chg = (curr['Close'] / df['Close'].iloc[-2] - 1) * 100
    price_above_up = curr['Close'] > bb['BBU_20_2.0'].iloc[-1] # 突破上軌
    
    bw = curr['bw']
    bw_ratio = 0
    if mkt_bw > 0: bw_ratio = bw / mkt_bw
    
    if not (slope_positive and high_volume and price_above_up):
        return "未達准入", bw

    # 策略判定邏輯
    res = "未達准入"
    
    # 策略 D/E 環境條件
    env_de = (mkt_bw > 14.5 or otc_bw > 9.5) and bw > 20
    
    if env_de and (0.8 <= bw_ratio <= 1.2):
        if 3 <= pct_chg <= 5: res = "【D：動能同步】"
    elif env_de and (1.2 < bw_ratio <= 2.0):
        if 3 <= pct_chg <= 7: res = "【E：超額擴張】"
    elif 5 <= bw <= 10:
        if 3 <= pct_chg <= 7: res = "【A：潛龍爆發】"
    elif 10 < bw <= 20:
        if 3 <= pct_chg <= 5: res = "【B：海巡狙擊】"
    elif 20 < bw <= 40:
        if 3 <= pct_chg <= 7: res = "【C：瘋狗浪】"

    # 燈號准入過濾
    if market_status == "🔴 紅燈" and "A" not in res: return "🔴 受限(需A策略)", bw
    if market_status == "🟡 黃燈" and not any(x in res for x in ["A", "B"]): return "🟡 受限(需A/B)", bw
    
    return res, bw

# --- 介面呈現 ---
st.title("姊布林ABCDE 策略戰情室")

# 1. 取得大盤數據判定燈號
@st.cache_data(ttl=3600)
def get_market_info():
    mkt = yf.download("^TWII", period="1mo", interval="1d")
    otc = yf.download("^TWO", period="1mo", interval="1d")
    # 此處簡化邏輯以符合您的燈號描述
    # 實際運算應包含 BW, 5MA, 20MA
    return mkt, otc

mkt_data, otc_data = get_market_info()

# 2. 側邊欄：輸入股票代碼
with st.sidebar:
    st.header("⚙️ 設定區")
    input_codes = st.text_area("請輸入股票代碼 (每行一個)", value="2330\n2317").split('\n')

if st.button("🚀 開始掃描戰情"):
    results = []
    # 預設市場狀態 (範例：需對接實際指數計算)
    market_status = "🟡 黃燈" 
    mkt_bw, otc_bw = 10.5, 8.2 

    for code in input_codes:
        code = code.strip()
        if not code: continue
        
        # 修正名稱顯示問題
        ticker_id = f"{code}.TW"
        t = yf.Ticker(ticker_id)
        # 優先抓取 shortName 或 longName
        info = t.info
        name = info.get('shortName') or info.get('longName') or info.get('symbol') or "未知"
        
        hist = t.history(period="2mo")
        status, bw = check_strategy(hist, market_status, mkt_bw, otc_bw)
        
        results.append({
            "股票代碼": code,
            "台股名稱": name, # 修正後的名稱欄位
            "判定結果": status,
            "個股帶寬%": f"{bw:.2f}%",
            "今日漲幅%": f"{(hist['Close'].pct_change().iloc[-1]*100):.2f}%" if not hist.empty else "0%"
        })
    
    st.table(pd.DataFrame(results))
