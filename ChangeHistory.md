# ChangeHistory

版本控管用的變更紀錄（依 PRD.md / PIC18F16Q20_PRD.md / PIC16F13145-CNANO.md 產生）。最新的在最上面。**每個版本標題都要寫修改日期，格式 `yyyy/mm/dd`**（`## vX.Y.Z — yyyy/mm/dd　說明`）。

## v5.1.5 — 2026/10/21　新增 LSF0108 + SOIC-8 flash 接線圖

- 新增 `docs/wiring_PIC18F16Q20-CNANO_LSF0108_SPIFlash_SOIC8.(png|svg)`，由 `tools/make_wiring_diagram_lsf0108.py` 產生；原 TXS0108E 圖保留不動。
- 上拉電阻**依 PIC18F16Q20 的 IOL ≤ 10 mA 設計**（DS40002387 D360）：B 側（3.3 V）**750 Ω**、A 側（1.2 V）**240 Ω**、MISO 的 A 側 **1 kΩ**。
  MCU 腳位拉低時灌電流 3.3/750 + 1.2/240 = 4.4 + 5.0 = **9.4 mA**（VOL = 0 V，最壞）。
  先前以 LSF0108 資料手冊 15 mA 設定（Eq. 3，B 220 Ω / A 68 Ω）算出 MCU 要灌約 29 mA，超出 IOL，已改掉；15 mA 設定只留在圖上當比較。
- 圖中同時畫出 EN 偏壓（EN 接 Vref_B、200 kΩ 接 VTG、0.1 µF）、VSENSE 與 SOIC-8 腳位。
- `docs/HARDWARE.md` 新增「LSF0108 + SOIC-8」一節（LSF0108 與 TXS0108E 的差異、上拉算式、灌電流與 flash VIL 提醒）。
- 風險：**未實機驗證**；MCU 在 10 mA 時只保證 VOL ≤ 0.6 V，高於 flash 的 VIL（0.24~0.36 V），請以示波器確認 A 側低電位。

## v5.1.4 — 2026/10/20　W25Q32NE 有資料手冊；顯示版本；獨立的支援清單；W25Q64NE 不支援

- `DOC/` 放入 W25Q32NE（RevE）與 W25Q64NE 資料手冊。W25Q32NE 改為有資料手冊根據：Chip Erase 最大 70 s（原借用 W25Q65NE 的 140 s），
  不再顯示「無資料手冊」警告。
- **W25Q64NE 不支援**（使用者決定）：它與 W25Q65NE 的 ID 同為 `EF 65 17`、同為 64Mbit，SFDP 也無法區分，只保留 W25Q65NE。
  插入 W25Q64NE 會被辨識為 W25Q65NE（其 Chip Erase 最大 160 s、tRES1 50 µs、fR 33 MHz 與 W25Q65NE 不同）。
- GUI v5.1：視窗上方新增版本列 `Programmer GUI v5.1 | Bridge: <板名> firmware <版本>`；Log 於啟動與連線時各記錄一次
  （啟動時韌體為 not connected，連線後由 `INFO` 取得）。
- GUI：新增獨立的「Supported SPI Flash」清單（廠牌/型號/ID/容量/VCC），啟動即列出，Auto Detect 命中的晶片反白；啟動 Log 也列出清單。
- 韌體 5.1.1：Sector Erase 逾時 1000 ms → 2000 ms。W25Q32NE 在 IoT 模式下 tSE 最大值為 1000 ms，原設定沒有餘裕。
- 18F16Q20 板已用 IPE 燒錄 5.1.1 並回讀驗證（7139 bytes，0 mismatches）；實機 GUI：版本列 `Bridge: PIC18F16Q20-CNANO firmware 5.1.1`，
  `Winbond W25Q32NE EF 65 16 4096 KB`，清單該列反白，無警告。16F13145 僅編譯（48.6%），未上板。
- **需要重新燒錄 Nano 韌體**：`firmwarelash_nano.bat 18f16q20`。

## v5.1.3 — 2026/10/20　韌體 5.1.0：Deep Power-Down 喚醒；MX25S1633F Chip Erase 等待改為 57 s

- 韌體 5.1.0：新增 `RDP` 指令（ABh + 50 µs + 一次 RDSR），開機時也自動送一次。50 µs 大於三份資料手冊的喚醒時間
  （MX25S1633F tRDP 45 µs、GD25UF16E / W25Q65NE tRES1 20 µs）。晶片沒在省電模式時 ABh 無影響。
- GUI：Auto Detect 讀 ID 前先送 `RDP`；舊韌體回 `ERR:cmd` 時略過。
- **實機發現**（PIC18F16Q20-CNANO + W25Q32NE）：MCU 重置後，ABh 之後的**第一筆** SPI 傳輸讀到 `00 00 00`，第二筆起正常。
  未送 ABh 時也觀察到重置後第一次 `ID` 偶爾為 `00 00 00`。原因未查明（推測與 TXS0108E 上電後第一次方向切換或 MCU 腳位初始化有關），
  處理方式是 ABh 之後先做一次 RDSR 吸收。修改後以 IPE 重置 MCU 五次、五種指令順序，第一次 `ID` 全部為 `EF 65 16`。
