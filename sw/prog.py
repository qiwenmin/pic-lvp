import argh
from intelhex import IntelHex16bit
from serial import Serial
from processors import processors

VERSION = '0.1.0'

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

def verify_data(ser: Serial, ih: IntelHex16bit, p: dict):
    flash_size = p['flash_size']
    config_size = p['config_size']
    word_mask = p['word_mask']

    reset_address(ser)
    flash_data = read_data(ser, flash_size)
    print(f'Read {len(flash_data)//2} words of flash data')

    load_config(ser)
    config_data = read_data(ser, config_size)
    config_addr = p['config_address']
    config_start = config_addr * 2
    print(f'Read {len(config_data)//2} words of config data')

    for start, end in ih.segments():
        print(f'Verifying segment {start//2:04x} - {end//2:04x}')
        if start < config_start:
            f_dat = flash_data[start:end]
            h_dat = ih.tobinstr(start, end-1)
            if f_dat != h_dat:
                print('Flash data does not match hex file!')
        else:
            for i in range(start//2, end//2):
                ih[i] = ih[i] & word_mask

            h_dat = ih.tobinstr(start, end-1)
            c_dat = config_data[start-config_start:end-config_start]
            if h_dat != c_dat:
                print('Config data does not match hex file!')
                print(f'h_dat: {h_dat}')
                print(f'c_dat: {c_dat}')

def flash_program(ser: Serial, addr: int, length: int, ih: IntelHex16bit, p: dict):
    word_mask = p['word_mask']

    offset = addr
    print(f'Writing {length} words at offset {offset}')

    reset_address(ser)
    inc_address(ser, offset)

    for i in range(addr, addr+length):
        data = ih[i] & word_mask
        load_data(ser, data)

        if (i + 1) % 16 == 0:
            write_flash(ser)

        inc_address(ser)

    if (addr + length) % 16 != 0:
        write_flash(ser)

def flash_config(ser: Serial, addr: int, length: int, ih: IntelHex16bit, p: dict):
    config_address = p['config_address']
    word_mask = p['word_mask']

    offset = addr - config_address
    print(f'Writing {length} words at offset {offset}')

    load_config(ser)

    inc_address(ser, offset)

    for i in range(length):
        data = ih[addr+i] & word_mask

        load_data(ser, data)
        write_flash(ser)
        inc_address(ser)

def flash_hex(ser: Serial, ih: IntelHex16bit, p: dict):
    config_address = p['config_address']

    # 擦除
    reset_address(ser)
    erase_all(ser)

    # 写入数据
    for start, end in ih.segments():
        print(f'Writing segment {start//2:04x} - {end//2:04x}')
        addr = start // 2
        length = (end - start) // 2
        if addr < config_address:
            flash_program(ser, addr, length, ih, p)
        else:
            flash_config(ser, addr, length, ih, p)

def prog(ser: Serial, ih: IntelHex16bit, p: dict, verify_only: bool):

    enter_prog_mode(ser)

    try:
        load_config(ser)

        config_addr = p['config_address']
        config_size = p['config_size']

        data = read_data(ser, config_size)

        (device_id_addr, device_id_mask, device_id_value) = p['device_id']
        config_addr = p['config_address']

        device_id_offset = (device_id_addr - config_addr) * 2

        read_device_id = int.from_bytes(data[device_id_offset:device_id_offset+2], byteorder='little') & device_id_mask
        if read_device_id != device_id_value:
            print(f'Device ID mismatch. Expected {hex(device_id_value)}, got {hex(read_device_id)}')
            raise ValueError('Device ID mismatch')

        print(f'Device ID: {hex(read_device_id)}')

        # 烧写数据
        if not verify_only:
            flash_hex(ser, ih, p)

        # 验证数据
        verify_data(ser, ih, p)

        #  成功
        print('Done.')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        exit_prog_mode(ser)

@argh.arg('-P', '--port', help='Serial port')
@argh.arg('-f', '--hexfile', help='Hex file')
@argh.arg('-p', '--processor', help='Processor type')
@argh.arg('-n', '--verify-only', help='Verify only', default=False, action='store_true')
@argh.arg('-l', '--list-processors', help='List supported processors', default=False, action='store_true')
def main(port: str = None, hexfile: str = None, processor: str = None, verify_only: bool = False, list_processors: bool = False):
    print(f'pic-lvp programmer v{VERSION}')

    if list_processors:
        print('Supported processors:')
        for p in processors:
            print(f'- {p}')
        return

    if processor is None:
        print('Processor not specified. Please specify processor type.')
        return

    p = processors.get(processor)
    if p is None:
        print(f'Processor {processor} not found.')
        return

    if (hexfile is None) or (port is None):
        print('Hex file and serial port must be specified.')
        return

    ih = IntelHex16bit(hexfile)
    with Serial(port, 115200) as ser:
        prog(ser, ih, p, verify_only)

argh.dispatch_command(main)
