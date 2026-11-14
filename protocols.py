"""Protocol waveform generators for the Spectrum RF project.

Known protocols (the classification target):
    LTE    downlink OFDM, 1.4 MHz carrier (6 RB, 72 subcarriers, 15 kHz spacing), normal/extended CP, PDCCH + PDSCH load,
           PSS/SSS and cell reference signals, FDD or TDD (UL subframes silent)
    DMR    ETSI DMR tier II: 4FSK 4800 sym/s (+-648 / +-1944 Hz), 12.5 kHz channel, 2-slot TDMA of 30 ms, sync words
    P25    APCO P25 phase 1: C4FM 4800 sym/s (+-600 / +-1800 Hz), 12.5 kHz channel, continuous, frame sync word
    TETRA  ETSI TETRA: pi/4-DQPSK 18 ksym/s, RRC 0.35, 25 kHz channel, 4-slot TDMA (14.167 ms slots, 56.67 ms frame)
Distractors (unlabelled hard negatives, in every set): AM (DSB voice), CW (keyed carrier), POCSAG (2-FSK paging, 1200 baud).
Held-out protocols (open-set test only): NBFM (analog voice), WFM (broadcast FM), GSM (GMSK, 8-slot TDMA).

Every generator returns complex baseband centred at 0 Hz at the scene sample rate (`fs`, default 2.56 MS/s) for the whole scene
length. Each protocol is synthesised at its own native rate and resampled (rational polyphase), so the symbol clocks are exact.
`plan_activity` returns the time structure of a transmission: the envelope intervals (what is physically on air, e.g. the
individual TDMA bursts) and the label intervals (bursts separated by less than MERGE_GAP_S are one transmission = one box).

Self-test with images:  python protocols.py   (writes protocol_preview.png next to this file)
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

import numpy as np
from scipy.signal import fftconvolve, resample_poly

DEFAULT_FS = 2_560_000.0
PROTOCOLS = ["LTE", "DMR", "P25", "TETRA"]
UNKNOWN_PROTOCOLS = ["NBFM", "WFM", "GSM"]          # held out: only in test_openset
DISTRACTORS = ["AM", "CW", "POCSAG"]                 # other emitters seen in every set but never labelled: hard negatives the detector must ignore
COARSE = {"LTE": "Wideband", "DMR": "Narrowband", "P25": "Narrowband", "TETRA": "Narrowband",
          "AM": "Distractor", "CW": "Distractor", "POCSAG": "Distractor", "NBFM": "Unknown", "WFM": "Unknown", "GSM": "Unknown"}
MERGE_GAP_S = 5e-3            # bursts closer than this form one labelled transmission (one box)

DMR_SLOT_S = 30e-3            # 2 slots per 60 ms frame
TETRA_SLOT_S = 0.014167       # 4 slots per 56.67 ms frame
GSM_SLOT_S = 576.9e-6         # 8 slots per 4.615 ms frame


# ---------------------------------------------------------------- helpers
def log_uniform(rng, lo, hi):
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


@lru_cache(maxsize=64)
def rrc_taps(sps, beta, span=8):
    """Root-raised-cosine, unit energy, span symbols (sps samples per symbol)."""
    n_t = span * sps
    t = np.arange(-(n_t // 2), n_t // 2 + 1) / sps
    h = np.empty_like(t)
    eps = 1e-6
    z = np.abs(t) < eps
    s = np.abs(np.abs(t) - 1 / (4 * beta)) < eps
    o = ~(z | s)
    h[z] = 1 - beta + 4 * beta / np.pi
    h[s] = beta / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
    to = t[o]
    h[o] = (np.sin(np.pi * to * (1 - beta)) + 4 * beta * to * np.cos(np.pi * to * (1 + beta))) / (np.pi * to * (1 - (4 * beta * to) ** 2))
    return h / np.sqrt(np.sum(h ** 2))


@lru_cache(maxsize=64)
def rc_pulse(sps, beta, span=8):
    """Full raised cosine (= RRC * RRC), unit peak: the ISI-free frequency pulse of 4FSK / C4FM."""
    p = np.convolve(rrc_taps(sps, beta, span), rrc_taps(sps, beta, span))
    return p / p.max()


_TRIM = 4096   # output samples discarded at both ends of a resampled signal (filter transient)


def _resample(x, fs_in, fs_out, n, rng):
    """Resample a native-rate signal to fs_out and return n samples (random start inside the margin)."""
    ratio = Fraction(int(round(fs_out)), 1) / Fraction(fs_in).limit_denominator(10 ** 7)
    up, down = ratio.numerator, ratio.denominator
    y = resample_poly(x, up, down).astype(np.complex64)
    start = _TRIM + int(rng.integers(0, 2000))
    if len(y) < start + n:
        raise RuntimeError("native signal too short")
    return y[start:start + n]


def _native_len(n, fs_in, fs_out):
    return int(np.ceil((n + _TRIM + 2000 + _TRIM) * fs_in / fs_out)) + 16


def _hex_dibits(h):
    bits = bin(int(h, 16))[2:].zfill(len(h) * 4)
    return [int(bits[i:i + 2], 2) for i in range(0, len(bits), 2)]


_LEVEL = {0b01: 3, 0b00: 1, 0b10: -1, 0b11: -3}        # DMR and P25 dibit -> 4FSK level
DMR_SYNC = {"bs_voice": "755FD7DF75F7", "bs_data": "DFF57D75DF5D", "ms_voice": "7F7D5DD57DFD", "ms_data": "D5D7F77FD757"}
P25_SYNC = "5575F5FF77FF"


# ---------------------------------------------------------------- 4FSK family: DMR and P25
def _fsk4(rng, n, fs, unit_hz, beta, syms_fn, rs=4800.0, sps=10):
    fs_nat = rs * sps
    n_nat = _native_len(n, fs_nat, fs)
    n_sym = n_nat // sps + 16
    lev = syms_fn(n_sym)
    up = np.zeros(n_sym * sps)
    up[::sps] = lev
    f = fftconvolve(up, rc_pulse(sps, beta), mode="same")[:n_nat] * unit_hz
    x = np.exp(2j * np.pi * np.cumsum(f) / fs_nat).astype(np.complex64)
    return _resample(x, fs_nat, fs, n, rng)


def gen_dmr(rng, n, fs):
    link = str(rng.choice(["bs_voice", "bs_data", "ms_voice", "ms_data"]))
    sync = [_LEVEL[d] for d in _hex_dibits(DMR_SYNC[link])]          # 24 symbols, sits in the middle of every 144-symbol slot
    unit = 648.0 * rng.uniform(0.95, 1.05)
    phase0 = int(rng.integers(0, 144))

    def syms(m):
        lev = rng.choice([-3, -1, 1, 3], m).astype(float)
        for s0 in range(66 + phase0 - 144, m, 144):
            for k, v in enumerate(sync):
                if 0 <= s0 + k < m:
                    lev[s0 + k] = v
        return lev

    x = _fsk4(rng, n, fs, unit, 0.2, syms)
    return x, dict(link=link, baud=4800.0, dev_unit_hz=unit)


def gen_p25(rng, n, fs):
    sync = [_LEVEL[d] for d in _hex_dibits(P25_SYNC)]                # frame sync once per 864-symbol (180 ms) superframe
    unit = 600.0 * rng.uniform(0.95, 1.05)
    phase0 = int(rng.integers(0, 864))

    def syms(m):
        lev = rng.choice([-3, -1, 1, 3], m).astype(float)
        for s0 in range(phase0 - 864, m, 864):
            for k, v in enumerate(sync):
                if 0 <= s0 + k < m:
                    lev[s0 + k] = v
        return lev

    x = _fsk4(rng, n, fs, unit, 0.2, syms)
    return x, dict(baud=4800.0, dev_unit_hz=unit)


# ---------------------------------------------------------------- TETRA: pi/4-DQPSK
_TETRA_DPHI = {0b00: np.pi / 4, 0b01: 3 * np.pi / 4, 0b11: -3 * np.pi / 4, 0b10: -np.pi / 4}


def gen_tetra(rng, n, fs):
    rs, sps, beta = 18000.0, 8, 0.35
    fs_nat = rs * sps
    n_nat = _native_len(n, fs_nat, fs)
    n_sym = n_nat // sps + 16
    dphi = np.array([_TETRA_DPHI[int(d)] for d in range(4)])[rng.integers(0, 4, n_sym)]
    sym = np.exp(1j * (np.pi / 4 * 0 + np.cumsum(dphi) + rng.uniform(0, 2 * np.pi)))
    up = np.zeros(n_sym * sps, dtype=np.complex128)
    up[::sps] = sym
    y = fftconvolve(up, rrc_taps(sps, beta, 8), mode="same")[:n_nat]
    return _resample(y.astype(np.complex64), fs_nat, fs, n, rng), dict(baud=rs, rolloff=beta)


# ---------------------------------------------------------------- LTE downlink OFDM (1.4 MHz)
def _zc(root, length=62):
    k = np.arange(length)
    return np.exp(-1j * np.pi * root * k * (k + 1) / 63.0)


_QAM = {}


def _qam_points(m):
    if m not in _QAM:
        k = int(np.sqrt(m))
        lv = np.arange(-(k - 1), k, 2)
        c = (lv[:, None] + 1j * lv[None, :]).ravel()
        _QAM[m] = c / np.sqrt(np.mean(np.abs(c) ** 2))
    return _QAM[m]


def gen_lte(rng, n, fs):
    fs_nat, nfft, n_rb = 1_920_000.0, 128, 6
    n_sc = 12 * n_rb                                                  # 72 used subcarriers (DC unused)
    ext_cp = rng.random() < 0.1
    sym_per_slot = 6 if ext_cp else 7
    cps = [32] * 6 if ext_cp else [10] + [9] * 6
    n_nat = _native_len(n, fs_nat, fs)
    n_slots = n_nat // 960 + 3
    n_sub = n_slots // 2 + 1
    sps_ = 2 * sym_per_slot                                           # symbols per 1 ms subframe

    tdd_cfg = int(rng.choice([-1, 0, 1, 2], p=[0.65, 0.1, 0.15, 0.1]))
    dl_sets = {0: {0, 1, 5, 6}, 1: {0, 1, 4, 5, 6, 9}, 2: {0, 1, 3, 4, 5, 6, 8, 9}}
    cell_load = rng.uniform(0.15, 1.0)
    mod_pref = int(rng.choice([4, 16, 64], p=[0.3, 0.35, 0.35]))
    pci = int(rng.integers(0, 504))
    ncfi = int(rng.integers(1, 4))
    crs_shift = pci % 6
    pss_root = (25, 29, 34)[pci % 3]
    sc_idx = np.r_[np.arange(-n_sc // 2, 0), np.arange(1, n_sc // 2 + 1)] % nfft    # FFT bins of the used subcarriers
    sc_pos = np.arange(n_sc)
    crs_cols = (sc_pos % 6 == crs_shift)
    cen62 = np.zeros(n_sc, bool)
    cen62[n_sc // 2 - 31:n_sc // 2 + 31] = True
    sf_off = int(rng.integers(0, 10))
    chunks = []
    for sf in range(n_sub):
        sfn = (sf + sf_off) % 10
        grid = np.zeros((sps_, n_sc), dtype=np.complex128)
        dl = tdd_cfg < 0 or sfn in dl_sets[tdd_cfg]
        if dl:
            rb_on = rng.random(n_rb) < np.clip(cell_load + rng.normal(0, 0.2), 0.05, 1.0)
            if not rb_on.any():
                rb_on[int(rng.integers(0, n_rb))] = True
            col_on = np.repeat(rb_on, 12)
            m = int(rng.choice([4, mod_pref, mod_pref]))
            pts = _qam_points(m)
            for s in range(sps_):
                if s < ncfi:                                           # PDCCH: all subcarriers
                    grid[s] = _qam_points(4)[rng.integers(0, 4, n_sc)]
                else:
                    grid[s, col_on] = pts[rng.integers(0, len(pts), int(col_on.sum()))]
                if s % sym_per_slot in ((0, 3) if ext_cp else (0, 4)):    # cell reference signals on every 6th subcarrier
                    grid[s, crs_cols] = _qam_points(4)[rng.integers(0, 4, int(crs_cols.sum()))] * np.sqrt(2.0)
            if sfn in (0, 5):                                          # SSS then PSS in the last two symbols of the first slot
                grid[sym_per_slot - 2, cen62] = _zc(pss_root + 1) * 1.4
                grid[sym_per_slot - 1, cen62] = _zc(pss_root) * 1.4
            if tdd_cfg >= 0 and sfn in (1, 6):                         # special subframe: 9 symbols of DwPTS
                grid[min(9, sps_):] = 0
        X = np.zeros((sps_, nfft), dtype=np.complex128)
        X[:, sc_idx] = grid
        xt = np.fft.ifft(X, axis=1) * nfft
        for s in range(sps_):
            cp = cps[s % sym_per_slot]
            chunks.append(np.concatenate([xt[s, -cp:], xt[s]]))
    x = np.concatenate(chunks)
    X = np.fft.fft(x)                                                  # transmit filter: +-0.55 MHz flat, -inf at +-0.65 MHz (removes the symbol-edge skirts)
    t = np.clip((np.abs(np.fft.fftfreq(len(x), 1 / fs_nat)) - 0.55e6) / 0.10e6, 0, 1)
    x = np.fft.ifft(X * 0.5 * (1 + np.cos(np.pi * t))).astype(np.complex64)
    if len(x) < n_nat:
        raise RuntimeError("LTE native signal too short")
    info = dict(bw_mhz=1.4, cp="extended" if ext_cp else "normal", duplex="FDD" if tdd_cfg < 0 else f"TDD{tdd_cfg}",
                load=float(cell_load), qam=mod_pref, pci=pci, pdcch_symbols=ncfi)
    return _resample(x, fs_nat, fs, n, rng), info


# ---------------------------------------------------------------- held-out protocols
def _audio(rng, m, fs_a, bw_hz):
    t = np.arange(m) / fs_a
    k = 10
    f = rng.uniform(300.0, bw_hz, k)
    ph = rng.uniform(0, 2 * np.pi, k)
    tl = np.linspace(0, m / fs_a, max(int(m / fs_a * 40), 4) + 4)
    env = np.abs(np.stack([np.interp(t, tl, rng.standard_normal(tl.size)) for _ in range(k)]))
    a = (env * np.sin(2 * np.pi * f[:, None] * t[None, :] + ph[:, None])).sum(0)
    return a / (np.max(np.abs(a)) + 1e-12)


def gen_nbfm(rng, n, fs):
    fs_nat = 51_200.0
    dev = float(rng.choice([2500.0, 5000.0]))
    a = _audio(rng, _native_len(n, fs_nat, fs), fs_nat, rng.uniform(2500, 3000))
    x = np.exp(2j * np.pi * dev * np.cumsum(a) / fs_nat).astype(np.complex64)
    return _resample(x, fs_nat, fs, n, rng), dict(deviation_hz=dev)


def gen_wfm(rng, n, fs):
    fs_nat = 512_000.0
    dev = float(rng.uniform(50e3, 75e3))
    a = _audio(rng, _native_len(n, fs_nat, fs), fs_nat, 15e3)
    x = np.exp(2j * np.pi * dev * np.cumsum(a) / fs_nat).astype(np.complex64)
    return _resample(x, fs_nat, fs, n, rng), dict(deviation_hz=dev)


def gen_gsm(rng, n, fs):
    rs, sps, bt = 13e6 / 48.0, 4, 0.3
    fs_nat = Fraction(13_000_000, 12)                                  # 4 x 270.833 kbaud, exact
    n_nat = _native_len(n, float(fs_nat), fs)
    n_sym = n_nat // sps + 16
    f = np.repeat(2.0 * rng.integers(0, 2, n_sym) - 1.0, sps)
    sigma = np.sqrt(np.log(2)) / (2 * np.pi * bt)
    tt = np.arange(-int(1.5 * sps), int(1.5 * sps) + 1) / sps
    g = np.exp(-tt ** 2 / (2 * sigma ** 2))
    f = fftconvolve(f, g / g.sum(), mode="same")
    x = np.exp(1j * 2 * np.pi * np.cumsum(f * 0.25 * rs) / float(fs_nat)).astype(np.complex64)   # h = 0.5, peak dev = rs / 4
    ratio = Fraction(int(round(fs)), 1) / fs_nat
    y = resample_poly(x, ratio.numerator, ratio.denominator).astype(np.complex64)
    start = _TRIM + int(rng.integers(0, 2000))
    return y[start:start + n], dict(baud=rs, bt=bt)


def gen_am(rng, n, fs):
    """DSB-AM voice-like (carrier plus two sidebands, audio 300 Hz to 3-4 kHz): a narrow line with sidebands."""
    fs_nat = 25_600.0
    bw, m = float(rng.uniform(3000, 4000)), float(rng.uniform(0.3, 0.95))
    a = _audio(rng, _native_len(n, fs_nat, fs), fs_nat, bw)
    x = (1.0 + m * a).astype(np.complex64)
    return _resample(x, fs_nat, fs, n, rng), dict(audio_bw_hz=bw, mod_index=m)


def gen_cw(rng, n, fs):
    """Unmodulated carrier with a little phase noise (keying comes from the burst envelope)."""
    f0 = float(rng.uniform(-200.0, 200.0))
    ph = np.cumsum(rng.standard_normal(n)) * 2 * np.pi * 2.0 / fs                      # about 2 Hz random-walk phase noise
    return np.exp(1j * (2 * np.pi * f0 * np.arange(n) / fs + ph)).astype(np.complex64), dict(offset_hz=f0)


def gen_pocsag(rng, n, fs):
    """POCSAG paging: 2-FSK, 512 / 1200 / 2400 baud, +-4.5 kHz deviation, Gaussian-smoothed (a data signal 10 kHz wide)."""
    baud = float(rng.choice([512.0, 1200.0, 2400.0]))
    sps = 40
    fs_nat = baud * sps
    nn = _native_len(n, fs_nat, fs)
    f = np.repeat(2.0 * rng.integers(0, 2, nn // sps + 4) - 1.0, sps)[:nn]
    g = np.hanning(sps)
    f = np.convolve(f, g / g.sum(), mode="same") * 4500.0
    x = np.exp(2j * np.pi * np.cumsum(f) / fs_nat).astype(np.complex64)
    return _resample(x, fs_nat, fs, n, rng), dict(baud=baud, deviation_hz=4500.0)


GENERATORS = {"LTE": gen_lte, "DMR": gen_dmr, "P25": gen_p25, "TETRA": gen_tetra, "NBFM": gen_nbfm, "WFM": gen_wfm, "GSM": gen_gsm,
              "AM": gen_am, "CW": gen_cw, "POCSAG": gen_pocsag}


def gen_protocol(rng, name, n, fs=DEFAULT_FS):
    """-> (complex64 baseband of length n centred at 0 Hz, dict of the drawn parameters)."""
    return GENERATORS[name](rng, n, fs)


# ---------------------------------------------------------------- time structure
def _s(v, fs):
    return int(round(v * fs))


def _clip(ints, n):
    return [(max(0, a), min(n, b)) for a, b in ints if min(n, b) - max(0, a) >= 2]


def merge_intervals(ints, gap):
    """Merge intervals separated by <= gap samples (one transmission = one box)."""
    out = []
    for a, b in sorted(ints):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _call_window(rng, n, fs):
    """A push-to-talk call is far longer than a 77 ms scene: it spans the whole scene (60%), or starts (20%) or ends (20%) inside it."""
    r = rng.random()
    if r < 0.6:
        return 0, n
    edge = int(rng.uniform(0.1, 0.9) * n)
    return (edge, n) if r < 0.8 else (0, edge)


def _slot_bursts(rng, n, fs, slot_s, n_slots, active, burst_frac, window):
    """Bursts of a TDMA carrier: one per active slot per frame, inside `window` = (start, end) samples."""
    slot = slot_s * fs
    frame = slot * n_slots
    base = rng.uniform(0, frame)
    ints = []
    k0 = int(np.floor((window[0] - base) / slot)) - 1
    k1 = int(np.ceil((window[1] - base) / slot)) + 1
    for k in range(k0, k1 + 1):
        if (k % n_slots) in active:
            a = base + k * slot
            ints.append((int(a), int(a + burst_frac * slot)))
    return _clip([(max(a, window[0]), min(b, window[1])) for a, b in ints], n)


def plan_activity(rng, name, n, fs=DEFAULT_FS):
    """-> (envelope intervals, label intervals, info). Intervals are [start, end) in samples."""
    gap = _s(MERGE_GAP_S, fs)
    info = {}
    if name == "LTE":
        env = [(0, n)]
    elif name == "P25":
        env = [_call_window(rng, n, fs)]
    elif name == "DMR":
        mode = str(rng.choice(["downlink", "uplink_1slot", "uplink_2slot"], p=[0.3, 0.45, 0.25]))
        win = _call_window(rng, n, fs)
        info["dmr_mode"] = mode
        if mode == "downlink":                                          # repeater: continuous 4FSK, both slots
            env = [win]
        else:                                                           # mobile bursts: 27.5 ms in a 30 ms slot
            active = {int(rng.integers(0, 2))} if mode == "uplink_1slot" else {0, 1}
            env = _slot_bursts(rng, n, fs, DMR_SLOT_S, 2, active, 27.5 / 30.0, win)
    elif name == "TETRA":
        mode = str(rng.choice(["downlink_main", "downlink_partial", "uplink_1slot", "uplink_multi"], p=[0.3, 0.25, 0.3, 0.15]))
        info["tetra_mode"] = mode
        if mode == "downlink_main":                                     # BS main carrier: always on, all four slots
            env = [(0, n)]
        else:
            if mode == "uplink_1slot":
                active = {int(rng.integers(0, 4))}
            elif mode == "downlink_partial":
                active = set(int(v) for v in rng.choice(4, int(rng.integers(1, 4)), replace=False))
            else:
                active = set(int(v) for v in rng.choice(4, int(rng.integers(2, 4)), replace=False))
            env = _slot_bursts(rng, n, fs, TETRA_SLOT_S, 4, active, 0.93 if mode.startswith("uplink") else 1.0, _call_window(rng, n, fs)
                               if mode.startswith("uplink") else (0, n))
    elif name == "GSM":
        active = set(int(v) for v in rng.choice(8, int(rng.integers(1, 9)), replace=False))
        env = _slot_bursts(rng, n, fs, GSM_SLOT_S, 8, active, 0.94, (0, n))
    elif name in ("NBFM", "WFM", "AM", "CW", "POCSAG"):
        env = [_call_window(rng, n, fs)]
    else:
        raise ValueError(name)
    if not env:                                                         # window shorter than one slot: fall back to one slot-sized burst
        s0 = int(rng.uniform(0, n * 0.6))
        env = [(s0, min(n, s0 + _s(0.02, fs)))]
    return env, merge_intervals(env, gap), info


# ---------------------------------------------------------------- preview / self-test
if __name__ == "__main__":
    import time
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from numpy.lib.stride_tricks import sliding_window_view
    from scipy.signal import get_window

    fs, n_fft, hop, n_fr = DEFAULT_FS, 2048, 1024, 192
    n = (n_fr - 1) * hop + n_fft
    win = get_window("hann", n_fft)
    names = PROTOCOLS + DISTRACTORS + UNKNOWN_PROTOCOLS
    fig, axes = plt.subplots(2, 5, figsize=(26, 9))
    for ax, name in zip(axes.ravel(), names):
        rng = np.random.default_rng(7)
        t0 = time.time()
        x, info = gen_protocol(rng, name, n, fs)
        env, lab, ainfo = plan_activity(rng, name, n, fs)
        m = np.zeros(n, np.float32)
        for a, b in env:
            m[a:b] = 1
        x = x * m
        fr = sliding_window_view(x, n_fft)[::hop]
        X = np.fft.fftshift(np.fft.fft(fr * win, axis=-1), axes=-1)
        db = 10 * np.log10(np.abs(X) ** 2 / np.sum(win ** 2) + 1e-12)
        pk = db.max()
        ax.imshow(db, aspect="auto", cmap="viridis", vmin=pk - 60, vmax=pk,
                  extent=[-fs / 2e3, fs / 2e3, n / fs * 1e3, 0])
        ax.set_title(f"{name} {ainfo or ''}  ({time.time() - t0:.2f} s, {len(env)} bursts -> {len(lab)} boxes)", fontsize=8)
        ax.set_xlabel("kHz")
        ax.set_ylabel("ms")
        print(f"{name:6s} power={np.mean(np.abs(x[m > 0]) ** 2):.3g}  info={info}  activity={ainfo}  bursts={len(env)} boxes={len(lab)}")
    plt.tight_layout()
    out = Path(__file__).resolve().parent / "protocol_preview.png"
    fig.savefig(out, dpi=80)
    print("wrote", out)
