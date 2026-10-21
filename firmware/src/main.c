/*
 * 1.2 V SPI-NOR programmer bridge for Curiosity Nano boards
 *   (MX25S1633F / GD25UF16E / W25Q65NE: all JESD216 SFDP capable, 3-byte addressing)
 *   - PIC16F13145-CNANO (DS50003649)
 *   - PIC18F16Q20-CNANO (DS50003588)
 * One source file; the board is selected by the compiler device (-mcpu=16F13145 / -mcpu=18F16Q20).
 *
 * PC (USB CDC = on-board debugger) <-UART-> MCU <-SPI 3.3V-> TXS0108E <-SPI 1.2V-> MX25S1633F
 *
 * Both boards use the SAME physical edge-connector holes for the flash wiring (docs/HARDWARE.md):
 *
 *   function   edge label           PIC16F13145   PIC18F16Q20   TXS0108E B side
 *   CS#        SPI SS               RB5           RA4           B1
 *   MISO       SPI MISO             RC7           RC6           B2
 *   WP#        right row 7 (*)      RA4           RB7           B3
 *   MOSI       SPI MOSI             RC6           RC3           B4
 *   SCLK       SPI SCK              RB7           RA5           B5
 *   RESET#     I2C SDA / I3C1 SDA   RB4           RC1           B6
 *   VSENSE     right row, RA1 hole  RA1           RA1           (1.2 V rail; optional, ADC)
 *   UART TX/RX (board fixed)        RC4 / RC5     RC4 / RC5     (USB CDC)
 *   LED0 (active low)               RC2           RC7
 *   (*) 7th hole below VTG on the right-hand edge row.
 *
 * On the PIC18F16Q20, RB5/RB6 are MVIO pins fixed at 1.2 V (I2C/I3C only) and are NOT used.
 * SPI is bit-banged (mode 0) so only the UART needs PPS.
 * Protocol: docs/PROTOCOL.md (ASCII command lines ending in '\n', raw binary data phases).
 */
#include <xc.h>
#include <stdint.h>

#if defined(_16F13145)
#define BOARD_PIC16F13145 1
#elif defined(_18F16Q20)
#define BOARD_PIC18F16Q20 1
#else
#error "Unsupported device: build with -mcpu=16F13145 or -mcpu=18F16Q20"
#endif

#if defined(BOARD_PIC16F13145)
/* HFINTOSC 32 MHz selected by RSTOSC; the hardware loads OSCFRQ to match. */
#pragma config FEXTOSC = OFF, RSTOSC = HFINTOSC_32MHz, CLKOUTEN = OFF, CSWEN = ON
#pragma config VDDAR = HI, FCMEN = OFF
#pragma config MCLRE = EXTMCLR, PWRTS = PWRT_OFF, LPBOREN = OFF, BOREN = ON, BORV = LO
#pragma config DACAUTOEN = OFF, PPS1WAY = OFF, STVREN = ON, DEBUG = OFF
#pragma config WDTCPS = WDTCPS_31, WDTE = OFF, WDTCWS = WDTCWS_7, WDTCCS = SC
#pragma config BBSIZE = BB512, BBEN = OFF, SAFEN = OFF
#pragma config WRTAPP = OFF, WRTB = OFF, WRTC = OFF, WRTSAF = OFF, LVP = ON
#pragma config CP = OFF

#define _XTAL_FREQ 32000000UL
#define BOARD_NAME "PIC16F13145-CNANO"
#define UART_BRG   15               /* BRG16=1, BRGH=1: 32 MHz / (4 * 16) = 500 kbps (debugger CDC max) */

#define CS_PIN    LATBbits.LATB5
#define SCK_PIN   LATBbits.LATB7
#define MOSI_PIN  LATCbits.LATC6
#define MISO_PIN  PORTCbits.RC7
#define WP_PIN    LATAbits.LATA4
#define RST_PIN   LATBbits.LATB4
#define LED_PIN   LATCbits.LATC2    /* 0 = LED on */
#else
/* MVECEN = OFF: every interrupt uses the single vector at 0x0008 (our ISR); the low-priority
 * vector warning from XC8 is harmless. */