- MX25S1633F `chip_erase_s` 38 s → 57 s（MX25S1633FM2IG2 出廠為 Ultra Low Power 模式，tCE 最大 57 s）。
- 18F16Q20 板已用 IPE 燒錄 5.1.0 並回讀驗證（7139 bytes，0 mismatches），實機 Auto Detect：`Winbond W25Q32NE`、4096 KB、無 blocker。
  16F13145 僅編譯（48.6%），未上板。pytest 52 項通過（模擬器加入 Deep Power-Down 行為）。
- **需要重新燒錄 Nano 韌體**：`firmware\flash_nano.bat 18f16q20`。

## v5.1.2 — 2026/10/20　燒錄必要參數與 SFDP 欄位對照表

- 新增 `docs/SFDP_MAPPING.md`（與 `.html`）：列出燒錄程式必要的參數（辨識、容量、寫入、抹除、狀態輪詢、保護、電壓、時脈、重置），
  每項對應 JESD216H 的欄位（DWORD/位元與章節），並列出 MX25S1633F / GD25UF16E / W25Q65NE 的資料手冊值與程式目前的來源。
- 結論：SFDP 能提供容量、位址模式、頁大小、擦除類型與時間、忙碌輪詢、QE、軟體重置；
  **JEDEC ID、Page Program / Read / Chip Erase 指令、WRSR 時間、03h 最高時脈、SR 保護位元、OTP 位元、VCC 電壓都不在 SFDP 內**，必須靠資料手冊。
- 用實機 MX25S1633F 的 SFDP 原始值逐欄核對（DW1/2/8/9/10/11/14/15/16），並列出 W25Q32NE 的原始值。
- 從對照表發現的待辦（尚未修改程式）：
  - 韌體沒有送 ABh（Release from Deep Power-Down）；三顆都支援，晶片若在省電模式 ID 會讀不到。
  - MX25S1633FM2IG2 出廠預設 Ultra Low Power 模式，tCE 最大 57 s；`chip_erase_s` 目前 38 s，GUI 等待 58 s 只剛好夠。

## v5.1.1 — 2026/10/20　文件更新、HTML 版文件

- `docs/USER_GUIDE.md` 更新過時內容：
  - Read ID 加入 W25Q32NE（`EF 65 16`）；Read SR / Config SR 說明位元名稱依晶片切換、GD25UF16E / Winbond 顯示 SR2。
  - Chip Erase 容量依偵測結果（2 / 4 / 8 MB），不再寫死 2MB；「Chip Erase first」條件改為「超過晶片容量一半」，列出各晶片逾時。
  - Status Register 表改為三家對照（MX25S1633F：SRWD/QE/BP3–0；GD25UF16E：SRP0/BP4–0；Winbond：SRP/SEC/TB/BP2–0），
    補 SR2 位元、CMP 反轉保護、SRP1 / SRL 電源鎖定的解除方式、LB OTP 警告。依各資料手冊核對（SR1/SR2 位元表、SRP 表、Chip Erase 保護說明）。
  - 移除不存在的 `DATASHEET_NOTES.md` 連結，改指向 `DOC/` 資料手冊；「SPI 先選 1MHz」改為 GUI 實際有的「Slow」。
  - 疑難排解新增 `not in the supported list`、`SFDP density ... does not match`、`ERR:vio` 三種訊息的處理方式。
- 新增 `tools/md2html.py`（不需第三方套件）：把 `docs/*.md` 與 `ChangeHistory.md` 轉成同目錄的 `.html`，含頁面間導覽列。
  修改 `.md` 後執行 `tools\py.cmd tools\md2html.py` 重新產生。
- `ChangeHistory.md` 修正 3 個控制字元：v3.1.x 兩處 `firmware\flash_nano.bat` 的 `\f` 被存成換頁字元（顯示成 `firmwarelash_nano.bat`），
  v4.0.0 一處 `\b`、`\f` 被存成退格/換頁字元。

## v5.1.0 — 2026/10/20　未列入支援的 ID：依 SFDP 欄位定義顯示 SPI flash

- 使用者要求：JEDEC ID 不在支援清單時，依 JESD216H 的 SFDP 欄位定義顯示該 SPI flash。
- `gui/flashdb.py` 新增 `describe_sfdp()` / `generic_name()`，並擴充 `parse_sfdp()`：
  - 6.2 SFDP 標頭：JESD216 版本、參數表頭數、Access Protocol。
  - 6.3 參數表頭：每個表的名稱（依 6.4–6.20 指派的 ID：FF00h Basic、FF81h Sector Map、FF84h 4-byte Address、
    FF87h SCCR Map、FF05h/FF06h xSPI…）、版本、DWORD 數、位址。6.3.3：ID LSB 為奇同位 = JEP106 廠商碼 → 顯示「Vendor table (廠商)」。
  - 6.4 Basic Flash Parameter Table：密度（DWORD2，含 2^N 編碼）、位址位元組數與 Fast Read 模式（DWORD1/5：1-1-2、1-2-2、1-1-4、1-4-4、
    2-2-2、4-4-4、DTR）、Erase Type 1–4 大小/指令（DWORD8/9）及其典型時間（DWORD10，依類型編號對應，缺號的類型不會錯位）、
    頁大小 / 頁寫入典型時間 / Chip Erase 典型時間與最大倍率（DWORD10/11）。
  - 名稱格式：`<JEP106 廠商> SPI-NOR <容量> (ID xx xx xx)`；只有支援的三家廠商是確定的，其他廠商標註「(JEP106)」表示查表得出。
