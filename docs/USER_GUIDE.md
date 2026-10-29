# GUI 操作說明

## 介面

| 區塊 | 內容 |
|---|---|
| 版本列 | 顯示 `Programmer GUI v… \| Bridge: <板名> firmware <版本>`；啟動時韌體顯示 not connected，Connect 後更新。Log 也會記錄這兩個版本 |
| Program count | 視窗右上角：累計燒錄 **Pass（綠）/ Fail（紅）/ Total（黑）**，存於 `%APPDATA%\MX25S1633F_Programmer\stats.json`；每次燒錄另記在 `program_history.csv`（時間、結果、檔名、CRC、秒數、失敗原因）；Reset count 歸零、Open history 開啟 |
| Supported SPI Flash… | 「SPI clock」列右側的按鈕，點選開啟獨立視窗：廠牌、型號、JEDEC ID、容量、VCC；Auto Detect 偵測到的晶片該列反白 |
| Custom Flash… | 在 Supported SPI Flash 視窗內，新增／修改／刪除自訂 SPI flash，見下方「自訂 SPI Flash」。自訂項目以藍字、型號後加 `*` 顯示 |
| 上方列 | COM 埠（自動找 Curiosity Virtual COM Port，兩種 Nano 都可）、Connect、Raw Monitor；第二列：SPI clock、Pin drive、WP# High |
| Firmware File | 📂 Load File… 載入 .bin / .hex，顯示大小、位址範圍、CRC32 |
| Commands | 圖示按鈕，7 欄等寬對齊：第 1 列 Auto Detect～Reset，第 2 列 Sector Erase～Read->File 與 Stop（見下表） |
| About | 「SPI clock」列最右側的按鈕：程式名稱、GUI 版本、程式更新日期、MCU（Microchip PIC18F16Q20）、MCU Firmware 版本（Connect 後由 `INFO` 讀取，未連線顯示 not connected）、設計者、Email、GitHub 網址（短網址 `github.com/khsu-tw/K12SPI_Programmer`，點一下用瀏覽器開啟） |
| 彈出視窗 | Supported SPI Flash、Custom Flash、Config SR、Raw Monitor、About 都開在主視窗右側（多個同時開時依序往下錯開；螢幕太窄時貼齊螢幕右緣） |
| 參數列 | Address (hex)、Length (hex)、Verify after program、Double-check Read->File（用板上 CRC32 再確認讀出資料） |
| 進度 | 單行狀態：目前階段（抹除/燒錄/驗證）、訊息與右側 0~100%，下方是細進度條 |
| Log | 預設收合，按 **▶ Show Log** 展開、**▼ Hide Log** 收合。收合時若出現錯誤，按鈕會顯示「⚠ new error」；內容照常累積，展開即可看到全部 |

| 按鈕 | 動作 | 會用到的參數 |
|---|---|---|
| 🔎 Auto Detect | 檢查 IO 電壓（VSENSE）→ 讀 JEDEC ID（9Fh）→ 讀 SFDP（5Ah）辨識廠牌/型號/容量；Connect 時自動執行。電壓不是 1.2 V 或辨識失敗時鎖定 Program/Erase/Config SR。ID 不在支援清單時，依 JESD216H SFDP 欄位在 Log 列出廠商、容量、位址模式、頁大小、擦除類型與時間、Fast Read 模式及各參數表，標籤顯示橘色「SFDP only」，只能 Hex Dump / Read→File | — |
| 🔍 Read ID | 讀 ID：`C2 2B 25` MX25S1633F、`C8 83 15` GD25UF16E、`EF 65 17` W25Q65NE、`EF 65 16` W25Q32NE | — |
| 📋 Read SR | 讀出並解碼 Status Register（位元名稱依偵測到的晶片；GD25UF16E / Winbond 另顯示 SR2） | — |
| ⚙ Config SR | 開啟 Config Options 對話框（只列出偵測到的晶片可寫的 SR1 位元） | — |
| 🧹 Sector Erase | 抹除 Address 所在的 4KB 扇區 | Address |
| 🗑 Chip Erase | 抹除整顆（容量依偵測結果：MX25S1633F / GD25UF16E 2MB、W25Q32NE 4MB、W25Q65NE 8MB；會先確認） | — |
| 📥 Program (loaded) | 抹除需要的扇區 → 逐頁燒錄 → （選）驗證 | Address |
| ✅ Verify (loaded) | 比對 flash 和載入的檔案 | Address |
| 💾 Read→File | 讀出存成 .bin | Address、Length |
| 📄 Hex Dump | 在 Log 顯示 hex（最多 4KB） | Address、Length |
| 🔁 Reset | 軟體重置 flash | — |
| 📶 Link Test | 以 200 次 RDID 找出最快且穩定的 SPI clock / Pin drive 並套用 | — |
| ■ Stop | 中止進行中的動作 | — |

