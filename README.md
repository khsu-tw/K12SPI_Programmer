# 1.2V SPI NOR Flash Programmer（PIC18F16Q20 Curiosity Nano）

用 **PIC18F16Q20 Curiosity Nano（PIC18F16Q20-CNANO）**
經 **TXS0108E** 電位轉換，燒錄 1.2V SPI NOR flash：Macronix **MX25S1633F**（16Mbit，`C2 2B 25`）、
GigaDevice **GD25UF16E**（16Mbit，`C8 83 15`）、Winbond **W25Q65NE**（64Mbit，`EF 65 17`），
以及 Winbond **W25Q32NE**（32Mbit，`EF 65 16`，資料手冊 RevE 在 `DOC/`）。
W25Q64NE 與 W25Q65NE 的 JEDEC ID 同為 `EF 65 17`、容量同為 64Mbit，無法區分，**只支援 W25Q65NE**；插入 W25Q64NE 會被辨識成 W25Q65NE。
GUI 啟動與 UART 連線時顯示燒錄程式版本與 Nano 韌體版本，並在獨立的「Supported SPI Flash」清單列出支援的晶片（偵測到的那一列會反白）。
GUI 的 **Auto Detect** 先檢查 1.2 V，再讀 JEDEC ID 與 JESD216H SFDP 辨識廠牌/型號/容量；
IO 電壓不是 1.2 V（1.14–1.26 V 以外）時韌體與 GUI 都拒絕燒錄/抹除。
PC 端 GUI 可讀 ID、抹除、燒錄、驗證、讀出存檔、Link Test，並修改 Status Register。

```
[PC GUI] --USB-C (CDC 500000bps)--> [PIC18F16Q20-CNANO] --SPI 3.3V--> [TXS0108E B|A] --SPI 1.2V--> [MX25S1633F]
```

接線圖：[docs/wiring_CNANO_TXS0108E_MX25S1633F.png](docs/wiring_CNANO_TXS0108E_MX25S1633F.png)，
腳位表見 [docs/HARDWARE.md](docs/HARDWARE.md)，協定見 [docs/PROTOCOL.md](docs/PROTOCOL.md)，操作見 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)，
燒錄必要參數與 JESD216H（SFDP）欄位對照見 [docs/SFDP_MAPPING.md](docs/SFDP_MAPPING.md)。
版本紀錄見 [ChangeHistory.md](ChangeHistory.md)。

## 專案結構

```
├─ PIC18F16Q20_PRD.md              需求文件
├─ README.md / .html               本說明
├─ ChangeHistory.md / .html        版本變更紀錄
├─ DOC/                            datasheet / User Guide / JESD216H
├─ firmware/
│  ├─ src/main.c                   韌體原始碼（XC8，PIC18F16Q20）
│  ├─ prebuilt/*.hex               預編譯 HEX（pic18f16q20）
│  ├─ build.bat                    以 XC8 編譯：build.bat
│  ├─ flash_nano.bat               以 MPLAB IPE（板載 nEDBG）燒錄並回讀驗證：flash_nano.bat
│  └─ verify_hex.py                比對 HEX 與回讀內容
├─ gui/
│  ├─ mx25s1633_gui.py, hexfile.py GUI 原始碼
│  ├─ flashdb.py                   支援晶片表、JESD216H SFDP 解析
│  ├─ build_exe.bat                打包成免安裝 .exe
│  └─ dist/K1V2SPI_Programmer.exe
├─ tests/ *                        pytest（HEX 解析、SFDP 解析、模擬韌體通訊）
├─ tools/ *                        py.cmd / py.sh、make_wiring_diagram.py、md2html.py
├─ docs/                           HARDWARE / PROTOCOL / USER_GUIDE / SFDP_MAPPING（.md 與 .html）、接線圖
└─ setup_env.bat / setup_env.sh    建立 Python 環境
```

\* `BD/`、`Datasheet/`、`tests/`、`tools/` 不在本公開 repo 內（已加入 `.gitignore`），放在 private repo `khsu-tw/K12SPI_Programmer_Private`。需要建置、測試或重新產生文件時，把它們複製到本目錄同一層。

**文件規則**：README、`docs/` 下的文件與 ChangeHistory 都以 `.md` 為原始檔，每次修改後產生同名 `.html` 作為正式紀錄：
`tools\py.cmd tools\md2html.py`。請改 `.md`，不要直接改 `.html`（會被覆蓋）。

## 快速開始

1. **只要用 GUI**：直接執行 `gui\dist\K1V2SPI_Programmer.exe`（免安裝，不需要 Python）。
2. **燒韌體到 Nano**（第一次使用）：USB-C 接上 Nano，執行
   `firmware\flash_nano.bat`（PIC18F16Q20-CNANO）
   （以 MPLAB X v6.30 的 IPE 經板載 nEDBG 燒錄，並回讀比對；最後一行 `Programmed and verified` 才算成功。
   需要先安裝 MPLAB X；沒有時可加 `--dragdrop` 改用拖放，但大檔可能被截斷，見 ChangeHistory v5.0.1）。
3. 依 [docs/HARDWARE.md](docs/HARDWARE.md) 接線，先**不放 flash**測通訊，再照 USER_GUIDE 的順序測試。

### 開發（VS Code）

- `setup_env.bat` 建立 Python 環境（在 OneDrive 時建在 `%LOCALAPPDATA%\MX25S1633F_Programmer\venv`，可用 `MX25_VENV` 覆寫）。
- Task：**Setup**、**FW: Build PIC18F16Q20-CNANO (XC8)**、**FW: Flash …**、
  **GUI: Run**、**GUI: Build Windows EXE**、**Test**。
  編譯需 MPLAB XC8 ≥ 3.x，加上 PIC18F-Q_DFP（`DFP_18FQ`），路徑可用環境變數覆寫。
- 命令列：`tools\py.cmd gui\mx25s1633_gui.py`、`tools\py.cmd -m pytest tests`。
- GUI 與其他序列埠程式**不能同時開同一個 COM 埠**。

## 重要警告

- MX25S1633F 的 **VCC 只能 1.14–1.6V**。flash 的任何一腳都不可以接到 3.3V。
- TXS0108E 規定 **VCCA ≤ VCCB**：**VCCA = 1.2V（接 flash）、VCCB = 3.3V（Nano 的 VTG）**，**OE 接 VCCA**。
