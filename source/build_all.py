"""Build the combined "Shadowrun Runner Pack" IPS: Persistent Runners v5 + More Enemies With Runners + Smart Targeting
+ Less Slowdown + Arena Leagues + Glutman's Jobs.

  python3 build_all.py CLEAN_ROM OUT_PREFIX     -> OUT_PREFIX.sfc and OUT_PREFIX.ips (one patch for the clean 1 MB ROM)

Each part still builds on its own (build_runners.py / build_enemies.py / build_targeting.py / build_speed.py /
build_arena.py). They use separate code areas ($BF8000 / $BFE000 / $BFE800 / $BFEC00+$BFF400 / $BE8000) and separate hook bytes, so the combined result is byte-identical to applying
the IPS files files one after another in any order (apart from the header checksum, which is recomputed here).
"""
import sys, zlib
import build_runners, build_enemies, build_targeting, build_speed, build_arena
from build_runners import make_ips

PARTS = [('Persistent Runners v5', build_runners.patch),
         ('More Enemies With Runners v2', build_enemies.patch),
         ('Smart Targeting', build_targeting.patch),
         ('Less Slowdown', build_speed.patch),
         ('Arena Leagues + Glutman\'s Jobs', build_arena.patch)]


def patch(rom):
    for name, fn in PARTS: rom = fn(rom)
    return rom


if __name__ == '__main__':
    clean = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    assert zlib.crc32(clean) == 0x3F34DFF0, 'expects the clean Shadowrun (USA) ROM'
    new = patch(clean)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(clean, new))
    print('parts:', ', '.join(n for n, _ in PARTS)); print('ROM', len(new), 'bytes, CRC32 %08X' % zlib.crc32(new))
