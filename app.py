import json
import time
from datetime import datetime
from google import genai
from google.genai import types
import streamlit as st

# 從 parsers 資料夾匯入模組
from parsers.benq_parser import process_benq_compare
from parsers.upi_parser import process_upi_semiconductor

# 1. 頁面基本設定
st.set_page_config(
    page_title="Shipping Docs 自動解析工具",
    layout="wide",
)

st.title("📄 Shipping Docs 自動解析工具")
st.caption("支援供應商: 力智、明基(報單轉換)")

# 讀取 Secrets 中的 API Key，若無則從 Sidebar 輸入
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader(
    "選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件，並自動辨識格式處理中..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                upload_date_str = datetime.now().strftime("%Y/%m/%d")

                # 整合 Prompt
                prompt = f"""
                你是一個專業的半導體與電子零件 Shipping Docs 解析專家。
                請閱讀這份文件，判斷文件屬於哪種格式 (document_type)：

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
                - 請嚴格回傳純 JSON Object，不要包含 Markdown 標記 (如 ```json )。
                """

                # 動態搜尋與嘗試模型
                available_models = []
                try:
                    for m in client.models.list():
                        m_name = (
                            m.name.replace("models/", "")
                            if hasattr(m, "name")
                            else str(m)
                        )
                        if (
                            hasattr(m, "supported_generation_methods")
                            and "generateContent"
                            in m.supported_generation_methods
                        ):
                            available_models.append(m_name)
                        elif not hasattr(m, "supported_generation_methods"):
                            available_models
