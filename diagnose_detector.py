"""Break the detector's box quality down by SNR, family, bandwidth and duration, to see where recall and box regression fail.

    python diagnose_detector.py                                     # runs/detector/best.pt on val, conf 0.25, IoU 0.5
    python diagnose_detector.py --weights runs/detector_1cls/best.pt --conf 0.1
    python diagnose_detector.py --max-scenes 100                    # quick look

Matching is class-agnostic (greedy one-to-one by score), so the numbers describe localisation; "cls acc" is the family accuracy of the
matched boxes (6-class detector only). Per group: n ground-truth boxes, recall, mean IoU of the matched boxes, mean absolute error of the
four box edges (x0 / x1 in frequency bins, y0 / y1 in time frames) and how many of the misses have a prediction with IoU >= 0.1 (poorly
placed rather than not found). Uses val by default; the frozen test sets are for Evaluation.ipynb. Writes diagnose_<set>.json next to the weights.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from spectrum_common import FAMILIES, PROJECT_DIR, SetReader, box_iou_matrix, find_dataset_root, match_detections, save_json, snr_bin_labels
from train_detector import Detector


def collect(det, reader, conf, thr, chunk=64):
    """One row per ground-truth box (matched or not) plus the number of false-positive predictions."""
    rows, n_fp = [], 0
    for s in range(0, len(reader), chunk):
        idx = list(range(s, min(s + chunk, len(reader))))
        for i, dets in zip(idx, det.detect_batch([reader.spec_db(i) for i in idx], conf=conf)):
            gt = reader.boxes(i)
            gt = gt[gt.family_id <= len(FAMILIES)].reset_index(drop=True)
            pb = np.array([d["box"] for d in dets]).reshape(-1, 4)
            gb = gt[["box_x0", "box_y0", "box_x1", "box_y1"]].to_numpy(int)
            m = match_detections(pb, [d["score"] for d in dets], gb, thr)
            n_fp += int((m < 0).sum())
            iou = box_iou_matrix(pb, gb)
            pred_of = {int(g): p for p, g in enumerate(m) if g >= 0}
            for g, r in enumerate(gt.itertuples()):
                p = pred_of.get(g)
                row = dict(family=r.family, snr=r.snr_db, bw=gb[g, 2] - gb[g, 0] + 1, dur=gb[g, 3] - gb[g, 1] + 1, matched=p is not None,
                           near=p is None and len(pb) > 0 and iou[:, g].max() >= 0.1)
                if p is not None:
                    row.update(iou=iou[p, g], e_x0=abs(pb[p, 0] - gb[g, 0]), e_x1=abs(pb[p, 2] - gb[g, 2]), e_y0=abs(pb[p, 1] - gb[g, 1]),
                               e_y1=abs(pb[p, 3] - gb[g, 3]), cls_ok=None if det.single_class else dets[p]["cls"] == r.family_id - 1)
                rows.append(row)
    return pd.DataFrame(rows), n_fp


def summarize(df, by):
    g = df.groupby(by, observed=True)
    out = pd.DataFrame(dict(n=g.size(), recall=g["matched"].mean(), miss_near=g["near"].sum() / g.size(), mean_iou=g["iou"].mean(),
                            err_x0=g["e_x0"].mean(), err_x1=g["e_x1"].mean(), err_y0=g["e_y0"].mean(), err_y1=g["e_y1"].mean()))
    if df["cls_ok"].notna().any():
        out["cls_acc"] = g["cls_ok"].apply(lambda v: v.dropna().astype(float).mean())
    return out.round(3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(PROJECT_DIR / "runs" / "detector" / "best.pt"))
    ap.add_argument("--root", default=None)
    ap.add_argument("--set", default="val")
    ap.add_argument("--conf", type=float, default=0.25, help="operating confidence (Evaluation.ipynb uses 0.25)")
    ap.add_argument("--iou", type=float, default=0.5, help="IoU for a ground-truth box to count as found")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--max-scenes", type=int, default=None)
    a = ap.parse_args()

    det = Detector(a.weights, device=a.device)
    reader = SetReader(find_dataset_root(a.root), a.set, a.max_scenes)
    df, n_fp = collect(det, reader, a.conf, a.iou)
    df["snr_bin"] = snr_bin_labels(df.snr).to_numpy()
    df["dur_bin"] = pd.cut(df.dur, [0, 8, 16, 32, 1000], labels=["<8 fr", "8-15 fr", "16-31 fr", ">=32 fr"], right=False)
    df["bw_bin"] = pd.cut(df.bw, [0, 16, 32, 64, 2000], labels=["<16 bins", "16-31 bins", "32-63 bins", ">=64 bins"], right=False)
    df["all"] = "all"

    print(f"{a.weights}  set={a.set}  scenes={len(reader)}  conf={a.conf}  IoU>={a.iou}  false positives/scene={n_fp / len(reader):.2f}")
    res = {}
    for by in ("all", "snr_bin", "family", "dur_bin", "bw_bin"):
        res[by] = summarize(df, by)
        print(f"\n--- by {by}\n{res[by].to_string()}")
    out = Path(a.weights).parent / f"diagnose_{a.set}.json"
    save_json({k: v.reset_index().to_dict("records") for k, v in res.items()} | dict(false_positives_per_scene=n_fp / len(reader)), out)
    print("\nsaved to", out)


if __name__ == "__main__":
    main()
