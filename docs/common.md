# 共用設定與測試

## Python

Windows 先執行 `py -0p` 與 `py -3 -V` 找出 Python 3 的 `python.exe` 絕對路徑。Hook 必須直接使用 `python.exe -u`；不要用可能遺失標準輸入的 `py` 啟動 Hook。macOS 或 Linux 使用 `python3`。

## 設定檔

若沒有 `config.json`，由使用者複製 `config.example.json` 後自行填入 `token` 與 `chat_id`。AI 不得讀取、輸出或修改真實 `config.json`。

通知文案支援三個保留字串：

- `{platform}`：自動替換為 `Windows`、`Mac` 或 `Linux`。
- `{IDE}`：Hook 會替換為 `Codex` 或 `Cursor`；直接執行命令時預設為 `CLI`。
- `{project}`：Codex 使用 Hook `cwd` 的最後一層目錄名；Cursor 使用 `workspace_roots` 的第一個目錄名；直接執行時使用目前目錄名。無法取得時顯示 `未知專案`。

只有以上三個字串會被替換，其他大括號內容會保留原樣。例如：

```json
"AI_done": "{platform}上{project}的{IDE} A.I.的工作已完成."
```

## 本機小窗

用同一個 Python 啟動根目錄的 `status_prompt.pyw` 並保持執行。Windows 可用 `pythonw.exe` 隱藏終端視窗。若缺少套件，使用已確認的 Python 執行：

```text
<python> -m pip install Pillow pystray
```

## 使用

正式狀態為 `AI_wait`、`AI_fail`、`AI_done`；測試狀態為 `AI_testWait`、`AI_testDone`。

本機小窗立即更新。Telegram 依 `coalesce_seconds` 收束後只傳最後一則；`auto_delete_seconds` 控制多久後刪除通知，缺欄或 `0` 表示停用。

自由文字不參與收束：

```text
<python> telegram_notify.py message "額外訊息"
```

## 測試

安裝或修改後，依目前 IDE 執行測試：

```text
<python> telegram_notify.py --ide Codex AI_testWait
<python> telegram_notify.py --ide Codex AI_testDone
```

Cursor 將上面的 `Codex` 改成 `Cursor`。等待約 `coalesce_seconds` 秒後，確認 Telegram 收到含正確平台與 IDE 的完成文案；同時確認根目錄沒有 `notify_flush.err`。

## 常見問題

| 現象 | 處理方式 |
|---|---|
| 找不到 `config.json` | 由使用者複製 `config.example.json` 並自行填入設定 |
| Unauthorized 或找不到聊天 | 重新確認 `token` 與 `chat_id`，不要把內容交給 AI |
| 網路逾時 | 檢查網路與防火牆後重試 |
| 找不到模組或命令 | 確認工作目錄與 Python 絕對路徑 |
| 文案仍出現 `{IDE}` | 確認 Hook 有傳入 `--ide Codex` 或 `--ide Cursor` |
| 文案仍出現 `{project}` | 確認使用目前版本的 Hook 與 `telegram_notify.py` |

取得 `chat_id` 前，先對 Telegram 機器人傳一則訊息，再由使用者自行開啟 `https://api.telegram.org/bot<token>/getUpdates`，找出 `"chat":{"id": ...}`。權杖與識別碼只能由使用者寫入本機 `config.json`。
