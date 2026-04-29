# 請在你的本地環境運行這段小腳本，並回報結果
import glob
import os
import pandas as pd

folder = "revenue_data"
all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
print(f"找到檔案數量: {len(all_files)}")
if len(all_files) >= 3:
    for f in all_files[:3]:
        df = pd.read_csv(f, encoding='utf-8-sig', nrows=1) # 僅讀一行測試
        print(f"檔案: {f} | 欄位清單: {df.columns.tolist()}")
