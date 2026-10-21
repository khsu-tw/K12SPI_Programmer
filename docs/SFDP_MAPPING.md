# 燒錄必要參數與 JESD216H（SFDP）欄位對照

依據 `DOC/` 下的三份資料手冊（MX25S1633F Rev.1.3、GD25UF16E Rev1.0、W25Q65NE_DTR RevD）與 `DOC/JESD216H.pdf`。
本燒錄器只用 **1-1-1（單線）SPI、3-byte 位址、03h Read、02h Page Program**，所以 Quad / DTR / QPI 等欄位不列入必要項目。

**必要性**：

- **必要**：燒錄程式缺了它就無法正確讀寫或抹除。
- **安全**：設錯會損壞晶片或把晶片鎖住。
- **選用**：可以改善行為，但不影響基本燒錄。

**SFDP 欄位代號**：`DWn[x:y]` = JEDEC Basic Flash Parameter Table（ID FF00h）第 n 個 DWORD 的第 x–y 位元；條號為 JESD216H 的章節。

## 1. 辨識與容量

| 參數 | 燒錄程式用途 | 必要性 | JESD216H 欄位 | MX25S1633F | GD25UF16E | W25Q65NE | 程式目前來源 |
|---|---|---|---|---|---|---|---|
| JEDEC ID（9Fh） | 判斷廠牌/型號 | 必要 | **無**。SFDP 不含 ID；只有廠商自訂表的 ID LSB = JEP106 廠商碼（6.3.3） | `C2 2B 25` | `C8 83 15` | `EF 65 17` | `flashdb.KNOWN`（資料手冊） |
| SFDP 是否存在 | 能否依 SFDP 解析 | 必要 | 6.2.1 簽章 `50444653h`；6.2.2 版本、表頭數 | 有（rev 1.6，3 個表）※ | 有（資料手冊未公開內容） | 有（資料手冊未公開內容） | 讀 5Ah |
| 容量 | 位址範圍、檔案大小檢查、Chip Erase 範圍 | 必要 | DW2（6.4.5）：bit31=0 時 bits30:0 = 位元數−1 | 16 Mbit（SFDP `00FFFFFFh`）※ | 16 Mbit | 64 Mbit | SFDP，並與資料手冊值比對 |
| 位址位元組數 | 3-byte 或 4-byte 位址 | 必要 | DW1[18:17]（6.4.4）：00b = 只用 3-byte | 3-byte（SFDP 00b）※ | 3-byte | 3-byte（8 MB 仍在 3-byte 範圍內） | SFDP；4-byte only 則拒絕 |

## 2. 寫入（Page Program）

| 參數 | 燒錄程式用途 | 必要性 | JESD216H 欄位 | MX25S1633F | GD25UF16E | W25Q65NE | 程式目前來源 |
|---|---|---|---|---|---|---|---|
| Page Program 指令 | 寫入資料 | 必要 | **無**（1-1-1 的 02h 視為標準指令；只有 4-byte Address 表 FF84h 有 4-byte 版本） | 02h | 02h | 02h | 韌體寫死 02h |
| 頁大小 | 一次最多寫入的位元組數，不可跨頁 | 必要 | DW11[7:4]（6.4.14）：頁大小 = 2^N | 256 B（SFDP N=8）※ | 256 B | 256 B | SFDP；不是 256 則拒絕 |
| 頁寫入時間 tPP | 每頁寫完的等待上限 | 必要 | DW11[13:8] 典型值、DW11[3:0] 典型→最大倍率 | 典型 0.6 / 最大 4.6 ms（HPM）；ULP 1.1 / 8.5 ms。SFDP：典型 640 µs × 8 = 5.1 ms※ | 0.6 / 3 ms（Normal）；LPM 0.7 / 4 ms | 0.25 / 1.2 ms | 韌體：PW 等 100 ms、PP 等 50 ms（皆大於最大值） |
| Write Enable | 每次寫入/抹除前設 WEL | 必要 | 無專屬欄位；DW16[6:0]（6.4.19）說明 SR1 用 06h 或 50h | 06h | 06h | 06h | 韌體寫死 06h |

## 3. 抹除

