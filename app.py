import json
import time
from datetime import datetime
from google import genai
from google.genai import types
import streamlit as st

# 從 parsers 資料夾匯入您剛建立的模組
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
                            available_models.append(m_name)
                except Exception:
                    available_models = [
                        "gemini-2.5-flash",
                        "gemini-2.0-flash",
                        "gemini-1.5-flash",
                    ]

                flash_models = [
                    m for m in available_models if "flash" in m.lower()
                ]
                other_models = [
                    m for m in available_models if "flash" not in m.lower()
                ]
                models_to_try = flash_models + other_models

                if not models_to_try:
                    models_to_try = [
                        "gemini-2.5-flash",
                        "gemini-2.0-flash",
                        "gemini-1.5-flash",
                    ]

                response = None
                last_error = None

                for model_name in models_to_try:
                    for attempt in range(2):
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=[
                                    types.Part.from_bytes(
                                        data=file_bytes, mime_type=mime_type
                                    ),
                                    prompt,
                                ],
                            )
                            if response and response.text:
                                break
                        except Exception as e:
                            last_error = e
                            err_msg = str(e)
                            if (
                                "503" in err_msg
                                or "UNAVAILABLE" in err_msg
                                or "429" in err_msg
                            ):
                                time.sleep(2)
                                continue
                            else:
                                break
                    if response and response.text:
                        break

                if not response or not response.text:
                    raise last_error

                clean_json = (
                    response.text.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                raw_data = json.loads(clean_json)
                doc_type = raw_data.get("document_type", "UPI_SEMICONDUCTOR")

                # =========================================================
                # 呼叫 parsers 模組處理邏輯
                # =========================================================
                
if doc_type == "BENQ_COMPARE":
    st.success("✅ 自動辨識為 **BENQ/報單比對** 格式！")
    df_compare, excel_bytes = process_benq_compare(raw_data)

    st.subheader("📋 報單比對 17 欄位預覽")
    st.dataframe(df_compare, use_container_width=True)

    st.download_button(
        label="📥 下載報單比對 Excel (.xlsx)",
        data=excel_bytes,
        file_name="報單比對.xlsx",  # 👈 這裡已改為「報單比對.xlsx」
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

                else:
                    st.success("✅ 自動辨識為 **力智/半導體** 格式！")
                    df_inv, df_pack, excel_bytes = process_upi_semiconductor(
                        raw_data
                    )

                    st.subheader("🧾 Invoice（發票）解析結果預覽")
                    st.dataframe(df_inv, use_container_width=True)

                    st.subheader("📦 Packing List（裝箱單）解析結果預覽")
                    st.dataframe(df_pack, use_container_width=True)

                    st.download_button(
                        label="📥 下載多頁籤 Excel 檔案 (.xlsx)",
                        data=excel_bytes,
                        file_name=f"Parsed_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.success("解析成功！已依據文件格式產出對應 Excel 檔案。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
