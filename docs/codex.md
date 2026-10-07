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

轉接器會自動加入 `--ide Codex`，讓 `{IDE}` 顯示為 `Codex`；並從 Codex Hook 的 `cwd` 取工作目錄名，讓 `{project}` 顯示目前專案。共用設定與驗證方式見[共用設定與測試](common.md)。
