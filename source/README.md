# Shadowrun (SNES) toolkit

ROM checked: Shadowrun (USA), 1 MB LoROM FastROM, 8 KB battery SRAM, no coprocessor.
SHA-1 b04afb21c94dab5c8b982d0c133898dd5ec1d104, header checksum valid.

* `snes_retro.py` + `cores/snes9x_libretro.so` - headless emulator harness (stable_retro-style API). `SR_ROM=path python3 your_script.py`
* `disassemble.sh` - snes2asm disassembly -> WLA-DX project -> rebuild; verified byte-identical.
* `tools/bin/` - WLA-DX assembler/linker (Linux x86-64 builds). `tools/snes2asm/` - the disassembler (Python, needs PyYAML).
* `states/after_intro.state` - snes9x save state ~30 s into the game (morgue intro).

Rebuild the core: git clone --depth 1 https://github.com/libretro/snes9x.git && cd snes9x/libretro && make
Rebuild WLA-DX: git clone https://github.com/vhelin/wla-dx && cmake -B build wla-dx && make -C build wla-65816 wla-spc700 wlalink
