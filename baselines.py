"""Classical baselines (R&D Section 4): CA/SO-CFAR detector and a feature-based gradient-boosting protocol classifier.

    python baselines.py                          # tune CFAR on val, train the feature classifier on train, evaluate on val
    python baselines.py --max-scenes 300 --no-iq # quick smoke run

Outputs in --out (default runs/baselines): cfar.json, feature_clf.joblib, val_metrics.json.
Only train and val are used here; the frozen test sets are evaluated in Evaluation.ipynb.
"""
from __future__ import annotations

import argparse
import itertools
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
from scipy import ndimage
from scipy.ndimage import convolve1d, uniform_filter, uniform_filter1d
from scipy.signal import fftconvolve, find_peaks, firwin, resample_poly
from scipy.stats import f as f_dist

from spectrum_common import (DF, FAMILIES, FS, HOP, N_FFT, PROJECT_DIR, SetReader, box_bandwidth_hz, box_center_hz, cls_metrics,
                             find_dataset_root, match_detections, save_json, set_seed)

try:
    from tqdm.auto import tqdm
except ImportError:
    def tqdm(x, **kw):
        return x


# =============================================================== CFAR detector
@dataclass
class CFARParams:
    mode: str = "so"          # "ca" = cell averaging, "so" = smallest-of (robust to a neighbour on one side)
    pfa: float = 1e-4
    smooth_t: int = 3         # test statistic = box-car mean over smooth_t frames x smooth_f bins
    smooth_f: int = 3
    train_t: int = 8          # noise is averaged over +-train_t frames
    guard_f: int = 16         # bins excluded around the cell under test (DMR / P25 / TETRA are 6 to 20 bins wide). LTE (about 860 bins) is wider
                              # than guard + training strips, so this detector only finds its edges: a limit of the classical baseline
    train_f: int = 24         # training strip width on each side of the guard
    close_f: int = 2          # merge gaps narrower than this many bins
    min_cells: int = 6        # drop components smaller than this


class CFARDetector:
    """2-D CFAR on the power spectrogram. The noise level is estimated from strips beside the guard region (in frequency only),
    so a continuous signal does not raise its own threshold. Components of the thresholded map become boxes."""

    def __init__(self, params=None, **kw):
        self.p = params or CFARParams(**kw)

    def _noise(self, P):
        p = self.p
        Pt = uniform_filter1d(P, size=2 * p.train_t + 1, axis=0, mode="nearest")
        L = 2 * (p.guard_f + p.train_f) + 1
        kl, kr = np.zeros(L), np.zeros(L)
        kl[:p.train_f] = 1.0 / p.train_f
        kr[-p.train_f:] = 1.0 / p.train_f
        left, right = convolve1d(Pt, kl, axis=1, mode="nearest"), convolve1d(Pt, kr, axis=1, mode="nearest")
        return (left + right) / 2 if p.mode == "ca" else np.minimum(left, right)

    def detect(self, db):
        p = self.p
        P = 10.0 ** (np.asarray(db, np.float32) / 10.0)
        S = uniform_filter(P, size=(p.smooth_t, p.smooth_f), mode="nearest")
        n_cells = (2 if p.mode == "ca" else 1) * p.train_f * (2 * p.train_t + 1)
        alpha = f_dist.isf(p.pfa, 2 * p.smooth_t * p.smooth_f, 2 * n_cells)
        ratio = S / np.maximum(self._noise(P), 1e-9)
        mask = ndimage.binary_closing(ratio > alpha, structure=np.ones((1, p.close_f))) if p.close_f > 1 else ratio > alpha
        labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
        out = []
        for k, sl in enumerate(ndimage.find_objects(labels), 1):
            comp = labels[sl] == k
            if comp.sum() < p.min_cells:
                continue
            out.append(dict(box=(sl[1].start, sl[0].start, sl[1].stop - 1, sl[0].stop - 1),
                            score=float(10 * np.log10(ratio[sl][comp].mean()))))
        return out