#pragma config FEXTOSC = OFF, RSTOSC = HFINTOSC_64MHZ, CLKOUTEN = OFF, PR1WAY = OFF, CSWEN = ON
#pragma config FCMEN = OFF, FCMENP = OFF, FCMENS = OFF
#pragma config MCLRE = EXTMCLR, PWRTS = PWRT_OFF, MVECEN = OFF, IVT1WAY = OFF
#pragma config LPBOREN = OFF, BOREN = ON, BORV = VBOR_2P45
#pragma config PPS1WAY = OFF, STVREN = ON, LVP = ON, DEBUG = OFF, XINST = OFF
#pragma config WDTE = OFF, BBEN = OFF
#pragma config VDDIO2MD = STANDARD_RANGE, VDDIO3MD = LOW_VOLTAGE_RANGE
#pragma config CP = OFF, WRTB = OFF, WRTC = OFF, WRTD = OFF, WRTSAF = OFF, WRTAPP = OFF

#define _XTAL_FREQ 64000000UL
#define BOARD_NAME "PIC18F16Q20-CNANO"
#define UART_BRG   31               /* BRGS=1: 64 MHz / (4 * 32) = 500 kbps (debugger CDC max) */

#define CS_PIN    LATAbits.LATA4
#define SCK_PIN   LATAbits.LATA5
#define MOSI_PIN  LATCbits.LATC3
#define MISO_PIN  PORTCbits.RC6
#define WP_PIN    LATBbits.LATB7
#define RST_PIN   LATCbits.LATC1    /* VDDIO2 domain = VCC_TARGET (3.3 V) by default */
#define LED_PIN   LATCbits.LATC7    /* 0 = LED on */
#endif

#define FW_VERSION "5.1.1"

/* MX25S1633F commands */
#define CMD_WREN  0x06
#define CMD_RDSR  0x05
#define CMD_WRSR  0x01
#define CMD_RDCR  0x15
#define CMD_RDSR2 0x35
#define CMD_SFDP  0x5A
#define CMD_READ  0x03
#define CMD_PP    0x02
#define CMD_SE    0x20
#define CMD_BE32  0x52
#define CMD_BE64  0xD8
#define CMD_CE    0x60
#define CMD_RDID  0x9F
#define CMD_RSTEN 0x66
#define CMD_RST   0x99
#define CMD_RDP   0xAB              /* Release from Deep Power-Down (all three parts; SFDP DWORD14) */

static uint8_t spi_delay;           /* 0 = fastest; each step adds ~0.25 us per half clock */
static uint8_t pagebuf[256];
static uint8_t rx_ovf;              /* set when the UART RX FIFO overflowed */
static uint8_t vio_check = 1;       /* 1 = refuse program/erase/WRSR while VSENSE is outside the 1.2 V window (fail closed at power-up; GUI VCHK 0 if VSENSE is not wired) */

#define VIO_MIN_MV 1140U            /* 1.2 V -5 %: common minimum of all supported flashes */
#define VIO_MAX_MV 1260U            /* 1.2 V +5 %: GD25UF16E / W25Q65NE maximum operating voltage */

/* ---------------------------------------------------------------- UART */
static void uart_init(void)
{
#if defined(BOARD_PIC16F13145)
    RX1PPS = 0x15;                  /* RC5 */
    RC4PPS = 0x13;                  /* TX1 on RC4 */
    SP1BRG = UART_BRG;
    BAUD1CONbits.BRG16 = 1;
    TX1STA = 0x24;                  /* TXEN=1, SYNC=0, BRGH=1 */
    RC1STA = 0x90;                  /* SPEN=1, CREN=1 */
    PIE4bits.RC1IE = 1;
    INTCONbits.PEIE = 1;
    INTCONbits.GIE = 1;
#else
    U1RXPPS = 0x15;                 /* RC5 */
    RC4PPS  = 0x13;                 /* TX1 on RC4 */
    U1BRG   = UART_BRG;
    U1CON0  = 0xB0;                 /* BRGS=1, TXEN=1, RXEN=1, async 8-bit */
    U1CON1bits.ON = 1;
    PIE6bits.U1RXIE = 1;
    INTCON0bits.GIE = 1;
#endif
}

