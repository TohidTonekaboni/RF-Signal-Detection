"""Shared helpers for the Spectrum RF project.

Used by baselines.py, train_classifier.py, train_detector.py and Evaluation.ipynb:
dataset constants, a memory-mapped reader for the sets written by 01_create_dataset.ipynb,
the spectrogram function (identical to the generator), box crops, box matching and metrics.
"""
from __future__ import annotations

import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")   # some ops are missing on Apple MPS

import json
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import get_window

# ---------------------------------------------------------------- constants (must match the generator)
FS = 256_000.0
N_FFT = 1024
HOP = 256
N_FRAMES = 128
N_SAMPLES = (N_FRAMES - 1) * HOP + N_FFT
DF = FS / N_FFT
DB_MIN, DB_MAX = -20.0, 60.0
DB_STEP = (DB_MAX - DB_MIN) / 255.0
PAD_DB = -2.4                                  # typical noise-floor level, used to pad crops at the scene edge
FAMILIES = ["CW", "AM", "FM", "PSK", "QAM", "FSK"]   # class index i  <->  family_id i + 1 in the tables
UNKNOWN_FAMILY_ID = 7
SNR_EDGES = [-np.inf, 5, 10, 15, 20, 25, 30, np.inf]
SNR_LABELS = ["<5", "5-10", "10-15", "15-20", "20-25", "25-30", ">=30"]
CROP_T, CROP_F = 64, 128                       # classifier crop: 64 frames x 128 bins (32 kHz) around a box

PROJECT_DIR = Path(__file__).resolve().parent
TEST_SETS = ["test", "test_1khz", "test_robust", "test_openset", "test_snr_stress"]


# ---------------------------------------------------------------- paths and device
def find_dataset_root(root=None):
    """Explicit path > $SPECTRUM_ROOT > newest dataset/spectrum_rf_v* folder next to this file."""
    root = root or os.environ.get("SPECTRUM_ROOT")
    if root:
        return Path(root)
    found = sorted((PROJECT_DIR / "dataset").glob("spectrum_rf_v*"))
    if not found:
        raise FileNotFoundError("no dataset found: run 01_create_dataset.ipynb or pass --root")
    return found[-1]


def pick_device(name="auto"):
    import torch
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def set_seed(seed):
    import random
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


# ---------------------------------------------------------------- tables and the memory-mapped reader
def load_table(base):
    base = Path(base)
    if base.with_suffix(".parquet").exists():
        return pd.read_parquet(base.with_suffix(".parquet"))
    return pd.read_csv(str(base) + ".csv.gz")


def dequantize_db(q):
    return np.asarray(q).astype(np.float32) * DB_STEP + DB_MIN


def quantize_db(db):
    return np.clip(np.round((np.asarray(db) - DB_MIN) / DB_STEP), 0, 255).astype(np.uint8)


class SetReader:
    """Read one set: reader.spec_db(i), reader.iq(i), reader.boxes(i), reader.scenes / reader.signals tables."""

    def __init__(self, root, set_name, max_scenes=None):
        self.root, self.name = Path(root), set_name
        self.dir = self.root / "sets" / set_name
        if not (self.dir / "_SUCCESS").exists():
            raise FileNotFoundError(f"set '{set_name}' is not complete: {self.dir}")
        self.scenes = load_table(self.dir / "scenes")
        self.signals = load_table(self.dir / "signals")
        if max_scenes:
            self.scenes = self.scenes.iloc[:max_scenes].reset_index(drop=True)
            self.signals = self.signals[self.signals.scene_id.isin(set(self.scenes.scene_id))]
        self._by_scene = {k: g.reset_index(drop=True) for k, g in self.signals.groupby("scene_id")}
        self._empty = self.signals.iloc[0:0]
        self._mm = {}

    def __getstate__(self):                      # do not pickle open memmaps into DataLoader workers
        d = dict(self.__dict__)
        d["_mm"] = {}
        return d

    def __len__(self):
        return len(self.scenes)

    def shard(self, kind, k):
        key = (kind, int(k))
        if key not in self._mm:
            self._mm[key] = np.load(self.dir / f"shard_{int(k):04d}_{kind}.npy", mmap_mode="r")
        return self._mm[key]

    def spec_u8(self, i):
        r = self.scenes.iloc[i]
        return self.shard("spec", r["shard"])[int(r["pos"])]

    def spec_db(self, i):
        return dequantize_db(self.spec_u8(i))

    def iq(self, i):
        r = self.scenes.iloc[i]
        if not (self.dir / f"shard_{int(r['shard']):04d}_iq.npy").exists():
            return None
        raw = np.asarray(self.shard("iq", r["shard"])[int(r["pos"])])
        return ((raw[..., 0].astype(np.float32) + 1j * raw[..., 1].astype(np.float32)) * r["iq_scale"]).astype(np.complex64)

    def boxes(self, i):
        return self._by_scene.get(self.scenes.iloc[i]["scene_id"], self._empty)


# ---------------------------------------------------------------- spectrogram (same STFT as the generator)
_WIN = get_window("hann", N_FFT).astype(np.float32)
_WIN_ENERGY = float(np.sum(_WIN.astype(np.float64) ** 2))


def spectrogram_db(x):
    """Complex baseband (unit-variance noise = 0 dB) -> float32 dB [128 frames, 1024 bins], bins ascending from -fs/2."""
    x = np.asarray(x)[:N_SAMPLES]
    if len(x) < N_SAMPLES:
        raise ValueError(f"need at least {N_SAMPLES} samples, got {len(x)}")
    fr = sliding_window_view(x, N_FFT)[::HOP]
    X = np.fft.fftshift(np.fft.fft(fr * _WIN, axis=-1), axes=-1)
    return (10 * np.log10((X.real ** 2 + X.imag ** 2) / _WIN_ENERGY + 1e-12)).astype(np.float32)