| 參數 | 燒錄程式用途 | 必要性 | JESD216H 欄位 | MX25S1633F | GD25UF16E | W25Q65NE | 程式目前來源 |
|---|---|---|---|---|---|---|---|
| 4KB Sector Erase 指令 | 最小抹除單位 | 必要 | DW1[15:8] 指令、DW1[1:0]=01b 表示全區支援 4KB（6.4.4） | 20h（SFDP 20h / 01b）※ | 20h | 20h | SFDP；不是 20h 則拒絕 |
| 擦除類型 1–4 大小與指令 | 抹除計畫選 4K / 32K / 64K | 必要 | DW8、DW9（6.4.11、6.4.12）：大小 = 2^N、指令 | 4K=20h、32K=52h、64K=D8h※ | 同左 | 同左 | SFDP；只用 SFDP 有列出的大小 |
| 擦除時間 tSE / tBE1 / tBE2 | 等待上限、進度估算 | 必要 | DW10（6.4.13）：各類型典型時間 + DW10[3:0] 最大倍率 | 30/240 ms、0.15/1.5 s、0.28/3 s（HPM）。SFDP：30/160/288 ms × 12※ | 50/300 ms、0.12/1.6 s、0.2/3 s | 45/600 ms、0.12/2 s、0.15/2.5 s | 韌體：SE 1 s、B32 5 s、BE 10 s |
| Chip Erase 指令 | 整顆抹除 | 必要 | **無** | 60h / C7h | 60h / C7h | 60h / C7h | 韌體寫死 60h |
| Chip Erase 時間 tCE | 等待上限 | 必要 | DW11[30:24]（6.4.14）典型 + DW10[3:0] 倍率 | 典型 5 / 最大 38 s（HPM）；ULP 7.5 / 57 s。SFDP：5.1 s × 12 ≈ 61 s※ | 5 / 40 s；LPM 6 / 50 s | 40 / 140 s | `chip_erase_s` 57 / 50 / 140 s（資料手冊最大值，MX 取 ULP），韌體上限 150 s |

## 4. 狀態輪詢與保護

| 參數 | 燒錄程式用途 | 必要性 | JESD216H 欄位 | MX25S1633F | GD25UF16E | W25Q65NE | 程式目前來源 |
|---|---|---|---|---|---|---|---|
| 忙碌輪詢 | 判斷寫入/抹除完成 | 必要 | DW14[7:2] bit2（6.4.17）：可用 05h 讀 WIP bit0 | 05h、WIP=bit0（SFDP 支援）※ | 05h、WIP=bit0 | 05h、BUSY=bit0 | 韌體寫死 05h / bit0 |
| WEL 位元 | 確認 Write Enable 生效 | 必要 | 無；DW16 註明 SR1 bit1:0 為業界慣例 | bit1 | bit1 | bit1 | 韌體寫死 bit1 |
| SR1 保護位元定義 | 抹除/寫入前須清為 0；Config SR 對話框 | 安全 | **無**。DW16[6:0] 只說明 SR1 是揮發/非揮發與用 06h 或 50h 致能；保護位元位置不在 SFDP 內 | SRWD、QE、BP3–BP0 | SRP0、BP4–BP0 | SRP、SEC、TB、BP2–BP0 | `flashdb.SR1_*`（資料手冊） |
| SR2 與 WRSR 寫法 | 寫 SR1 時不能誤清 SR2 | 安全 | 間接：DW15[22:20] QER（6.4.18）描述 SR2 是否存在、寫 1 位元組是否清除 SR2 | 無 SR2（SFDP QER=010b：QE 在 SR1 bit6）※ | 有 SR2；只寫 1 位元組會清 SR2 可寫位元（資料手冊 7.4，行為同 QER 001b 的描述；QE 固定為 1 不受影響） | 有 SR2；用 31h 單獨寫入（資料手冊 7.3.5） | `has_sr2`（資料手冊）；Config SR 一律帶 SR2 原值寫回 |
| WRSR 時間 tW | WRSR 後等待上限 | 必要 | **無** | 8 / 40 ms（HPM）；ULP 10 / 50 ms | 2 / 20 ms | 2 / 20 ms | 韌體等 100 ms |
| OTP 位元 | 設 1 後無法復原，禁止誤寫 | 安全 | **無** | — | LB3–LB1、CMP（SR2） | LB3–LB1（SR2） | GUI 不提供修改 SR2 |

## 5. 電壓、時脈與重置

| 參數 | 燒錄程式用途 | 必要性 | JESD216H 欄位 | MX25S1633F | GD25UF16E | W25Q65NE | 程式目前來源 |
|---|---|---|---|---|---|---|---|
| VCC 工作電壓 | 1.2 V 互鎖（最高優先） | 安全 | **無**（JESD216H 沒有任何電壓欄位） | 1.14–1.6 V | 1.14–1.26 V | 1.14–1.26 V | VSENSE 窗口 1.14–1.26 V（三者交集） |
| 03h Read 最高時脈 fR | SPI 速度上限 | 必要 | **無**。DW20（6.4.23）只有 4S-4S-4S / 4S-4D-4D / 8S / 8D 模式的速度 | 50 MHz | 50 MHz（Normal）；LPM 40 MHz | 84 MHz | bit-bang 遠低於上限；以 Link Test 決定 |
| Read 指令 | 讀出、驗證、CRC | 必要 | **無**（03h 為標準指令） | 03h | 03h | 03h | 韌體寫死 03h |
| 軟體重置 | 讓晶片回到上電狀態 | 選用 | DW16[13:8]（6.4.19）bit4：66h + 99h | 66h + 99h（SFDP 有）※ | 66h + 99h | 66h + 99h | GUI Reset 按鈕 |
| Deep Power-Down 退出 | 晶片若停在省電模式，ID 會讀不到 | 選用 | DW14[31:8]（6.4.17）：是否支援、進入/退出指令、退出延遲 | 進入 B9h / 退出 ABh（SFDP 有）※；tRDP 45 µs | B9h / ABh；tRES1 20 µs | B9h / ABh；tRES1 20 µs | 韌體 5.1.0：`RDP` 指令與開機時送 ABh，等 50 µs |

