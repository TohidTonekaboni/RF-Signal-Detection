# Training


python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_1 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 1 --freeze 10 --patience 15 --imgsz 1536

## Step 2
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_2 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 2 --noise-prob 0.7


python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_2/best.pt --conf 0.1


## Run 3
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_3 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 2 --noise-prob 0.5


## Run 4
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_4 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 2048 --time-scale 2 --noise-prob 0.5


# Run 5
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_5 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 1 --noise-prob 0.5

# Run 6

# Oversample CW and AM in the train set only (val/test stay identical, seeds unchanged).
# Written to a NEW folder so the dataset of runs 1-5 is untouched. Takes a while (regenerates all sets).
SPECTRUM_OUT=dataset_boost SPECTRUM_TRAIN_BOOST="CW=3,AM=2" \
  jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb \
  --output-dir logs --output 01_create_dataset_boost.ipynb

# Same settings as Run 5, only the training data changes
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_6 \
  --root dataset_boost/spectrum_rf_v0.2.0_pilot \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 1 --noise-prob 0.5

# Diagnose on the original val set (default root), same conf values as Run 5
for c in 0.1 0.25 0.4; do
  python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_6/best.pt --conf $c \
    | tee logs/diag_run6_conf${c}.txt
done


# Run 7
# Run 6 data (CW/AM boost) plus (a) 40% of train sessions with harder receiver impairments (5 ppm, 10 bit ADC, Rician fading,
# stronger DC/IQ imbalance: harder than train, still milder than test_robust) and (b) 15% of train scenes as close-spaced pairs
# (250 Hz to 10 kHz). val and all test sets are generated exactly as before. New folder, takes a while.
SPECTRUM_OUT=dataset_hard SPECTRUM_TRAIN_BOOST="CW=3,AM=2" \
  SPECTRUM_TRAIN_MID_FRAC=0.4 SPECTRUM_TRAIN_PAIR_FRAC=0.15 \
  jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb \
  --output-dir logs --output 01_create_dataset_hard.ipynb

# Same settings as Run 6, only the training data changes
python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_7 \
  --root dataset_hard/spectrum_rf_v0.2.0_pilot \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 2 --patience 25 --epochs 80 \
  --imgsz 1536 --time-scale 1 --noise-prob 0.5

# Diagnose on the original val set (default root), same conf values as before
for c in 0.1 0.25 0.4; do
  python3 diagnose_detector.py --weights runs/detector_1cls_yolo26s_7/best.pt --conf $c \
    | tee logs/diag_run7_conf${c}.txt
done

# Frozen test sets: in Evaluation.ipynb set  YOLO_1CLS_RUN = "detector_1cls_yolo26s_7"  and run all cells
# (or headless, writes the executed copy to logs/):
jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run7.ipynb
# Compare with run 6 (Evaluation): test detection F1 0.912, test_robust detection F1 0.722, 1 kHz success 0.005
