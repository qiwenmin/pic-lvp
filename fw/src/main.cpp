#include <Arduino.h>

#include "console.h"

#define LED_PIN 16
#define MCLR_PIN 29
#define DAT_PIN 28
#define CLK_PIN 27

#define ISP_SIG_DELAY asm volatile ("nop\nnop\nnop\nnop\n");

#define ISP_DAT(x) do { ISP_SIG_DELAY; digitalWrite(DAT_PIN, x); } while (0)
#define ISP_CLK(x) do { ISP_SIG_DELAY; digitalWrite(CLK_PIN, x); } while (0)
#define ISP_CLK_OUT do { pinMode(CLK_PIN, OUTPUT); } while (0)
#define ISP_DAT_OUT do { pinMode(DAT_PIN, OUTPUT); } while (0)
#define ISP_CLK_IN do { pinMode(CLK_PIN, INPUT); } while (0)
#define ISP_DAT_IN do { pinMode(DAT_PIN, INPUT); } while (0)
#define ISP_MCLR(x) do { digitalWrite(MCLR_PIN, x); } while (0)

#define ISP_DAT_V (digitalRead(DAT_PIN))

#define ISP_DELAY_US 1
#define ISP_DELAY do { delayMicroseconds(ISP_DELAY_US); } while (0)
#define ISP_DELAY3 do { delayMicroseconds(3*ISP_DELAY_US); } while (0)

static const uint16_t resp_buf_size = 2048;

struct context_t {
    bool bin_mode;
    uint8_t resp_buf[resp_buf_size];
    uint16_t resp_len;
};

static context_t ctx;

void acquire_isp_dat_clk(void)
{
    ISP_DAT(LOW);
    ISP_CLK(LOW);
    ISP_CLK_OUT;
    ISP_DAT_OUT;
}

void release_isp_dat_clk(void)
{
    ISP_CLK_IN;
    ISP_DAT_IN;
}

Console con(&Serial, true);

static void isp_send(uint64_t data, uint8_t bits) {
    ISP_DELAY;

    for (uint8_t i = 0; i < bits; i++) {
        ISP_CLK(HIGH);
        ISP_DAT((data >> i) & 1);

        ISP_DELAY;

        ISP_CLK(LOW);

        ISP_DELAY;
    }

    ISP_DAT(LOW);
}

static uint16_t isp_read_bits(uint8_t bits) {
    ISP_DAT_IN;

    uint16_t data = 0;

    for (auto i = 0; i < bits; i++) {
        ISP_CLK(HIGH);
        ISP_DELAY;

        data = data >> 1;
        if (ISP_DAT_V) {
            data |= 0x8000;
        }

        ISP_CLK(LOW);
        ISP_DELAY;
    }

    ISP_DAT_OUT;
    ISP_DAT(LOW);

    data = data >> (16 - bits);
    data >>= 1;
    data &= 0x3FFF;

    return data;
}

static void cmd_enter_program_mode() {
    acquire_isp_dat_clk();

    ISP_MCLR(0);
    delay(30);
    delayMicroseconds(300);

    //  '0100 1101 0100 0011 0100 1000 0101 0000'
    isp_send(0b01001101010000110100100001010000, 33);
}

static void cmd_exit_program_mode() {
    release_isp_dat_clk();
    ISP_MCLR(HIGH);
    delay(30);
    ISP_MCLR(LOW);
    delay(30);
    ISP_MCLR(HIGH);
}

static void cmd_reset_address() {
    isp_send(0x16, 6);
}

static void cmd_inc_address() {
    isp_send(0x06, 6);
}

static void cmd_load_config() {
    isp_send(0x00, 6);
    ISP_DELAY3;
    isp_send(0x00, 16);
}

static void cmd_read_pgm(uint16_t count) {
    if (count > (resp_buf_size >> 1)) count = (resp_buf_size >> 1);

    for (auto i = 0; i < count; i++) {
        isp_send(0x04, 6); // read program memory
        ISP_DELAY3;
        auto data = isp_read_bits(16);
        ISP_DELAY3;
        isp_send(0x06, 6); // increment address
        ISP_DELAY3;

        ctx.resp_buf[i * 2] = data & 0xFF;
        ctx.resp_buf[i * 2 + 1] = (data >> 8) & 0xFF;
    }
    ctx.resp_len = count * 2;
}

static void cmd_load_data(uint16_t data) {
    isp_send(0x02, 6);
    ISP_DELAY3;
    isp_send(data << 1, 16);
}

static void cmd_erase_row() {
    isp_send(0x11, 6);

    delay(5);
}

static void cmd_erase_all() {
    isp_send(0x09, 6);

    delay(10);
}

static void cmd_prog_it() {
    isp_send(0x08, 6);

    delay(10);
}

static void cmd_prog_et_begin() {
    isp_send(0x18, 6);

    delay(5);
}

static void cmd_prog_et_end() {
    isp_send(0x0a, 6);

    ISP_DELAY3;
}

static void con_enter_program_mode(ArgList& L, Stream& S) {
    cmd_enter_program_mode();
}

static void con_exit_program_mode(ArgList& L, Stream& S) {
    cmd_exit_program_mode();
}

static void con_reset_address(ArgList& L, Stream& S) {
    cmd_reset_address();
}

static void con_inc_address(ArgList& L, Stream& S) {
    cmd_inc_address();
}

static void con_load_config(ArgList& L, Stream& S) {
    cmd_load_config();
}

static void print_hex4(Stream &S, uint16_t data) {
    if (data < 0x10) {
        S.print("000");
    } else if (data < 0x100) {
        S.print("00");
    } else if (data < 0x1000) {
        S.print("0");
    }
    S.print(data, HEX);
}

