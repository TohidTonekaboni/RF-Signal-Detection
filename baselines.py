"""Classical baselines (R&D Section 4): CA/SO-CFAR detector and a feature-based gradient-boosting classifier.

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
from scipy.signal import find_peaks
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
    guard_f: int = 40         # bins excluded around the cell under test (signals up to about 20 kHz wide)
    train_f: int = 40         # training strip width on each side of the guard
    close_f: int = 3          # merge gaps (AM carrier/sidebands, FSK tones) narrower than this many bins
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


IQ_FEATURES = ["env_kurt", "env_cv", "env_papr", "inst_freq_std"]


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
    return dict(env_kurt=np.mean(a ** 4) / m2 ** 2, env_cv=a.std() / (a.mean() + 1e-12), env_papr=a.max() ** 2 / m2, inst_freq_std=inst.std() / max(bw, 1.0))


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
            if b.family_id > 6 and not include_unknown:
                continue
            f = box_features(db, (b.box_x0, b.box_y0, b.box_x1, b.box_y1), iq, use_iq)
            f.update(label=int(b.family_id) - 1, snr_db=float(b.snr_db), scene_idx=i)
            rows.append(f)
    return pd.DataFrame(rows)


# =============================================================== feature classifier
def make_gb(n_jobs=-1):
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(objective="multi:softprob", n_estimators=300, max_depth=6, learning_rate=0.1, subsample=0.8,
                             colsample_bytree=0.8, tree_method="hist", n_jobs=n_jobs), "xgboost"
    except Exception as e:      # xgboost missing or its OpenMP runtime unavailable
        from sklearn.ensemble import HistGradientBoostingClassifier
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


def train_feature_classifier(train_reader, val_reader, use_iq=True):
    from sklearn.utils.class_weight import compute_sample_weight
    tr = build_feature_table(train_reader, use_iq, desc="train features")
    va = build_feature_table(val_reader, use_iq, desc="val features")
    names = [c for c in tr.columns if c not in ("label", "snr_db", "scene_idx")]
    model, backend = make_gb()
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
        clf, m = train_feature_classifier(SetReader(root, "train", a.max_scenes), val, use_iq=not a.no_iq)
        clf.save(out / "feature_clf.joblib")
        metrics["feature_classifier_val"] = m
        print(f"feature classifier ({m['backend']}) val accuracy {m['accuracy']:.3f}  macro-F1 {m['macro_f1']:.3f}")
    save_json(metrics, out / "val_metrics.json")
    print("saved to", out)


if __name__ == "__main__":
    main()
