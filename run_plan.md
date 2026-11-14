# Run 1

SPECTRUM_PROFILE=pilot jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb --output-dir logs --output 01_create_dataset_pilot.ipynb


python3 train_detector.py --model yolo26s.yaml --epochs 60 --patience 25 --out runs/detector_run1
python3 train_classifier.py --out runs/classifier_run1
python3 baselines.py


YOLO_RUN=detector_run1 CLASSIFIER_RUN=classifier_run1 \
  jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run1.ipynb

# where the detector fails, by SNR, protocol and box size (uses val)
python3 diagnose_detector.py --weights runs/detector_run1/best.pt --conf 0.25


# Run 2
#
# Run 1 (pilot, 8000 train scenes) reached detection F1 0.968 / class-aware F1 0.948 on `test`, but:
#   - test_robust: detection F1 0.839, 0.69 false alarms per scene. 96% of the off-signal false alarms were IQ images
#     (the mirror copy of a strong signal at the receiver's 20-30 dB image rejection; train only had 30-50 dB).
#   - NBFM (analog voice) was detected and called DMR/P25 in 96.6% of the cases; ResNet max-softmax open-set AUROC 0.83.
#   - DMR vs P25: 2-6% confusion, worst for short P25 stubs (77% / 35% accuracy for short / very short bursts).
#   - YOLO validation mAP50 peaked at epoch 27 of 60 (0.939) and ended at 0.909.
#
# What changed in the code (dataset version 0.4.0, so a new dataset folder is needed):
#   1. IQ images:  train has 40% "mid" sessions (18-40 dB image rejection, 10 bit ADC, 5 ppm; SPECTRUM_TRAIN_MID_FRAC=0.4 is the default now)
#                  and Detector drops detections that are the mirror image of a stronger one (spectrum_common.mirror_suppress).
#                  On run 1's weights alone the filter lifted test_robust detection F1 from 0.839 to 0.929 with the same recall.
#   2. Unknown:    AM / CW / POCSAG distractors in 30% of the scenes of every set (unlabelled = hard negatives for YOLO);
#                  NBFM / WFM / GSM stay held out (test_openset only); train_classifier.py writes calibration.json
#                  (energy threshold from the val boxes of the known protocols); Evaluation reports the operating point and the detectors' fire rate.
#   3. DMR vs P25: with SPECTRUM_STORE_IQ=1, baselines.py adds 4FSK features (symbol-averaged deviation levels, sync-word match with the
#                  DMR and P25 words). Evaluation has the pipeline "YOLO (single-stage) + IQ refine" (boxes called DMR/P25 re-decided by the GBM).
#                  On a 1500-scene check the GBM went from 91.1% to 95.1% on DMR/P25 (97% above 20 dB SNR).
#   4. More data:  new profiles medium (24k train) and main (60k train); IQ stored (about 1.1 MB per scene: main about 105 GB, medium about 42 GB).
#
# IMPORTANT: run 2 uses a harder test set than run 1 (distractors everywhere, so a detection on one is a false alarm).
# To compare fairly, also evaluate the run 1 models on the new data (step 7).


# 1. Dataset. "main" (about 10-15 min to build) is the plan; use medium when disk or training time is short, mini (about 2 min) for a dry run.
SPECTRUM_PROFILE=main SPECTRUM_STORE_IQ=1 \
  jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb --output-dir logs --output 01_create_dataset_main.ipynb
# -> dataset/spectrum_rf_v0.4.0_main  (the scripts pick the newest version, then the biggest profile; run 1's v0.3.0 is ignored)
# Dry run of the whole chain in a separate folder (then pass --root dataset_mini/spectrum_rf_v0.4.0_mini to every script):
# SPECTRUM_PROFILE=mini SPECTRUM_STORE_IQ=1 SPECTRUM_OUT=dataset_mini jupyter nbconvert --to notebook --execute 01_create_dataset.ipynb --output-dir logs --output 01_create_dataset_mini.ipynb


# 2. Detector: the run 1 settings on the bigger dataset. (--time-scale stays 1 so that only the data changes; try 2 in run 2b.)
python3 train_detector.py --model yolo26s.yaml --epochs 40 --patience 15 --out runs/detector_run2
# check the first lines: root must be .../spectrum_rf_v0.4.0_main

# 3. ResNet classifier (also writes runs/classifier_run2/calibration.json for the unknown rejection)
python3 train_classifier.py --epochs 30 --out runs/classifier_run2

# 4. Baselines with IQ features (CFAR tuning about 2 min, features about 20 min with IQ). Run 1's runs/baselines stays untouched.
python3 baselines.py --out runs/baselines_run2
# if the log says "xgboost" it crashed on macOS before; the default is scikit-learn boosting (--gb xgboost to opt in)


# 5. Evaluation on the frozen test sets
YOLO_RUN=detector_run2 CLASSIFIER_RUN=classifier_run2 BASELINES_RUN=baselines_run2 \
  jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run2.ipynb
# summary: runs/evaluation/detector_run2/summary.json

# 6. Where the detector fails (val): by SNR, protocol, box size
python3 diagnose_detector.py --weights runs/detector_run2/best.pt --conf 0.25


# 7. Fair comparison: the run 1 models on the NEW data (same test sets as run 2). Needs the run 1 folders (detector_run1, classifier_run1, baselines).
YOLO_RUN=detector_run1 CLASSIFIER_RUN=classifier_run1 BASELINES_RUN=baselines \
  jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run1_on_v040.ipynb
# -> runs/evaluation/detector_run1/summary.json is overwritten: copy the run 1 summary first if you want to keep it.


# 8. Demos and statistics (no training)
DETECTOR_WEIGHTS=runs/detector_run2/best.pt BASELINES_DIR=runs/baselines_run2 \
  jupyter nbconvert --to notebook --execute inference.ipynb --output-dir logs --output inference_run2.ipynb
YOLO_RUN=detector_run2 BASELINES_RUN=baselines_run2 \
  jupyter nbconvert --to notebook --execute test.ipynb --output-dir logs --output test_run2.ipynb


# 9. Optional run 2b: the same, with a finer time grid (short bursts had 0.86 recall below 20 frames in run 1)
# python3 train_detector.py --model yolo26s.yaml --epochs 40 --patience 15 --time-scale 2 --out runs/detector_run2b
# YOLO_RUN=detector_run2b CLASSIFIER_RUN=classifier_run2 BASELINES_RUN=baselines_run2 \
#   jupyter nbconvert --to notebook --execute Evaluation.ipynb --output-dir logs --output Evaluation_run2b.ipynb


# What to look at (run 1 on its own data -> goal), in Evaluation_run2.ipynb:
#   - test_robust detection F1 (section 5 table; "YOLO (no mirror filter)" row shows the filter alone):   0.839 -> above 0.92, false alarms below 0.25 per scene
#   - detectors' fire rate on NBFM / AM / POCSAG (section 6, last table): run 1 weights on v0.4.0 gave about 0.97 / 0.6-0.7 / 0.8-0.9 (small samples) -> clearly lower for AM and POCSAG
#   - ResNet at the calibrated threshold (section 6): known kept about 95%, share of NBFM / WFM / GSM / distractors rejected
#   - DMR / P25 F1 of the best pipeline vs "... + IQ refine" (section 4 leaderboard):                       0.957 / 0.945 -> higher with IQ refine
#   - YOLO training curve: is the best epoch later than 27 and does val mAP50 stay near its maximum?
# Expect NBFM to stay hard: the distractors (AM, CW, POCSAG) do not look like NBFM, so rejecting it needs more diverse negatives.
