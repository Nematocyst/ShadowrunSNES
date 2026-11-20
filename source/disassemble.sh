#!/bin/sh
# Disassemble Shadowrun (USA) into a WLA-DX project and rebuild it, checking the result is byte-identical.
# Usage: sh disassemble.sh path/to/Shadowrun.sfc [output_dir]
set -e
HERE=$(cd "$(dirname "$0")" && pwd); ROM=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); OUT=${2:-$HERE/sr_asm}
export PATH="$HERE/tools/bin:$HERE/tools/snes2asm/bin:$PATH" PYTHONPATH="$HERE/tools/snes2asm"
python3 "$HERE/tools/snes2asm/bin/snes2asm" -o "$OUT" "$ROM"
cat >> "$OUT/hdr.asm" <<'ASM'

; --- Shadowrun fix: original leftover bytes at $00:FFB0-$FFBF (file $7FB0) that snes2asm drops ---
.BANK 0 SLOT 0
.ORGA $FFB0
.SECTION "PreHeaderLo" FORCE
.db $EB,$FF
.ENDS
.ORGA $FFB6
.SECTION "PreHeaderHi" FORCE
.db $C0,$74,$3D,$00,$03,$00,$75,$0A,$0E,$00
.ENDS
ASM
cd "$OUT" && make >/dev/null
cmp game.smc "$ROM" && echo "OK: rebuilt ROM is byte-identical to the original ($OUT/game.smc)"
