from datetime import datetime
import io
import pandas as pd


def process_benq_compare(raw_data, filename_prefix="CB9PF"):
    """專門處理 BENQ 17 欄位報單比對邏輯"""
    compare_data = raw_data.get("compare_data", [])
    df = pd.DataFrame(compare_data)

    compare_cols = [
        "*貨物編號",
        "*出口項次",
        "*出口報單號碼",
        "*報關日期",
        "Item No",
        "*Item Description",
        "*Unit",
        "*Quantity",
        "*統計方式",
        "*匯率",
        "核銷進口報單號碼",
        "進口項次",
        "BOM No",
        "保稅",
        "監管編號",
        "報單類別",
        "單價",
    ]
    for col in compare_cols:
        if col not in df.columns:
            df[col] = None

    # 強制修正單位（如 m/M 轉為 MTR，其它轉大寫）
    if "*Unit" in df.columns:

        def fix_unit(u):
            if not u:
                return ""
            u_str = str(u).strip().upper()
            return "MTR" if u_str in ["M", "MTR"] else u_str

        df["*Unit"] = df["*Unit"].apply(fix_unit)

    df = df[compare_cols]

    # 產出 Excel Buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="GoodsCompare")

    return df, output.getvalue()
