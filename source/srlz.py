"""Shadowrun (SNES) graphics decompressor - a Python port of the routine at $809E1E (entries $809E01 / $809ED0).

Block layout (at a 24-bit ROM pointer):
  word 0  decompressed size ($809ED0 reads it; $809E01 = map tile groups always uses $80 = 128 bytes and still skips it)
  word 1  offset of the control bit stream, counted from the block start + 2
  bytes 4.. literal bytes, read forward as they are used
  control stream: 16-bit words read high bit first (big-endian per word)
Decoding, starting with a literal run:
  literal run: n = gamma code (A=1; repeat: bit 1 -> stop, else A = A*2 + next bit); copy n literal bytes
  match:       offset = k bits, k = $809FB6[out_len] while out_len < 256, else $809FB6[out_len >> 8] + 8;
               the offset is ABSOLUTE (from the start of the output); length = gamma + 2
  after each match one bit: 1 -> another match, 0 -> literal run. Stop when out_len >= size.
Map tile graphics: tile id t (14 bits) -> group of four 8x8 4bpp tiles = 128 bytes,
  block = ROM (bank $82 + ((t >> 10) & 15)) : word at $8DA431 + (t >> 1 & ~1); tile = (t & 3) * 32 bytes into it.
Other screens: 3-byte pointers at $80FFB0 + 3*n (title, menus...), decompressed by $81AA58 into $7E23A0.
"""
import sys


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)


class Rom:
    def __init__(self, data): self.d = data
    def b(self, a): return self.d[L(a)]
    def w(self, a): return self.d[L(a)] | self.d[L(a + 1)] << 8   # LoROM: callers stay inside a bank


def decompress(rom, addr, size=None):
    """addr = 24-bit SNES address of the block. Returns (bytes, number of input bytes the stream reached)."""
    R = rom if isinstance(rom, Rom) else Rom(rom)
    bank = addr & 0xFF0000; base = addr & 0xFFFF
    def rb(off): return R.b(bank | ((base + off) & 0xFFFF))
    def rw(off): return rb(off) | rb(off + 1) << 8
    total = rw(0) if size is None else size
    bitpos = rw(2) + 2          # control stream offset
    lit = 4
    state = {'cnt': 0, 'reg': 0, 'pos': bitpos}
    table = [R.b(0x809FB6 + i) for i in range(256)]

    def bit():
        if state['cnt'] == 0:
            state['reg'] = (rb(state['pos']) << 8) | rb(state['pos'] + 1); state['pos'] += 2; state['cnt'] = 16
        state['cnt'] -= 1; v = (state['reg'] >> 15) & 1; state['reg'] = (state['reg'] << 1) & 0xFFFF; return v

    def gamma():
        a = 1
        while not bit(): a = a * 2 + bit()
        return a

    out = bytearray()
    while True:
        n = gamma()
        for _ in range(n): out.append(rb(lit)); lit += 1
        if len(out) >= total: break
        while True:
            pos = len(out)
            k = table[pos] if pos < 256 else table[(pos >> 8) & 0xFF] + 8
            off = 0
            for _ in range(k): off = off * 2 + bit()
            ln = gamma() + 2
            for i in range(ln): out.append(out[off + i])
            if len(out) >= total or not bit(): break
        if len(out) >= total: break
    return bytes(out[:total]), max(lit, state['pos'])


def tile_group_addr(rom, t):
    R = rom if isinstance(rom, Rom) else Rom(rom)
    return ((0x82 + ((t >> 10) & 15)) << 16) | R.w(0x8DA431 + ((t >> 1) & 0x1FFE))


def map_tile(rom, t):
    """32 bytes of 4bpp tile data for map tile id t"""
    data, _ = decompress(rom, tile_group_addr(rom, t), 0x80)
    return data[(t & 3) * 32:(t & 3) * 32 + 32]


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    a = int(sys.argv[2], 16); d, used = decompress(rom, a, int(sys.argv[3], 16) if len(sys.argv) > 3 else None)
    print(len(d), 'bytes out'); print(d[:64].hex(' '))
