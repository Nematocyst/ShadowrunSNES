"""Shadowrun (SNES) script bytecode disassembler (stack VM run by the interpreter at $80F353).
Usage: python3 srscript.py ROM FILE_OFFSET_HEX [count] [SCRIPT_BASE_HEX]  (jump operands are offsets from the script's base)
Opcode meanings worked out from the handler table at $80F27E; names are best guesses where marked '?'."""
import sys

OPS = {
    0x00: ('push.b', 1), 0x02: ('push.lb', 1), 0x04: ('push.gb', 2), 0x0A: ('push.sb', 1),
    0x0C: ('push.lsb', 1), 0x0E: ('push.gsb', 2), 0x14: ('push.w', 2), 0x16: ('push.lw', 1),
    0x18: ('push.gw', 2), 0x2C: ('pop.lb', 1), 0x2E: ('pop.gb', 2), 0x34: ('pop.lw', 1),
    0x36: ('pop.gw', 2), 0x44: ('jz', 2), 0x46: ('jnz', 2), 0x48: ('jmp', 2), 0x4C: ('call', 2),
    0x50: ('ret', 0), 0x52: ('spawn_script', 2), 0x54: ('end', 0), 0x56: ('yield', 0),
    0x58: ('native', 1), 0x5C: ('add', 0), 0x5E: ('sub', 0), 0x60: ('mul', 0), 0x62: ('mul?', 0),
    0x64: ('?64', 0), 0x66: ('?66', 0), 0x68: ('div', 0), 0x6A: ('div?', 0), 0x6C: ('mod?', 0),
    0x6E: ('mod?', 0), 0x70: ('?70', 0), 0x72: ('?72', 0), 0x74: ('?74', 0), 0x76: ('?76', 0),
    0x78: ('neg', 0), 0x7A: ('shl', 0), 0x7C: ('shr', 0), 0x7E: ('and', 0), 0x80: ('or', 0),
    0x82: ('xor', 0), 0x84: ('not', 0), 0x86: ('inc', 0), 0x88: ('dec', 0), 0x8A: ('lt', 0),
    0x8C: ('lt?', 0), 0x8E: ('lt.s', 0), 0x92: ('le', 0), 0x94: ('le?', 0), 0x96: ('le.s', 0),
    0x9A: ('gt', 0), 0x9C: ('gt?', 0), 0x9E: ('gt.s', 0), 0xA2: ('ge', 0), 0xA4: ('ge?', 0),
    0xA6: ('ge.s', 0), 0xAA: ('eq', 0), 0xAC: ('eq?', 0), 0xAE: ('eq.s', 0), 0xB0: ('eq', 0),
    0xB2: ('ne', 0), 0xB4: ('ne?', 0), 0xB6: ('ne.s', 0), 0xB8: ('ne', 0), 0xBA: ('dup', 0),
    0xBC: ('drop', 0), 0xBE: ('bool', 0), 0xC0: ('push0', 0), 0xC2: ('push.lb0', 0),
}
NATIVE = {0x78: 'HIRE_RUNNER', 0xD5: 'RUNNER_TIME_LEFT', 0x83: 'DISMISS_RUNNER',
          0xAB: 'ADD_COMBATANT', 0xBF: 'REMOVE_COMBATANT'}


def snes(off): return 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)


def dis(rom, off, count=60, base=None):
    out = []
    bank = off & ~0x7FFF
    for _ in range(count):
        op = rom[off]
        if op not in OPS:
            out.append(f'{off:05X}  {op:02X}           ??'); off += 1; continue
        name, n = OPS[op]; v = int.from_bytes(rom[off + 1:off + 1 + n], 'little')
        arg = ''
        if n: arg = f'${v:0{n*2}X}' if n == 2 else f'{v}'
        if op in (0x44, 0x46, 0x48, 0x4C): arg = f'-> {base + v:05X}' if base is not None else f'-> +{v:04X}'
        if op == 0x58 and v in NATIVE: arg += f'  ({NATIVE[v]})'
        out.append(f'{off:05X}  {rom[off:off+1+n].hex(" "):<12} {name} {arg}')
        off += 1 + n
    return out


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    b = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    print('\n'.join(dis(rom, int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 60, b)))