static void uart_putc(uint8_t c)
{
#if defined(BOARD_PIC16F13145)
    while (!PIR4bits.TX1IF) { }
    TX1REG = c;
#else
    while (U1FIFObits.TXBF) { }
    U1TXB = c;
#endif
}

static void uart_puts(const char *s)
{
    while (*s) uart_putc((uint8_t)*s++);
}

/* RX ring buffer filled by the interrupt handler. The UART hardware FIFO is only a few bytes deep,
 * so without this, data sent right behind a command line (PW) is lost while the line is parsed. */
static volatile uint8_t rx_buf[256];
static volatile uint8_t rx_head;    /* written by ISR only  */
static volatile uint8_t rx_tail;    /* written by main only */

void __interrupt() isr(void)
{
#if defined(BOARD_PIC16F13145)
    while (PIR4bits.RC1IF) {
        uint8_t next = (uint8_t)(rx_head + 1);
        uint8_t c;
        if (RC1STAbits.OERR) { RC1STAbits.CREN = 0; RC1STAbits.CREN = 1; rx_ovf = 1; }
        c = RC1REG;
        if (next == rx_tail) { rx_ovf = 1; continue; }     /* ring full: drop */
        rx_buf[rx_head] = c;
        rx_head = next;
    }
#else
    while (!U1FIFObits.RXBE) {
        uint8_t next = (uint8_t)(rx_head + 1);
        uint8_t c = U1RXB;
        if (next == rx_tail) { rx_ovf = 1; continue; }     /* ring full: drop */
        rx_buf[rx_head] = c;
        rx_head = next;
    }
    if (U1ERRIRbits.RXFOIF) { U1ERRIRbits.RXFOIF = 0; rx_ovf = 1; }
#endif
}

static uint8_t uart_getc(void)
{
    while (rx_head == rx_tail) { }
    uint8_t c = rx_buf[rx_tail];
    rx_tail = (uint8_t)(rx_tail + 1);
    return c;
}

static void uart_puthex8(uint8_t v)
{
    static const char hx[] = "0123456789ABCDEF";
    uart_putc(hx[v >> 4]);
    uart_putc(hx[v & 15]);
}

static void uart_puthex32(uint32_t v)
{
    uart_puthex8((uint8_t)(v >> 24)); uart_puthex8((uint8_t)(v >> 16));
    uart_puthex8((uint8_t)(v >> 8));  uart_puthex8((uint8_t)v);
}

/* ----------------------------------------------------------------- SPI */
static void spi_wait(void)
{
    for (uint8_t i = spi_delay; i; i--) { NOP(); NOP(); NOP(); NOP(); }
}

#define FAST_BIT(m)     MOSI_PIN = (out & (m)) ? 1 : 0;     SCK_PIN = 1;     if (MISO_PIN) in |= (m);     SCK_PIN = 0;

static uint8_t spi_xfer(uint8_t out)
{
    uint8_t in = 0;
    if (spi_delay == 0) {           /* fast path: unrolled, no waits (used for bulk read/CRC) */
        FAST_BIT(0x80) FAST_BIT(0x40) FAST_BIT(0x20) FAST_BIT(0x10)
        FAST_BIT(0x08) FAST_BIT(0x04) FAST_BIT(0x02) FAST_BIT(0x01)
        return in;
    }
    for (uint8_t i = 0; i < 8; i++) {
        MOSI_PIN = (out & 0x80) ? 1 : 0;
        out <<= 1;
        spi_wait();
        SCK_PIN = 1;
        spi_wait();
        in = (uint8_t)((in << 1) | (MISO_PIN ? 1 : 0));
        SCK_PIN = 0;
    }
    return in;
}

static void spi_addr(uint32_t a)
{
    spi_xfer((uint8_t)(a >> 16));
    spi_xfer((uint8_t)(a >> 8));
    spi_xfer((uint8_t)a);
}

static void cs_low(void)  { CS_PIN = 0; NOP(); NOP(); }
static void cs_high(void) { CS_PIN = 1; NOP(); NOP(); NOP(); NOP(); }

