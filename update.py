Python
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DATA_FILE = "data.json"

# 15 個指定鍵值的預設結構
DEFAULT_DATA = {
    "台指結算": {"value": None, "prev": None},
    "現貨量(億)": {"value": None},
    "融資餘額(億)": {"value": None, "prev": None},
    "美元兌台幣": {"value": None},
    "外資現貨(億)": {"value": None},
    "投信現貨(億)": {"value": None},
    "自營商現貨(億)": {"value": None},
    "外資台指期未平倉": {"value": None, "prev": None},
    "五大淨額(口)": {"value": None},
    "十大淨額(口)": {"value": None},
    "P/C未平倉比": {"value": None},
    "外資選擇權未平倉淨額(萬)": {"value": None},
    "小台散戶多空比(%)": {"value": None},
    "微台散戶多空比(%)": {"value": None},
    "台積電美股ADR指數": {"value": None, "change": None},
}


def load_existing_data():
  """讀取舊的 data.json，若檔案不存在或格式毀損則回傳預設結構"""
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = json.load(f)
        return content.get("data", DEFAULT_DATA)
    except Exception as e:
      print(f"讀取舊 data.json 失敗: {e}，將使用預設結構初始化。")
  return DEFAULT_DATA


def save_data(data_dict):
  """將最終結果存成 UTF-8 編碼的 JSON 檔案，並記錄更新時的台灣時間"""
  try:
    from zoneinfo import ZoneInfo

    tw_time = datetime.now(ZoneInfo("Asia/Taipei")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
  except Exception:
    tw_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  output = {"update_time": tw_time, "data": data_dict}
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=4)
  print(f"資料已成功更新並儲存至 {DATA_FILE}，更新時間: {tw_time}")


def update_field(field_name, new_val, data_dict, old_data, is_triple=False):
  """更新欄位數值邏輯：

  - 若成功抓到新數值，且 is_triple 為 True（需要保留 prev 的欄位），
    會先把舊的 value 移至 prev，再將新數值寫入 value。
  - 若抓到的新數值為 None（代表假日休市或未抓到），則完整保留舊數值。
  """
  if new_val is not None:
    if is_triple:
      old_val = old_data.get(field_name, {}).get("value")
      data_dict[field_name]["prev"] = old_val
      data_dict[field_name]["value"] = new_val
    else:
      data_dict[field_name]["value"] = new_val
  else:
    # 沒抓到新數字時保留舊資料
    data_dict[field_name] = old_data.get(field_name, data_dict[field_name])


def scrape_wantgoo():
  old_data = load_existing_data()
  new_data = dict(old_data)  # 複製一份舊資料作為預設保留基底

  with sync_playwright() as p:
    # 啟動無頭瀏覽器，並加上完整瀏覽器標頭避免被阻擋
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()

    try:
      # 1. 抓取台股大盤與現貨、三大法人、融資餘額等相關頁面
      print("正在連線至玩股網 (台股大盤頁面)...")
      page.goto("https://www.wantgoo.com/stock", timeout=60000)
      page.wait_for_load_state("domcontentloaded")
      soup_stock = BeautifulSoup(page.content(), "html.parser")

      # 2. 抓取期貨選擇權與籌碼頁面
      print("正在連線至玩股網 (期貨選擇權籌碼頁面)...")
      page.goto("https://www.wantgoo.com/futures", timeout=60000)
      page.wait_for_load_state("domcontentloaded")
      soup_futures = BeautifulSoup(page.content(), "html.parser")

      # --- 💡 實際爬蟲抓取對應數據 (請依玩股網網頁最新 CSS Selector 調整) ---
      # 範例結構：將抓到的數值暫存於字典中（若未抓到或非開盤日請維持 None）
      scraped_values = {
          "台指結算": None,
          "現貨量(億)": None,
          "融資餘額(億)": None,
          "美元兌台幣": None,
          "外資現貨(億)": None,
          "投信現貨(億)": None,
          "自營商現貨(億)": None,
          "外資台指期未平倉": None,
          "五大淨額(口)": None,
          "十大淨額(口)": None,
          "P/C未平倉比": None,
          "外資選擇權未平倉淨額(萬)": None,
          "小台散戶多空比(%)": None,
          "微台散戶多空比(%)": None,
          "台積電美股ADR指數": None,
          "台積電美股ADR漲跌": None,
      }

      # 範例抓取程式碼寫法提示：
      # stock_qty_elem = soup_stock.select_one('.your-target-selector')
      # if stock_qty_elem:
      #     scraped_values["現貨量(億)"] = float(stock_qty_elem.text.strip().replace(',', ''))

      # 依序更新 15 個指定欄位
      triple_fields = ["台指結算", "融資餘額(億)", "外資台指期未平倉"]

      for key in DEFAULT_DATA.keys():
        if key == "台積電美股ADR指數":
          val = scraped_values.get("台積電美股ADR指數")
          chg = scraped_values.get("台積電美股ADR漲跌")
          if val is not None:
            new_data[key]["value"] = val
            if chg is not None:
              new_data[key]["change"] = chg
        else:
          is_triple = key in triple_fields
          new_val = scraped_values.get(key)
          update_field(key, new_val, new_data, old_data, is_triple=is_triple)

    except Exception as e:
      print(f"爬取過程中發生例外錯誤: {e}，將完整保留舊資料不覆蓋。")
    finally:
      browser.close()

  return new_data


if __name__ == "__main__":
  print("=== 開始執行玩股網盤後數據更新行程 ===")
  updated_data = scrape_wantgoo()
  save_data(updated_data)