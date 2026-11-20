"""Tiny assembler for Shadowrun's script bytecode (see srscript.py for the opcode table).

    s = Script(header=b'\\x01\\x10')
    s.pop_lb(0); s.label('top'); s.push(10); s.push(1); s.native(0x9E); s.drop(); s.jmp('top')
    blob = s.done()            # header + code, jump operands = offsets from the code start
"""


class Script:
    def __init__(self, header=b'\x01\x10'):
        self.hdr = bytes(header); self.c = bytearray(); self.labels = {}; self.fix = []

    def op(self, *bs): self.c += bytes(bs)
    def label(self, n): self.labels[n] = len(self.c)

    # pushes
    def push(self, v):
        v &= 0xFFFF
        if v == 0: self.op(0xC0)
        elif v < 0x100: self.op(0x00, v)
        elif v >= 0xFF80: self.op(0x0A, v & 0xFF)
        else: self.op(0x14, v & 0xFF, v >> 8)
    def self_(self): self.op(0xC2)                 # push local byte 0 (= self once the script did pop_lb(0))
    def gb(self, addr): self.op(0x04, addr & 0xFF, (addr >> 8) & 0xFF)       # push global byte ($7E:addr)
    def gw(self, addr): self.op(0x18, addr & 0xFF, (addr >> 8) & 0xFF)       # push global word
    def set_gb(self, addr): self.op(0x2E, addr & 0xFF, (addr >> 8) & 0xFF)   # pop into global byte
    def set_gw(self, addr): self.op(0x36, addr & 0xFF, (addr >> 8) & 0xFF)
    def lb(self, n): self.op(0x02, n)
    def pop_lb(self, n): self.op(0x2C, n)
    # ops
    def native(self, n): self.op(0x58, n)
    def drop(self): self.op(0xBC)
    def dup(self): self.op(0xBA)
    def add(self): self.op(0x5C)
    def sub(self): self.op(0x5E)
    def mul(self): self.op(0x60)
    def and_(self): self.op(0x7E)
    def eq(self): self.op(0xAA)
    def ne(self): self.op(0xB2)
    def lt(self): self.op(0x8A)
    def gt(self): self.op(0x9A)
    def spawn(self, sid): self.op(0x52, sid & 0xFF, sid >> 8)
    def end(self): self.op(0x56)
    def _j(self, opc, lab): self.op(opc, 0, 0); self.fix.append((len(self.c) - 2, lab))
    def jz(self, lab): self._j(0x44, lab)
    def jnz(self, lab): self._j(0x46, lab)
    def jmp(self, lab): self._j(0x48, lab)
    # common idioms
    def wait(self, frames):                      # native #9E(1, frames): wait for the timer
        self.push(frames); self.push(1); self.native(0x9E); self.drop()

    def done(self):
        for at, lab in self.fix: self.c[at:at + 2] = self.labels[lab].to_bytes(2, 'little')
        return self.hdr + bytes(self.c)
