"""SNES stand-in for stable_retro: drives the snes9x libretro core directly through ctypes.

Same idea as the Genesis stable_retro.py from the Buck Rogers project, with SNES specifics:
  env = make(game=NAME); obs, info = env.reset(); obs, r, term, trunc, info = env.step(action12)
  env.get_ram()                         -> numpy uint8 copy of the 128 KB work RAM ($7E0000-$7FFFFF), native order
  env.get_sram() / env.set_sram(b)      -> battery save RAM (cartridge SRAM), if the game has any
  env.em.get_state() / set_state(b)     -> libretro serialize / unserialize (snes9x save-state bytes)
  env.unwrapped.data.memory.extract(addr, '|u1') / assign(addr, '|u1', v)
        addr can be a full SNES address ($7E0000-$7FFFFF, or the $0000-$1FFF low-RAM mirror in banks $00-$3F/$80-$BF)
  env.read_rom(addr, n)                 -> bytes straight from the loaded ROM file (no copier header), by file offset
  env.screen()                          -> current frame as an RGB numpy array
Button order = stable_retro's SNES order: B, Y, SELECT, START, UP, DOWN, LEFT, RIGHT, A, X, L, R
               (= libretro joypad ids 0-11, so the list maps 1:1).
Games: register(name, rom_path); Shadowrun is pre-registered as Shadowrun-Snes (path from $SR_ROM or the uploads folder).
Core path: $SNES_CORE or ./cores/snes9x_libretro.so next to this file. One emulator per process.
SNES runs ~60 frames/s (NTSC): one env.step() = one frame.
"""
import ctypes as C, glob, os, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.environ.get('SNES_CORE', os.path.join(HERE, 'cores', 'snes9x_libretro.so'))


def _default_rom():
    if os.environ.get('SR_ROM'): return os.environ['SR_ROM']
    hits = [p for p in glob.glob('/mnt/user-data/uploads/*') if 'shadowrun' in p.lower()
            and p.lower().endswith(('.sfc', '.smc'))]
    return hits[0] if hits else '/mnt/user-data/uploads/Shadowrun (USA).sfc'


GAMES = {'Shadowrun-Snes': _default_rom()}
SYSDIR = os.path.join(HERE, 'retro_sys'); os.makedirs(SYSDIR, exist_ok=True)

BUTTONS = ['B', 'Y', 'SELECT', 'START', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'A', 'X', 'L', 'R']


def register(name, rom_path): GAMES[name] = os.path.abspath(rom_path)


def action(*names):
    """action('A'), action('UP', 'B') -> 12-element list in stable_retro SNES order."""
    a = [0] * 12
    for n in names: a[BUTTONS.index(n.upper())] = 1
    return a


class _GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIOB_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
LOG_CB = C.CFUNCTYPE(None, C.c_int, C.c_char_p)
INPUT_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

_lib = None; _state = {}


