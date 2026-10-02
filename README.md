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
   用同一個 Python（Windows 可用 `pythonw`）啟動專案根目錄的 `status_prompt.pyw`，並保持在跑。

5. **驗證**  
   使用者要求測試時才執行：  
   `<python> telegram_notify.py AI_testWait`／`AI_testDone`。  
   平時不要主動打真實 Telegram。

## 使用

開始前先檢查本機，自己找能用的 Python 3，並決定這個系統的掛鉤怎麼叫。

狀態短名：`AI_wait`、`AI_fail`、`AI_done`；測試用 `AI_testWait`、`AI_testDone`。

本機小窗立刻更新。Telegram 依 `coalesce_seconds` 收束後只送最後一則；`auto_delete_seconds` 控制本機送出後多久清空已記編號（缺欄或 `0` 關閉）。文案缺欄時用 `config.example.json` 預設句。

掛鉤送 `AI_wait`／`AI_fail`／`AI_done`；AI 不要自己送這三個。請保持 `status_prompt.pyw` 在跑。

自由文字：

`telegram_notify.py message "額外訊息"`

測試（使用者要求時才跑）：

`telegram_notify.py AI_testWait`

`telegram_notify.py AI_testDone`
