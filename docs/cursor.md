# Cursor 專用設定

Cursor 使用 `cursor_hooks/ai_status_notify.py`，不可套用 Codex 的事件名稱或回傳格式。

## 安裝

1. 以 `cursor_hooks/hooks.example.json` 為範本。
2. 將 `__PYTHON__` 換成 Python 3 的 `python.exe` 絕對路徑。
3. 將 `__PROJECT__` 換成本專案根目錄絕對路徑；JSON 內的 Windows 反斜線需寫成 `\\`，也可使用 `/`。
4. 合併到 `~/.cursor/hooks.json`；Windows 路徑為 `%USERPROFILE%\.cursor\hooks.json`。

命令必須直接呼叫專案內腳本：

```text
<Python絕對路徑> -u <專案根>/cursor_hooks/ai_status_notify.py
```

不要使用可能已過期、寫死舊路徑的 `~/.cursor/hooks/ai_status_notify.py` 複本。

## 事件對應

| Cursor 事件 | 通知 |
|---|---|
| `preToolUse`，比對 `Write|StrReplace|Delete|EditNotebook` | `AI_wait` |
| `beforeShellExecution` | `AI_wait` |
| `postToolUseFailure` | `AI_fail` |
| `subagentStart`、`subagentStop` | `AI_wait` |
| `stop` | `AI_done` |

轉接器會自動加入 `--ide Cursor`，讓 `{IDE}` 顯示為 `Cursor`。共用設定與驗證方式見[共用設定與測試](common.md)。
