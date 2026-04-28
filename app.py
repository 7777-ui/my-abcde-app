import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE & 營收戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# --- 背景與UI設置 ---
def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)

set_ui_cleanup("header_image.png")

# --- 🔐 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 0. 全域共用：大盤環境偵測 ---
def get_market_price_yahoo(target):
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', res.text)
        if m: return float(m.group(1))
    except: return None
    return None

@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    indices = {"上市": {"id": "TSE", "yf": "^TWII"}, "上櫃": {"id": "OTC", "yf": "^TWOII"}}
    for k, v in indices.items():
        curr_p = get_market_price_yahoo(v["id"])
        df_h = yf.download(v["yf"], period="2mo", progress=False)
        if not df_h.empty and curr_p:
            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
            c_list = df_h['Close'].iloc[-19:].tolist() + [curr_p]
            m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
            std_v = pd.Series(c_list).std()
            bw = (std_v * 4) / m20 if m20 != 0 else 0
            light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
    return res

m_env = get_market_env()

# --- 頁面標題與大盤狀態 ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 側邊欄：模式切換 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇模式", ["姊布林策略", "營收動能參數"])

# =================================================================
# 區塊 A：姊布林策略 (保持原始邏輯)
# =================================================================
if mode == "姊布林策略":
    st.sidebar.markdown("---")
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150, placeholder="例如: 2330 2454")
    
    # 原始姊布林專用價格抓取 (確保不影響營收區塊)
    def jb_get_price(sid):
        url = f"https://tw.stock.yahoo.com/quote/{sid}"
        try:
            r = requests.get(url, timeout=5)
            m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', r.text)
            if m: return float(m.group(1))
        except: return None
        return None

    if st.sidebar.button("🚀 開始掃描姊布林"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("姊布林策略掃描中..."):
            # 讀取產業資料
            mapping = {}
            for f in ["TWSE.csv", "TPEX.csv"]:
                if os.path.exists(f):
                    try: 
                        df_info = pd.read_csv(f, encoding='utf-8-sig')
                        for _, row in df_info.iterrows():
                            mapping[str(row.iloc[0]).strip()] = {
                                "簡稱": str(row.iloc[1]), "排位": str(row.iloc[2]), 
                                "指標": str(row.iloc[3]), "細分": str(row.iloc[4]), "技術": str(row.iloc[5])
                            }
                    except: pass

            for code in codes:
                p_curr = jb_get_price(code)
                if not p_curr: continue
                
                df = yf.download(f"{code}.TW", period="2mo", progress=False)
                m_type = "上市"
                if df.empty or len(df) < 10:
                    df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                    m_type = "上櫃"
                
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    p_yest = float(df['Close'].iloc[-1])
                    c_20 = df['Close'].iloc[-19:].tolist() + [p_curr]
                    m20 = sum(c_20)/20
                    std = pd.Series(c_20).std()
                    up = m20 + (std * 2)
                    bw = (std * 4)/m20
                    chg = (p_curr - p_yest)/p_yest
                    vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                    
                    # 邏輯判定
                    res_tag = ""
                    fail = []
                    if p_curr <= up: fail.append("未站上軌")
                    if m20 <= df['Close'].iloc[-20:-1].mean(): fail.append("斜率負")
                    if vol_amt < 5: fail.append("量不足")
                    
                    if not fail:
                        main_light = m_env['上市']['燈號']
                        if "🔴 紅燈" in main_light:
                            if 0.05<=bw<=0.1 and 0.03<=chg<=0.07: res_tag="🔥【A：潛龍】"
                            elif 0.1<bw<=0.2 and 0.03<=chg<=0.05: res_tag="🎯【B：海龍】"
                            else: res_tag="⚪ 參數不符(大盤紅燈)"
                        else:
                            c_env = m_env[m_type]
                            if "🟢 綠燈" in c_env['燈號']:
                                env_de = (m_env['上市']['帶寬']>0.145 or m_env['上櫃']['帶寬']>0.095)
                                if env_de and bw>0.2 and 0.8<=(bw/c_env['帶寬'])<=1.2 and 0.03<=chg<=0.05: res_tag="💎【D：共振】"
                                elif env_de and bw>0.2 and 1.2<(bw/c_env['帶寬'])<=2.0 and 0.03<=chg<=0.07: res_tag="🚀【E：超額】"
                                elif 0.05<=bw<=0.1 and 0.03<=chg<=0.07: res_tag="🔥【A：潛龍】"
                                elif 0.1<bw<=0.2 and 0.03<=chg<=0.05: res_tag="🎯【B：海龍】"
                                elif 0.2<bw<=0.4 and 0.03<=chg<=0.07: res_tag="🌊【C：瘋狗】"
                    
                    if not res_tag: res_tag = "⚪ " + ("/".join(fail) if fail else "參數不符")

                    info = mapping.get(code, {"簡稱":f"台股{code}","排位":"-","指標":"-","細分":"-","技術":"-"})
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                        "現價": p_curr, "漲幅%": round(chg*100, 2), "成交值(億)": round(vol_amt, 2),
                        "個股帶寬%": f"{bw:.2%}", "產業排位": info["排位"], "族群細分": info["細分"]
                    })
            if results: st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
            else: st.warning("查無符合代碼之數據")