def db_to_gray(db):
    """The image convention of the YOLO export: -10..40 dB -> 0..255."""
    return np.clip((np.asarray(db) + 10.0) / 50.0 * 255.0, 0, 255).astype(np.uint8)


def gray_to_db(img):
    return np.asarray(img).astype(np.float32) / 255.0 * 50.0 - 10.0


# ---------------------------------------------------------------- box helpers (boxes are inclusive [x0, y0, x1, y1] in bins / frames)
def box_center_hz(box):
    return ((box[0] + box[2] + 1) / 2.0 - N_FFT / 2) * DF


def box_bandwidth_hz(box):
    return (box[2] - box[0] + 1) * DF


def box_times_ms(box):
    """Start and end of a box in ms of scene time. Frame k is the window centred at k * HOP + N_FFT / 2 samples."""
    return (box[1] * HOP + N_FFT / 2 - HOP / 2) / FS * 1e3, (box[3] * HOP + N_FFT / 2 + HOP / 2) / FS * 1e3


def box_iou_matrix(a, b):
    a, b = np.asarray(a, float).reshape(-1, 4), np.asarray(b, float).reshape(-1, 4)
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    iw = np.minimum(a[:, None, 2], b[None, :, 2]) - np.maximum(a[:, None, 0], b[None, :, 0]) + 1
    ih = np.minimum(a[:, None, 3], b[None, :, 3]) - np.maximum(a[:, None, 1], b[None, :, 1]) + 1
    inter = np.clip(iw, 0, None) * np.clip(ih, 0, None)
    area_a = (a[:, 2] - a[:, 0] + 1) * (a[:, 3] - a[:, 1] + 1)
    area_b = (b[:, 2] - b[:, 0] + 1) * (b[:, 3] - b[:, 1] + 1)
    return inter / (area_a[:, None] + area_b[None, :] - inter)


def match_detections(pred_boxes, scores, gt_boxes, thr=0.5):
    """Greedy one-to-one matching by descending score. Returns an int array: matched gt index per prediction or -1."""
    out = np.full(len(pred_boxes), -1, dtype=int)
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return out
    iou = box_iou_matrix(pred_boxes, gt_boxes)
    taken = set()
    for p in np.argsort(-np.asarray(scores)):
        order = np.argsort(-iou[p])
        for g in order:
            if iou[p, g] < thr:
                break
            if g not in taken:
                out[p] = g
                taken.add(int(g))
                break
    return out


# ---------------------------------------------------------------- classifier crops
def normalize_db(db):
    return (np.clip(db, -10.0, 40.0) - 5.0) / 15.0


def make_crop(spec, box, shift=(0, 0), mask_jitter=(0, 0, 0, 0), crop_t=CROP_T, crop_f=CROP_F):
    """Two-channel crop around a box: [0] spectrogram in dB (padded with the noise floor), [1] box mask. Returns float32 [2, crop_t, crop_f].

    spec: [T, F] uint8 (quantized) or float dB, anything sliceable (memmap views are fine).
    shift = (frames, bins) moves the crop center; mask_jitter = (dx0, dx1, dy0, dy1) perturbs the mask edges.
    """
    x0, y0, x1, y1 = [int(v) for v in box]
    T, F = spec.shape
    fs0 = (x0 + x1) // 2 + int(shift[1]) - crop_f // 2
    ts0 = (y0 + y1) // 2 + int(shift[0]) - crop_t // 2
    img = np.full((crop_t, crop_f), PAD_DB, np.float32)
    a0, a1, b0, b1 = max(fs0, 0), min(fs0 + crop_f, F), max(ts0, 0), min(ts0 + crop_t, T)
    if a1 > a0 and b1 > b0:
        src = np.asarray(spec[b0:b1, a0:a1])
        if src.dtype == np.uint8:
            src = dequantize_db(src)
        img[b0 - ts0:b1 - ts0, a0 - fs0:a1 - fs0] = src
    mask = np.zeros_like(img)
    j = mask_jitter
    mx0, mx1 = np.clip([x0 + j[0] - fs0, x1 + 1 + j[1] - fs0], 0, crop_f)
    my0, my1 = np.clip([y0 + j[2] - ts0, y1 + 1 + j[3] - ts0], 0, crop_t)
    if mx1 > mx0 and my1 > my0:
        mask[my0:my1, mx0:mx1] = 1.0
    return np.stack([img, mask])


# ---------------------------------------------------------------- metrics
def snr_bin_labels(snr):
    return pd.cut(pd.Series(np.asarray(snr, float)), SNR_EDGES, labels=SNR_LABELS, right=False)


def cls_metrics(y_true, y_pred, snr=None, n_classes=len(FAMILIES)):
    """Accuracy, macro-F1, per-class P/R/F1, confusion matrix and accuracy per SNR bin."""
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    labels = list(range(n_classes))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    out = dict(n=int(len(y_true)), accuracy=float((y_true == y_pred).mean()) if len(y_true) else float("nan"),
               macro_f1=float(f.mean()),
               per_class={FAMILIES[i]: dict(precision=float(p[i]), recall=float(r[i]), f1=float(f[i]), support=int(s[i])) for i in labels},
               confusion=confusion_matrix(y_true, y_pred, labels=labels).tolist())
    if snr is not None:
        b = snr_bin_labels(snr).to_numpy()
        out["acc_by_snr"] = {lab: dict(acc=float((y_true[b == lab] == y_pred[b == lab]).mean()), n=int((b == lab).sum()))
                             for lab in SNR_LABELS if (b == lab).any()}
    return out


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
