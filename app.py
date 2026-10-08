import io
import json
from datetime import datetime
from google import genai
from google.genai import types
import openpyxl
import pandas as pd
import streamlit as st

# 1. 頁面基本設定
st.set_page_config(
    page_title="多客戶 Shipping Docs AI 自動解析與報單比對工具",
    layout="wide",
)

st.title("📄 多客戶 Shipping Docs AI 自動解析工具")
st.caption(
    "支援力智 (uPI) 雙頁籤 Invoice/Packing 處理，以及 BENQ 等標準 17 欄位報單比對自動生成。"
)

# 讀取 Secrets 中的 API Key，若無則從 Sidebar 輸入
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader(
    "選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"]
)


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


if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在自動識別文件類型並提取資料中..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                upload_date_str = datetime.now().strftime("%Y/%m/%d")

                # 整合 Prompt
                prompt = f"""
                你是一個專業的半導體與電子零件 Shipping Docs 解析專家。
                請閱讀這份文件，首先判斷文件屬於哪種格式 (document_type)：

                【格式 A：BENQ_COMPARE】
                若為 BENQ (明基材料) 的 Commercial Invoice (含有 GOODS NO, 偏光片規格如 M315/M240, 或 (91.xxx) 格式料號)：
                請回傳 JSON Object，格式如下：
                {{
                  "document_type": "BENQ_COMPARE",
                  "compare_data": [
                    {{
                      "*貨物編號": "頁面頂部 GOODS NO (如 CB9PF260768)",
                      "*出口項次": 1,
                      "*出口報單號碼": null,
                      "*報關日期": "{upload_date_str}",
                      "Item No": "UNIT PRICE 正下方括號內文字 (如 91.4A311.020.161)",
                      "*Item Description": "僅保留中間規格描述 (如 B/MN/AUO/31.5/M315QAN01.0/Z-TAC_PET/TLN/161)，嚴格刪除 'Polarizer Film' 及 'C/No:' 以下的所有文字",
                      "*Unit": "單位一律轉大寫 (如 PCS, MTR)",
                      "*Quantity": 數量數字,
                      "*統計方式": null,
                      "*匯率": null,
                      "核銷進口報單號碼": null,
                      "進口項次": null,
                      "BOM No": "BOM No. 文字 (如 C0115029913)",
                      "保稅": null,
                      "監管編號": "C5790",
                      "報單類別": null,
                      "單價": 單價數字
                    }}
                  ]
                }}

                【格式 B：UPI_SEMICONDUCTOR】
                若為力智 (uPI) 或一般半導體/IC 廠商的 Invoice / Packing List：
                請將 INVOICE 與 PACKING LIST 明細資料分開擷取，回傳 JSON Object 格式如下：
                {{
                  "document_type": "UPI_SEMICONDUCTOR",
                  "invoice_data": [
                    {{
                      "頁碼": "...",
                      "發票號碼": "...",
                      "型號": "...",
                      "封裝規格": "...",
                      "PO單號": "...",
                      "項次": "...",
                      "數量": 數字,
                      "單價": 數字,
                      "總價": 數字,
                      "發票總金額": 數字(僅在最後一筆顯示)
                    }}
                  ],
                  "packing_data": [
                    {{
                      "頁碼": "...",
                      "LIST NO/單號": "...",
                      "型號": "...",
                      "封裝規格": "...",
                      "PO單號": "...",
                      "項次": "...",
                      "數量": 數字,
                      "總 GW (KGS)": 數字(僅在最後一筆顯示),
                      "總 NW (KGS)": 數字(僅在最後一筆顯示)
                    }}
                  ]
                }}

                注意事項：
                - 數量、單價、總價等數值欄位請回傳純數字 (不要加千分位逗號)。
                - 請嚴格回傳純 JSON Object。
                """

                # ⚡ 核心極速呼叫：指定 Flash + 開啟原生 JSON 模式
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(
                            data=file_bytes, mime_type=mime_type
                        ),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )

                if not response or not response.text:
                    st.error("API 未成功回傳內容，請稍後再試。")
                    st.stop()

                clean_json = (
                    response.text.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                raw_data = json.loads(clean_json)

                doc_type = raw_data.get("document_type", "UPI_SEMICONDUCTOR")

                # =========================================================
                # 處理情況 A: BENQ 報單比對 (17 欄位)
                # =========================================================
                if doc_type == "BENQ_COMPARE":
                    st.success("✅ 自動辨識為 **BENQ/報單比對** 格式！")
                    compare_data = raw_data.get("compare_data", [])
                    df_compare = pd.DataFrame(compare_data)

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
                        if col not in df_compare.columns:
                            df_compare[col] = None
                    df_compare = df_compare[compare_cols]

                    st.subheader("📋 報單比對 17 欄位預覽")
                    st.dataframe(df_compare, use_container_width=True)

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df_compare.to_excel(
                            writer, index=False, sheet_name="GoodsCompare"
                        )
                    excel_data = output.getvalue()

                    st.download_button(
                        label="📥 下載報單比對 Excel (.xlsx)",
                        data=excel_data,
                        file_name=f"GoodsCompare_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                # =========================================================
                # 處理情況 B: 力智 (uPI) / 一般半導體 (雙 Sheet 格式)
                # =========================================================
                else:
                    st.success("✅ 自動辨識為 **力智/半導體** 格式！")
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

                    # 數值欄位轉純數字 (修正縮排)
                    inv_num_cols = ["數量", "單價", "總價", "發票總金額"]
                    for col in inv_num_cols:
                        df_inv[col] = df_inv[col].apply(clean_numeric)

                    pack_num_cols = ["數量", "總 GW (KGS)", "總 NW (KGS)"]
                    for col in pack_num_cols:
                        df_pack[col] = df_pack[col].apply(clean_numeric)

                    st.subheader("🧾 Invoice（發票）解析結果預覽")
                    st.dataframe(df_inv, use_container_width=True)

                    st.subheader("📦 Packing List（裝箱單）解析結果預覽")
                    st.dataframe(df_pack, use_container_width=True)

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df_inv.to_excel(
                            writer, index=False, sheet_name="Invoice"
                        )
                        df_pack.to_excel(
                            writer, index=False, sheet_name="Packing_List"
                        )
                    excel_data = output.getvalue()

                    st.download_button(
                        label="📥 下載多頁籤 Excel 檔案 (.xlsx)",
                        data=excel_data,
                        file_name=f"Parsed_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.success("解析成功！已依據文件格式產出對應 Excel 檔案。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