def _load_core():
    global _lib
    if _lib: return _lib
    lib = C.CDLL(CORE)
    st = _state; st['buttons'] = [0] * 16; st['fmt'] = 0; st['frame'] = None; st['vars'] = {}
    st['log'] = LOG_CB(lambda level, fmt: None)
    sysdir = C.create_string_buffer(SYSDIR.encode() + b'\0'); st['sysdir'] = sysdir

    def env_cb(cmd, data):
        cmd &= 0xFFFF                                  # strip the EXPERIMENTAL flag
        if cmd == 3:                                   # GET_CAN_DUPE
            C.cast(data, C.POINTER(C.c_bool))[0] = True; return True
        if cmd in (9, 31):                             # GET_SYSTEM_DIRECTORY / GET_SAVE_DIRECTORY
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(sysdir); return True
        if cmd == 10:                                  # SET_PIXEL_FORMAT
            st['fmt'] = C.cast(data, C.POINTER(C.c_int))[0]; return True
        if cmd == 16 and data:                         # SET_VARIABLES -> remember defaults
            arr = C.cast(data, C.POINTER(C.c_char_p * 2)); i = 0
            while arr[i][0]:
                key, val = arr[i][0], arr[i][1] or b''
                default = val.split(b'; ', 1)[-1].split(b'|')[0]
                st['vars'][key] = C.create_string_buffer(default)
                i += 1
            for kv in os.environ.get('SNES_VARS', '').split(';'):   # e.g. SNES_VARS="snes9x_layer_5=disabled"
                if '=' in kv:
                    k, v = kv.split('=', 1); st['vars'][k.encode()] = C.create_string_buffer(v.encode())
            return True
        if cmd == 15 and data:                         # GET_VARIABLE
            v = C.cast(data, C.POINTER(C.c_void_p * 2))[0]
            key = C.string_at(v[0]) if v[0] else b''
            if key in st['vars']:
                v[1] = C.addressof(st['vars'][key]); return True
            return False
        if cmd == 27 and data:                         # GET_LOG_INTERFACE
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(st['log'], C.c_void_p).value; return True
        if cmd == 17:                                  # GET_VARIABLE_UPDATE
            C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
        if cmd == 52 and data:                         # GET_CORE_OPTIONS_VERSION -> 0 = legacy SET_VARIABLES
            C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
        return False

    def video_cb(data, w, h, pitch):
        if data: st['frame'] = (C.string_at(data, pitch * h), w, h, pitch)

    def input_cb(port, device, index, id_):
        if port != 0 or device != 1: return 0
        if id_ == 256:                                 # RETRO_DEVICE_ID_JOYPAD_MASK
            return sum(1 << i for i, v in enumerate(st['buttons']) if v)
        return st['buttons'][id_] if id_ < 16 else 0

    def audiob_cb(d, n):                              # optional audio capture: st['audio'] = bytearray to record into
        if st.get('audio') is not None and d: st['audio'] += C.string_at(d, 4 * n)
        return n

    st['cbs'] = (ENV_CB(env_cb), VIDEO_CB(video_cb), AUDIO_CB(lambda l, r: None),
                 AUDIOB_CB(audiob_cb), POLL_CB(lambda: None), INPUT_CB(input_cb))
    lib.retro_set_environment(st['cbs'][0]); lib.retro_init()
    lib.retro_set_video_refresh(st['cbs'][1]); lib.retro_set_audio_sample(st['cbs'][2])
    lib.retro_set_audio_sample_batch(st['cbs'][3]); lib.retro_set_input_poll(st['cbs'][4])
    lib.retro_set_input_state(st['cbs'][5])
    lib.retro_get_memory_data.restype = C.c_void_p; lib.retro_get_memory_size.restype = C.c_size_t
    lib.retro_serialize_size.restype = C.c_size_t
    lib.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]; lib.retro_serialize.restype = C.c_bool
    lib.retro_unserialize.argtypes = [C.c_void_p, C.c_size_t]; lib.retro_unserialize.restype = C.c_bool
    lib.retro_load_game.argtypes = [C.POINTER(_GameInfo)]; lib.retro_load_game.restype = C.c_bool
    _lib = lib; return lib


def _wram_offset(addr):
    """Full SNES address -> offset into the 128 KB WRAM, or raise."""
    bank, lo = addr >> 16, addr & 0xFFFF
    if bank in (0x7E, 0x7F): return addr - 0x7E0000
    if (bank <= 0x3F or 0x80 <= bank <= 0xBF) and lo < 0x2000: return lo      # low-RAM mirror
    if addr < 0x20000: return addr                                             # bare offset
    raise ValueError(f'${addr:06X} is not work RAM')


class _Memory:
    def __init__(self, env): self.env = env
    def extract(self, addr, fmt='|u1'):
        assert fmt == '|u1'; return self.env._ram[_wram_offset(addr)]
    def assign(self, addr, fmt, value):
        assert fmt == '|u1'; self.env._ram[_wram_offset(addr)] = value & 0xFF


