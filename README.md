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
