import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

# --- 2. 終極 CSS (隱藏英文菜單 + 輕量化大盤區) ---
def set_final_ui(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            img_data = f.read()
        b64_encoded = base64.b64encode(img_data).decode()
        style = f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{b64_encoded}");
            background-attachment: fixed;
            background-size: 100% auto; 
            background-position: center bottom;
            background-color: #0E1117;
        }}
        .stApp::before {{
            content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background-color: rgba(0, 0, 0, 0.6); z-index: -1;
        }}

        /* 輕量化大盤區 */
        div[data-testid="stHorizontalBlock"] {{
            position: sticky; top: 0px; z-index: 1000;
            background-color: rgba(40, 40, 40, 0.4); 
            padding: 10px; border-radius: 10px;
            backdrop-filter: blur(8px);
        }}

        /* 表格區底色加深 */
        [data-testid="stDataFrame"] {{
            background-color: rgba(10, 10, 10, 0.95) !important;
            border: 1px solid #333;
        }}

        /* 強制隱藏 Streamlit 原生英文菜單按鈕 (因為它無法中文化) */
        button[title="View fullscreen"] {{ display: none; }}
        
        header {{ visibility: hidden; }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_final_ui("header_image.png")

# --- 3. 穩定版名稱抓取 (雙重備援) ---
@st.cache_data(ttl=86400)
def get_reliable_names():
    names = {}
    # 第一層：證交所官方清單
    urls = ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]
    for url in urls:
        try:
            r = requests.get(url, timeout=5)
            df = pd.read_html(r.text)[0]
            for val in df.iloc[:, 0]:
                parts = str(val).split('\u3000')
                if len(parts) >= 2: names[parts[0].strip()] = parts[1].strip()
        except: continue
    
    # 第二層：如果第一層失敗，嘗試從 Yahoo Info 抓取特定標籤 (當作最後防線)
    return names

stock_db = get_reliable_names()

# --- 4. 大盤偵測 ---
@st.cache_data(ttl=300)
def get_market():
    res = {}
    for k, v in {"上市": "^TWII", "上櫃": "^TWOII"}.items():
        try:
            df = yf.download(v, period="2mo", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            c, m5, m20 = df['Close'].iloc[-1], df['Close'].rolling(5).mean().iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
            bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / m20
            light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": float(c), "帶寬": float(bw)}
        except: res[k] = {"燈號": "⚠️", "價格": 0, "帶寬": 0}
    return res

# --- 5. 主介面 ---
st.markdown("### 🏹 私密戰情室：姊布林ABCDE 策略判定")
m_env = get_market()

# 凍結窗格：大盤資訊
m_col1, m_col2 = st.columns(2)
with m_col1:
    st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2:
    st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# 日期顯示 (確保在凍結範圍外)
st.write(f"📅 **數據掃描時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}**")

# 側邊欄
raw_input = st.sidebar.text_area("請輸入股票代碼", height=250)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("正在對接台股資料庫..."):
        for code in codes:
            # 名稱修正：如果 db 找不到，直接詢問 yfinance 的 shortName
            name = stock_db.get(code)
            if not name or name == "未知":
                try:
                    tk = yf.Ticker(f"{code}.TW")
                    name = tk.info.get('shortName', "未知")
                    # 再次清理，確保沒有英文
                    name = re.sub(r'[a-zA-Z\s\-]+', '', name) if name != "未知" else "未知"
                except: name = "未知"

            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            m_type = "上市"
            if df.empty:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                m_type = "上櫃"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                env = m_env[m_type]
                
                # 計算帶寬與判定
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                bw = (df['STD'].iloc[-1] * 4) / df['20MA'].iloc[-1]
                
                p_curr, p_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                
                # ABCDE 判定簡化邏輯 (與先前一致)
                res_tag = "⚪ 未達准入"
                if p_curr > df['Upper'].iloc[-1] and df['20MA'].iloc[-1] > df['20MA'].iloc[-2] and vol_amt >= 5:
                    if bw > 0.2 and 0.8 <= ratio <= 1.2: res_tag = "💎【D：帶寬共振】"
                    elif bw > 0.2 and ratio > 1.2: res_tag = "🚀【E：超額擴張】"
                    elif 0.05 <= bw <= 0.1: res_tag = "🔥【A：潛龍爆發】"
                    elif 0.1 < bw <= 0.2: res_tag = "🎯【B：海龍狙擊】"
                    elif 0.2 < bw <= 0.4: res_tag = "🌊【C：瘋狗浪】"

                results.append({
                    "股票代碼": code, "台股名稱": name, "判定結果": res_tag, 
                    "個股帶寬%": round(bw*100, 2), "今日漲幅%": round(chg*100, 2), 
                    "成交值(億)": round(vol_amt, 1), "對比比值": round(ratio, 2)
                })
        
        if results:
            # 使用自定義 CSS 標題，避免英文選單干擾
            st.markdown("#### 📊 判定結果清單 (點擊欄位名稱可排序)")
            st.dataframe(
                pd.DataFrame(results), 
                use_container_width=True, hide_index=True,
                column_config={
                    "個股帶寬%": st.column_config.NumberColumn(format="%.2f%%"),
                    "今日漲幅%": st.column_config.NumberColumn(format="%.2f%%")
                }
            )
