import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
import time
import os

# --- 1. 設置網頁標題、圖示與密碼鎖 ---
st.set_page_config(
    page_title="🏹 姊布林ABCDE 戰情室", # 網頁分頁上的標題
    page_icon="🏹", # 網頁分頁上的小圖示
    layout="wide"
)

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    st.title("🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": # <--- 這裡修改密碼
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
        # 下載證交所上市/上櫃名稱
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        url_otc = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        def fetch(u):
            r = requests.get(u)
            d = pd.read_html(r.text)[0]
            d.columns = d.iloc[0]
            d = d.iloc[1:]
            res = {}
            for v in d['有價證券代號及名稱']:
                p = str(v).split('\u3000') # 證交所格式: '2330 台積電'
                if len(p) >= 2: res[p[0]] = p[1] # 轉為字典: {'2330': '台積電'}
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
            # 抓取 2個月資料
            df = yf.download(sym, period="2mo", interval="1d", progress=False)
            if df.empty:
                time.sleep(1)
                df = yf.download(sym, period="2mo", interval="1d", progress=False)
            
            # 處理部分格式問題
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # 計算指標
            df['5MA'] = df['Close'].rolling(5).mean()
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            # 取得最後一個交易日
            valid_df = df.dropna(subset=['Close', '5MA', '20MA', 'BW'])
            curr = valid_df.iloc[-1]
            
            price, m5, m20, bw = float(curr['Close']), float(curr['5MA']), float(curr['20MA']), float(curr['BW'])
            
            # 燈號判定
            if price > m5: light = "🟢 綠燈"
            elif price > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
                
            status[name] = {"燈號": light, "價格": price, "帶寬": bw}
        except:
            status[name] = {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0}
    return status

# --- 4. 介面執行與視覺美化 ---

# 👉 改動點: 加入封面圖片
# 請在 GitHub 的同一個目錄下，上傳一張圖片，命名為 header_image.png 即可顯示。
image_path = "header_image.png"
if os.path.exists(image_path):
    st.image(image_path, use_column_width=True) # use_column_width 讓圖片與頁面等寬
else:
    # 如果找不到圖片，顯示一個提示框，不會當機
    # st.warning(f"👉 如果想顯示封面圖片，請上傳名為 '{image_path}' 的圖片到 GitHub 目錄下。")
    # 如果不要圖片顯示，就留空即可
    pass

st.title("🏹 私密戰情室：姊布林ABCDE 策略判定")
m_env = get_market_status()

# 自定義卡片顯示組件
def draw_market_card(title, data):
    price_str = f"{data['價格']:,.2f}" if data['價格'] > 0 else "---"
    bw_str = f"{data['帶寬']:.2%}"
    st.markdown(f"""
        <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid #4CAF50;">
            <p style="color: #AAAAAA; font-size: 24px; margin-bottom: 5px;">{title} ({price_str})</p>
            <p style="color: white; font-size: 42px; font-weight: bold; margin: 0;">{data['燈號']}</p>
            <p style="color: #4CAF50; font-size: 22px; margin-top: 10px;">↑ 帶寬: {bw_str}</p>
        </div>
    """, unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    draw_market_card("加權指數", m_env.get('上市', {"燈號": "偵測中", "價格": 0.0, "帶寬": 0.0}))
with col2:
    draw_market_card("OTC 指數", m_env.get('上櫃', {"燈號": "偵測中", "價格": 0.0, "帶寬": 0.0}))

st.markdown("<br>", unsafe_allow_html=True)

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請貼入三竹股池資料", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner("同步掃描分析中..."):
        for code in codes:
            # 優先嘗試上市代碼
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            is_otc = False
            if df.empty:
                # 嘗試上櫃代碼
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                is_otc = True
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                market = "上櫃" if is_otc else "上市"
                env = m_env.get(market, {"燈號": "🔴 紅燈", "價格": 0.0, "帶寬": 0.0})
                
                # 計算個股布林帶
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                df['BW'] = (df['STD'] * 4) / df['20MA']
                
                today, yest = df.iloc[-1], df.iloc[-2]
                price = float(today['Close'])
                up = float(today['Upper'])
                ma20 = float(today['20MA'])
                ma20_y = float(yest['20MA'])
                vol_amt = (float(today['Volume']) * price) / 100000000 # 成交值 (億)
                chg = (price - float(yest['Close'])) / float(yest['Close']) # 漲幅
                bw = float(today['BW']) # 帶寬
                
                # --- ABCDE 策略判定邏輯 ---
                strategy = "⚪ 未達准入"
                if price > up and ma20 > ma20_y and vol_amt >= 5:
                    # A策略：窄帶+溫和上漲
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: 
                        strategy = "🔥【A：潛龍爆發】"
                    # B策略：中帶+溫和上漲+大盤非紅燈
                    elif "🔴 紅燈" not in env['燈號'] and 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: 
                        strategy = "🎯【B：海巡狙擊】"
                    # C策略：寬帶+大盤綠燈
                    elif "🟢 綠燈" in env['燈號'] and bw >= 0.2: 
                        strategy = "🌊【C：瘋狗浪】"

                results.append({
                    "代碼": code, "名稱": stock_names.get(code, "未知"),
                    "判定": strategy, "個股帶寬": f"{bw:.2%}", "漲幅": f"{chg:.2%}", "成交值": f"{vol_amt:.1f}億"
                })
        
        if results:
            # 使用 Markdown 來解決 Unicode 寬度導致對不齊的問題
            df_results = pd.DataFrame(results)
            # 格式化個股帶寬和漲幅為綠色
            styled_df = df_results.style.format({
                "漲幅": lambda x: f'<span style="color: #4CAF50;">{x}</span>',
                "個股帶寬": lambda x: f'<span style="color: #4CAF50;">{x}</span>'
            })
            st.write(styled_df.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.warning("無有效股票代碼資料")