static uint8_t flash_rdsr(void)
{
    cs_low(); spi_xfer(CMD_RDSR); uint8_t v = spi_xfer(0); cs_high();
    return v;
}

static void flash_wren(void)
{
    cs_low(); spi_xfer(CMD_WREN); cs_high();
}

/* wait for WIP=0; returns 0 on timeout. Polls every ~50 us so a finished page costs no extra ms. */
static uint8_t flash_wait(uint32_t timeout_ms)
{
    uint32_t n = timeout_ms * 20UL;
    while (n--) {
        if (!(flash_rdsr() & 0x01)) return 1;
        __delay_us(50);
    }
    return 0;
}

/* CRC-32 (zlib / IEEE 802.3), nibble-wise table in program memory (16F13145 has only 1 KB RAM) */
static const uint32_t crc_nib[16] = {
    0x00000000UL, 0x1DB71064UL, 0x3B6E20C8UL, 0x26D930ACUL, 0x76DC4190UL, 0x6B6B51F4UL,
    0x4DB26158UL, 0x5005713CUL, 0xEDB88320UL, 0xF00F9344UL, 0xD6D6A3E8UL, 0xCB61B38CUL,
    0x9B64C2B0UL, 0x86D3D2D4UL, 0xA00AE278UL, 0xBDBDF21CUL
};

static uint32_t crc32_update(uint32_t crc, uint8_t b)
{
    crc ^= b;
    crc = (crc >> 4) ^ crc_nib[(uint8_t)crc & 15];
    crc = (crc >> 4) ^ crc_nib[(uint8_t)crc & 15];
    return crc;
}

/* ------------------------------------------------------- VSENSE (RA1) */
/* ADC referenced to the FVR at 2.048 V (independent of the 3.3 V VTG), 10-bit, right-justified:
 * 1 count = 2 mV (a floating pin with the pull-up on reads 1023 = full scale). Same ADC/FVR registers on both boards. RA1 = ANA1. */
static uint16_t vio_sample(void)
{
    uint16_t sum = 0;
    ANSELAbits.ANSELA1 = 1;
    TRISAbits.TRISA1 = 1;
    FVRCON = 0x82;                  /* FVREN=1, ADFVR=2x (2.048 V) */
    for (uint16_t t = 0; t < 20000 && !FVRCONbits.FVRRDY; t++) { }   /* bounded: never hang the bridge */
    ADREF = 0x03;                   /* positive reference = FVR, negative = VSS */
    ADPCH = 0x01;                   /* ANA1 */
    ADCON0 = 0x94;                  /* ADON=1, ADCS=FRC, right-justified */
    ADACQ = 40;                     /* acquisition time in TAD */
    for (uint8_t i = 0; i < 4; i++) {
        ADCON0bits.ADGO = 1;
        while (ADCON0bits.ADGO) { }
        sum += (uint16_t)(((uint16_t)ADRESH << 8) | ADRESL);
    }
    ADCON0bits.ADON = 0;
    return (uint16_t)(sum >> 1);    /* mean of 4 counts x 2 mV/count = sum / 2 mV */
}

/* pullup=1 enables the pin's weak pull-up: a pin tied to the 1.2 V rail does not move, a floating pin
 * (VSENSE not wired) is pulled up to VDD and reads full scale. The GUI compares both readings. */
static uint16_t vio_read_mv(uint8_t pullup)
{
    uint16_t mv;
    WPUAbits.WPUA1 = pullup;
    if (pullup) __delay_us(300);
    mv = vio_sample();
    WPUAbits.WPUA1 = 0;
    return mv;
}

/* highest-priority interlock: called before every program/erase/WRSR */
static uint8_t vio_ok(void)
{
    uint16_t mv;
    if (!vio_check) return 1;
    mv = vio_read_mv(0);
    return (mv >= VIO_MIN_MV && mv <= VIO_MAX_MV) ? 1 : 0;
}

/* -------------------------------------------------------------- parsing */
static char line[40];