## 燒錄速度

- 抹除會自動選最大的對齊區塊（64KB → 32KB → 4KB），比逐一 4KB 快很多。
- 頁寫入採流水線：傳下一頁資料的同時，flash 正在寫上一頁；全空白（0xFF）的頁會略過。
- 驗證以每 64KB 比對板上 CRC，不需把資料讀回 PC；SPI clock 設為 Max 最快（不穩時用 Link Test）。
- 檔案超過晶片容量的一半時可勾選「Chip Erase first」（資料全清）。Chip Erase 逾時依資料手冊最大值：
  MX25S1633F 57 s（Ultra Low Power 模式的最大值）、GD25UF16E 50 s、W25Q65NE 140 s、W25Q32NE 70 s。

## 第一次使用的建議順序

1. **先不接 flash**：只接 USB-C，燒好 Nano 韌體（`firmware/flash_nano.bat`；用 MPLAB IPE 燒錄並回讀驗證，最後一行應為 `Programmed and verified`。**不要用拖放到 CURIOSITY 磁碟機**：PIC18F16Q20-CNANO 上 5.0.0 的 HEX 會被截斷，且 STATUS.TXT 仍顯示 Ready），GUI 按 Connect。出現 `Bridge alive.` 表示通訊正常；
   這時 `ID:FF FF FF` 是正常的。
2. **斷電接線**：依 HARDWARE.md 接好 TXS0108E 與 1.2V LDO，先不放 flash。上電後用電表確認 VCCA、OE、
   flash 座 pin 8 都是約 1.2V，flash 座任何一腳都沒有 3.3V。
3. **放入 flash**：SPI clock 先選 Slow → Connect → 應出現 `Detected Macronix MX25S1633F ...`（換其他晶片則顯示對應型號）；
   穩定後再用 📶 Link Test 找最快的設定。

## 一般燒錄流程

1. Connect → Log 會出現 `Bridge alive.` 和 `Detected <廠牌> <型號> ...`
2. （建議）先備份：Address `000000`、Length 用 Auto Detect 自動帶入的整顆容量（例如 2MB = `200000`）→ 💾 Read→File。
3. 📂 Load File… 選擇燒錄檔。.hex 會自動帶入起始位址；.bin 預設從 0x000000 開始。
4. 確認 Address → 按 📥 Program (loaded)。
5. 勾選「Verify after program」的話，燒完會自動驗證，最後顯示 `VERIFY OK`。

## Status Register（Config SR）

SR1（05h）的位元定義**三家不同**，GUI 依偵測到的晶片自動切換：

| Bit | MX25S1633F | GD25UF16E | W25Q65NE / W25Q32NE |
|---|---|---|---|
| 7 | SRWD：SR 寫入保護 | SRP0：SR 保護 | SRP：SR 保護 |
| 6 | QE：Quad Enable（=1 時 WP#/RESET# 變 SIO2/SIO3） | BP4 | SEC：保護單位 4KB 扇區(1) / 64KB 區塊(0) |
| 5 | BP3 | BP3 | TB：從頂端(0) / 底端(1) 保護 |
| 4~2 | BP2~BP0 | BP2~BP0 | BP2~BP0 |
| 1 | WEL：唯讀，Write Enable Latch | WEL | WEL |
| 0 | WIP：唯讀，Write In Progress | WIP | BUSY |

- **SR2**（35h，只有 GD25UF16E 與 Winbond）：GD25UF16E 為 SUS1、CMP、LB3~LB1、SUS2、QE、SRP1；Winbond 為 SUS、CMP、LB3~LB1、QE、SRL。
  Config SR 只改 SR1，但會把 SR2 原值一併寫回：GD25UF16E 只寫 1 個位元組時會把 SR2 的可寫位元清 0。
  LB3~LB1 是 OTP，設成 1 就無法復原，GUI 不提供修改。
