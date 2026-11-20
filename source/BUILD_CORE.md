# Rebuilding the SNES core (if cores/snes9x_libretro.so is missing)
git clone --depth 1 https://github.com/libretro/snes9x.git
cd snes9x/libretro && make -j8
cp snes9x_libretro.so <folder with snes_retro.py>/cores/