static void read_line(void)
{
    uint8_t n = 0;
    for (;;) {
        uint8_t c = uart_getc();
        if (c == '\r') continue;
        if (c == '\n') {
#if defined(BOARD_PIC18F16Q20)
            U1ERRIRbits.RXFOIF = 0;
#endif
            rx_ovf = 0;
            break;
        }
        if (c >= 'a' && c <= 'z') c -= 32;
        if (n < sizeof(line) - 1) line[n++] = (char)c;
    }
    line[n] = 0;
}

/* parse next hex token starting at *p; returns 0xFFFFFFFF if none */
static uint32_t next_hex(const char **p)
{
    const char *s = *p;
    uint32_t v = 0;
    uint8_t got = 0;
    while (*s == ' ') s++;
    for (;; s++) {
        char c = *s;
        uint8_t d;
        if (c >= '0' && c <= '9') d = (uint8_t)(c - '0');
        else if (c >= 'A' && c <= 'F') d = (uint8_t)(c - 'A' + 10);
        else break;
        v = (v << 4) | d;
        got = 1;
    }
    *p = s;
    return got ? v : 0xFFFFFFFFUL;
}

static uint8_t starts(const char *cmd, const char *name, const char **args)
{
    while (*name) { if (*cmd++ != *name++) return 0; }
    if (*cmd != 0 && *cmd != ' ') return 0;
    *args = cmd;
    return 1;
}

/* ------------------------------------------------------------- commands */
#define ERR(msg) uart_puts("ERR:" msg "\n")

static uint8_t range_ok(uint32_t addr, uint32_t len)
{
    return addr <= 0xFFFFFFUL && len != 0xFFFFFFFFUL && len != 0 && len <= 0x1000000UL &&
           addr + len <= 0x1000000UL;
}

static void cmd_id(void)
{
    cs_low(); spi_xfer(CMD_RDID);
    uint8_t a = spi_xfer(0), b = spi_xfer(0), c = spi_xfer(0);
    cs_high();
    uart_puts("ID:"); uart_puthex8(a); uart_putc(' ');
    uart_puthex8(b); uart_putc(' '); uart_puthex8(c); uart_putc('\n');
}

/* LINK n : read ID n times, count how many equal the first read and look like a real ID (mfr byte not 00/FF) */
static void cmd_link(const char *args)
{
    uint32_t n = next_hex(&args);
    uint16_t good = 0, first_set = 0;
    uint8_t ref[3] = {0, 0, 0};
    if (n == 0xFFFFFFFFUL || n == 0 || n > 0xFFFF) { ERR("arg"); return; }
    for (uint16_t i = 0; i < (uint16_t)n; i++) {
        uint8_t id[3];
        cs_low(); spi_xfer(CMD_RDID);
        id[0] = spi_xfer(0); id[1] = spi_xfer(0); id[2] = spi_xfer(0);
        cs_high();
        if (!first_set) { ref[0] = id[0]; ref[1] = id[1]; ref[2] = id[2]; first_set = 1; }
        if (id[0] != 0x00 && id[0] != 0xFF && id[0] == ref[0] && id[1] == ref[1] && id[2] == ref[2]) good++;
    }
    uart_puts("LINK:");
    uart_puthex8((uint8_t)(good >> 8)); uart_puthex8((uint8_t)good);
    uart_putc('/');
    uart_puthex8((uint8_t)(n >> 8)); uart_puthex8((uint8_t)n);
    uart_putc('\n');
}

static void cmd_read(const char *args)
{
    uint32_t addr = next_hex(&args), len = next_hex(&args);
    if (!range_ok(addr, len) || len > 0x10000UL) { ERR("arg"); return; }
    uart_puts("OK\n");
    cs_low(); spi_xfer(CMD_READ); spi_addr(addr);
    while (len--) uart_putc(spi_xfer(0));
    cs_high();
}

/* SFDP addr len : JESD216 Read SFDP (5Ah + 3 address bytes + 8 dummy clocks), len <= 256 */
static void cmd_sfdp(const char *args)
{
    uint32_t addr = next_hex(&args), len = next_hex(&args);
    if (addr > 0xFFFFFFUL || len == 0xFFFFFFFFUL || len == 0 || len > 0x100UL) { ERR("arg"); return; }
    uart_puts("OK\n");
    cs_low(); spi_xfer(CMD_SFDP); spi_addr(addr); spi_xfer(0);
    while (len--) uart_putc(spi_xfer(0));
    cs_high();
}