- GUI：Auto Detect 遇到未列入的 ID 時，在 Log 逐行列出上述欄位，晶片標籤顯示橘色「SFDP only - not supported, read-only」，
  Length 設為 SFDP 容量（上限 16 MB，因為 3-byte 位址）。**Program / Erase / Config SR 一律停用**，Hex Dump 與 Read→File 可用。
- 實機 SFDP 解碼核對（測試寫的是實際輸出）：
  - MX25S1633F：rev 1.6，3 個表（Basic、Macronix 廠商表 FFC2h、4-byte Address FF84h），4K/32K/64K 典型 30/160/288 ms，Chip Erase 典型 5.1 s。
  - W25Q32NE：rev 1.10，Basic（23 DWORDs），4K/32K/64K 典型 48/16/160 ms，Chip Erase 典型 20 s，支援 4-4-4 與 DTR。
    注意 32K 典型 16 ms 比 4K 的 48 ms 還短，這是晶片 SFDP 本身的值（DWORD10 = 00A50226h），照實顯示。
- pytest 49 項通過。

## v5.0.1 — 2026/10/20　5.0.0 燒錄後無回應：拖放燒錄截斷 HEX；W25Q65NE 實際 ID；VIO 換算

- **現象**：燒入 5.0.0 後 GUI `[FAIL] timeout (no response)`，連 `PING` 都沒回應；4.0.0 正常。
- **原因（已用 MPLAB IPE 回讀確認）**：PIC18F16Q20-CNANO 的拖放燒錄（debugger fw 01.22.0059）在 HEX 檔案位移 18402 處停止寫入：
  程式記憶體 0x1998 以上（含 UART/中斷用的程式與 CRC 表）與**全部 Config bits** 都是空白（FFh），STATUS.TXT 仍顯示 `Ready.`、沒有 FAIL.TXT。
  4.0.0 的 HEX 只有 16772 bytes，沒超過這個長度，所以一直正常。韌體程式本身沒有問題。
  二分法時看到的「`vio_check` 初值不同就會掛」只是巧合：該版 HEX 的長度剛好跨過截斷點，後來重複燒同一個版本也會失敗。
- **修正**：`firmware\flash_nano.bat` 改用 MPLAB IPE `ipecmd -TPnEDBG` 燒錄，每次呼叫都加 `-OL`（否則 IPE 讓 MCU 停在 reset，看起來也像沒回應），
  燒完再用 `-GF` 回讀，以 `firmware\verify_hex.py` 逐位元組比對（含 config）。拖放改為 `--dragdrop` 選項，並標示「未驗證」。
  實測：18F16Q20 燒 5.0.0 → `verify: 7051 bytes checked, 0 mismatches` → `PING`/`INFO 5.0.0`/`ID`/`VIO` 全部正常。
- **以 W25Q65NESSIG 名義取得的晶片實為 32 Mbit**（更正本版稍早「`EF 65 16` = W25Q65NE」的錯誤推論）：
  - 9Fh 連讀三次皆為 `EF 65 16`；容量碼 `16h` = 2^22 bytes = 4 MB。W25Q65NE（64 Mbit）應為 `17h`。
  - SFDP（JESD216 rev 1.10，1 個參數表頭）密度 = 32 Mbit，與 ID 一致。
  - 唯讀繞回測試：0x000000/0x100000/0x200000 與 +0x400000 的 4 KB 內容皆相同 → 位址在 4 MB 處繞回。
    **限制**：這三塊都是空白（全 FFh），所以「相同」不能單獨證明繞回；結論主要依據 ID 與 SFDP 兩個獨立來源一致。
    要確切證明需在 0x000000 寫入資料再讀 0x400000，屬寫入操作，未執行。
  - 處理：`gui/flashdb.py` 新增獨立項目 `EF 65 16` = 4 MB，標記 `datasheet=False`，每次偵測都在 Log 警告
    「no datasheet; capacity from SFDP, SR bits / erase time borrowed from W25Q65NE」。Status Register 位元與 Chip Erase 時間
    沿用 W25Q65NE，**無資料手冊根據**。W25Q65NE（`EF 65 17`，8 MB）維持不變；兩者 SFDP 密度不符時互相擋下。
  - 實機 SFDP 已存為測試資料 `EF6516_SFDP_REAL`。pytest 45 項通過。
  - **頂面印字為 `25Q32NESIG` → 確認為 Winbond W25Q32NE（32 Mbit）**，是收到的料號錯了（不是 W25Q65NESSIG），
    晶片本身正常：ID、SFDP、印字三者一致。項目名稱改為 `W25Q32NE`。
    `DOC/` 沒有 W25Q32NE 資料手冊，仍維持 `datasheet=False` 與警告；要正式支援請把資料手冊放進 `DOC/`，
    我再核對 Status Register 與 tCE。
- **VIO 換算**：ADC 實為 10-bit（外加上拉的浮接腳讀 `07FE` ≈ 1023×2），所以 1 count = 2 mV，不是 0.5 mV。改為 `sum >> 1`。
  舊的換算會把 1.2 V 讀成 0.3 V，接上 VSENSE 時會誤擋燒錄（浮接判斷不受影響）。