def detection_f1(pred_lists, gt_lists, thr=0.5):
    tp = fp = fn = 0
    for pred, gt in zip(pred_lists, gt_lists):
        m = match_detections([d["box"] for d in pred], [d["score"] for d in pred], gt, thr)
        tp += int((m >= 0).sum())
        fp += int((m < 0).sum())
        fn += len(gt) - int((m >= 0).sum())
    return dict(f1=2 * tp / max(2 * tp + fp + fn, 1), precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1), tp=tp, fp=fp, fn=fn)


def gt_boxes(reader, i):
    b = reader.boxes(i)
    b = b[b.family_id <= len(FAMILIES)]                    # distractors (AM, CW, POCSAG) and held-out signals are not targets
    return [(r.box_x0, r.box_y0, r.box_x1, r.box_y1) for r in b.itertuples()]


def tune_cfar(reader, n_scenes=150, log=print):
    """Grid search on the validation set (never on test): maximise F1 at IoU 0.5."""
    idx = np.random.default_rng(0).choice(len(reader), min(n_scenes, len(reader)), replace=False)
    dbs = [reader.spec_db(int(i)) for i in idx]
    gts = [gt_boxes(reader, int(i)) for i in idx]
    best, rows = None, []
    grid = itertools.product(["ca", "so"], [1e-2, 1e-3, 1e-4, 1e-5, 1e-6], [(3, 3), (3, 5), (2, 4)], [4, 10])
    for mode, pfa, (st, sf), mc in tqdm(list(grid), desc="tune CFAR"):
        det = CFARDetector(CFARParams(mode=mode, pfa=pfa, smooth_t=st, smooth_f=sf, min_cells=mc))
        res = detection_f1([det.detect(d) for d in dbs], gts)
        rows.append(dict(mode=mode, pfa=pfa, smooth=(st, sf), min_cells=mc, **res))
        if best is None or res["f1"] > best[0]:
            best = (res["f1"], det.p)
    log(f"best CFAR on {len(idx)} val scenes: F1={best[0]:.3f} {asdict(best[1])}")
    return best[1], rows