static void cmd_vio(void)
{
    uint16_t mv = vio_read_mv(0), mv_pu = vio_read_mv(1);
    uart_puts("VIO:"); uart_puthex8((uint8_t)(mv >> 8)); uart_puthex8((uint8_t)mv);
    uart_putc(' '); uart_puthex8((uint8_t)(mv_pu >> 8)); uart_puthex8((uint8_t)mv_pu); uart_putc('\n');
}

static void cmd_crc(const char *args)
{
    uint32_t addr = next_hex(&args), len = next_hex(&args);
    uint32_t crc = 0xFFFFFFFFUL;
    if (!range_ok(addr, len)) { ERR("arg"); return; }
    cs_low(); spi_xfer(CMD_READ); spi_addr(addr);
    while (len--) crc = crc32_update(crc, spi_xfer(0));
    cs_high();
    uart_puts("CRC:"); uart_puthex32(~crc); uart_putc('\n');
}

static void cmd_pp(const char *args)
{
    uint32_t addr = next_hex(&args), len = next_hex(&args);
    if (addr > 0xFFFFFFUL || len == 0xFFFFFFFFUL || len == 0 || len > 256 ||
        ((addr & 0xFF) + len) > 256) {
        ERR("arg"); return;
    }
    if (!vio_ok()) { ERR("vio"); return; }
    if (!flash_wait(100)) { ERR("busy"); return; }
    uart_puts("RDY\n");
    /* buffer the whole page first so a slow SPI clock cannot overrun the UART */
    for (uint16_t i = 0; i < (uint16_t)len; i++) pagebuf[i] = uart_getc();
    flash_wren();
    if (!(flash_rdsr() & 0x02)) { ERR("wel"); return; }
    cs_low(); spi_xfer(CMD_PP); spi_addr(addr);
    for (uint16_t i = 0; i < (uint16_t)len; i++) spi_xfer(pagebuf[i]);
    cs_high();
    if (!flash_wait(50)) { ERR("timeout"); return; }
    uart_puts("OK\n");
}

/* PW addr len : like PP but with NO 'RDY' handshake - the host sends the data right behind the
 * command line. Replies OK as soon as the page program has been *started*; the next PW (or SYNC)
 * waits for it to finish, so the UART transfer of page N+1 overlaps the flash programming of page N. */
static void cmd_pw(const char *args)
{
    uint32_t addr = next_hex(&args), len = next_hex(&args);
    uint8_t ok = !(addr > 0xFFFFFFUL || len == 0xFFFFFFFFUL || len == 0 || len > 256 ||
                   ((addr & 0xFF) + len) > 256);
    uint16_t n = (len >= 1 && len <= 256) ? (uint16_t)len : 0;
    for (uint16_t i = 0; i < n; i++) {
        uint8_t c = uart_getc();
        if (ok) pagebuf[i] = c;
    }
    if (!ok) { ERR("arg"); return; }
    if (rx_ovf) { rx_ovf = 0; ERR("ovf"); return; }
    if (!vio_ok()) { ERR("vio"); return; }
    if (!flash_wait(100)) { ERR("timeout"); return; }      /* previous page still programming */
    flash_wren();
    if (!(flash_rdsr() & 0x02)) { ERR("wel"); return; }
    cs_low(); spi_xfer(CMD_PP); spi_addr(addr);
    for (uint16_t i = 0; i < n; i++) spi_xfer(pagebuf[i]);
    cs_high();
    uart_puts("OK\n");
}

static void cmd_sync(void)
{
    if (!flash_wait(1000)) { ERR("timeout"); return; }
    uart_puts("OK\n");
}

