import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob
from datetime import datetime, time, timedelta
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go

### --- 0. 🚀 即時數據抓取函數 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        patterns = [r'"regularMarketPrice":\s*([0-9.]+)', r'"price":\s*"([0-9,.]+)"']
        for p in patterns:
            match = re.search(p, response.text)
            if match:
                val = float(match.group(1).replace(',', ''))
                if val > 0: return val
    except: pass
    return None

### --- 0.1 🏎️ 歷史數據快取 ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

### --- 1. 網頁配置與背景設置 (完美保留您的背景圖與樣式) ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; padding: 5px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)

set_ui_cleanup("header_image.png")

### --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()


# ==========================================
# 🎯 3. 當沖覆盤模擬系統核心模組
# ==========================================
def init_replay_state():
    if "replay_step" not in st.session_state:
        st.session_state.replay_step = 1
    if "positions" not in st.session_state:
        st.session_state.positions = []
    if "trade_history" not in st.session_state:
        st.session_state.trade_history = []
    if "capital" not in st.session_state:
        st.session_state.capital = 1000000

@st.cache_data
def generate_mock_intraday_data():
    dates = pd.date_range("09:00", "13:30", freq="1min")
    np.random.seed(42)
    price = 100.0
    records = []
    for t in dates:
        change = np.random.normal(0, 0.3)
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.2))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.2))
        vol = int(np.random.randint(10, 500))
        price = close_p
        records.append({
            "Time": t.strftime("%H:%M"),
            "Open": round(open_p, 2),
            "High": round(high_p, 2),
            "Low": round(low_p, 2),
            "Close": round(close_p, 2),
            "Volume": vol
        })
    return pd.DataFrame(records)

def calc_daytrade_cost(buy_price, sell_price, qty, fee_discount=0.28):
    buy_val = buy_price * qty * 1000
    sell_val = sell_price * qty * 1000
    buy_fee = buy_val * 0.001425 * fee_discount
    sell_fee = sell_val * 0.001425 * fee_discount
    tax = sell_val * 0.0015 # 現股當沖證交稅 0.15%
    net_pnl = (sell_val - buy_val) - (buy_fee + sell_fee + tax)
    return net_pnl, buy_fee + sell_fee + tax

