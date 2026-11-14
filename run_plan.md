# Run 1

SPECTRUM_PROFILE=pilot jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb --output-dir logs --output 01_create_dataset_pilot.ipynb


python3 train_detector.py --model yolo26s.yaml --epochs 60 --patience 25 --out runs/detector_run1
python3 train_classifier.py --out runs/classifier_run1
python3 baselines.py


YOLO_RUN=detector_run1 CLASSIFIER_RUN=classifier_run1 \
  jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run1.ipynb

# where the detector fails, by SNR, protocol and box size (uses val)
python3 diagnose_detector.py --weights runs/detector_run1/best.pt --conf 0.25