- **SFDP 實機驗證**：MX25S1633F 實際 SFDP（JESD216 rev 1.6，3 個參數表頭，16 Mbit，3-byte 位址，256 B 頁，4K/32K/64K 擦除）
  解析正確，已存成測試資料 `MX25S1633F_SFDP_REAL`。pytest 44 項通過。
- **仍未實機驗證**：GD25UF16E 與 W25Q65NE 的 SFDP（本次插座上是 MX25S1633F）；VSENSE 接 1.2 V 時的讀值（本次 RA1 浮接，讀 0 / 2046 mV）；
  16F13145 板的 IPE 燒錄流程。

## v5.0.0 — 2026/10/19　支援 GD25UF16E / W25Q65NE，Auto Detect（JEDEC ID + SFDP），1.2 V 電壓互鎖

依 `DOC/DS-01151-GD25UF16E-Rev1.0.pdf`、`DOC/W25Q65NE_DTR RevD 05052026.pdf`、`DOC/MX25S1633FVer13_Microchip.pdf`、
`DOC/JESD216H.pdf`。

- 支援晶片：MX25S1633F（`C2 2B 25`，2 MB）、GD25UF16E（`C8 83 15`，2 MB）、W25Q65NE（`EF 65 17`，8 MB）。
  三者都是 3 位元組位址、256 位元組頁、4 KB/32 KB/64 KB 擦除（20h/52h/D8h）、Chip Erase 60h，可共用同一套指令。
- **Auto Detect**（新按鈕，Connect 時自動執行）：量電壓 → `9Fh` JEDEC ID → `5Ah` SFDP（JESD216H 6.2 標頭、6.4 Basic Flash
  Parameter Table：位址模式、4 KB 擦除、密度、Erase Type 1–4、頁大小）。ID 對應表在 `gui/flashdb.py`。
  以下任一不成立就鎖定 Program/Erase/Config SR：ID 不在支援表、SFDP 讀不到/簽章不是 `SFDP`、SFDP 密度與資料手冊不符、
  只支援 4 位元組位址、頁大小不是 256、SFDP 沒宣告 20h 4 KB 擦除。
- 依偵測結果調整：Flash 容量（Length 預設、檔案大小檢查、Read->File 範圍）、擦除計畫（只用 SFDP 宣告的區塊大小）、
  Chip Erase 逾時（MX 38 s / GD 50 s / W25 140 s，取資料手冊最大值）、Status Register 位元表（三家定義不同）。
- GD25UF16E / W25Q65NE 有 SR2：新增 `RDSR2`（35h）；`WRSR xx [yy]` 可附第二個位元組。GD25UF16E 只寫 1 位元組會把 SR2 可寫位元
  清 0，所以 Config SR 會把目前的 SR2 原值一併寫回。
- **最高優先權：1.2 V 互鎖**。JESD216H 沒有電壓欄位，SFDP 無法得知 IO 電壓，所以新增 **VSENSE（RA1，兩板相同）** 選配接線，
  韌體以 FVR 2.048 V 為參考的 ADC 量測 1.2 V 軌。窗口 1.14–1.26 V（三顆晶片的交集）。韌體 `VCHK` 預設為 1（上電即鎖），
  窗口外時 PP/PW/SE/B32/BE/CE/WRSR 一律 `ERR:vio`；GUI 的 `guard()` 在每次 Program/Erase/Config SR 前再量一次。
  沒接 VSENSE：以弱上拉前後讀值差判斷腳位浮接，改用 ID+SFDP 並顯示警告（或勾選「Ignore VSENSE」）。
- 韌體 5.0.0：位址上限由 2 MB 放寬為 24 位元（16 MB）；`LINK` 不再限定廠商碼 C2；`INFO` 改回 `SPINOR-BRIDGE`；新增指令
  `SFDP`、`VIO`、`VCHK`、`RDSR2`。編譯：16F13145 Program 48.1%、Data 62.4%；18F16Q20 Program 10.8%、Data 15.5%。
- 測試：pytest 42 項通過（模擬器加入 SFDP/VIO/VCHK；三顆晶片的 SFDP 影像、電壓窗口邊界與窗口外、浮接 VSENSE、無晶片、未知晶片、
  SFDP 簽章錯誤、密度 2^N 編碼、64 Mbit 完整燒錄/驗證）。
- **未經實機驗證，重要**：
  1. 目前沒有接上 Nano 與這三顆晶片；SFDP 解析以 JESD216H 的位元定義實作，測試用的 SFDP 影像是**依標準自行構造**，
     不是真實晶片傾印。三家資料手冊都沒有公開 SFDP 內容（MX 與 GD 註明需向原廠索取 Application Note；W25Q65NE 參照 Winbond SFDP Definition Table），
     第一次上板請確認 Log 的 `SFDP:` 行（密度、頁大小、擦除大小）符合預期。
  2. GD25UF16E 的 JEDEC ID 第三位元組 `15` 與 W25Q65NE 的 `EF 65 17` 取自資料手冊（W25Q65NE 表格寫 `6517`）。
  3. VSENSE 的 ADC 設定（`ADPCH=0x01`=ANA1、`ADREF=0x03`=FVR 正參考、`ADCON0=0x94`、`FVRCON=0x82`）依 ADC² 暫存器結構寫成，
     **通道編號與 ADREF 編碼 DFP 標頭檔沒有列出，也無法連網查資料手冊，未對照資料手冊確認**。請上板用 `VIO` 指令對照電表驗證：
     接 1.2 V 應讀約 `04B0`（1200）；若數值不對，優先檢查這四個常數。韌體預設互鎖為開，若量測不準會**誤擋**燒錄（安全方向），
     可暫時勾選「Ignore VSENSE」。
  4. W25Q65NE 為 8 MB，現行速度下整顆讀寫/驗證耗時約為 2 MB 的 4 倍。