# =================================================================
# 區塊 B：營收動能區塊 (獨立邏輯)
# =================================================================
elif mode == "營收動能參數":
    st.info("模式：抓取近三月平均年增率 > 20% 個股")
    
    # 營收區塊專用價格抓取
    def rev_get_realtime(sid):
        url = f"https://tw.stock.yahoo.com/quote/{sid}"
        try:
            r = requests.get(url, timeout=5)
            p = re.search(r'"regularMarketPrice":\s*([0-9.]+)', r.text)
            c = re.search(r'"regularMarketChangePercent":\s*([-0-9.]+)', r.text)
            if p and c: return float(p.group(1)), float(c.group(1))
        except: pass
        return None, None

    if st.sidebar.button("📊 執行營收自動篩選"):
        path = "revenue_data"
        all_files = glob.glob(os.path.join(path, "*.csv"))
        
        if not all_files:
            st.error(f"找不到營收資料夾 '{path}' 或 CSV 檔案")
        else:
            with st.spinner("正在計算營收動能..."):
                rev_list = []
                for f in all_files:
                    try:
                        # 僅選取必要欄位
                        tmp_df = pd.read_csv(f, encoding='utf-8-sig')
                        cols = ['資料年月', '公司代號', '公司名稱', '營業收入-去年同月增減(%)']
                        # 修正: 根據您的需求，我們需要的是年增率來平均
                        tmp_df = tmp_df[cols]
                        rev_list.append(tmp_df)
                    except: pass
                
                if rev_list:
                    full_rev = pd.concat(rev_list)
                    full_rev['公司代號'] = full_rev['公司代號'].astype(str).str.strip()
                    
                    # 計算平均年增率 (依公司代號分組，取最近三筆)
                    avg_rev = full_rev.groupby('公司代號')['營業收入-去年同月增減(%)'].apply(lambda x: x.head(3).mean()).reset_index()
                    avg_rev.columns = ['代號', '近三月平均年增%']
                    
                    # 篩選 > 20%
                    targets = avg_rev[avg_rev['近三月平均年增%'] > 20].copy()
                    
                    # 取得產業資料
                    ind_map = {}
                    for f in ["TWSE.csv", "TPEX.csv"]:
                        if os.path.exists(f):
                            try:
                                d_i = pd.read_csv(f, encoding='utf-8-sig')
                                for _, r in d_i.iterrows():
                                    ind_map[str(r.iloc[0]).strip()] = {"名稱":str(r.iloc[1]), "排位":str(r.iloc[2]), "細分":str(r.iloc[4])}
                            except: pass

                    final_results = []
                    for _, row in targets.iterrows():
                        sid = row['代號']
                        avg_val = row['近三月平均年增%']
                        
                        # 抓取即時行情 (與姊布林分開)
                        price, change = rev_get_realtime(sid)
                        if not price: continue
                        
                        # 取得成交量計算成交值(億)
                        d_vol = yf.download(f"{sid}.TW", period="1d", progress=False)
                        if d_vol.empty: d_vol = yf.download(f"{sid}.TWO", period="1d", progress=False)
                        v_amt = 0
                        if not d_vol.empty:
                            v_amt = (d_vol['Volume'].iloc[-1] * price) / 100000000
                        
                        info = ind_map.get(sid, {"名稱": "未知", "排位": "-", "細分": "-"})
                        
                        final_results.append({
                            "代號": sid,
                            "名稱": info["名稱"],
                            "近三月平均年增%": round(avg_val, 2),
                            "現價": price,
                            "漲跌幅%": change,
                            "成交值(億)": round(v_amt, 2),
                            "產業排位": info["排位"],
                            "族群細分": info["細分"]
                        })
                    
                    if final_results:
                        res_df = pd.DataFrame(final_results)
                        # 顯示結果，Streamlit 內建標題點擊排序功能
                        st.dataframe(res_df.sort_values("近三月平均年增%", ascending=False), use_container_width=True, hide_index=True)
                    else:
                        st.warning("未找到符合近三月平均年增 > 20% 的個股。")

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