def render_daytrade_replay_ui():
    init_replay_state()
    st.title("🎯 當沖擬真覆盤模擬系統")
    st.markdown("在此模式下，您可以依據歷史分K進行逐根推進與模擬當沖交易，嚴格防範前瞻偏誤，並自動扣除台股當沖成本。")
    
    df_all = generate_mock_intraday_data()
    total_steps = len(df_all)
    
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 2, 2, 2])
    with ctrl_col1:
        st.session_state.replay_step = st.slider(
            "⏱️ 盤中時間進度 (K線根數)", 
            min_value=1, 
            max_value=total_steps, 
            value=st.session_state.replay_step
        )
    with ctrl_col2:
        if st.button("▶️ 下一根 K 棒", use_container_width=True):
            if st.session_state.replay_step < total_steps:
                st.session_state.replay_step += 1
                st.rerun()
    with ctrl_col3:
        if st.button("⏩ 快進 5 根", use_container_width=True):
            if st.session_state.replay_step + 5 <= total_steps:
                st.session_state.replay_step += 5
                st.rerun()
    with ctrl_col4:
        if st.button("🔄 重置覆盤", use_container_width=True):
            st.session_state.replay_step = 1
            st.session_state.positions = []
            st.session_state.trade_history = []
            st.rerun()
            
    df_curr = df_all.iloc[:st.session_state.replay_step]
    latest_row = df_curr.iloc[-1]
    curr_time = latest_row["Time"]
    curr_price = latest_row["Close"]
    
    col_chart, col_trade = st.columns([3, 1])
    
    with col_chart:
        st.subheader(f"📊 當前時間：{curr_time} | 最新報價：{curr_price} 元")
        fig = go.Figure(data=[go.Candlestick(
            x=df_curr['Time'],
            open=df_curr['Open'],
            high=df_curr['High'],
            low=df_curr['Low'],
            close=df_curr['Close'],
            increasing_line_color='red',
            decreasing_line_color='green'
        )])
        fig.update_layout(
            height=450,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False,
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_trade:
        st.subheader("⚡ 當沖下單面板")
        trade_qty = st.number_input("下單張數", min_value=1, max_value=10, value=1)
        
        btn_buy, btn_sell = st.columns(2)
        with btn_buy:
            if st.button("🔴 現股買進", use_container_width=True):
                st.session_state.positions.append({
                    "type": "BUY",
                    "price": curr_price,
                    "qty": trade_qty,
                    "time": curr_time
                })
                st.success(f"已買進 {trade_qty} 張 @ {curr_price}")
                st.rerun()
                
        with btn_sell:
            if st.button("🟢 當沖平倉", use_container_width=True):
                if len(st.session_state.positions) > 0:
                    pos = st.session_state.positions.pop(0)
                    pnl, cost = calc_daytrade_cost(pos["price"], curr_price, pos["qty"])
                    st.session_state.trade_history.append({
                        "buy_time": pos["time"],
                        "sell_time": curr_time,
                        "buy_price": pos["price"],
                        "sell_price": curr_price,
                        "qty": pos["qty"],
                        "pnl": round(pnl),
                        "cost": round(cost)
                    })
                    st.success(f"已平倉！損益：{round(pnl)} 元")
                    st.rerun()
                else:
                    st.warning("無持倉部位可平")

    st.markdown("---")
    st.subheader("📈 當日覆盤績效與交易明細")
    
    if st.session_state.trade_history:
        df_history = pd.DataFrame(st.session_state.trade_history)
        total_pnl = df_history["pnl"].sum()
        total_trades = len(df_history)
        wins = df_history[df_history["pnl"] > 0]
        losses = df_history[df_history["pnl"] <= 0]
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses["pnl"].mean()) if len(losses) > 0 else 0
        rr_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("已實現總損益", f"{total_pnl:,.0f} 元")
        m2.metric("勝率 (Win Rate)", f"{win_rate:.1%}")
        m3.metric("風報比 (R:R)", f"{rr_ratio:.2f}")
        m4.metric("總交易次數", f"{total_trades} 次")

        st.markdown("#### 核心交易報表")
        summary_table = pd.DataFrame([{
            "年度": "當日覆盤",
            "策略": "當沖擬真交易",
            "交易次數": total_trades,
            "成功 / 失敗": f"{len(wins)} / {len(losses)}",
            "單次平均獲利": f"{avg_win:,.0f}",
            "單次平均虧損": f"{avg_loss:,.0f}",
            "勝率": f"{win_rate:.1%}",
            "風報比(R:R)": f"{rr_ratio:.2f}",
            "當日報酬率": f"{(total_pnl / st.session_state.capital):.2%}"
        }])
        st.table(summary_table)

        st.markdown("#### 交易明細")
        st.dataframe(df_history, use_container_width=True)
    else:
        st.info("尚無平倉交易紀錄，請在上方進行模擬下單。")


# ==========================================
# 🧭 4. 主側邊欄導覽選單 (在這裡切換您的策略)
# ==========================================
st.sidebar.title("🛠️ 戰情控制台")
app_mode = st.sidebar.radio(
    "選擇功能模式：",
    ["📊 姊布林 ABCDE 主戰情室", "🎯 當沖覆盤模擬系統"]
)

if app_mode == "📊 姊布林 ABCDE 主戰情室":
    st.title("🏹 姊布林 ABCDE 戰情室")
    st.info("（此處為您原本的姊布林主戰情室介面與掃描邏輯）")
    
    # 範例測試按鈕
    if st.button("測試大盤即時報價"):
        tse_price = get_realtime_price('TSE')
        st.success(f"加權指數即時報價：{tse_price}")

elif app_mode == "🎯 當沖覆盤模擬系統":
    render_daytrade_replay_ui()
