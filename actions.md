# Actions: improve the single-class detector

Goal: raise recall on CW and narrow signals (under 16 bins) without raising false positives.
Baseline (val, conf 0.1): run 1 recall 0.927 / 0.56 FP per scene; run 2 recall 0.887 / 0.32 FP per scene, CW recall 0.60.

Run everything from the project root. Add `--device 0` to the training commands to force CUDA (default `auto` already prefers CUDA).

## Step 1: compare run 1 and run 2 at the same confidence

`diagnose_detector.py` overwrites `diagnose_val.json` on every call, so each result is also saved to a log.

```bash
mkdir -p logs
for r in 1 2; do
  for c in 0.1 0.25 0.4; do
    python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_$r/best.pt --conf $c \
      | tee logs/diag_run${r}_conf${c}.txt
  done
done
```

Read from each log: `recall` (all), `false positives/scene`, CW recall (by family), recall for `<16 bins` (by bw_bin).
Compare the two runs at a similar false-positive rate, not at the same conf.

Decision: if run 2 matches run 1 at the same false-positive rate, the gap was only the threshold. Still do step 2 for CW.

## Step 2: undo the most likely cause (`--noise-prob`)

Same as run 2, only `--noise-prob 0.5` (run 1 value). New output folder.

```bash
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_3 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 2 --noise-prob 0.5
```

Then diagnose it the same way:

```bash
for c in 0.1 0.25 0.4; do
  python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_3/best.pt --conf $c \
    | tee logs/diag_run3_conf${c}.txt
done
```

Decision: keep 0.5 if CW recall is back to about 0.83 or higher. If CW is still low, the cause is something else (try `--time-scale 1` as run 4).

## Step 3: more pixels for narrow signals

Start from the best settings of step 2. Only `--imgsz` changes. Needs more GPU memory; lower `--batch` if it runs out.

```bash
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_4 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 2048 --time-scale 2 --noise-prob 0.5
```

```bash
for c in 0.1 0.25 0.4; do
  python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_4/best.pt --conf $c \
    | tee logs/diag_run4_conf${c}.txt
done
```

Compare CW and `<16 bins` recall against run 3.

## Step 4 (optional): oversample CW and AM in training

Change the class sampling in `01_create_dataset.ipynb` (`sample_known_class`) to favor CW and AM, then regenerate the `train` set only:

```bash
SPECTRUM_REBUILD=train jupyter nbconvert --to notebook --execute --inplace 01_create_dataset.ipynb
```

Retrain with the best settings so far and a new `--out` (for example `runs/detector_1cls_yolo26s_5`), then diagnose as above.

## Step 5: pick the final model and confirm

1. Choose the run with the best recall at about 0.3 false positives per scene (from the logs).
2. Evaluate it once on the `test` and `test_robust` sets in `Evaluation.ipynb` (set the weights path to the winning `best.pt`).
3. Point `inference.ipynb` at the same weights (`WEIGHTS = ROOT / "runs/<winner>/best.pt"`) and re-run it.