static void cmd_erase(uint8_t cmd, const char *args, uint32_t timeout_ms)
{
    uint32_t addr = 0;
    if (cmd != CMD_CE) {
        addr = next_hex(&args);
        if (addr > 0xFFFFFFUL) { ERR("arg"); return; }
    }
    if (!vio_ok()) { ERR("vio"); return; }
    if (!flash_wait(100)) { ERR("busy"); return; }
    flash_wren();
    if (!(flash_rdsr() & 0x02)) { ERR("wel"); return; }
    cs_low(); spi_xfer(cmd);
    if (cmd != CMD_CE) spi_addr(addr);
    cs_high();
    if (!flash_wait(timeout_ms)) { ERR("timeout"); return; }
    uart_puts("OK\n");
}

static void cmd_wrsr(const char *args)
{
    uint32_t v = next_hex(&args), v2 = next_hex(&args);       /* optional 2nd byte = SR2 (GD25UF16E clears SR2 on a 1-byte write) */
    if (v > 0xFF || (v2 != 0xFFFFFFFFUL && v2 > 0xFF)) { ERR("arg"); return; }
    if (!vio_ok()) { ERR("vio"); return; }
    flash_wren();
    cs_low(); spi_xfer(CMD_WRSR); spi_xfer((uint8_t)v);
    if (v2 != 0xFFFFFFFFUL) spi_xfer((uint8_t)v2);
    cs_high();
    if (!flash_wait(100)) { ERR("timeout"); return; }
    uart_puts("OK\n");
}

static void cmd_slew(uint8_t limited)
{
    /* SLRCONx bit = 1: slew-rate limited (slow edges); 0: maximum slew rate (fast edges) */
    uint8_t v = limited ? 1 : 0;
#if defined(BOARD_PIC16F13145)
    SLRCONBbits.SLRB5 = v; SLRCONBbits.SLRB7 = v; SLRCONBbits.SLRB4 = v;    /* CS#, SCLK, RESET# */
    SLRCONCbits.SLRC6 = v;                                                   /* MOSI */
    SLRCONAbits.SLRA4 = v;                                                   /* WP# */
#else
    SLRCONAbits.SLRA4 = v; SLRCONAbits.SLRA5 = v;
    SLRCONCbits.SLRC3 = v;
    SLRCONBbits.SLRB7 = v; SLRCONCbits.SLRC1 = v;
#endif
    uart_puts("OK\n");
}

static void cmd_hwreset(void)
{
    RST_PIN = 0; __delay_ms(2); RST_PIN = 1; __delay_ms(2);
    uart_puts("OK\n");
}

/* ABh alone (no ID read) wakes a flash left in Deep Power-Down; harmless when it is awake.
 * Wait > tRES1: MX25S1633F tRDP 45 us, GD25UF16E / W25Q65NE tRES1 20 us. */
static void flash_release_dp(void)
{
    cs_low(); spi_xfer(CMD_RDP); cs_high();
    __delay_us(50);
    /* Measured on W25Q32NE + TXS0108E (2026-10-20): the first transaction after ABh reads all zeros,
     * the next one is correct. Root cause not identified; absorb it with a harmless status read. */
    (void)flash_rdsr();
}

static void cmd_swreset(void)
{
    cs_low(); spi_xfer(CMD_RSTEN); cs_high();
    cs_low(); spi_xfer(CMD_RST);   cs_high();
    __delay_ms(1);
    uart_puts("OK\n");
}