## v4.0.0 — 2026/10/07　新增 PIC16F13145-CNANO 支援（與 PIC18F16Q20-CNANO 共用接線）

- 依 `PIC16F13145-CNANO.md` 建立新專案 `PIC16F_MX25S_Prog`（由 `PIC18F_MX25S_Prog` v3.1.4 複製；原專案已另存
  `PIC18F_MX25S_Prog_backup_20261006.zip`）。
- 韌體：同一份 `firmware/src/main.c`，依編譯晶片（`-mcpu=16F13145` / `-mcpu=18F16Q20`）選板。
  - **接腳設計為同一組邊緣排針**，TXS0108E/flash 接線兩板共用：
    CS#=SPI SS（16F13145 RB5 / Q20 RA4）、MISO=SPI MISO（RC7 / RC6）、WP#=右排第 7 孔（RA4 / RB7）、
    MOSI=SPI MOSI（RC6 / RC3）、SCLK=SPI SCK（RB7 / RA5）、RESET#=I2C SDA（RB4 / RC1）。
  - 16F13145：EUSART1（RC4 TX / RC5 RX，PPS）、HFINTOSC 32 MHz、SP1BRG=15（BRG16+BRGH）→ 500 kbps；中斷式 RX 環形緩衝。
  - 16F13145 只有 1 KB RAM：CRC-32 改為 16 項 nibble 表（放在程式記憶體），不再使用 1 KB 的 byte 表。
  - `INFO` 回 `OK <板名> MX25S1633F-BRIDGE 4.0.0`。
- 編譯結果：16F13145 Program 40.3%（3305/8192 words）、Data 61.8%（633/1024 bytes）；18F16Q20 Program 9.1%、Data 15.3%。
- `build.bat [16f13145|18f16q20|all]` 產生 `mx25_bridge_pic16f13145.hex` / `mx25_bridge_pic18f16q20.hex`；
  `flash_nano.bat [16f13145|18f16q20]`。VS Code tasks 同步更新（並修正 tasks.json 中 `\b`、`\f` 被當成控制字元的路徑）。
- GUI v4.0：標題、Log、Port 偵測文字改為兩板通用（通訊協定不變）；EXE 更名 `PIC16F_MX25S1633F_Programmer.exe`。
- 接線圖改為 `wiring_CNANO_TXS0108E_MX25S1633F.(png|svg)`，同時標示兩板腳位；HARDWARE/PROTOCOL/USER_GUIDE/README 更新。
- 測試：pytest 16 項通過（兩個 HEX 皆可解析）。
- **未經實機驗證**：目前沒有接上 Nano，16F13145 的韌體僅通過編譯；請依 USER_GUIDE「第一次使用的建議順序」上板確認
  （PING/INFO → 不放 flash 時 ID 應為 FF FF FF → 放入 flash 後 ID = C2 2B 25），特別是 500 kbps 鮑率與時脈 32 MHz。
- 已知限制：16F13145 時脈 32 MHz（Q20 為 64 MHz），bit-bang SPI 最高速度較慢；WP#/SLEW 腳位 RA4 在 16F13145 是晶振共用腳（預設直連邊緣排針，可用）。

## v3.1.4 — 2026/10/06　Read->File 只讀 1KB

- 原因：Read->File 讀取 Length 欄位的長度，預設 `100`（hex，256 位元組）；使用者未改長度。
- 修正：Length 預設改為 `200000`（整顆 2MB），載入檔案時**不**更動；Read->File 開始時在 Log 顯示實際讀取的位址與長度。
- Hex Dump 仍限制最多 4KB。
- 使用者要求：讀取長度一律以整個 FLASH 為預設。

## v3.1.3 — 2026/10/06　SPI clock = Max 時 ID 讀成 FF FF FF

- 實機掃描（LINK 100 次 RDID）：
  - Pin drive = Fast edge：Max → 0/100（讀到 FF）；其餘各檔也不穩（2~86/100）。
  - Pin drive = Slow edge：Max 94/100、Fast 99/100、Normal 以下全部 100/100。
- 原因：Max 沒有任何延遲且邊緣極快；TXS0108E 的 one-shot 加速電路遇到過快/過度振鈴的邊緣會誤動作，造成 MISO/SCLK 失真。
- 修正（GUI）：預設 Pin drive = **Slow edge**、SPI clock = **Normal**；Link Test 先掃 Slow edge，找到穩定設定即套用「比最快穩定檔慢一級」以保留餘裕。韌體不需更動。
- 建議：長杜邦線或面包板請維持 Slow edge；需要更快再用 Link Test 驗證。

## v3.1.2 — 2026/10/06　GUI 找不到 Nano 串口

