# AI 狀態通知

## `config.json` 讀取禁止規則

- 禁止開啟、讀取、搜尋、輸出、轉述、建立或改寫真實 `config.json`。
- 只可讀 `config.example.json`。
- 只有 `telegram_notify.py` 可讀 `config.json`。不要印出權杖或對話識別碼。不要提交 `config.json`。

## 文件索引

接手的 AI 先讀共用文件，再只讀目前使用的 IDE 文件，不要一次載入全部說明。

```text
README.md
└─ docs/
   ├─ index.md   文件路由
   ├─ common.md  共用設定、保留字串與測試
   ├─ codex.md   Codex 安裝與事件
   └─ cursor.md  Cursor 安裝與事件
```

- [文件目錄](docs/index.md)
- [共用設定與測試](docs/common.md)
- [Codex 專用設定](docs/codex.md)
- [Cursor 專用設定](docs/cursor.md)

通知文案可使用 `{project}` 顯示目前專案名稱。Codex 以 Hook 提供的工作目錄判定；Cursor 以第一個工作區根目錄判定。詳細規則見[共用設定與測試](docs/common.md)。
