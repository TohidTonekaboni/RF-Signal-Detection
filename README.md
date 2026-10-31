# Training


python3 train_detector.py --single-class --model yolo26s.pt --out runs/detector_1cls_yolo26s_1 \
  --optimizer AdamW --lr0 0.0005 --warmup-epochs 1 --freeze 10 --patience 15 --imgsz 1536