static void execute(void)
{
    const char *a;
    if (starts(line, "PW", &a))          cmd_pw(a);          /* first: data follows immediately */
    else if (starts(line, "PING", &a))   uart_puts("OK PONG\n");
    else if (starts(line, "INFO", &a))   uart_puts("OK " BOARD_NAME " SPINOR-BRIDGE " FW_VERSION "\n");
    else if (starts(line, "ID", &a))     cmd_id();
    else if (starts(line, "LINK", &a))   cmd_link(a);
    else if (starts(line, "SFDP", &a))   cmd_sfdp(a);
    else if (starts(line, "VIO", &a))    cmd_vio();
    else if (starts(line, "VCHK", &a)) {
        uint32_t v = next_hex(&a);
        if (v > 1) ERR("arg"); else { vio_check = (uint8_t)v; uart_puts("OK\n"); }
    }
    else if (starts(line, "RDSR2", &a)) {
        cs_low(); spi_xfer(CMD_RDSR2); uint8_t v = spi_xfer(0); cs_high();
        uart_puts("SR2:"); uart_puthex8(v); uart_putc('\n');
    }
    else if (starts(line, "RDSR", &a)) { uart_puts("SR:"); uart_puthex8(flash_rdsr()); uart_putc('\n'); }
    else if (starts(line, "RDCR", &a)) {
        cs_low(); spi_xfer(CMD_RDCR); uint8_t v = spi_xfer(0); cs_high();
        uart_puts("CR:"); uart_puthex8(v); uart_putc('\n');
    }
    else if (starts(line, "WRSR", &a))   cmd_wrsr(a);
    else if (starts(line, "READ", &a))   cmd_read(a);
    else if (starts(line, "CRC", &a))    cmd_crc(a);
    else if (starts(line, "PP", &a))     cmd_pp(a);
    else if (starts(line, "SE", &a))     cmd_erase(CMD_SE, a, 2000);   /* W25Q32NE IoT mode tSE max 1000 ms */
    else if (starts(line, "B32", &a))    cmd_erase(CMD_BE32, a, 5000);
    else if (starts(line, "BE", &a))     cmd_erase(CMD_BE64, a, 10000);
    else if (starts(line, "SYNC", &a))   cmd_sync();
    else if (starts(line, "CE", &a))     cmd_erase(CMD_CE, a, 150000UL);
    else if (starts(line, "WP", &a)) {
        uint32_t v = next_hex(&a);
        if (v > 1) ERR("arg"); else { WP_PIN = (uint8_t)v; uart_puts("OK\n"); }
    }
    else if (starts(line, "LED", &a)) {
        uint32_t v = next_hex(&a);
        if (v > 1) ERR("arg"); else { LED_PIN = v ? 0 : 1; uart_puts("OK\n"); }
    }
    else if (starts(line, "SPEED", &a)) {
        uint32_t v = next_hex(&a);
        if (v > 0x3F) ERR("arg"); else { spi_delay = (uint8_t)v; uart_puts("OK\n"); }
    }
    else if (starts(line, "SLEW", &a)) {
        uint32_t v = next_hex(&a);
        if (v > 1) ERR("arg"); else cmd_slew((uint8_t)v);
    }
    else if (starts(line, "HWRESET", &a)) cmd_hwreset();
    else if (starts(line, "RST", &a))     cmd_swreset();
    else if (starts(line, "RDP", &a))   { flash_release_dp(); uart_puts("OK\n"); }
    else                                  ERR("cmd");
}

/* ----------------------------------------------------------------- main */
void main(void)
{
    ANSELA = 0; ANSELB = 0; ANSELC = 0;

    /* idle levels before enabling outputs: CS#/WP#/RESET# high, SCK low, LED off */
    CS_PIN = 1; WP_PIN = 1; RST_PIN = 1; SCK_PIN = 0; MOSI_PIN = 0; LED_PIN = 1;
#if defined(BOARD_PIC16F13145)
    TRISBbits.TRISB5 = 0; TRISBbits.TRISB7 = 0; TRISBbits.TRISB4 = 0;      /* CS#, SCLK, RESET# */
    TRISAbits.TRISA4 = 0;                                                   /* WP# */
    TRISCbits.TRISC6 = 0;                                                   /* MOSI */
    TRISCbits.TRISC2 = 0;                                                   /* LED0 */
    TRISCbits.TRISC7 = 1;           /* MISO */
#else
    TRISAbits.TRISA4 = 0; TRISAbits.TRISA5 = 0;
    TRISBbits.TRISB7 = 0;
    TRISCbits.TRISC1 = 0; TRISCbits.TRISC3 = 0; TRISCbits.TRISC7 = 0;
    TRISCbits.TRISC6 = 1;           /* MISO */
#endif
    TRISCbits.TRISC5 = 1;           /* UART RX */
    TRISCbits.TRISC4 = 0;           /* UART TX */

    spi_delay = 0;
    uart_init();
    __delay_ms(50);                 /* let the flash side settle after power-up */
    flash_release_dp();

    for (;;) {
        read_line();
        if (line[0]) execute();
    }
}
