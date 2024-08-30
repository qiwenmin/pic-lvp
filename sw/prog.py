import argh
from intelhex import IntelHex16bit
from serial import Serial

def read_dev_id(ser: Serial):
    """暂时未实现"""
    pass

def expect(ser: Serial, expected: bytes):
    actual = ser.read(len(expected))
    if actual!= expected:
        raise ValueError(f'Expected {expected!r}, got {actual!r}')

def exec_cmd(ser: Serial, cmd: bytes, expected: bytes = b'\x00\x00'):
    ser.write(cmd)
    expect(ser, expected)

def enter_prog_mode(ser: Serial):
    # 进入bin模式
    exec_cmd(ser, b'.\r\n', b'.\r\n')

    # 进入编程模式
    exec_cmd(ser, b'p')

def exit_prog_mode(ser: Serial):
    # 退出编程模式
    exec_cmd(ser, b'q')

    # 退出bin模式
    exec_cmd(ser, b'x', b'\n> ')

def load_config(ser: Serial):
    exec_cmd(ser, b'c')

def read_data(ser: Serial, length: int) -> bytes:
    ser.write(b'r')
    ser.write(length.to_bytes(2, byteorder='little'))
    l = ser.read(2)
    data = ser.read(l[0] + (l[1] << 8))
    return data

def reset_address(ser: Serial):
    exec_cmd(ser, b'0')

def erase_all(ser: Serial):
    exec_cmd(ser, b'a')

def inc_address(ser: Serial, offset: int = 1):
    for _ in range(offset):
        exec_cmd(ser, b'i')

def load_data(ser: Serial, data: int):
    exec_cmd(ser, b'l' + data.to_bytes(2, byteorder='little'))

def write_flash(ser: Serial):
    exec_cmd(ser, b'w')

def verify_data(ser: Serial, ih: IntelHex16bit):
    reset_address(ser)
    flash_data = read_data(ser, 0x0400)
    print(f'Read {len(flash_data)} bytes of flash data')

    load_config(ser)
    config_data = read_data(ser, 0x10)

    print(f'Read {len(config_data)} bytes of config data')

    for start, end in ih.segments():
        print(f'Verifying segment {start//2:04x} - {end//2:04x}')
        if start < 0x10000:
            f_dat = flash_data[start:end]
            h_dat = ih.tobinstr(start, end-1)
            if f_dat != h_dat:
                print('Flash data does not match hex file!')
        else:
            for i in range(start//2, end//2):
                ih[i] = ih[i] & 0x3fff

            h_dat = ih.tobinstr(start, end-1)
            c_dat = config_data[start-0x10000:end-0x10000]
            if h_dat != c_dat:
                print('Config data does not match hex file!')
                print(f'h_dat: {h_dat}')
                print(f'c_dat: {c_dat}')

def flash_program(ser: Serial, addr: int, length: int, ih: IntelHex16bit):
    offset = addr
    print(f'Writing {length} words at offset {offset}')

    reset_address(ser)
    inc_address(ser, offset)

    for i in range(addr, addr+length):
        data = ih[i] & 0x3fff
        load_data(ser, data)

        if (i + 1) % 16 == 0:
            write_flash(ser)

        inc_address(ser)

    if (addr + length) % 16 != 0:
        write_flash(ser)

def flash_config(ser: Serial, addr: int, length: int, ih: IntelHex16bit):
    offset = addr - 0x8000
    print(f'Writing {length} words at offset {offset}')

    load_config(ser)

    inc_address(ser, offset)

    for i in range(length):
        data = ih[addr+i] & 0x3fff

        load_data(ser, data)
        write_flash(ser)
        inc_address(ser)

def flash_hex(ser: Serial, ih: IntelHex16bit):
    # 擦除
    reset_address(ser)
    erase_all(ser)

    # 写入数据
    for start, end in ih.segments():
        print(f'Writing segment {start//2:04x} - {end//2:04x}')
        addr = start // 2
        length = (end - start) // 2
        if addr < 0x8000:
            flash_program(ser, addr, length, ih)
        else:
            flash_config(ser, addr, length, ih)

def prog(ser: Serial, ih: IntelHex16bit):

    enter_prog_mode(ser)

    try:
        load_config(ser)

        data = read_data(ser, 0x10)

        device_id = int.from_bytes(data[12:14], byteorder='little')
        print(f'Device ID: {hex(device_id)}')

        # 烧写数据
        flash_hex(ser, ih)

        # 验证数据
        verify_data(ser, ih)

    finally:
        exit_prog_mode(ser)

def main(port: str, hexfile: str):
    ih = IntelHex16bit(hexfile)
    with Serial(port, 115200) as ser:
        prog(ser, ih)

argh.dispatch_command(main)
