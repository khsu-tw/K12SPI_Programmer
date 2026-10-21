# 序列埠協定（PC <-> PIC18F16Q20 Curiosity Nano）

UART **500000 8N1**（Nano debugger CDC 上限 500 kbps）。指令為 ASCII 一行、以 `\n` 結尾（不分大小寫）；
數值一律十六進位。回應為 `OK...` / `ERR:xxx` 一行。

| 指令 | 回應 | 說明 |
|---|---|---|
| `PING` | `OK PONG` | 通訊測試 |
| `INFO` | `OK PIC18F16Q20-CNANO SPINOR-BRIDGE 5.1.1` | 韌體資訊 |
| `ID` | `ID:C2 2B 25` | RDID 9Fh（MX25S1633F `C2 2B 25`、GD25UF16E `C8 83 15`、W25Q65NE `EF 65 17`） |
| `SFDP addr len` | `OK` 後接 len 個原始位元組 | JESD216 Read SFDP（5Ah + 3 位元組位址 + 8 個 dummy clock），len ≤ 256 |
| `VIO` | `VIO:aaaa bbbb` | VSENSE（RA1）電壓，單位 mV（十六進位）。`aaaa` = 一般讀值，`bbbb` = 開啟腳位弱上拉後的讀值；兩者差距大 = 腳位浮接（未接線） |
| `VCHK 0\|1` | `OK` | 1 = 啟用電壓互鎖：VSENSE 不在 1.14–1.26 V 時，PP/PW/SE/B32/BE/CE/WRSR 一律回 `ERR:vio`。**上電預設為 1** |
| `LINK n` | `LINK:gggg/nnnn` | 連續讀 n 次 ID，回報與第一次相同且廠商碼不是 00/FF 的次數（Link Test 用） |
| `RDSR` / `RDCR` / `RDSR2` | `SR:xx` / `CR:xx` / `SR2:xx` | 讀 Status Register 1（05h）/ Configuration Register（15h，MX25）/ Status Register 2（35h，GD25UF16E、W25Q65NE） |
| `WRSR xx [yy]` | `OK` | WREN + WRSR + 等待完成；給第二個位元組 `yy` 時一併寫入 SR2（GD25UF16E 只寫 1 位元組會把 SR2 可寫位元清 0） |
| `READ addr len` | `OK` 後接 len 個原始位元組 | len ≤ 0x10000 |
| `CRC addr len` | `CRC:xxxxxxxx` | 板上計算 flash 區段 CRC-32（zlib 相同），用於驗證與 Read→File 雙重確認 |
| `PW addr len` | （無 RDY）資料緊接在指令行後送出 → `OK` | 流水線寫入：MCU 收完資料、啟動頁寫入後即回 `OK`，下一個 `PW`/`SYNC` 才等待上一頁完成；UART 溢位回 `ERR:ovf` |
| `SYNC` | `OK` | 等待目前的寫入/抹除完成 |
| `PP addr len` | `RDY` → PC 送 len 個位元組 → `OK` | 單頁 ≤ 256 bytes，不可跨頁 |
| `SE addr` | `OK` | 4KB Sector Erase（20h） |
| `B32 addr` | `OK` | 32KB Block Erase（52h） |
| `BE addr` | `OK` | 64KB Block Erase（D8h） |
| `CE` | `OK` | Chip Erase（60h），最長等 150 s（W25Q65NE tCE 最大 140 s） |
| `WP 0\|1` | `OK` | 控制 WP#（RB7） |
| `SPEED n` | `OK` | SPI 延遲 0（最快）~3F，數字越大越慢 |
| `SLEW 0\|1` | `OK` | 1 = SPI 輸出腳限制轉換率（邊緣較慢） |
| `LED 0\|1` | `OK` | 1 = LED0 亮（RC7） |
| `HWRESET` | `OK` | RESET# 腳拉低 2 ms（RC1） |
| `RST` | `OK` | RSTEN(66h)+RST(99h) |
| `RDP` | `OK` | Release from Deep Power-Down（ABh）+ 等 50 µs + 一次 RDSR。韌體開機時也會自動執行一次；GUI 在 Auto Detect 讀 ID 前送出 |

錯誤：`ERR:cmd`（未知指令）、`ERR:arg`、`ERR:busy`、`ERR:wel`（寫入被保護/未致能）、`ERR:timeout`、`ERR:ovf`（UART 接收溢位）、`ERR:vio`（VSENSE 電壓不在 1.14–1.26 V，已拒絕寫入/抹除）。

位址範圍為 24 位元（`READ`/`CRC`/`SFDP`/`SE`…最大 0xFFFFFF），可涵蓋 W25Q65NE 的 8 MB。
