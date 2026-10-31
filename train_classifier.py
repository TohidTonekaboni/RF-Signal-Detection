"""Train the modulation-family classifier (CW / AM / FM / PSK / QAM / FSK) on spectrogram crops around labeled boxes.

    python train_classifier.py                               # ResNet-18, 30 epochs, device picked automatically (cuda > mps > cpu)
    python train_classifier.py --arch resnet34 --epochs 40
    python train_classifier.py --max-scenes 300 --epochs 2   # quick smoke run

Input of the network: a 2-channel crop of 64 frames x 128 bins around a box: channel 0 = spectrogram (dB, normalised),
channel 1 = box mask (tells the network which signal to classify when several overlap).
Training uses the ground-truth boxes with jitter, so it also tolerates the boxes of a detector (two-stage pipeline).

Uses train and val only. The frozen test sets are evaluated once, in Evaluation.ipynb.
Outputs in --out (default runs/classifier): best.pt, last.pt, history.json, val_metrics.json, config.json.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from spectrum_common import (CROP_F, CROP_T, FAMILIES, PROJECT_DIR, SetReader, cls_metrics, find_dataset_root, make_crop, normalize_db,
                             pick_device, save_json, set_seed)

ARCHS = ("resnet18", "resnet34", "mobilenet_v3_small", "efficientnet_b0")     # small / medium / larger trade-off


# =============================================================== data
class BoxCropDataset(Dataset):
    """One item per labeled box. Reads only the crop from the memory-mapped shard."""

    def __init__(self, root, set_name, train, max_scenes=None, include_unknown=False):
        reader = SetReader(root, set_name, max_scenes)
        sg = reader.signals
        if not include_unknown:
            sg = sg[sg.family_id <= len(FAMILIES)]
        sg = sg.reset_index(drop=True)
        self.boxes = sg[["box_x0", "box_y0", "box_x1", "box_y1"]].to_numpy(int)
        self.shard, self.pos = sg["shard"].to_numpy(int), sg["pos"].to_numpy(int)
        self.labels = sg["family_id"].to_numpy(int) - 1
        self.snr = sg["snr_db"].to_numpy(float)
        reader.scenes = reader.signals = None            # keep the object small: it is pickled into the DataLoader workers
        reader._by_scene = {}
        self.reader, self.train, self._rng = reader, train, None

    def __len__(self):
        return len(self.labels)

    def rng(self):
        if self._rng is None:
            self._rng = np.random.default_rng(torch.initial_seed() % (2 ** 32))
        return self._rng

    def __getitem__(self, i):
        spec = self.reader.shard("spec", self.shard[i])[self.pos[i]]
        box = self.boxes[i]
        if self.train:
            r = self.rng()
            shift = (int(r.integers(-4, 5)), int(r.integers(-6, 7)))                       # move the crop (frames, bins)
            jitter = (*[int(v) for v in r.integers(-2, 3, 2)], *[int(v) for v in r.integers(-1, 2, 2)])   # mimic detector box error
            x = make_crop(spec, box, shift, jitter)
            if r.random() < 0.5:                                                           # extra noise: lowers the effective SNR
                p = 10.0 ** (x[0] / 10.0) + r.exponential(r.uniform(0.05, 0.5), x[0].shape)
                x[0] = 10.0 * np.log10(p)
            if r.random() < 0.5:                                                           # mirror the frequency axis
                x = x[:, :, ::-1]
        else:
            x = make_crop(spec, box)
        x = np.ascontiguousarray(x)
        x[0] = normalize_db(x[0])
        return torch.from_numpy(x), int(self.labels[i])


def sampler_weights(labels, snr):
    """Class-balanced sampling (R&D Section 7). No SNR re-balancing: the train set is already skewed towards low SNR on purpose."""
    w = 1.0 / np.bincount(labels, minlength=len(FAMILIES))[labels]
    return w / w.sum()


# =============================================================== model
def build_model(arch, n_classes=len(FAMILIES), in_ch=2):
    import torchvision.models as tvm
    if arch in ("resnet18", "resnet34"):
        m = getattr(tvm, arch)(weights=None, num_classes=n_classes)
        m.conv1 = nn.Conv2d(in_ch, 64, 3, 1, 1, bias=False)           # small input: 3x3 stem, keep the max-pool
    elif arch == "mobilenet_v3_small":
        m = tvm.mobilenet_v3_small(weights=None, num_classes=n_classes)
        m.features[0][0] = nn.Conv2d(in_ch, 16, 3, 1, 1, bias=False)
    elif arch == "efficientnet_b0":
        m = tvm.efficientnet_b0(weights=None, num_classes=n_classes)
        m.features[0][0] = nn.Conv2d(in_ch, 32, 3, 1, 1, bias=False)
    else:
        raise ValueError(f"unknown arch {arch}, choose from {ARCHS}")
    return m


def load_classifier(path, device=None):
    """Returns (model in eval mode on device, checkpoint dict)."""
    device = device or pick_device()
    ck = torch.load(path, map_location="cpu")
    model = build_model(ck["arch"])
    model.load_state_dict(ck["state_dict"])
    return model.to(device).eval(), ck


@torch.no_grad()
def predict_crops(model, crops, device, batch=256):
    """crops: float32 [n, 2, CROP_T, CROP_F] with channel 0 already normalised. Returns logits [n, 6]."""
    out = []
    for s in range(0, len(crops), batch):
        out.append(model(torch.from_numpy(crops[s:s + batch]).to(device)).float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, len(FAMILIES)), np.float32)


def classify_boxes(model, spec, boxes, device):
    """Logits for boxes of one scene. spec: [128, 1024] uint8 (stored) or float dB."""
    if len(boxes) == 0:
        return np.zeros((0, len(FAMILIES)), np.float32)
    crops = np.stack([make_crop(spec, b) for b in boxes])
    crops[:, 0] = normalize_db(crops[:, 0])
    return predict_crops(model, crops, device)


# =============================================================== training
@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    logits, labels = [], []
    for x, y in loader:
        logits.append(model(x.to(device)).float().cpu().numpy())
        labels.append(y.numpy())
    return np.concatenate(logits), np.concatenate(labels)


def train(a):
    set_seed(a.seed)
    device = pick_device(a.device)
    root, out = find_dataset_root(a.root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tr = BoxCropDataset(root, "train", True, a.max_scenes)
    va = BoxCropDataset(root, "val", False, a.max_scenes)
    print(f"device={device}  arch={a.arch}  train boxes={len(tr)}  val boxes={len(va)}  classes={FAMILIES}")

    sampler = WeightedRandomSampler(torch.from_numpy(sampler_weights(tr.labels, tr.snr)), num_samples=len(tr), replacement=True)
    tr_loader = DataLoader(tr, batch_size=a.batch, sampler=sampler, num_workers=a.workers, drop_last=True,
                           persistent_workers=a.workers > 0, pin_memory=device.type == "cuda")
    va_loader = DataLoader(va, batch_size=256, shuffle=False, num_workers=0)

    model = build_model(a.arch).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.wd)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(tr_loader), pct_start=0.15)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=a.label_smoothing)
    use_amp = device.type == "cuda"
    config = {**vars(a), "classes": FAMILIES, "crop": [CROP_T, CROP_F], "root": str(root)}
    save_json(config, out / "config.json")

    history, best_f1, bad = [], -1.0, 0
    for epoch in range(1, a.epochs + 1):
        t0, tot, n = time.time(), 0.0, 0
        model.train()
        for x, y in tr_loader:
            x, y = x.to(device), y.to(device)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=use_amp):
                loss = loss_fn(model(x), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            sched.step()
            tot, n = tot + float(loss) * len(y), n + len(y)
        logits, labels = evaluate(model, va_loader, device)
        m = cls_metrics(labels, logits.argmax(1), va.snr)
        history.append(dict(epoch=epoch, train_loss=tot / n, val_accuracy=m["accuracy"], val_macro_f1=m["macro_f1"], seconds=time.time() - t0))
        print(f"epoch {epoch:3d}/{a.epochs}  loss {tot / n:.4f}  val acc {m['accuracy']:.4f}  macro-F1 {m['macro_f1']:.4f}  ({time.time() - t0:.0f} s)")
        ck = dict(state_dict=model.state_dict(), arch=a.arch, classes=FAMILIES, crop=[CROP_T, CROP_F], epoch=epoch, val_macro_f1=m["macro_f1"])
        torch.save(ck, out / "last.pt")
        if m["macro_f1"] > best_f1:                       # model selection on the validation set only
            best_f1, bad = m["macro_f1"], 0
            torch.save(ck, out / "best.pt")
        else:
            bad += 1
        save_json(history, out / "history.json")
        if a.patience and bad >= a.patience:
            print(f"early stop: no improvement for {a.patience} epochs")
            break

    model, ck = load_classifier(out / "best.pt", device)
    logits, labels = evaluate(model, va_loader, device)
    metrics = cls_metrics(labels, logits.argmax(1), va.snr)
    metrics["best_epoch"] = ck["epoch"]
    save_json(metrics, out / "val_metrics.json")
    print(f"best epoch {ck['epoch']}: val accuracy {metrics['accuracy']:.4f}  macro-F1 {metrics['macro_f1']:.4f}")
    for k, v in metrics["per_class"].items():
        print(f"  {k:4s} precision {v['precision']:.3f}  recall {v['recall']:.3f}  f1 {v['f1']:.3f}  (n={v['support']})")
    print("saved to", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="dataset folder (default: newest in ./dataset)")
    ap.add_argument("--out", default=str(PROJECT_DIR / "runs" / "classifier"))
    ap.add_argument("--arch", default="resnet18", choices=ARCHS)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--wd", type=float, default=1e-2)
    ap.add_argument("--label-smoothing", type=float, default=0.05)
    ap.add_argument("--patience", type=int, default=0, help="early stopping on val macro-F1 (0 = off)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="auto", help="auto | cuda | mps | cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-scenes", type=int, default=None, help="use only the first N scenes of train and val (smoke test)")
    train(ap.parse_args())


if __name__ == "__main__":
    main()