class _Em:
    def __init__(self, env): self.env = env
    def get_state(self):
        lib = self.env._lib; n = lib.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert lib.retro_serialize(buf, n); return buf.raw
    def set_state(self, data):
        buf = C.create_string_buffer(bytes(data), len(data))
        assert self.env._lib.retro_unserialize(buf, len(data)), 'unserialize failed'


class _Data:
    def __init__(self, env): self.memory = _Memory(env)


class Env:
    def __init__(self, game):
        if _state.get('loaded') not in (None, game):
            raise RuntimeError('one game per process with this stand-in; start a new process for another ROM')
        self._lib = lib = _load_core(); self.game = game
        if not _state.get('loaded'):
            rom = open(GAMES[game], 'rb').read()
            if len(rom) % 0x8000 == 512: rom = rom[512:]           # strip a copier (SMC) header
            _state['rom'] = rom
            self._rombuf = C.create_string_buffer(rom, len(rom)); _state['rombuf'] = self._rombuf
            info = _GameInfo(GAMES[game].encode(), C.cast(self._rombuf, C.c_void_p), len(rom), None)
            assert lib.retro_load_game(C.byref(info)), 'core refused the ROM'
            _state['loaded'] = game
        self.rom = _state['rom']
        ptr = lib.retro_get_memory_data(2); size = lib.retro_get_memory_size(2)     # SYSTEM_RAM
        assert size == 0x20000, f'unexpected work RAM size {size}'
        self._ram = (C.c_uint8 * size).from_address(ptr)
        sp, ss = lib.retro_get_memory_data(0), lib.retro_get_memory_size(0)        # SAVE_RAM
        self._sram = (C.c_uint8 * ss).from_address(sp) if sp and ss else None
        self.em = _Em(self); self.data = _Data(self); self.unwrapped = self
    def reset(self):
        self._lib.retro_reset(); return None, {}
    def step(self, action):
        b = _state['buttons']
        for i in range(12): b[i] = 1 if action[i] else 0
        self._lib.retro_run(); return None, 0.0, False, False, {}
    def get_ram(self):
        return np.frombuffer(bytes(self._ram), dtype=np.uint8).copy()
    def get_sram(self):
        return None if self._sram is None else bytes(self._sram)
    def set_sram(self, data):
        assert self._sram is not None and len(data) == len(self._sram)
        C.memmove(self._sram, bytes(data), len(data))
    def read_rom(self, offset, n): return self.rom[offset:offset + n]
    def screen(self):
        data, w, h, pitch = _state['frame']
        if _state['fmt'] != 2: raise NotImplementedError(f"pixel format {_state['fmt']}")
        a = np.frombuffer(data, np.uint16).reshape(h, pitch // 2)[:, :w]
        r = ((a >> 11) & 31) << 3; g = ((a >> 5) & 63) << 2; bl = (a & 31) << 3
        return np.dstack([r, g, bl]).astype(np.uint8)
    def close(self): pass


def make(game='Shadowrun-Snes', render_mode=None, **kw):
    return Env(game)


def rom_header(rom):
    """Parse the SNES internal header (LoROM $7FC0 or HiROM $FFC0) -> dict."""
    best = None
    for base, kind in ((0x7FC0, 'LoROM'), (0xFFC0, 'HiROM')):
        if len(rom) < base + 0x40: continue
        h = rom[base:base + 0x40]
        chk, comp = h[0x1E] | h[0x1F] << 8, h[0x1C] | h[0x1D] << 8
        score = (chk ^ comp == 0xFFFF) * 2 + all(32 <= c < 127 for c in h[:21])
        if best is None or score > best[0]:
            best = (score, kind, base, h, chk)
    _, kind, base, h, chk = best
    return {'title': h[:21].decode('ascii', 'replace').strip(), 'map': kind, 'map_mode': h[0x15],
            'cart_type': h[0x16], 'rom_kb': 1 << h[0x17], 'sram_kb': (1 << h[0x18]) if h[0x18] else 0,
            'region': h[0x19], 'version': h[0x1B], 'checksum': chk,
            'checksum_ok': (sum(rom) & 0xFFFF) == chk}
