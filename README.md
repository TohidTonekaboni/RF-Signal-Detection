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
