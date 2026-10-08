import io
import re
import pandas as pd


def process_benq_compare(raw_data, filename_prefix="CB9PF"):
    """專門處理 BENQ 17 欄位報單比對邏輯 (完全依循原始文件順序)"""
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

    # 1. 強制修正單位（如 m/M 轉為 MTR，其它轉大寫）
    if "*Unit" in df.columns:

        def fix_unit(u):
            if not u or pd.isna(u):
                return ""
            u_str = str(u).strip().upper()
            return "MTR" if u_str in ["M", "MTR"] else u_str

        df["*Unit"] = df["*Unit"].apply(fix_unit)

    # 2. 強制修正【統計方式】為兩碼字串 (例如 "2" -> "02")
    if "*統計方式" in df.columns:

        def fix_stat_mode(val):
            if pd.isna(val) or val is None:
                return ""
            v_str = str(val).strip()
            if v_str.isdigit() and len(v_str) == 1:
                return f"0{v_str}"
            return v_str

        df["*統計方式"] = df["*統計方式"].apply(fix_stat_mode)

    # 3. 強制修正【報單類別】只保留前兩碼 (例如 "B9保稅廠產品出口" -> "B9")
    if "報單類別" in df.columns:

        def fix_doc_type(val):
            if pd.isna(val) or not val:
                return ""
            val_str = str(val).strip()
            match = re.match(r"^([A-Z0-9]{2})", val_str, re.IGNORECASE)
            return match.group(1).upper() if match else val_str[:2].upper()

        df["報單類別"] = df["報單類別"].apply(fix_doc_type)

    # 4. 強制修正【報關日期】(若出現 115/10/08 自動轉 2026/10/08)
    if "*報關日期" in df.columns:

        def fix_date(d):
            if pd.isna(d) or not d:
                return ""
            d_str = str(d).strip()
            parts = d_str.split("/")
            if len(parts) == 3 and len(parts[0]) <= 3:
                try:
                    year = int(parts[0]) + 1911
                    return f"{year}/{parts[1].zfill(2)}/{parts[2].zfill(2)}"
                except ValueError:
                    pass
            return d_str

        df["*報關日期"] = df["*報關日期"].apply(fix_date)

    # 5. 強制整理【保稅】欄位
    if "保稅" in df.columns:

        def fix_bonded(val):
            if pd.isna(val) or not val:
                return ""
            v_str = str(val).strip().upper()
            if "YB" in v_str:
                return "YB"
            if "NB" in v_str:
                return "NB"
            return v_str

        df["保稅"] = df["保稅"].apply(fix_bonded)

    # -------------------------------------------------------------
    # ⚡ 完全尊重報單 / Invoice 的原始項次與順序，不實施任何重新排序
    # -------------------------------------------------------------
    if "*出口項次" in df.columns and not df.empty:
        seq_list = list(range(1, len(df) + 1))
        df["*出口項次"] = pd.to_numeric(
            df["*出口項次"], errors="coerce"
        ).fillna(pd.Series(seq_list, index=df.index))

    df = df[compare_cols]

    # 產出 Excel Buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="GoodsCompare")

    return df, output.getvalue()
