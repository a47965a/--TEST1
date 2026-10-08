import io
import pandas as pd


def clean_numeric(val):
    """清理逗號並轉為純數字，若無法轉換則回傳 None (Excel 空白)"""
    if pd.isna(val) or val == "" or val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    cleaned_str = str(val).replace(",", "").strip()
    try:
        num = float(cleaned_str)
        return int(num) if num.is_integer() else num
    except ValueError:
        return val


def process_upi_semiconductor(raw_data):
    """專門處理力智 (uPI) / 半導體雙分頁邏輯"""
    df_inv = pd.DataFrame(raw_data.get("invoice_data", []))
    df_pack = pd.DataFrame(raw_data.get("packing_data", []))

    inv_cols = [
        "頁碼",
        "發票號碼",
        "型號",
        "封裝規格",
        "PO單號",
        "項次",
        "數量",
        "單價",
        "總價",
        "發票總金額",
    ]
    for col in inv_cols:
        if col not in df_inv.columns:
            df_inv[col] = None
    df_inv = df_inv[inv_cols]

    pack_cols = [
        "頁碼",
        "LIST NO/單號",
        "型號",
        "封裝規格",
        "PO單號",
        "項次",
        "數量",
        "總 GW (KGS)",
        "總 NW (KGS)",
    ]
    for col in pack_cols:
        if col not in df_pack.columns:
            df_pack[col] = None
    df_pack = df_pack[pack_cols]

    # 數字清理
    for col in ["數量", "單價", "總價", "發票總金額"]:
        df_inv[col] = df_inv[col].apply(clean_numeric)

    for col in ["數量", "總 GW (KGS)", "總 NW (KGS)"]:
        df_pack[col] = df_pack[col].apply(clean_numeric)

    # 產出雙頁籤 Excel Buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_inv.to_excel(writer, index=False, sheet_name="Invoice")
        df_pack.to_excel(writer, index=False, sheet_name="Packing_List")

    return df_inv, df_pack, output.getvalue()