※ = 由實機（MX25S1633F，2026-10-20）讀出的 SFDP 值核對過。GD25UF16E 與 W25Q65NE 尚未讀過實機 SFDP，表中為資料手冊值。

## 6. SFDP 能提供 vs 只能靠資料手冊

| 只能從 SFDP 取得或可由 SFDP 驗證 | SFDP 沒有、必須靠資料手冊（`flashdb.py`） |
|---|---|
| 容量、位址位元組數、頁大小 | JEDEC ID 與型號名稱 |
| 4KB 抹除指令、擦除類型 1–4 大小與指令 | Page Program 02h、Read 03h、Chip Erase 60h 指令 |
| 擦除 / 頁寫入 / Chip Erase 典型時間與最大倍率 | WRSR 時間 tW、03h 最高時脈 fR |
| 忙碌輪詢方式（05h WIP） | SR1 保護位元位置（BP / SRP / SEC / TB / CMP） |
| QE 位置與 SR2 寫法（QER） | OTP 位元（LB、GD 的 CMP）與電源鎖定位元（SRP1 / SRL） |
| 軟體重置、Deep Power-Down 指令 | **VCC 工作電壓** |

這也是程式只讓支援清單內的晶片燒錄的原因：未列入的晶片雖然可以從 SFDP 算出容量與抹除方式，但**保護位元與電壓**不在 SFDP 內，設錯可能把晶片鎖住或損壞。

## 7. 實機 SFDP 原始值

| DWORD | 對應參數 | MX25S1633F | W25Q32NE（以 W25Q65NE 名義收到的料） |
|---|---|---|---|
| 表頭 | 版本 / 表數 | rev 1.6 / 3 個表（FF00h、FFC2h Macronix、FF84h 4-byte） | rev 1.10 / 1 個表（FF00h，23 DWORDs） |
| DW1 | 位址、4KB 抹除、讀取模式 | `FFF120E5h` | `FFF920E5h` |
| DW2 | 容量 | `00FFFFFFh`（16 Mbit） | `01FFFFFFh`（32 Mbit） |
| DW8 | 擦除類型 1/2 | `520F200Ch` | `520F200Ch` |
| DW9 | 擦除類型 3/4 | `FF00D810h` | `0000D810h` |
| DW10 | 擦除時間、最大倍率 | `00C549D5h`（30/160/288 ms，× 12） | `00A50226h`（48/16/160 ms，× 14） |
| DW11 | 頁大小、頁寫入、Chip Erase | `B3A52983h`（256 B，640 µs，5.1 s） | `C414F281h`（256 B，1216 µs，20 s） |
| DW14 | 忙碌輪詢、Deep Power-Down | `5CD5C5F7h` | `5CD5C2F7h` |
| DW15 | QER | `FF29BE00h`（QER 010b） | `FF6DF639h`（QER 110b） |
| DW16 | SR1 寫法、軟體重置 | `FFFFD0F0h` | `80F830E9h` |

W25Q32NE 的 32K 典型時間（16 ms）比 4K（48 ms）短，是晶片 SFDP 本身的值，照實列出。

## 8. 從這張表看出的問題與處理

- **Deep Power-Down（已處理，韌體 5.1.0）**：三顆都支援 B9h / ABh，原本韌體不送 ABh，晶片若在省電模式 ID 會讀成 `FF FF FF`。
  現在韌體開機與 GUI Auto Detect 都會先送 ABh。實測 W25Q32NE：ABh 之後的第一筆 SPI 傳輸讀到全 0，第二筆才正確，原因未查明，
  韌體在 ABh 後多做一次 RDSR 吸收掉。
- **MX25S1633F 的 ULP 模式（已處理）**：MX25S1633FM2IG2 出廠預設是 Ultra Low Power 模式，Chip Erase 最大 57 s。
  `chip_erase_s` 已由 38 s 改為 57 s（GUI 等待 77 s）。
- **GD25UF16E 的 QE**：QE 固定為 1、不能改（資料手冊 6.1 QE bit），但手冊也註明「WP# pin is still available for Standard/Dual SPI」。
  本燒錄器只用 1-1-1 單線 SPI，所以 WP# 與 SRP0 硬體保護仍然有效，GUI 的「WP# High」照常需要。
- **GD25UF16E / W25Q65NE 的 SFDP**：還沒讀過實機，上板後請比對 Log 的 `SFDP:` 行與本表。