- 現象：啟動後 log 只有 Ready/HW 兩行，沒有 `Bridge alive.`（沒有連線）。
- 原因：Windows 把 Nano 的 CDC 顯示為「USB Serial Device (COMxx)」（VID 03EB），不含 "Curiosity"，自動選擇沒命中。
- 修正：以 USB VID 0x03EB（Microchip）辨識 Nano；若只有一個 Microchip 串口，啟動後自動連線。
- 已用實機確認 COM14 可通訊，`INFO` 回 `... BRIDGE 3.1.1`（韌體 3.1.1 已成功燒入）。
- 觀察：該次 `ID` 回 `FF FF FF`，表示 flash 當下沒有回應（未接線/1.2V 未供電/OE 未接），需檢查硬體。

## v3.1.1 — 2026/10/06　修正 PW 寫入 timeout（UART 接收溢位）

- 現象：Program 抹除完成後第一個頁寫入即 `[FAIL] timeout (no response)`。
- 原因：`PW` 的 256 位元組資料緊接在指令行之後送出；UART 硬體接收 FIFO 很淺，MCU 解析指令行、呼叫 `cmd_pw` 期間資料被丟掉，MCU 等不到足量位元組而不回應。
- 修正（韌體 3.1.1）：UART 接收改為中斷驅動的 256 位元組環形緩衝（`MVECEN=OFF`，單一中斷向量 0x0008）；緩衝滿時設 `ERR:ovf` 旗標。
  `build.bat` 加 `-Wno-2019` 隱藏無害的低優先權向量警告。
- 編譯：Program 5916/65536 bytes (9.0%)，Data 1649/4096 bytes (40.3%)。
- **需重新燒錄 Nano 韌體**（`firmware\flash_nano.bat`）。
- 註：GUI 端沒有改動；若仍 timeout，請在 Raw Monitor 貼出最後幾行。

## v3.1.0 — 2026/10/06　提升燒錄/驗證速度、百分比進度、燒錄成功/失敗計數

**需求**：提升燒錄和驗證速度；進度以百分比顯示；能記錄燒錄成功及失敗次數。

### 速度（韌體 3.1.0 + GUI 3.1）
- 抹除：自動改用 64KB（`BE`，D8h）/ 32KB（`B32`，52h）區塊抹除，其餘才用 4KB；可選「超過 1MB 先 Chip Erase」。
- 寫入：新增 `PW`（無 RDY 握手的流水線頁寫入）與 `SYNC`；傳下一頁的同時 flash 正在寫上一頁。全 0xFF 頁略過。
- `flash_wait` 由每 1 ms 輪詢改為每 50 µs，頁寫入完成即繼續。
- 驗證：改為每 64KB 比對板上 CRC（不搬資料回 PC），不符時才讀回定位第一個不同位元組。
- 韌體新增 UART 接收溢位偵測（`ERR:ovf`），GUI 自動重送該頁最多 3 次。
- Program 完成後進度不再卡在「等待」：抹除/寫入/驗證依資料手冊時間加權合成單一 0~100%。

### 進度與計數（GUI）
- 進度條旁顯示 **0~100%**；狀態列顯示目前階段（ERASING / WRITING / VERIFYING）及其百分比。Read->File、Double-check 也改為百分比並以 64KB 分段比對。
- 新增 **OK / FAIL / Total 計數**，存在 `%APPDATA%\MX25S1633F_Programmer\stats.json`（關閉程式後保留）；
  每次燒錄另追加 `program_history.csv`（時間、結果、檔名、CRC32、秒數、失敗原因）。按鈕：Reset count、Open history。
  只有「Program」動作計入；使用者按 Stop 不算失敗。
- Stop 後改為等傳輸線靜止才清除殘留回應，避免下一個指令讀到舊資料。

### 測試
- pytest 由 9 增至 15 項：流水線寫入、區塊抹除、抹除規劃、計數持久化、Program 成功/失敗路徑（含故意損毀一頁驗證會失敗且計入 FAIL）。全數通過。
- 韌體編譯 0 warning：Program 5780/65536 bytes (8.8%)，Data 1389/4096 bytes (33.9%)。

### 注意
- **尚未在實體硬體上測試**；請重新燒錄 Nano 韌體（`firmware\flash_nano.bat`）並改用新的 exe。實際加速幅度需實測。
- 寫入瓶頸是 flash 本身的頁寫入時間（約 4.6 ms/頁，2MB ≈ 10 s 以上）與 USB-UART 500 kbps（2MB ≈ 40 s），無法再低於此；驗證時間取決於 MCU bit-bang SPI 速度。
- 舊版 HEX 不支援 `PW`/`B32`/`BE`，新 GUI 必須搭配 3.1.0 韌體。

## v3.0.1 — 2026/10/06　驗證/讀取速度改善

- 問題：Program 完成後的驗證（`CRC`）與 Read 很慢，整段 ~1.9MB 需讀遍 flash。
- 韌體 3.0.1：`SPEED 0` 時 SPI 走展開的無延遲快速路徑；CRC-32 改為查表（開機建立 1KB 表，Data 33.7%）；預設 SPEED=0。
- GUI：預設 SPI clock 改為 Max（Link Test 仍會驗證穩定度）；CRC 逾時依長度計算（10 s + 300 µs/byte）。
- **需重新燒錄 Nano 韌體**（`firmware\flash_nano.bat`）並使用新的 exe。
- 新 HEX 與 exe 的雜湊以實際檔案為準（`sha256sum`）。

