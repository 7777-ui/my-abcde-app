import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests

# --- 1. 設置網頁標題與密碼鎖 ---
st.set_page_config(page_title="🏹 ABCDE 戰情室", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    st.title("🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": # <--- 這裡請自行修改密碼
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    return False

if not check_password():
    st.stop()

# --- 2. 核心抓取邏輯 (快取名稱表) ---
@st.cache_data
def get_stock_names():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        url_otc = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        def fetch(u):
            r = requests.get(u)
            d = pd.read_html(r.text)[0]
            d.columns = d.iloc[0]
            d = d.iloc[1:]
            res = {}
            for v in d['有價證券代號及名稱']:
                p = str(v).split('\u3000')
                if len(p) >= 2: res[p[0]] = p[1]
            return res
        all_names = fetch(url)
        all_names.update(fetch(url_otc))
        return all_names
    except: return {}

stock_names = get_stock_names()

# --- 3. 大盤環境偵測 (徹底解決週末報錯版本) ---
def get_market_status():
    status = {}
    def get_market_status():
    status = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for name, sym in indices.items():
        # 抓取最近一個月資料
        df = yf.download(sym, period="1mo", interval="1d", progress=False)
        
        # 核心防呆：如果 df 是空的，直接給預設值跳過
        if df is None or df.empty or len(df) < 5:
            status[name] = {"燈號": "⚪ 無資料", "帶寬": 0.0, "門檻": 0.0}
            continue
            
        try:
            # 計算指標
            df['5MA'] = df['Close'].rolling(5).mean()
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            # 取得最後一個「非空值」的列
            valid_df = df.dropna(subset=['Close', '5MA', '20MA', 'BW'])
            if valid_df.empty:
                status[name] = {"燈號": "⚪ 計算失敗", "帶寬": 0.0, "門檻": 0.0}
                continue
                
            curr = valid_df.iloc[-1]
            price = float(curr['Close'])
            m5 = float(curr['5MA'])
            m20 = float(curr['20MA'])
            bw = float(curr['BW'])
            
            # 燈號判定
            if price > m5:
                light = "🟢 綠燈"
            elif price > m20:
                light = "🟡 黃燈"
            else:
                light = "🔴 紅燈"
                
            status[name] = {"燈號": light, "帶寬": bw, "門檻": 0.145 if name == "上市" else 0.095}
        except Exception as e:
            status[name] = {"燈號": "⚠️ 錯誤", "帶寬": 0.0, "門檻": 0.0}
            
    return status
            
        status[name] = {"燈號": light, "帶寬": bw, "門檻": 0.145 if name == "上市" else 0.095}
    return status

# --- 4. 側邊欄設定 ---
st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請貼入三竹股池資料", height=200, placeholder="直接把三竹那坨貼進來...")
analyze_btn = st.sidebar.button("🚀 開始掃描戰情")

# --- 5. 主畫面執行 ---
st.title("🏹 私密戰情室：ABCDE 策略判定")

# 獲取大盤狀態
m_env = get_market_status()

# 顯示大盤狀態指標
col1, col2 = st.columns(2)
with col1: 
    st.metric("加權指數 (上市)", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with col2: 
    st.metric("OTC 指數 (上櫃)", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

if analyze_btn and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner(f"正在掃描 {len(codes)} 檔股票..."):
        for code in codes:
            # 優先嘗試上市
            df = yf.download(f"{code}.TW", period="1mo", interval="1d", progress=False)
            is_otc = False
            if df.empty or len(df) < 20:
                df = yf.download(f"{code}.TWO", period="1mo", interval="1d", progress=False)
                is_otc = True
            
            if df.empty or len(df) < 2: continue
            
            market = "上櫃" if is_otc else "上市"
            env = m_env[market]
            
            # 計算個股指標
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['Upper'] = df['20MA'] + (df['STD'] * 2)
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            today = df.iloc[-1]
            yest = df.iloc[-2]
            
            price = float(today['Close'])
            up = float(today['Upper'])
            ma20 = float(today['20MA'])
            ma20_y = float(yest['20MA'])
            vol_amt = (float(today['Volume']) * price) / 100000000
            chg = (price - float(yest['Close'])) / float(yest['Close'])
            bw = float(today['BW'])
            bw_ratio = bw / env['帶寬'] if env['帶寬'] != 0 else 0
            
            # 策略判定邏輯
            strategy = "⚪ 未達准入"
            if price > up and ma20 > ma20_y and vol_amt >= 5:
                if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: 
                    strategy = "🔥【A：潛龍爆發】"
                elif env['燈號'] in ["🟢 綠燈", "🟡 黃燈"] and 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: 
                    strategy = "🎯【B：海巡狙擊】"
                elif env['燈號'] == "🟢 綠燈":
                    if bw >= 0.2 and 0.8 <= bw_ratio <= 1.2: 
                        strategy = "⚡【D/E：瘋狗連動】"
                    elif bw >= 0.2: 
                        strategy = "🌊【C：瘋狗浪】"
                else: 
                    strategy = f"⚠️ 燈號不准入 ({env['燈號']})"

            results.append({
                "代碼": code, 
                "名稱": stock_names.get(code, "未知"),
                "判定": strategy, 
                "個股帶寬": f"{bw:.2%}", 
                "漲幅": f"{chg:.2%}", 
                "成交值": f"{vol_amt:.1f}億"
            })
            
    if results:
        st.table(pd.DataFrame(results))
    else:
        st.warning("無符合代碼或資料抓取失敗")
