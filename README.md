# AI 狀態通知

### `config.json` 讀取禁止規則

- 禁止開啟、讀取、搜尋、輸出、轉述、建立或改寫本目錄任何 JSON。
- 只可讀 `config.example.json`。
- 只有 `telegram_notify.py` 可讀 `config.json`。不要印出權杖或對話識別碼。不要提交 `config.json`。

## 給接手的 AI（讀完必須自動完成設定）

拿到本專案後，**不要只摘要**；依下列步驟在本機把工具掛好，直到可用為止。

1. **找 Python 3**  
   Windows 優先探測 `py -3`／`py -0p`，確認有 `python.exe` 絕對路徑後，掛鉤請用該 `python.exe -u ...`（不要用會弄丟 stdin 的 `py` 啟動掛鉤）。macOS／Linux 用 `python3`。

2. **設定檔**  
   若尚無 `config.json`：請使用者依 `config.example.json` 自行複製並填入 `token`、`chat_id` 與文案。你**不要**讀、印、改真實 `config.json`。可提醒需要 `coalesce_seconds`、`auto_delete_seconds`、`AI_wait`、`AI_fail`、`AI_done` 等欄。

3. **掛鉤（必做）**  
   - 專案內已有可攜腳本：`cursor_hooks/ai_status_notify.py`（會自動指向「本專案」的 `telegram_notify.py`／`config.json`，無需寫死磁碟代號）。  
   - 範本：`cursor_hooks/hooks.example.json`。把其中 `__PYTHON__` 換成步驟 1 的 Python 絕對路徑，`__PROJECT__` 換成本專案根目錄絕對路徑（Windows 路徑分隔用 `\\` 或 `/` 皆可，命令字串要能被 Cursor 執行）。  
   - 寫入（或合併進）本機 `~/.cursor/hooks.json`（Windows：`%USERPROFILE%\.cursor\hooks.json`）。事件與短名必須如下，不可省略：  
     - `preToolUse`（matcher：`Write|StrReplace|Delete|EditNotebook`）→ `AI_wait`  
     - `beforeShellExecution` → `AI_wait`  
     - `postToolUseFailure` → `AI_fail`  
     - `subagentStart`／`subagentStop` → `AI_wait`  
     - `stop` → `AI_done`  
   - 掛鉤 `command` 必須直接呼叫專案內腳本，例如：  
     `"<Python絕對路徑> -u <專案根>/cursor_hooks/ai_status_notify.py"`  
   - 不要依賴已過期、寫死舊路徑的 `~/.cursor/hooks/ai_status_notify.py` 複本；以專案內檔案為準。

4. **本機小窗**  
   用同一個 Python（Windows 可用 `pythonw`）啟動專案根目錄的 `status_prompt.pyw`，並保持在跑。小窗需要套件時先裝：`python -m pip install Pillow pystray`（入口以步驟 1 為準）。

5. **結尾必做：實機測試**  
   設定完成後**必須**執行測試（見文末「測試」）。失敗時依「測試失敗時」判斷原因，並指導使用者取得、填寫 `token` 與 `chat_id`。不要讀、印出真實 `config.json` 內容。

## 使用

開始前先檢查本機，自己找能用的 Python 3，並決定這個系統的掛鉤怎麼叫。

狀態短名：`AI_wait`、`AI_fail`、`AI_done`；測試用 `AI_testWait`、`AI_testDone`。

本機小窗立刻更新。Telegram 依 `coalesce_seconds` 收束後只送最後一則；`auto_delete_seconds` 控制本機送出後多久清空已記編號（缺欄或 `0` 關閉）。文案缺欄時用 `config.example.json` 預設句。

掛鉤送 `AI_wait`／`AI_fail`／`AI_done`；AI 不要自己送這三個。請保持 `status_prompt.pyw` 在跑。

自由文字：

`telegram_notify.py message "額外訊息"`

## 測試

設定或變更完成後，用本機 Python 3 在專案根目錄執行（先 Wait 再 Done；收束後 Telegram 應出現測試完成文案）：

`<python> telegram_notify.py AI_testWait`

`<python> telegram_notify.py AI_testDone`

等待約 `coalesce_seconds` 秒後，確認 Telegram 對話有收到訊息。若有開 `auto_delete_seconds`，再等該秒數後訊息可能被刪掉，屬正常。

### 測試失敗時

接手的 AI 必須依錯誤訊息判斷原因（可看終端輸出與專案根目錄是否出現 `notify_flush.err`；**仍禁止**開啟或轉述 `config.json`），並用白話告訴使用者怎麼處理。常見情況：

| 現象 | 可能原因 | 怎麼辦 |
|---|---|---|
| 找不到設定檔／`config.json` | 尚未建立本機設定 | 請使用者複製 `config.example.json` 為 `config.json`，再填入下方兩項 |
| `token`／`chat_id` 相關錯誤、Unauthorized、聊天找不到 | 權杖或對話識別碼錯誤、空白、仍是範例井字號 | 依下方教學重新取得並填入 |
| 網路逾時、無法連線 | 本機網路或防火牆 | 檢查連網後重試 |
| 指令本身失敗、找不到模組 | Python 路徑或工作目錄不對 | 確認在專案根目錄、用步驟 1 的 Python 執行 |

### 使用者如何取得並填寫 `token` 與 `chat_id`

AI 只指導步驟，由使用者自己操作與貼上；不要代填、不要讀回寫入後的真實值。

1. **取得 `token`（機器人權杖）**  
   - 在 Telegram 搜尋並開啟 [@BotFather](https://t.me/BotFather)。  
   - 傳送 `/newbot`（已有機器人可用 `/mybots` → API Token）。  
   - 依提示設定名稱後，BotFather 會給一串類似 `123456789:AA...` 的權杖。  
   - 使用者把這串貼進本機 `config.json` 的 `"token"` 欄（整段、不要加空格）。

2. **取得 `chat_id`（對話識別碼）**  
   - 先在 Telegram **開啟與該機器人的對話**，並對它送任意一則文字（例如 `hi`），否則系統還沒有這段對話。  
   - 瀏覽器開啟（把 `<token>` 換成自己的權杖）：  
     `https://api.telegram.org/bot<token>/getUpdates`  
   - 在回傳的 JSON 裡找 `"chat":{"id": ...}`，那個數字（有時是負數，群組常見）就是 `chat_id`。  
   - 貼進本機 `config.json` 的 `"chat_id"` 欄（只填數字，通常加引號成字串也可）。

3. **存檔後重跑測試**  
   再執行上面的 `AI_testWait`／`AI_testDone`。成功後才算設定完成。