# =============================================================== hand-crafted features
def spec_features(db, box):
    """Features of one box from the dB spectrogram (shape, level, spectral and temporal statistics)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    F = db.shape[1]
    reg = db[y0:y1 + 1, x0:x1 + 1]
    h, w = reg.shape
    pw = 10.0 ** (reg / 10.0)
    prof, tprof = pw.mean(0), pw.mean(1)
    prof_db, tprof_db = 10 * np.log10(prof + 1e-12), 10 * np.log10(tprof + 1e-12)
    bins = np.arange(w)
    pn = prof / prof.sum()
    cen = (pn * bins).sum()
    sd = np.sqrt((pn * (bins - cen) ** 2).sum()) + 1e-9
    smooth = uniform_filter1d(prof, 3) if w >= 3 else prof
    peaks, _ = find_peaks(smooth, prominence=0.15 * smooth.max())
    c = w // 2
    lo, hi = max(x0 - 6, 0), min(x1 + 7, F)
    ext = db[y0:y1 + 1, lo:hi].mean(0)
    reg_prof = reg.mean(0)
    drops = []
    if x0 - lo > 0:
        drops.append(reg_prof[:3].mean() - ext[:x0 - lo].mean())
    if hi - 1 - x1 > 0:
        drops.append(reg_prof[-3:].mean() - ext[x1 - lo + 1:].mean())
    cent_t = (pw * bins).sum(1) / pw.sum(1)
    lag1 = np.corrcoef(tprof_db[:-1], tprof_db[1:])[0, 1] if h >= 4 and tprof_db.std() > 1e-6 else 0.0
    return dict(
        width_bins=w, height_frames=h, log_area=np.log(w * h),
        mean_db=reg.mean(), std_db=reg.std(), max_db=reg.max(), p10_db=np.percentile(reg, 10), p90_db=np.percentile(reg, 90),
        peak_to_mean_db=reg.max() - reg.mean(),
        flatness=np.exp(np.mean(np.log(prof + 1e-12))) / (prof.mean() + 1e-12), peak_ratio=prof.max() / prof.mean(),
        center_ratio=prof[max(c - 1, 0):c + 2].mean() / prof.mean(),
        prof_skew=(pn * ((bins - cen) / sd) ** 3).sum(), prof_kurt=(pn * ((bins - cen) / sd) ** 4).sum(), prof_sd_frac=sd / w,
        n_peaks=len(peaks), peak_spacing=np.diff(peaks).mean() / w if len(peaks) >= 2 else 0.0,
        edge_drop_db=float(np.mean(drops)) if drops else np.nan,
        bw3_frac=(prof_db > prof_db.max() - 3).sum() / w, bw10_frac=(prof_db > prof_db.max() - 10).sum() / w,
        cv_time=tprof.std() / tprof.mean(), std_time_db=tprof_db.std(), lag1_time=float(np.nan_to_num(lag1)),
        texture=reg.std(0).mean() if h > 1 else 0.0,
        wander=cent_t.std() / w, peak_wander=reg.argmax(1).std() / w)


NB_FEATURES = ["nb_lvl_hi", "nb_lvl_lo", "nb_ratio", "nb_spread", "nb_sync_dmr", "nb_sync_p25"]
IQ_FEATURES = ["env_kurt", "env_cv", "env_papr", "inst_freq_std"] + NB_FEATURES

_NB_LP = firwin(255, 8_000.0, fs=320_000.0)             # channel filter at 320 kS/s: keeps the 12.5 kHz channel, rejects neighbours


def _sync_templates():
    """DMR (4 sync words) and P25 (1 frame sync word) as 24-symbol 4FSK level sequences (the same words the generator embeds)."""
    from protocols import DMR_SYNC, P25_SYNC, _LEVEL, _hex_dibits
    dmr = [np.array([_LEVEL[d] for d in _hex_dibits(h)]) for h in DMR_SYNC.values()]
    return dmr, np.array([_LEVEL[d] for d in _hex_dibits(P25_SYNC)])


def nb_features(iq, box, max_bw_hz=16_000.0):
    """4FSK features of a narrowband box from the stored IQ, to separate DMR from P25 (both 4800 baud, 12.5 kHz).

    The box is mixed to 0 Hz, filtered and decimated to 48 kS/s (10 samples per symbol) and FM demodulated. At the best symbol timing the
    instantaneous frequency falls on four levels: +-u and +-3u with u = 648 Hz (DMR) or 600 Hz (P25), so the outer level is 1944 or 1800 Hz.
    Features: the two level magnitudes (2-means on |f|), their ratio (ideal 3), the within-level spread, and the best symbol match (0 to 1) of
    the sliced symbols with the DMR sync words and with the P25 frame sync word (random data gives about 0.5 at the best of ~300 offsets)."""
    nan = dict.fromkeys(NB_FEATURES, np.nan)
    if iq is None or box_bandwidth_hz(box) > max_bw_hz:
        return nan
    x0, y0, x1, y1 = [int(v) for v in box]
    seg = iq[max(y0 * HOP + N_FFT // 2 - HOP // 2, 0):y1 * HOP + N_FFT // 2 + HOP // 2]
    if len(seg) < 20_000:                                   # under 8 ms: too few symbols
        return nan
    z = seg * np.exp(-2j * np.pi * box_center_hz(box) / FS * np.arange(len(seg)))
    z = resample_poly(z, 1, 8)                              # 2.56 MS/s -> 320 kS/s
    z = fftconvolve(z, _NB_LP, mode="same")
    z = resample_poly(z, 3, 20)[20:-20]                     # 320 kS/s -> 48 kS/s
    if len(z) < 400:
        return nan
    def two_means(a):                                       # 1-D 2-means on |f|: inner and outer level magnitude
        c = np.array([np.percentile(a, 25), np.percentile(a, 90)])
        for _ in range(15):
            hi = a > c.mean()
            if hi.all() or (~hi).all():
                break
            c = np.array([np.median(a[~hi]), np.median(a[hi])])
        return c

    # (1) levels: mean frequency over one symbol (10 samples), far less noisy than the instantaneous frequency
    fw = np.angle(z[10:] * np.conj(z[:-10])) * 4_800.0 / (2 * np.pi)
    fw = fw - np.median(fw)
    aw = np.abs(fw[int(np.argmax([np.abs(fw[o::10]).mean() for o in range(10)]))::10])
    c = two_means(aw)
    hi = aw > c.mean()
    spread = float(np.sqrt((np.sum((aw[hi] - c[1]) ** 2) + np.sum((aw[~hi] - c[0]) ** 2)) / len(aw)) / max(c[1], 1.0))

    # (2) sync words: instantaneous frequency at the symbol centres (ISI-free for the raised-cosine pulse), sliced to the four levels
    fi = np.convolve(np.angle(z[1:] * np.conj(z[:-1])) * 48_000.0 / (2 * np.pi), np.ones(3) / 3, mode="same")
    fi = fi - np.median(fi)
    v = fi[int(np.argmax([np.abs(fi[o::10]).mean() for o in range(10)]))::10]
    ci = two_means(np.abs(v))
    sym = np.sign(v) * np.where(np.abs(v) > ci.mean(), 3.0, 1.0)
    dmr_t, p25_t = _sync_templates()
    if len(sym) < 24:
        return nan
    win = np.lib.stride_tricks.sliding_window_view(sym, 24)
    best = lambda t: float((win == t).mean(axis=1).max())
    return dict(nb_lvl_hi=float(c[1]), nb_lvl_lo=float(c[0]), nb_ratio=float(c[1] / max(c[0], 1.0)), nb_spread=spread,
                nb_sync_dmr=max(best(t) for t in dmr_t), nb_sync_p25=best(p25_t))


def iq_features(iq, box):
    """Rotation-invariant envelope / instantaneous-frequency statistics of the signal isolated from the stored IQ."""
    nan = dict.fromkeys(IQ_FEATURES, np.nan)
    if iq is None:
        return nan
    x0, y0, x1, y1 = [int(v) for v in box]
    seg = iq[max(y0 * HOP + N_FFT // 2 - HOP // 2, 0):y1 * HOP + N_FFT // 2 + HOP // 2]
    if len(seg) < 256:
        return nan
    bw = box_bandwidth_hz(box)
    z = seg * np.exp(-2j * np.pi * box_center_hz(box) / FS * np.arange(len(seg)))
    Z = np.fft.fft(z)
    Z[np.abs(np.fft.fftfreq(len(seg), 1 / FS)) > bw / 2 + 500.0] = 0
    x = np.fft.ifft(Z)
    a = np.abs(x)
    m2 = np.mean(a ** 2) + 1e-12
    inst = np.angle(x[1:] * np.conj(x[:-1])) * FS / (2 * np.pi)
    return dict(env_kurt=np.mean(a ** 4) / m2 ** 2, env_cv=a.std() / (a.mean() + 1e-12), env_papr=a.max() ** 2 / m2, inst_freq_std=inst.std() / max(bw, 1.0),
                **nb_features(iq, box))


def box_features(db, box, iq=None, use_iq=True):
    f = spec_features(db, box)
    if use_iq:
        f.update(iq_features(iq, box))
    return f


def build_feature_table(reader, use_iq=True, include_unknown=False, desc="features"):
    import pandas as pd
    rows = []
    for i in tqdm(range(len(reader)), desc=desc):
        bx = reader.boxes(i)
        if len(bx) == 0:
            continue
        db = reader.spec_db(i)
        iq = reader.iq(i) if use_iq else None
        for b in bx.itertuples():
            if b.family_id > len(FAMILIES) and not include_unknown:
                continue
            f = box_features(db, (b.box_x0, b.box_y0, b.box_x1, b.box_y1), iq, use_iq)
            f.update(label=int(b.family_id) - 1, snr_db=float(b.snr_db), scene_idx=i)
            rows.append(f)
    return pd.DataFrame(rows)


# =============================================================== feature classifier
def make_gb(kind="hgb", n_jobs=-1):
    """kind "hgb" = scikit-learn HistGradientBoosting (default). "xgboost" is opt-in: on macOS it segfaults once torch has been imported
    (two OpenMP runtimes in one process), which set_seed() does."""
    try:
        if kind != "xgboost":
            raise ImportError("scikit-learn boosting requested")
        from xgboost import XGBClassifier
        return XGBClassifier(objective="multi:softprob", n_estimators=300, max_depth=6, learning_rate=0.1, subsample=0.8,
                             colsample_bytree=0.8, tree_method="hist", n_jobs=n_jobs), "xgboost"
    except Exception as e:      # xgboost missing or its OpenMP runtime unavailable
        from sklearn.ensemble import HistGradientBoostingClassifier
        if kind == "xgboost":
            print(f"xgboost unavailable ({type(e).__name__}); using sklearn HistGradientBoostingClassifier")
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, max_depth=8, early_stopping=True, random_state=0), "sklearn-hgb"


class FeatureClassifier:
    """Gradient-boosting family classifier on hand-crafted box features."""

    def __init__(self, model, names, use_iq, backend):
        self.model, self.names, self.use_iq, self.backend = model, list(names), use_iq, backend

    @classmethod
    def load(cls, path):
        d = joblib.load(path)
        return cls(d["model"], d["names"], d["use_iq"], d["backend"])

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(dict(model=self.model, names=self.names, use_iq=self.use_iq, backend=self.backend), path)

    def predict_proba(self, db, boxes, iq=None):
        if len(boxes) == 0:
            return np.zeros((0, len(FAMILIES)))
        feats = [box_features(db, b, iq, self.use_iq) for b in boxes]
        X = np.array([[f[n] for n in self.names] for f in feats], dtype=np.float32)
        return self.model.predict_proba(X)


def train_feature_classifier(train_reader, val_reader, use_iq=True, gb="hgb"):
    from sklearn.utils.class_weight import compute_sample_weight
    tr = build_feature_table(train_reader, use_iq, desc="train features")
    va = build_feature_table(val_reader, use_iq, desc="val features")
    names = [c for c in tr.columns if c not in ("label", "snr_db", "scene_idx") and tr[c].notna().any()]   # IQ features are all NaN when no IQ is stored
    model, backend = make_gb(gb)
    t0 = time.time()
    model.fit(tr[names].to_numpy(np.float32), tr["label"].to_numpy(), sample_weight=compute_sample_weight("balanced", tr["label"]))
    pred = model.predict(va[names].to_numpy(np.float32))
    metrics = cls_metrics(va["label"], pred, va["snr_db"])
    metrics.update(backend=backend, train_boxes=len(tr), val_boxes=len(va), fit_seconds=time.time() - t0)
    return FeatureClassifier(model, names, use_iq, backend), metrics


# =============================================================== CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="dataset folder (default: newest in ./dataset)")
    ap.add_argument("--out", default=str(PROJECT_DIR / "runs" / "baselines"))
    ap.add_argument("--max-scenes", type=int, default=None, help="use only the first N scenes of train and val (smoke test)")
    ap.add_argument("--tune-scenes", type=int, default=150, help="validation scenes used to tune CFAR")
    ap.add_argument("--no-iq", action="store_true", help="spectrogram features only (no envelope statistics from the stored IQ)")
    ap.add_argument("--gb", default="hgb", choices=["hgb", "xgboost"], help="boosting backend (xgboost can segfault on macOS when torch is loaded)")
    ap.add_argument("--skip-cfar", action="store_true")
    ap.add_argument("--skip-features", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    set_seed(a.seed)
    root, out = find_dataset_root(a.root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    val = SetReader(root, "val", a.max_scenes)
    metrics = {}
    if not a.skip_cfar:
        params, rows = tune_cfar(val, a.tune_scenes)
        save_json(asdict(params), out / "cfar.json")
        save_json(rows, out / "cfar_tuning.json")
        metrics["cfar_tuned_f1_val_subset"] = max(r["f1"] for r in rows)
    if not a.skip_features:
        clf, m = train_feature_classifier(SetReader(root, "train", a.max_scenes), val, use_iq=not a.no_iq, gb=a.gb)
        clf.save(out / "feature_clf.joblib")
        metrics["feature_classifier_val"] = m
        print(f"feature classifier ({m['backend']}) val accuracy {m['accuracy']:.3f}  macro-F1 {m['macro_f1']:.3f}")
    save_json(metrics, out / "val_metrics.json")
    print("saved to", out)


if __name__ == "__main__":
    main()
