# Codex 專用設定

Codex 使用 `codex_hooks/ai_status_notify.py`，不可套用 Cursor 的小寫事件名稱或回傳格式。

## 安裝

在使用者層 `~/.codex/hooks.json` 設定命令，直接呼叫：

```text
<Python絕對路徑> -u <專案根>/codex_hooks/ai_status_notify.py
```

設定完成或 Hook 內容變更後，重新開啟 Codex 並執行 `/hooks`，審查及信任目前定義；未信任的 Hook 不會執行。

## 事件對應

| Codex 事件 | 通知 |
|---|---|
| `UserPromptSubmit`、`PreToolUse`、`PermissionRequest` | `AI_wait` |
| `SubagentStart`、`SubagentStop` | `AI_wait` |
| `PostToolUse` 且結果可確認失敗 | `AI_fail` |
| `Interrupt` | `AI_fail` |
| `Stop` | `AI_done` |

不要設定 `SessionEnd`，避免結束工作階段時重複傳送完成通知。

轉接器會自動加入 `--ide Codex`，讓 `{IDE}` 顯示為 `Codex`；並由 Python 程式自動解析 `{project}`，不需要 AI 每次提供專案名。

## Codex 專案名解析

1. 由 Hook `transcript_path` 的最新工作區記錄取得根目錄。
2. 自動定位 `CODEX_HOME`；未設定時使用 `~/.codex`。Windows、macOS 與 Linux 都使用這個邏輯位置，不寫死使用者目錄。
3. 唯讀搜尋該位置的 `state_*.sqlite`，以工作區根目錄對應 Codex 桌面版的自訂專案名。
4. 資料庫不存在、格式改變或沒有對應名稱時，自動退回工作區、Git 根目錄或工作目錄名。
5. `memories`、`sessions`、`skills` 等 Codex 內部目錄不會被當成專案名。

此機制不需要在 `config.json` 新增必填欄位。若使用者將 Codex 狀態目錄改到自訂位置，由 Codex 自身的 `CODEX_HOME` 環境變數提供，Hook 會自動跟隨。共用設定與驗證方式見[共用設定與測試](common.md)。