## v3.0.0 — 2026/10/06　開發板更換為 PIC18F16Q20-CNANO、重建 GUI 與 .exe

**來源需求（PIC18F16Q20_PRD.md）**
1. 開發板改為 PIC18F16Q20-CNANO（`DOC/PIC18F16Q20-CNANO-UserGuide-DS50003588.pdf`）。
2. 重新產生硬體接線圖、燒錄程式。
3. 移除 ESP32-C3 相關程式碼及文件。
4. 仍需 GUI 燒錄程式操作 MX25S1633F，並打包成免安裝 Windows .exe（介面參照 PRD 內截圖）。
5. 畫 PIC18F16Q20 ↔ TXS0108E ↔ MX25S1633F 接線圖。

**依據文件**：PIC18F16Q20 Curiosity Nano User Guide（Pinout、Table 3-2、4.1 MVIO、4.2 LED）、MX25S1633F datasheet Rev.1.3、
PIC18F-Q_DFP 1.28.451（暫存器、PPS 值 TX1=0x13）、XC8 3.10。

### 新增
- `firmware/src/main.c`：PIC18F16Q20 韌體（XC8，64 MHz HFINTOSC，UART1 500000 bps，bit-bang SPI Mode 0）。
  - 腳位：CS#=RA4、SCLK=RA5、MOSI=RC3、MISO=RC6、WP#=RB7、RESET#=RC1、LED0=RC7（低亮）、UART RC4/RC5。
  - **不使用 RB5/RB6**（VDDIO3 域，板上固定 1.2V，只能做 I2C/I3C）。
  - 新指令：`LINK n`（Link Test）、`CRC addr len`（板上 CRC-32）、`SLEW 0|1`（Pin drive）、`LED 0|1`。
  - `PP` 先收整頁到緩衝再寫 flash，避免慢速 SPI 時 UART 溢位。
  - 編譯結果（0 warning）：Program 4620/65536 bytes (7.0%)，Data 357/4096 bytes (8.7%)。
- `firmware/prebuilt/mx25_bridge_pic18f16q20.hex`（13106 bytes，SHA-256 `19d8e9505676d1ae14e33a461a64218e3bbbbcc839b2e6feab55e428ca90ecd6`）。
- `gui/mx25s1633_gui.py`、`gui/hexfile.py`：Tkinter GUI（版面依截圖：Port/Connect/Raw Monitor、SPI clock、Pin drive、WP# High、
  Load File、Read ID / Read SR / Config SR / Link Test / Hex Dump / Reset / Sector Erase / Chip Erase / Program / Verify / Read->File / Stop、
  Verify after program、Double-check Read->File、狀態列與進度條、Log）。自動尋找 *Curiosity Virtual COM Port*。
- `gui/dist/MX25S1633F_Programmer.exe`：PyInstaller 單檔免安裝 exe（12,623,827 bytes，SHA-256 `66fc8e9e73908d0afce42a742d33a8792c8549c0c197c95afbc55d5699172ed9`）。
- `docs/wiring_PIC18F16Q20_TXS0108E_MX25S1633F.png/.svg`：接線圖；`tools/make_wiring_diagram.py` 可重新產生。
- `tests/test_hexfile.py`、`tests/test_bridge_sim.py`：9 個 pytest（HEX 解析、以模擬韌體驗證 GUI 通訊/燒錄/CRC）全數通過。
- `setup_env.bat/.sh`、`requirements.txt`、`gui/requirements-dev.txt`（pyserial、pyinstaller、pytest、pillow）。

### 變更
- `firmware/build.bat`、`firmware/flash_nano.bat`、`.vscode/tasks.json`：改為 PIC18F16Q20 目標與 HEX 檔名。
- `docs/HARDWARE.md`、`docs/PROTOCOL.md`、`docs/USER_GUIDE.md`、`README.md`：全面改寫（PIC18F16Q20、新指令、Link Test、exe 流程）。
- SPEED 參數改為韌體延遲值 0~3F（GUI 以 Max/Fast/Normal/Slow/Slower/Slowest 對應），不再是 MHz。

### 移除
- 所有 ESP32-C3 / PlatformIO / esptool 相關檔案與說明（`tools/pio.*`、`PATCH_README.txt`、v1.1.3 patch zip、`CHANGELOG.md`，其內容併入本檔的歷史區）。
- 上一版 PIC16F13145 的韌體、HEX 與接線文件（PRD 已改用 PIC18F16Q20；需要時可由 git 歷史或本檔重建，腳位見下方 v2.0.0 紀錄）。

### 尚未完成／需注意
- **尚未在實體硬體上測試**：韌體只做過編譯驗證，GUI 只對模擬韌體與啟動測試過。請先不接 flash 測 `Bridge alive.`，再接 flash 用 Link Test。
- 專案目前**不是 git repository**（本機無 .git）；建議 `git init` 後把本檔當作 commit 依據。
- PRD 第 2 行文字寫「更換為 PIC16F13145-CNANO」，標題與檔名為 PIC18F16Q20，本次以 **PIC18F16Q20** 為準。
- 預設不使用 Nano 板上的 1.2V（VDDIO3，MCP1711），flash 的 1.2V 需外接電源。
- 單檔 exe 可能被部分防毒軟體誤判；可改用 `tools\py.cmd gui\mx25s1633_gui.py`。
- Chip Erase 等待上限 60 s（datasheet 典型 38 s）。

