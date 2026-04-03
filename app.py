import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
import time

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
        if pwd == "test0403": # <--- 密碼可以在這修改
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

# --- 3. 大盤環境偵測 ---
def get_market_status():
    status = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for name, sym in indices.items():
        try:
            df = yf.download(sym, period="2mo", interval="1d", progress=False)
            if df.empty:
                time.sleep(1)
                df = yf.download(sym, period="2mo", interval="1d", progress=False)
            
            if df.empty or len(df) < 20:
                status[name] = {"燈號": "⚪ 資料不足", "價格": 0.0, "帶寬": 0.0}
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df['5MA'] = df['Close'].rolling(5).mean()
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            valid_df = df.dropna(subset=['Close', '5MA', '20MA', 'BW'])
            curr = valid_df.iloc[-1]
            
            price, m5, m20, bw = float(curr['Close']), float(curr['5MA']), float(curr['20MA']), float(curr['BW'])
            
            if price > m5: light = "🟢 綠燈"
            elif price > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
                
            status[name] = {"燈號": light, "價格": price, "帶寬": bw}
        except:
            status[name] = {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0}
            
    return status

# --- 4. 介面執行 ---
st.title("🏹 私密戰情室：ABCDE 策略判定")
m_env = get_market_status()

col1, col2 = st.columns(2)
with col1: 
    val = m_env.get('上市', {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0})
    # 將數字放在標題旁：加權指數 (22,345.67)
    label_text = f"加權指數 ({val['價格']:,.2f})" if val['價格'] > 0 else "加權指數"
    st.metric(label_text, val['燈號'], f"帶寬: {val['帶寬']:.2%}")

with col2: 
    val = m_env.get('上櫃', {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0})
    # 將數字放在標題旁：OTC 指數 (267.89)
    label_text = f"OTC 指數 ({val['價格']:,.2f})" if val['價格'] > 0 else "OTC 指數"
    st.metric(label_text, val['燈號'], f"帶寬: {val['帶寬']:.2%}")

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請貼入三竹股池資料", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner("同步分析中..."):
        for code in codes:
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            is_otc = False
            if df.empty:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                is_otc = True
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                market = "上櫃" if is_otc else "上市"
                env = m_env.get(market, {"燈號": "🔴 紅燈", "價格": 0.0, "帶寬": 0.0})
                
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                df['BW'] = (df['STD'] * 4) / df['20MA']
                
                today, yest = df.iloc[-1], df.iloc[-2]
                price, up, ma20, ma20_y = float(today['Close']), float(today['Upper']), float(today['20MA']), float(yest['20MA'])
                vol_amt = (float(today['Volume']) * price) / 100000000
                chg = (price - float(yest['Close'])) / float(yest['Close'])
                bw = float(today['BW'])
                
                strategy = "⚪ 未達准入"
                if price > up and ma20 > ma20_y and vol_amt >= 5:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: 
                        strategy = "🔥【A：潛龍爆發】"
                    elif "🔴 紅燈" not in env['燈號'] and 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: 
                        strategy = "🎯【B：海巡狙擊】"
                    elif "🟢 綠燈" in env['燈號'] and bw >= 0.2: 
                        strategy = "🌊【C：瘋狗浪】"

                results.append({
                    "代碼": code, "名稱": stock_names.get(code, "未知"),
                    "判定": strategy, "個股帶寬": f"{bw:.2%}", "漲幅": f"{chg:.2%}", "成交值": f"{vol_amt:.1f}億"
                })
        
        if results:
            st.table(pd.DataFrame(results))
        else:
            st.warning("無有效代碼")
