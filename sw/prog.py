import argh
from intelhex import IntelHex16bit
from serial import Serial

def read_dev_id(ser: Serial):
    pass

def expect(ser: Serial, expected: bytes):
    actual = ser.read(len(expected))
    if actual!= expected:
        raise ValueError(f'Expected {expected!r}, got {actual!r}')

def prog(ser: Serial, ih: IntelHex16bit):
    # 进入bin模式
    ser.write(b'.\r\n')
    expect(ser, b'.\r\n')

    # 进入编程模式
    ser.write(b'p')
    expect(ser, b'\x00\x00')

    ser.write(b'c')
    expect(ser, b'\x00\x00')

    ser.write(b'r')
    ser.write(b'\x10')
    ser.write(b'\x00')
    l = ser.read(2)
    # print(l)
    data = ser.read(l[0] + l[1] * 16)
    # print(data)
    print(f'Device ID: {hex(data[12] + data[13] * 256)}')

    # 擦除
    ser.write(b'0')
    expect(ser, b'\x00\x00')

    ser.write(b'a')
    expect(ser, b'\x00\x00')

    # 写入数据
    for start, end in ih.segments():
        print(f'Writing segment {start//2:04x} - {end//2:04x}')
        addr = start // 2
        length = (end - start) // 2
        if addr < 0x8000:
            offset = addr
            print(f'Writing {length} words at offset {offset}')

            ser.write(b'0')
            expect(ser, b'\x00\x00')

            for i in range(offset):
                ser.write(b'i')
                expect(ser, b'\x00\x00')

            for i in range(addr, addr+length):
                data = ih[i] & 0x3fff
                # print(hex(data))
                bs = data.to_bytes(2, byteorder='little')
                # print(bs)
                ser.write(b'l')
                ser.write(bs)
                expect(ser, b'\x00\x00')
                if (i + 1) % 16 == 0:
                    ser.write(b'w')
                    expect(ser, b'\x00\x00')
                ser.write(b'i')
                expect(ser, b'\x00\x00')

            if (addr + length) % 16 != 0:
                ser.write(b'w')
                expect(ser, b'\x00\x00')
        else:
            offset = addr - 0x8000
            print(f'Writing {length} words at offset {offset}')

            ser.write(b'c')
            expect(ser, b'\x00\x00')

            for i in range(offset):
                ser.write(b'i')
                expect(ser, b'\x00\x00')

            for i in range(length):
                data = ih[addr+i] & 0x3fff
                # print(hex(data))
                bs = data.to_bytes(2, byteorder='little')
                # print(bs)
                ser.write(b'l')
                ser.write(bs)
                expect(ser, b'\x00\x00')
                ser.write(b'w')
                expect(ser, b'\x00\x00')
                ser.write(b'i')
                expect(ser, b'\x00\x00')

    # 验证数据
    ser.write(b'0')
    expect(ser, b'\x00\x00')

    ser.write(b'r')
    ser.write(b'\x00')
    ser.write(b'\x04')
    l = ser.read(2)
    count = l[0] + (l[1] << 8)
    flash_data = ser.read(count)
    print(f'Read {count} bytes of flash data')

    ser.write(b'c')
    expect(ser, b'\x00\x00')
    ser.write(b'r')
    ser.write(b'\x10')
    ser.write(b'\x00')
    l = ser.read(2)
    count = l[0] + (l[1] << 8)
    config_data = ser.read(count)
    print(f'Read {count} bytes of config data')

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

    # 退出编程模式
    ser.write(b'q')
    expect(ser, b'\x00\x00')

    # 退出bin模式
    ser.write(b'x')
    expect(ser, b'\n> ')

    print(ih.segments())


def main(port: str, hexfile: str):
    ih = IntelHex16bit(hexfile)
    ser = Serial(port, 115200)

    prog(ser, ih)

argh.dispatch_command(main)