---

## 歷史紀錄

## v2.0.0 — 2026/10/06　開發板更換為 PIC16F13145-CNANO（已被 v3.0.0 取代）

**來源需求（PRD.md）**
- 開發板（Hardware Board）：PIC16F13145-CNANO，資料手冊 `DOC\PIC16F13145-CNANO-UserGuide-DS50003649.pdf`。
- 重新產生硬體接線圖、燒錄程式。

**依據文件**：PIC16F13145 Curiosity Nano User Guide（Pinout、Table 3-2、4.2/4.3 節）、MX25S1633F datasheet Rev.1.3、
PIC16F1xxxx_DFP 1.29.444（暫存器與 PPS 值）。

### 新增
- `firmware/src/main.c`：PIC16F13145 韌體（XC8），UART↔SPI 橋接。
  - UART1：RC5 RX / RC4 TX（連 Nano 板載 debugger 的 USB CDC），500000 bps，32 MHz HFINTOSC。
  - SPI（bit-bang Mode 0）：CS#=RB5、SCLK=RB7、MOSI=RC6、MISO=RC7；WP#=RB4、RESET#=RB6；LED0=RC2。
  - 指令：PING、INFO、ID、RDSR、RDCR、WRSR、READ、PP、SE、CE、WP、SPEED、HWRESET、RST。
  - 編譯結果（XC8 3.10，-O2，0 warning）：Program 1765/8192 words (21.5%)，Data 92/1024 bytes (9%)。
- `firmware/prebuilt/mx25_bridge_pic16f13145.hex`（10009 bytes，SHA-256 `58efaa733bf1f369505515af08a3862ff2d43bf9d611f3599a454e7b9866a3e2`）。
- `firmware/build.bat`：以 XC8 編譯（可用 `XC8_BIN`、`PIC_DFP` 覆寫路徑，暫存檔放 `%TEMP%`）。
- `firmware/flash_nano.bat`：拖放式燒錄（複製 HEX 到 `CURIOSITY` 磁碟機）。
- `docs/HARDWARE.md`：新的硬體接線圖與腳位表（Nano 腳位 ↔ TXS0108E ↔ MX25S1633F）。
- `docs/PROTOCOL.md`：新的序列埠協定說明。

### 變更
- `.vscode/tasks.json`：移除 PlatformIO / esptool / COM 埠輸入；新增 `FW: Build (XC8)`、`FW: Flash to Curiosity Nano (drag-and-drop)`。
- `README.md`、`docs/USER_GUIDE.md`：全面改寫為 Curiosity Nano 流程（燒錄、COM 埠名稱、疑難排解）。
- 硬體：原 ESP32-C3 的 3.3V 改為 Nano 的 VTG（3.3V）；TXS0108E VCCA=1.2V / VCCB=VTG / OE 接 VCCA 不變。
- `PATCH_README.txt`：專案資料夾名稱更新。

### 移除
- `tools/pio.cmd`、`tools/pio.sh`（不再使用 PlatformIO）。
- `firmware/prebuilt/README.md`（ESP32-C3 merged.bin 說明，已失效）。

### 尚未完成／需注意
- **尚未在實體硬體上測試**：韌體只做過編譯驗證，請依 USER_GUIDE「第一次使用的建議順序」先不接 flash 測試 `Bridge alive.`。
- 專案資料夾內**沒有** `gui/mx25s1633_gui.py`、`hexfile.py`、`setup_env.*`、`tests/` 等原始碼（只有 `gui/build_exe.bat`）。
  GUI 需把預設鮑率改為 500000、COM 埠偵測改為 "Curiosity Virtual COM Port"；協定與舊版 ESP32 韌體相容，
  但 `ID` 回應格式、`SPEED` 參數意義請以 `docs/PROTOCOL.md` 為準（舊 GUI 的 SPI MHz 選單需對應成 0~F 延遲值）。
- RC7（MISO）與 debugger DBG2 共用邊緣連接器，請勿同時使用 DGI GPIO。
- 若 MPLAB XC8 / DFP 版本不同，請設定 `XC8_BIN`、`PIC_DFP` 後重新執行 `firmware\build.bat`。

## v1.1.3 — （日期未記錄）VS Code Task 修正（ESP32-C3 時期）
- 新增 `tools\py.cmd` / `pio.cmd`，Task 改由啟動程式執行，修正 shell executable 路徑錯誤。

## v1.1.2 — （日期未記錄）OneDrive 相容性
- Python 環境、`.pio`、PyInstaller 暫存檔在 OneDrive 下改放 `%LOCALAPPDATA%` / `%TEMP%`。

## v1.1.1 — （日期未記錄）VS Code 環境設定
- 新增 `setup_env.bat` / `setup_env.sh` 與 Setup Task。

## v1.1 — （日期未記錄）ESP32-C3 Super Mini
- 開發板改為 ESP32-C3 Super Mini；新增 `WP`、`HWRESET`、`INFO` 指令。

## v1.0 — （日期未記錄）初版
- ESP32 序列橋接韌體 + Tkinter GUI。