- 保護區域的對照表請見各晶片資料手冊（`DOC/`）的 Memory Protection 表；GD25UF16E 與 Winbond 另受 SR2 的 **CMP** 影響（CMP=1 時保護範圍反轉）。
- 勾選後右上角會即時顯示 SR 數值；按 **Default** 全部清 0；按 **OK** 會執行 WREN → WRSR → 讀回比對。
- **只要 BP 位元不是全 0（或 CMP 造成任何區域受保護），Chip Erase 就不會執行**，被保護的區域也無法抹除或燒錄。燒錄失敗時請先把 BP 位元清 0。
- 如果 SRWD / SRP0 / SRP=1 導致寫不進去：先勾 **WP# High**（需要接 WP# 線），再改 SR。GD25UF16E 的 SRP1=1、Winbond 的 SRL=1 為電源鎖定，
  需斷電重上電才會解除（GD25UF16E 也可用軟體重置 66h+99h）。
- W25Q32NE 的 SR 位元與 W25Q65NE 相同（依 `DOC/` W25Q32NE 資料手冊 RevE）。
- **W25Q64NE 不支援**：它與 W25Q65NE 的 JEDEC ID（`EF 65 17`）與容量（64Mbit）相同，無法區分，插入時會顯示為 W25Q65NE。
  兩者的 Chip Erase 最大時間（160 s / 140 s）、tRES1（50 µs / 20 µs）、最高讀取時脈（33 MHz / 84 MHz）不同，若使用 W25Q64NE 請自行確認。

## 疑難排解：環境與 Task

| 現象 | 可能原因 / 處理方式 |
|---|---|
| `[ERROR] Python environment not found.` | 先執行 `setup_env.bat`（只用 .exe 的話不需要） |
| `[ERROR] XC8 not found` / `PIC16F1xxxx_DFP not found` / `PIC18F-Q_DFP not found` | 安裝 MPLAB XC8 與 MPLAB X，或設定環境變數 `XC8_BIN` / `DFP_16F1` / `DFP_18FQ` |
| `WinError 32 ... being used by another process` | 專案在 OneDrive 裡，同步時鎖住檔案。`setup_env.bat` 會把環境建到 `%LOCALAPPDATA%` |
| `Python not found` | 安裝 Python 3.9+，勾選 *Add python.exe to PATH* |
| 出現 tkinter 相關錯誤 | 重新執行 Python 安裝程式 → Modify → 勾選 *tcl/tk and IDLE* |
| .exe 被防毒軟體攔截 | PyInstaller 單檔 exe 偶有誤判；可改執行 `tools\py.cmd gui\mx25s1633_gui.py` |

## 疑難排解：燒錄 Curiosity Nano 韌體

| 現象 | 處理方式 |
|---|---|
| 找不到 `CURIOSITY` 磁碟機 | 換一條支援資料傳輸的 USB-C 線；接 Nano 的 USB-C 埠；等 Windows 完成驅動安裝 |
| 複製後 PS LED 快閃 2 秒（失敗） | 檔案損毀或 HEX 與板子不符（須為 PIC18F16Q20-CNANO 用的 pic18f16q20 HEX）：重新執行 `firmware\build.bat`；或改用 MPLAB X IPE 燒錄 |
| 燒完後 GUI 連不上 | 拔插 USB；按 GUI 的 ↻ 重新整理；COM 埠名稱為 *Curiosity Virtual COM Port*，鮑率 500000 |

## 疑難排解：硬體與通訊