static void con_read_pgm(ArgList& L, Stream& S) {
    auto p = L.getNextArg();
    uint16_t count = 1;
    if (!p.isEmpty()) {
        count = strtoul(p.c_str(), nullptr, 0);
        if (count == 0) count = 1;
    }

    cmd_read_pgm(count);

    for (auto i = 0; i < (ctx.resp_len >> 1); i++) {
        print_hex4(S, ctx.resp_buf[i * 2] + (ctx.resp_buf[i * 2+ 1] << 8));
        if ((i + 1) % 16 == 0) {
            S.println();
        } else {
            S.print(" ");
        }
    }

    if ((count % 16) != 0)
        S.println();
}

static void con_load_data(ArgList& L, Stream& S) {
    auto p = L.getNextArg();
    uint16_t data = 0;
    if (!p.isEmpty()) {
        data = strtoul(p.c_str(), nullptr, 0);
    }

    cmd_load_data(data);
}

static void con_erase_row(ArgList& L, Stream& S) {
    cmd_erase_row();
}

static void con_erase_all(ArgList& L, Stream& S) {
    cmd_erase_all();
}

static void con_prog_it(ArgList& L, Stream& S) {
    cmd_prog_it();
}

static void con_prog_et_begin(ArgList& L, Stream& S) {
    cmd_prog_et_begin();
}

static void con_prog_et_end(ArgList& L, Stream& S) {
    cmd_prog_et_end();
}

static void resp_bytes(uint8_t* data, uint16_t len) {
    Serial.write(len & 0xFF);
    Serial.write((len >> 8) & 0xFF);
    if (len > 0) Serial.write(data, len);
}

static void bin_enter_program_mode() {
    cmd_enter_program_mode();
    resp_bytes(nullptr, 0);
}

static void bin_exit_program_mode() {
    cmd_exit_program_mode();
    resp_bytes(nullptr, 0);
}

static void bin_reset_address() {
    cmd_reset_address();
    resp_bytes(nullptr, 0);
}

static void bin_inc_address() {
    cmd_inc_address();
    resp_bytes(nullptr, 0);
}

static void bin_load_config() {
    cmd_load_config();
    resp_bytes(nullptr, 0);
}

static void bin_read_pgm() {
    while (Serial.available() == 0) ; // wait
    uint8_t lo = Serial.read();
    while (Serial.available() == 0) ; // wait
    uint8_t hi = Serial.read();
    uint16_t count = (hi << 8) | lo;
    cmd_read_pgm(count);

    resp_bytes(ctx.resp_buf, ctx.resp_len);
}

static void bin_load_data() {
    while (Serial.available() == 0) ; // wait
    uint8_t lo = Serial.read();
    while (Serial.available() == 0) ; // wait
    uint8_t hi = Serial.read();
    uint16_t data = (hi << 8) | lo;
    cmd_load_data(data);

    resp_bytes(nullptr, 0);
}

static void bin_erase_row() {
    cmd_erase_row();
    resp_bytes(nullptr, 0);
}

static void bin_erase_all() {
    cmd_erase_all();
    resp_bytes(nullptr, 0);
}

static void bin_prog_it() {
    cmd_prog_it();
    resp_bytes(nullptr, 0);
}

static void bin_prog_et_begin() {
    cmd_prog_et_begin();
    resp_bytes(nullptr, 0);
}

static void bin_prog_et_end() {
    cmd_prog_et_end();
    resp_bytes(nullptr, 0);
}

static void bin_version() {
    uint8_t version[] = { '0', '1' };

    resp_bytes(version, sizeof(version));
}

static void bin_error() {
    Serial.write('?');
}

static void bin_mode_run() {
    if (Serial.available() > 0) {
        uint8_t c = Serial.read();
        switch (c) {
            case 'p':
                bin_enter_program_mode();
                break;
            case 'q':
                bin_exit_program_mode();
                break;
            case '0':
                bin_reset_address();
                break;
            case 'i':
                bin_inc_address();
                break;
            case 'c':
                bin_load_config();
                break;
            case 'r':
                bin_read_pgm();
                break;
            case 'l':
                bin_load_data();
                break;
            case 'e':
                bin_erase_row();
                break;
            case 'a':
                bin_erase_all();
                break;
            case 'w':
                bin_prog_it();
                break;
            case 'b':
                bin_prog_et_begin();
                break;
            case 'f':
                bin_prog_et_end();
                break;
            case 'v':
                bin_version();
                break;
            case 'x':
                ctx.bin_mode = false;
                Serial.print("\n> ");
                con.setPrompt("> ");
                break;
            case '\r':
            case '\n':
            case ' ':
                break;
            default:
                bin_error();
                break;
        }
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("PIC-LVP started");

    pinMode(LED_PIN, OUTPUT);

    pinMode(MCLR_PIN, OUTPUT);
    ISP_MCLR(HIGH);

    release_isp_dat_clk();

    digitalWrite(LED_PIN, HIGH);

    con.setPrompt("> ");
    con.onCmd("p", con_enter_program_mode);
    con.onCmd("q", con_exit_program_mode);

    con.onCmd("0", con_reset_address);
    con.onCmd("i", con_inc_address);
    con.onCmd("c", con_load_config);
    con.onCmd("r", con_read_pgm);

    con.onCmd("l", con_load_data);

    con.onCmd("e", con_erase_row);
    con.onCmd("a", con_erase_all);

    con.onCmd("w", con_prog_it);
    con.onCmd("b", con_prog_et_begin);
    con.onCmd("f", con_prog_et_end);

    con.onCmd(".", [](ArgList& L, Stream& S) { con.setPrompt(""); ctx.bin_mode = true; });

    ctx.bin_mode = false;
}

void loop() {
    if (ctx.bin_mode) {
        bin_mode_run();
    } else {
        con.run();
    }
}