| 現象 | 可能原因 / 處理方式 |
|---|---|
| `PING ... [FAIL] ERR:timeout` | ① 其他程式佔用了 COM 埠 ② 拔插 Nano USB 後重新連線 ③ 用 Raw Monitor 看原始輸出 |
| 找不到 COM 埠 | 換一條支援資料傳輸的 USB-C 線；確認裝置管理員中有 Curiosity Virtual COM Port |
| `ID:FF FF FF` | MISO 一直是高：flash 沒電（檢查 1.2V）、OE 沒接 VCCA、A3/SO 沒接好 |
| `ID:00 00 00` | MISO 一直是低：接線短路、flash 沒電、方向接反（檢查 pin 1 位置） |
| ID 偶爾錯誤 | 按 Link Test、SPI clock 選 Slow、Pin drive 選 Slow edge、縮短杜邦線、補 0.1µF 電容 |
| Erase/Program 失敗 | BP 位元保護中 → Config SR 把 BP 清 0 |
| WRSR 失敗 | SRWD / SRP0 / SRP=1 且 WP# 為低 → 勾 WP# High；GD25UF16E SRP1=1、Winbond SRL=1 → 斷電重上電 |
| `Blocked: ID xx xx xx is not in the supported list` | 晶片不在支援清單：Log 會依 SFDP 列出規格，只能讀取。要燒錄請按 **Custom Flash…** 加入（見下方「自訂 SPI Flash」），不必改程式 |
| `Blocked: SFDP density ... does not match` | ID 與 SFDP 容量不符：多半是晶片型號與預期不同（例如收到 W25Q32NE 而不是 W25Q65NE），請看晶片頂面印字 |
| `ERR:vio` / `IO voltage ... OUT OF RANGE` | VSENSE 量到的 1.2 V 軌不在 1.14–1.26 V，韌體拒絕寫入/抹除。用電表確認 1.2 V 電源 |
| Verify MISMATCH | 燒錄前沒有抹除該區域，或 SPI 速度太快 |

## 自訂 SPI Flash（不改程式支援新的 1.2 V 晶片）

晶片不在清單時，Log 會顯示「Blocked: ... not in the supported list」。按 **Custom Flash…** 填寫參數即可，不需要改程式或重新打包 exe，也不需要重燒 Nano。

容量、頁大小、擦除種類、位址模式一律由晶片的 SFDP 自動讀取，只需填 SFDP 沒有的資料：

| 欄位 | 必填 | 說明 |
|---|---|---|
| Vendor / Part | 是 | 顯示名稱 |
| JEDEC ID | 是 | 9Fh 回傳的 3 bytes，如 `EF 65 18`。不可與內建晶片相同 |
| Chip erase max (s) | 是 | 資料手冊 tCE 最大值，1~150 秒。用於逾時與進度條；填太小會在抹除完成前逾時 |
| Density (Mbit) | 否 | 填了會與 SFDP 容量比對，不符就禁止燒錄（防止 ID 對錯料） |
| SR1 writable bits | 否 | Config SR 對話框的位元，格式 `NAME=bit`，預設 `BP2=4, BP1=3, BP0=2`。bit 0/1（WIP/WEL）不可列 |
| SR1 readback mask | 否 | WRSR 後要比對的位元，空白 = 上面列出的全部位元 |
| VCC min-max | 否 | 必須涵蓋 1.14~1.26 V，否則拒絕儲存（避免對低壓晶片過壓） |
| Has Status Register 2 | 否 | Winbond / GigaDevice 型：WRSR 要連 SR2 一起寫回，否則 SR2 會被清掉 |

操作：先接上晶片按 Auto Detect（會顯示 SFDP 資料）→ Custom Flash… → **Use detected flash** 帶入 ID 與容量 → 依資料手冊補上 Chip erase 等欄位 → **Save / Update** → 再按 Auto Detect。

- 設定存在 `custom_flash.json`：若 exe／腳本旁邊有這個檔就用它（方便隨 exe 發給別人），否則用 `%APPDATA%\MX25S1633F_Programmer\custom_flash.json`。Open folder 可開啟所在資料夾，也可直接編輯 JSON。
- 格式範例：

```
{"flashes": [
  {"vendor": "Acme", "part": "AC25U128", "jedec": "EF 65 18", "chip_erase_s": 90,
   "has_sr2": true, "size_mbit": 128, "vcc_min": 1.14, "vcc_max": 1.26,
   "sr_bits": {"SRP": 7, "BP2": 4, "BP1": 3, "BP0": 2}}
]}
```

- 某一筆填錯只會略過該筆並在 Log 顯示原因，不影響其他晶片。
- 自訂晶片偵測時會顯示警告：抹除時間與 SR 遮罩是使用者提供的，程式沒有用資料手冊核對。**第一次請先用不重要的資料測試**，並確認 tCE 沒有填小。

**仍然做不到（寫死在韌體）**：只支援 3 byte 位址（容量 ≤ 128 Mbit）、256 B 頁、4 KB 擦除（20h）、tCE ≤ 150 秒、IO 電壓窗 1.14~1.26 V、標準 JEDEC 指令集；沒有 SFDP 的晶片也不能燒錄。超出這些限制要改 `firmware/src/main.c`。
