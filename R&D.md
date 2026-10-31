# R&D Plan: Spectrogram Dataset and Model Comparison for RF Signal Detection and Modulation Classification

**Status:** Draft for review
**Related document:** `rf_spectrum_intelligence_product_description.md` (PRD v1.0)
**Purpose:** Generate a labeled spectrogram dataset, train several algorithms, and compare them. The results decide whether the PRD targets (1 kHz separation, <30 ms, >95% accuracy) are feasible and which architecture to build.

---

## 1. Objectives

1. Build a **reproducible synthetic dataset of spectrograms** with ground-truth labels for signal **detection** (time-frequency boxes/masks) and **modulation class**.
2. Make the dataset **capable of testing 1 kHz signal separation**, i.e. the spectrogram resolution must physically allow it (see Section 2).
3. **Train and compare** classical and AI algorithms on identical data and metrics.
4. Produce the evidence needed to fill the "To be specified" cells in PRD §3.2 and to answer the open questions in PRD §14.

### Research questions

| # | Question | Feeds PRD |
|---|---|---|
| Q1 | At what SNR, bandwidth and observation time can two signals 1 kHz apart be resolved? | 1 kHz target |
| Q2 | Which detector gives the best Pd / Pfa vs SNR? | Detection latency |
| Q3 | Which classifier reaches >95% accuracy, over which classes and SNR range? | Accuracy target |
| Q4 | Does AI beat classical DSP, and by how much, for each task? | Architecture |
| Q5 | How much observation time does each model need, and does it fit a 30 ms budget? | Latency target |
| Q6 | Can a spectrogram alone classify modulation, or is IQ needed? | Input representation |
| Q7 | How well are unseen signals rejected as "unknown"? | Unknown-class handling |

---

## 1.1 Confirmed inputs

| Item | Decision |
|---|---|
| Receiver band | **VHF / UHF** (about 30 MHz to 1 GHz; example bands in Section 3.1) |
| Receiver hardware | **USRP (Ettus Research)**, exact model to be confirmed (assumed B200/B210-class for simulation defaults; see Section 3.3 and Section 8) |
| Burst behavior | Not specified by the product, so the dataset uses a **mixed burst profile** (Section 3.2) and reports results per burst duration |
| Sample rate (example) | **256 kS/s complex**, chosen in Section 2.1 |
| Target inference hardware | **NVIDIA CUDA GPU**, model **not yet selected**; it will be chosen from the measured throughput needs (sizing method in Section 9.2). Final latency numbers must be measured on a CUDA GPU |
| SNR range | **5 to 30 dB** (in-band SNR as defined in Section 2.5) |
| Classification target | **Modulation family** is enough (family set in Section 3.1); the 12 specific classes are still stored as labels |
| Labels | **Generated automatically by the dataset generator** with exact ground truth; no manual labeling (Section 3.4) |
| Development / test machine | **Mac with Apple Silicon (PyTorch MPS backend)**, for development, pilot runs and debugging only (see Section 9.1) |
| 1 kHz separation | If two signals' **center frequencies differ by 1 kHz, the algorithm should detect both** as separate signals. Success criteria in Section 6 |
| Signal classes | Noise only, CW, AM, NBFM, BPSK, QPSK, 8PSK, 16QAM, 64QAM, 2-FSK, 4-FSK, GMSK |

---

## 2. Key technical decisions (resolve these first)

### 2.1 Spectrogram resolution must be designed for 1 kHz

Frequency resolution of a spectrogram is set by the window length, not by the number of FFT points alone:

- Bin spacing: `Δf = fs / N_fft`; the window duration is about `T = N_fft / fs = 1 / Δf`.
- With a Hann window, the main lobe is about 4 bins wide, and two equal-power tones are separable only when spaced by roughly **2 bins or more**.
- To separate 1 kHz robustly, aim for **Δf ≤ 250 Hz** (1 kHz = 4 bins), which needs a window of **≥ 4 ms**.

**Proposed baseline configuration** (all parameters configurable):

| Parameter | Value | Note |
|---|---|---|
| Sample rate `fs` | 256 kS/s (complex) | See rationale below |
| `N_fft` | 1024 | Δf = 250 Hz, window = 4 ms |
| Window | Hann (also test Blackman-Harris, Kaiser) | Sidelobe level matters for weak neighbours |
| Hop | 256 samples (1 ms) | 75% overlap |
| Frames per image | 128 generated; crop to 16 / 32 / 64 / 128 for experiments | See 2.3 |
| Image | 1024 (freq) x T (time), log-power dB, per-image normalized | |

Also generate a **fine-resolution variant** (`N_fft` = 2048, Δf = 125 Hz) to measure the benefit of finer bins against the longer window.

**Why 256 kS/s for VHF/UHF:**
- Standard VHF/UHF channels are 12.5 kHz or 25 kHz wide (PMR, marine, airband, amateur, public safety). A 256 kHz view covers about 10 to 20 adjacent channels, so scenes with several signals are realistic.
- It is a clean decimation of common SDR rates: 2.048 MS/s / 8 = 256 kS/s (RTL-SDR and similar), so real captures (Section 8) can be reduced exactly to the simulated format.
- The spectrogram is 1024 bins x T frames, small enough to train quickly, and Δf = 250 Hz gives 4 bins across 1 kHz.
- Occupied bandwidths of the chosen classes (about 0.1 to 20 kHz) fit comfortably, with room for several signals and guard space.
- A wider view (for example 1 to 2 MS/s) would need N_fft = 4096 to 8192 to keep Δf = 250 Hz, which raises compute and latency cost. Keep that as a later scaling experiment.

**RF-side behavior at VHF/UHF that the simulator must reproduce:** the baseband view is the same at any carrier, but receiver oscillator error scales with carrier frequency (1 ppm at 450 MHz = 450 Hz). A low-cost SDR with tens of ppm can shift every signal by many kHz. The shift is common to all signals in one capture, so a true 1 kHz difference is preserved, but absolute positions move, so randomize the common offset and never let a model depend on absolute frequency.

### 2.2 "1 kHz separation": definition and physical limits

**Definition (confirmed):** two signals whose center frequencies differ by 1 kHz must both be detected as separate signals. Whether that is physically possible depends on the signals' bandwidths, so the dataset is divided into tiers:

| Tier | Signal bandwidth | Separation | Expected resolvability from spectrogram |
|---|---|---|---|
| T1 (resolvable) | ≤ 500 Hz (low baud rate, CW, narrow FSK) | 1 kHz | Yes, a clean test of the resolution requirement |
| T2 (marginal) | 500 Hz to 1 kHz | 1 kHz | Partial spectral overlap, tests sidelobes and window choice |
| T3 (overlapped) | > 1 kHz | 1 kHz | Spectra overlap heavily. Not resolvable by frequency alone, requires other cues (cyclostationarity, IQ-domain separation) |

**What this means for your class list at 1 kHz:**

| Signal pair | Realistic outcome |
|---|---|
| CW + CW | Resolvable (two thin lines) at modest SNR |
| CW + anything | Usually resolvable, the line stands out against the wider signal |
| AM + AM | The two **carrier lines** are visible 1 kHz apart, so detection of both is possible; the sidebands overlap, so per-signal class and bandwidth are hard |
| Low-rate BPSK / 2-FSK / GMSK (≤ about 500 baud) | Resolvable (T1) |
| NBFM + NBFM, and digital signals at several kbaud (QPSK, 8PSK, 16QAM, 64QAM, 4-FSK at 2.4 to 9.6 kbaud) | Occupied bandwidths of about 5 to 15 kHz overlap by 85% or more at 1 kHz spacing. **Not resolvable from spectral shape alone**; a spectrogram detector will normally report one signal |

So "detect both at 1 kHz" can be met for narrow signals and carrier-bearing signals, and probably cannot be met for wide signals with a spectrogram. The R&D should **measure exactly where that boundary is** and test whether additional cues (IQ-domain, cyclostationary, or multi-signal separation methods) extend it. If the real requirement includes wide signals, that must be raised early.

Each pair in the test set is labeled with its tier, so the model is **not penalized for physically impossible cases** and the report states exactly where the 1 kHz requirement holds. Also sweep separations of 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, and 10 kHz to plot a resolution curve.

### 2.3 Observation time vs the 30 ms latency target

Detection cannot be faster than the observation window. Each 4 ms window plus 1 ms hops gives roughly 4 + (T-1) ms of data for T frames. Therefore:

- Train and test with **different crop lengths (16, 32, 64, 128 frames)** and report accuracy vs observation time.
- This turns the PRD's latency target from a guess into a measured trade-off (Q5).
- Inference latency is measured separately in Experiment E7.

### 2.4 Spectrogram-only modulation classification has limits

A magnitude spectrogram discards phase. Distinguishing PSK from QAM orders (for example 16-QAM vs 64-QAM) or some similar digital modulations may be hard or impossible from magnitude alone, especially at low SNR.

Therefore:
- The primary deliverable uses **spectrogram input**, as requested.
- **Every sample also stores its raw IQ** and per-signal parameters, so IQ-based and hybrid models can be compared (Q6).
- The report separates classes into "separable from spectrogram" and "needs IQ", based on measured confusion.

### 2.5 SNR definition

Fix one definition and document it, since results are meaningless otherwise: **in-band SNR = signal power within occupied bandwidth / noise power in the same bandwidth**, with a minimum reference bandwidth of 500 Hz so that CW and other very narrow signals have a defined SNR. Also log per-bin SNR (in the 250 Hz spectrogram bins) and the SNR in a 12.5 kHz channel, so results can be converted to other conventions.

**Consequence of the 5 to 30 dB range:** a signal's power is spread across its bandwidth. A 12 kHz-wide NBFM or QPSK signal at 5 dB in-band SNR covers about 48 spectrogram bins, so its per-bin SNR is about 5 − 17 = −12 dB, while a CW line at 5 dB sits in one or two bins and is far easier to see. Expect wide signals at the low end of the range to be the hardest detection cases. The 5 dB lower limit is therefore not "easy" for wide signals, and the report should show detection and classification by SNR for each family.

---

## 3. Dataset specification

### 3.1 Signal classes (confirmed) and VHF/UHF generation parameters

The 12 classes are fixed for all algorithms. Parameter ranges below are starting values for VHF/UHF narrowband channels and can be tuned. Occupied bandwidth is about `symbol rate x (1 + roll-off)` for linear digital modulations and Carson's rule for FM.

| Class | VHF/UHF example use | Generation parameters | Occupied BW |
|---|---|---|---|
| Noise only | Empty channel | AWGN, plus colored-noise and spur variants | n/a |
| CW | Amateur CW, beacons | Constant or keyed (5 to 40 wpm) | 0.05 to 0.3 kHz |
| AM | Airband (118 to 137 MHz) | Audio 0.3 to 3 kHz (speech clips and multi-tone), index 0.3 to 0.95, carrier present | 5 to 8 kHz |
| NBFM | PMR, marine, amateur FM | Deviation 2.5 or 5 kHz, audio 0.3 to 3 kHz | 11 to 16 kHz |
| BPSK | Low-rate digital modes | 100 to 2400 baud (31 baud dropped: only 4 symbols fit in a 131 ms scene), RRC roll-off 0.2 to 0.5 | 0.12 to 3.6 kHz |
| QPSK | Narrowband data | 1.2 to 9.6 kbaud, roll-off 0.2 to 0.5 | 1.5 to 14 kHz |
| 8PSK | Narrowband data | 2.4 to 9.6 kbaud | 3 to 14 kHz |
| 16QAM | Narrowband data | 2.4 to 9.6 kbaud | 3 to 14 kHz |
| 64QAM | High-order data (synthetic) | 2.4 to 6 kbaud, generated over the full 5 to 30 dB range | 3 to 9 kHz |
| 2-FSK | Packet / telemetry | 100 to 4800 baud, modulation index 0.5 to 2 | 0.3 to 10 kHz |
| 4-FSK | DMR / P25-style | 2.4 to 4.8 kbaud, deviation ±0.6 to ±1.8 kHz | 5 to 10 kHz |
| GMSK | Narrowband data | 1.2 to 9.6 kbaud, BT 0.3 or 0.5 | 1.5 to 12 kHz |

**Modulation families (the classification target).** Because family-level classification is enough, each signal carries a three-level label, all stored in the dataset:

| Family (primary target) | Fine classes in the family | Coarse group |
|---|---|---|
| Noise only (no signal) | Noise only | Background |
| CW | CW | Carrier |
| AM | AM | Analog |
| FM | NBFM | Analog |
| PSK | BPSK, QPSK, 8PSK | Linear digital |
| QAM | 16QAM, 64QAM | Linear digital |
| FSK / CPM | 2-FSK, 4-FSK, GMSK | Frequency-shift digital |

Models are trained on the 6 signal families plus background. GMSK is grouped with FSK because it is continuous-phase frequency modulation (MSK-type) and has a similar spectral and tone structure.

**Caveat on PSK vs QAM:** in a magnitude spectrogram, PSK and QAM at the same symbol rate and roll-off have almost the same spectral shape, so they are largely indistinguishable from the spectrogram alone, especially at 5 to 10 dB. Therefore:
- Train and report PSK and QAM as separate families (primary).
- Also report the **coarse** grouping (PSK + QAM merged as "linear digital"), which is the level a spectrogram can realistically achieve.
- Report PSK vs QAM from IQ-based models (E8) to show what extra input would buy.
- The family-level accuracy target should be stated per coarse and per primary group, rather than as one number.

**Example RF placements** (stored as metadata; the baseband is identical): airband 118 to 137 MHz (AM), amateur 2 m (144 to 148 MHz) and 70 cm (430 to 440 MHz), marine VHF (156 to 162 MHz), PMR446 (446 MHz, 12.5 kHz channels).

**Held out for open-set tests (not in the 12):** for example OQPSK, 8-FSK, and a chirp signal.

Placement and band-limiting rules:
- Signals sit at random offsets inside the 256 kHz view; place pairs at exactly controlled spacings for the 1 kHz set.
- Keep every signal inside the view with a guard band, and allow partial overlaps in the harder tiers.
- Class definition is fixed (PRD §14 decision resolved); changes later require a new dataset version.

### 3.2 Scene generation (each spectrogram is one "scene")

- **0 to 4 signals per scene**, random class, center frequency, bandwidth, symbol rate, start time, and duration.
- **Burst profile.** A generated scene is 128 frames, about 131 ms long. Each signal gets one of these timing types:

| Burst type | On-time | Share of signals | Realistic source |
|---|---|---|---|
| Continuous | Whole scene (≥ 131 ms) | 35% | Voice net, beacon, data link, push-to-talk held down |
| Long burst | 30 to 130 ms | 25% | Voice syllables, short transmissions |
| Short burst | 10 to 30 ms | 20% | TDMA slots (a DMR slot is 30 ms), packet frames |
| Very short (stress) | 2 to 10 ms | 10% | Short telemetry, keyed pulses; near the resolution limit |
| Intermittent train | Repeated on/off bursts, 10 to 60 ms on and 10 to 60 ms off (at least 2 fit in the scene) | 10% | CW keying (a 20 wpm dot is about 60 ms), packet trains |

  Start times are random and signals may begin before or end after the scene, so partial bursts at the edges are included. Bursts of the same scene may or may not overlap in time.
- **Physical limits of short bursts (to report, not hide):** a burst of duration D has a spectral spread of at least about 1/D, so a 2 ms burst is at least about 500 Hz wide regardless of its modulation, and bursts shorter than the 4 ms analysis window are smeared in time. Two signals 1 kHz apart can only be separated while they are **on at the same time**, and for long enough (the 1 kHz sets sweep overlap time: 2, 5, 10, 20, 50 and 130 ms).
- Every scene stores the burst type per signal, so detection and classification results can be broken down by burst duration.
- Pulse shaping: root-raised-cosine, with randomized roll-off.
- Parameter ranges are chosen so all three tiers (2.2) are represented.
- **Dedicated pair subset:** scenes with exactly two signals at controlled separations, SNRs and bandwidths, for the 1 kHz experiments.
- **Hard negatives:** noise-only scenes, narrowband interferers, spurs, and impulsive noise, so false alarms are measured.

### 3.3 Channel and receiver impairments

| Category | Range / model |
|---|---|
| SNR | **5 to 30 dB** in-band, balanced across classes and burst types. `train` is skewed towards the 5 dB floor (truncated exponential, about 75% of signals below 15 dB, so low SNR gets more data); `val` and the test sets are uniform so every SNR bin has enough samples for per-SNR reporting. A small **out-of-range stress set** (−5 to 5 dB and 30 to 35 dB) is generated for robustness reporting only; it is not part of acceptance |
| Noise | AWGN (baseline); optionally colored noise |
| Multipath / fading | None, Rician, Rayleigh (tiered difficulty) |
| Carrier frequency offset | Common receiver offset (oscillator ppm x carrier) applied to the whole scene, plus small per-transmitter offsets (hundreds of Hz). USRP default: a TCXO of about 2 ppm (verify for your model), which is about ±300 Hz at 150 MHz and ±900 Hz at 450 MHz. With an external 10 MHz / GPSDO reference it drops far below that. Simulate both cases (±2 ppm and ±0.1 ppm), and also a wider ±10 ppm stress case. The common offset does not change differences between signals |
| Phase noise / clock drift | Random, bounded |
| Sample-rate offset | Small random ppm |
| Receiver (USRP-like) | ADC quantization (12 bit for B2xx-class, 14 bit for N2xx / X3xx-class; also simulate 8 bit as a low-end stress case), IQ imbalance and residual DC offset (the LO leakage spike at 0 Hz), gain-dependent noise figure, analog filter roll-off at the band edges, and the decimation filter response used to reach 256 kS/s |
| Interference | Co-channel and adjacent-channel signals |

Each impairment has a **difficulty level** so models can be trained on easy conditions and tested on harder ones (robustness, E4).

### 3.4 Labels (stored per scene)

**All labels are produced automatically by the generator.** Because the dataset is synthetic, the generator knows the exact parameters of every signal it creates, so no manual labeling is needed. The labeling rules are fixed and written into the dataset datasheet:

- **Frequency extent of a box:** the lower and upper frequency that hold 99% of the power of the ideal, noise-free signal (before the channel and noise are added). For symmetric signals this equals `center ± OBW/2`; for asymmetric signals (for example a short piece of a chirp) the box is not centered on the carrier. Boxes are at least one spectrogram bin wide (CW).
- **Time extent:** the spectrogram frames whose window center lies inside the signal's on-time (the ideal envelope, including the ramp), clipped to the scene, at least two frames. Each burst of an intermittent train is its own instance, linked by a signal index.
- **Symbol rate and burst length:** the generator raises the symbol rate (never above the class maximum) so that a burst holds at least 8 symbols; very short bursts of low-baud classes can still hold fewer.
- **Class labels:** fine class, family and coarse group, taken from the generator configuration, never predicted.
- **Overlaps:** every signal gets its own box and mask even when boxes overlap; overlapping pixels belong to several instances. Scenes also record whether two signals are separable in principle (tier from Section 2.2).
- **Receiver impairments** (common frequency offset, IQ imbalance) are applied before the labels are finalized, so the label frequency is where the signal actually appears in the spectrogram.
- **Automatic label QA** on every shard: boxes lie inside the scene; measured spectrogram energy inside each box exceeds the noise level at the stated SNR; box frequency matches the measured spectral peak within tolerance; masks are consistent with boxes; no NaN or empty labels; class counts match the design. A random sample (a few hundred scenes per build) is rendered with boxes drawn on the spectrogram and inspected by eye.

- **Per signal:** class, center frequency (Hz), lower/upper bandwidth edges, start time, end time, SNR, symbol rate, roll-off, impairment parameters.
- **Detection targets:** bounding boxes in time-frequency (YOLO/COCO format) and a **pixel mask** (segmentation).
- **Scene-level:** number of signals, pair tier, separation (where applicable), random seed, generator version.
- **Raw IQ** (compressed, for example int16 or float16) stored alongside each spectrogram.

### 3.5 Size and splits

| Stage | Scenes | Purpose |
|---|---|---|
| Pilot | ~10,000 | Validate pipeline and labels; quick baselines |
| Main | ~200,000 | Train / validate / test comparison |
| Scale-up (if needed) | 1,000,000+ | Test whether more data improves results |

Splits are **leakage-free**:
- Split by **generator seed group / scenario group**, never by random frame.
- Ratio ~70 / 15 / 15 (train / val / test).
- **Frozen test sets**, created before any tuning and never regenerated:
  1. General test set (balanced by class and SNR).
  2. **1 kHz test set** (pairs, all tiers, all SNRs).
  3. Robustness set (unseen impairment combinations).
  4. Open-set set (held-out classes).
  5. **Real-capture set** (small), from an actual SDR (Section 8).

### 3.6 Dataset storage format

- Spectrograms as `.npy` / `.npz` shards (or WebDataset / HDF5), labels as COCO/YOLO JSON plus a Parquet metadata table.
- Dataset version, generator commit hash, config file and seed stored with every shard.
- Checksums to verify integrity.

---

## 4. Algorithms to train and compare

Include a **classical baseline for every task**, so the value of AI is measured, not assumed.

### 4.1 Detection (time-frequency localization)

| Approach | Candidates |
|---|---|
| Classical baseline | Energy detector, CA-CFAR / OS-CFAR on the spectrogram |
| Object detection | YOLO (nano / small), RT-DETR, Faster R-CNN (accuracy reference) |
| Segmentation | U-Net, lightweight U-Net variants |

### 4.2 1 kHz resolution

| Approach | Candidates |
|---|---|
| Classical baseline | Peak finding on Welch / zoom-FFT estimate, MUSIC / ESPRIT on IQ (resolution reference) |
| AI | Detector or segmentation models above, evaluated on the 1 kHz test set |

### 4.3 Modulation classification

| Approach | Candidates |
|---|---|
| Classical + ML | Cumulant / cyclostationary / spectral features + XGBoost |
| Spectrogram CNN | ResNet-18/34, EfficientNet-B0, MobileNetV3 |
| Transformer | ViT-tiny / Swin-tiny on spectrogram patches |
| IQ-based (comparison) | ResNet-1D on raw IQ, optionally a Conformer |
| Two-stage (recommended to test) | Detector finds each signal, then a classifier runs on the cropped region or on that signal's IQ |
| Single-stage | Detector predicts class directly with the box |

Train each AI candidate at **small / medium / large** sizes to expose the accuracy vs latency trade-off.

### 4.4 Unknown / out-of-distribution handling

Max-softmax baseline, energy score, Mahalanobis distance on embeddings, deep ensemble, temperature scaling, and conformal prediction. Evaluated on the open-set test set.

---

## 5. Experiments

| ID | Experiment | Output |
|---|---|---|
| E1 | **1 kHz separation:** sweep separation, SNR, bandwidth tier, window length (`N_fft` 1024 vs 2048) | Resolution-probability heatmaps; minimum SNR for reliable 1 kHz separation |
| E2 | **Detection:** ROC, Pd vs SNR at fixed Pfa; single vs overlapping signals | Detector ranking; boundary error in Hz and ms |
| E3 | **Classification (modulation family):** per-family precision / recall / F1, confusion matrix, accuracy vs SNR (5 to 30 dB) at primary and coarse family levels; fine 12-class results as a secondary report | Which families meet the >95% target and where |
| E4 | **Robustness:** train on easy impairments, test on hard or unseen ones | Generalization gaps |
| E5 | **Open-set:** held-out classes | AUROC, false-accept rate for unknown signals |
| E6 | **Observation time:** crop lengths 16 / 32 / 64 / 128 frames | Accuracy vs time; feasibility of the 30 ms target |
| E6b | **Burst duration:** detection and classification results per burst type (continuous to 2 ms), and 1 kHz success vs time overlap of the pair | Shortest burst each model handles; whether 30 ms is enough for short bursts |
| E7 | **Latency and throughput** on a CUDA GPU: FP32 / FP16 / INT8, batch sizes 1 / 8 / 32 / 64, p50 / p95 / p99 | Latency-vs-throughput curve per model, input to GPU sizing (Section 9.2) |
| E8 | **Spectrogram vs IQ vs hybrid** for modulation | Answer to Q6 |
| E9 | **Sample efficiency:** accuracy vs training-set size; with / without self-supervised pretraining | Data needs for the real product |
| E10 | **Real-capture validation** | Sim-to-real gap |

---

## 6. Metrics

- **Detection:** mAP@IoU (0.5, 0.5:0.95), Pd at fixed Pfa, false alarms per minute, miss rate, center-frequency error (Hz), bandwidth error, start/end time error (ms).
- **1 kHz separation (success criterion):** a scene with two signals whose centers differ by 1 kHz counts as a success only if the algorithm outputs **two** detections, each matched one-to-one to a distinct ground-truth signal, with center-frequency error ≤ ±250 Hz (half the separation would be ±500 Hz, so ±250 Hz leaves margin), and, for the class-aware version, the correct class. Also report the single-detection merge rate (both signals reported as one) and the missed-signal rate. Report per tier, SNR, class pair, and separation.
- **Classification:** overall accuracy, **per-family** (primary and coarse) and per-fine-class precision / recall / F1, confusion matrix, accuracy vs SNR (5 to 30 dB), calibration (ECE).
- **Open-set:** AUROC, FPR at 95% TPR.
- **Efficiency:** parameters, FLOPs, latency p50 / p95 / p99, memory.
- Report **mean and 95% confidence interval across at least 3 seeds**. Never report a single overall accuracy figure.

---

## 7. Training methodology

- **Framework:** PyTorch (+ Lightning), Hydra configs, YOLO via Ultralytics or equivalent.
- **Augmentation:** frequency shift, time shift, extra noise, random cropping, SpecAugment-style masking (check that masking does not erase the very separation being tested).
- **Loss:** CE or focal loss for classification; standard detector losses; Dice + CE for segmentation.
- **Imbalance:** class-balanced sampling. SNR is not re-balanced in training: the train set is deliberately skewed towards low SNR, and `val`/test stay uniform in SNR.
- **Curriculum:** optionally train from high to low SNR.
- **Self-supervised pretraining** (contrastive / masked autoencoder) on unlabeled spectrograms, compared against training from scratch (E9).
- **Tuning rules:** hyperparameters tuned on the validation set only. The frozen test sets are touched **once per final model**.
- **Reproducibility:** fixed seeds, logged configs, dataset version, code commit and checkpoints in an experiment tracker (MLflow or Weights & Biases).

---

## 8. Real-data validation (to avoid a simulation-only illusion)

- Capture a **small real dataset** with the target SDR: known test signals from a signal generator or a second SDR, at known frequencies and separations (including 1 kHz).
- Verify the simulator first: compare noise floor shape, filter roll-off, IQ imbalance and DC spike with real captures, and tune the receiver model.
- Evaluate the models trained on synthetic data on the real set (E10) and measure the sim-to-real gap.
- Optionally fine-tune on a small amount of real data and measure the gain.

**Using the USRP to make labeled real data.** Most USRP models can also transmit (verify for yours). That lets you create real captures with exactly known ground truth:
- Generate the 12 classes in software, transmit them with one USRP (or one TX channel of a B210) into a second receiver channel through a cable and attenuator, so no over-the-air emission is needed. Set attenuation to sweep SNR.
- Build the 1 kHz test directly: transmit two signals with a controlled 1 kHz spacing and verify the detector finds both. Use a shared 10 MHz reference between transmitter and receiver so the measured spacing is not blurred by oscillator error.
- Over-the-air transmission is subject to licensing and spectrum regulations; keep to cabled or shielded setups and licensed or permitted bands.
- Capture at a rate the USRP supports (for example 2.048 MS/s where available) and decimate to 256 kS/s with a proper polyphase filter in the same code used for simulation. Confirm the achievable rates for your model in UHD.

Also validate the simulator itself against theory (for example BPSK/QPSK BER curves in AWGN, and known window resolution limits) before any model training.

---

## 9. Infrastructure and repository layout

```
spectrum-rd/
  configs/            # Hydra configs: signals, channel, spectrogram, models
  generator/          # signal sources, pulse shaping, channel, receiver model
  dataset/            # build, validate, shard, version scripts
  features/           # spectrogram / STFT code (single shared implementation)
  models/             # detectors, segmenters, classifiers, OOD methods
  baselines/          # CFAR, Welch, MUSIC, cumulant + XGBoost
  train/              # training entry points
  eval/               # metrics, plots, report generation
  bench/              # latency / throughput benchmarks, ONNX / TensorRT export
  notebooks/          # exploration only (results come from scripts)
  tests/              # unit tests for generator and metrics
```

- **Compute:** a CUDA GPU for the main training runs and all final benchmarks; a CPU-only machine (including the Mac) is enough for data generation (parallelized).

### 9.1 Mac (MPS) for development, CUDA for results

- **Use the Mac for:** writing and testing the generator, label visual QA, the pilot dataset, classical baselines, small-model debugging, and short training runs.
- **Use CUDA for:** the main 200k training runs, hyperparameter searches, the final model comparison, and **all latency and throughput numbers (E7)**. Latency measured on the Mac does not predict CUDA latency, and the 30 ms target must be proven on the target GPU.
- **MPS caveats:** some PyTorch operators are not implemented on MPS (set `PYTORCH_ENABLE_MPS_FALLBACK=1` and watch for silent CPU fallbacks); no float64; mixed-precision behaves differently from CUDA AMP; detection ops (NMS, ROI) may be slow or fall back; no TensorRT.
- **Keep results portable:** write device-agnostic code (`cuda` / `mps` / `cpu` selected in config), keep random seeds fixed, and re-run the final candidates on CUDA to confirm that rankings do not change.
- **Deployment path:** train in PyTorch, export to ONNX, run with ONNX Runtime (CUDA provider) and TensorRT (FP16 / INT8) on the target GPU. Check each candidate model exports cleanly early, because some detector heads are awkward to export.
- Name the CUDA GPU model and driver / CUDA version used for each measurement in the report; results depend on them.

### 9.2 Choosing the CUDA GPU from throughput

The GPU is not selected yet, so R&D should produce the numbers that select it, rather than assume one.

1. **Define the load** (from the product): number of simultaneous receiver streams `S`, and per stream the inference rate `r` (windows per second). With 1 ms hops, a window of `W` frames evaluated every `H` frames gives `r = 1000 / H` per second per stream. Example: stride `H` = 16 ms gives 62.5 windows/s per stream.
2. **Measure per-model cost** (E7) on any available CUDA GPU (local card or a cloud instance): throughput `T` in windows/s at batch sizes 1 to 64 in FP16 and INT8, plus end-to-end latency including data transfer, pre-processing (STFT on the GPU) and post-processing (NMS, thresholding).
3. **Size the card:** supported streams ≈ `T x U / r`, with a utilization factor `U` of about 0.5 to 0.7 for headroom. Larger batches raise `T` but add waiting time, so choose the batch size that still meets the latency budget.
4. **Scale to other GPUs** using measured results on a second, different card (for example a smaller and a larger one) and memory bandwidth / tensor-core ratios as a guide, then confirm on the chosen card before purchase.
5. **Move the STFT onto the GPU** (for example `torch.stft` with CUDA) and include it in the benchmark. It is cheap, but copying raw IQ to the GPU and computing spectrograms there is usually better than moving large spectrogram tensors.
6. Record GPU memory per stream and per model, because memory may limit stream count before compute does.

**Needed from the product:** the expected number of simultaneous streams `S` (receivers / channels) and the allowed end-to-end latency. Without them the output of this step is a throughput table per model, not a GPU choice.
- **Single STFT implementation** shared between dataset generation, training and the future product, so train/serve skew cannot occur.
- **Tests:** verify generator output against known spectra, label correctness (draw boxes over spectrograms and inspect them), and metric implementations on toy cases.

---

## 10. Timeline (indicative, about 8 weeks)

| Weeks | Work |
|---|---|
| 1 | Confirm class list, receiver, sample rate and separation definition; set up repo, tracking, configs |
| 2 | Build and validate signal generator, channel model and spectrogram pipeline; label visual QA; pilot dataset (10k) |
| 3 | Classical baselines (CFAR, Welch / MUSIC, cumulant + XGBoost); run E1 (resolution limits) |
| 4 | Generate main dataset (200k) with frozen test sets; first detector and classifier training |
| 5 | Full model comparison: E2, E3, E6, E8 |
| 6 | E4, E5, E9 (robustness, open-set, sample efficiency) |
| 7 | E7 latency benchmarks on target hardware; real captures and E10 |
| 8 | Final report, decision memo, updated PRD targets |

---

## 11. Decision gates (end of R&D)

1. **Is 1 kHz separation feasible,** and under what SNR, bandwidth tier and observation time? If not, renegotiate the requirement.
2. **Which models meet the accuracy target** per class and SNR range, and does the >95% claim hold on a fair test set?
3. **Does the 30 ms budget work** given the observation time the models need (E6) and measured inference time (E7)?
4. **Does AI beat classical DSP** enough to justify its cost for each task?
5. **Is spectrogram input sufficient** for modulation, or does the product need IQ input?
6. **How large is the sim-to-real gap,** and how much real data is needed?

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Simulation unrealistic, results do not transfer | Validate against theory and real captures; model receiver impairments; test sim-to-real early |
| Spectrogram resolution cannot show 1 kHz with the chosen parameters | Decide `N_fft`/window in Section 2 before generating the main dataset; run the fine-resolution variant |
| Label errors in synthetic data | Visual QA, automated consistency checks, unit tests |
| Data leakage inflates accuracy | Group-based splits, frozen test sets |
| Class confusion is physically unavoidable (for example PSK vs QAM from a magnitude spectrogram, or any family at 5 dB for wide signals) | Report per-family, show the coarse grouping, separate "needs IQ" distinctions, set SNR-conditional targets |
| Over-optimistic overall accuracy | Report by class and SNR with confidence intervals |
| Scope creep (too many classes / impairments) | Start with the pilot set and a small class list; add complexity only when baselines work |
| Latency measured on the wrong hardware | Benchmark on the target hardware with the real runtime and batch size |

---

## 13. Deliverables

1. Versioned generator and dataset-build code, plus the documented dataset (datasheet: classes, ranges, splits, known limitations).
2. Trained models and checkpoints, with configs and tracked experiments.
3. Results report: E1 to E10 plots and tables (resolution heatmaps, accuracy vs SNR, confusion matrices, latency).
4. Decision memo answering the gates in Section 11.
5. Proposed updates to PRD §3.2 (real, measured targets) and §14 (resolved decisions).

---

## 14. Decisions and remaining open questions

### Resolved (see Section 1.1)
- Signal classes: the 12 listed; classification target is the modulation family.
- Band: VHF / UHF. Example sample rate: 256 kS/s. SDR: USRP.
- SNR range: 5 to 30 dB.
- Labels: generated automatically by the dataset generator.
- Inference hardware: CUDA GPU (model chosen later from measured throughput). Development: Mac with MPS.
- 1 kHz separation: center frequencies 1 kHz apart, both signals detected.
- Burst behavior: mixed profile assumed (Section 3.2).

### Still open
1. Which **exact USRP model** and reference clock (B200/B210, N210, X310 and so on)? It sets ADC bits, oscillator accuracy, supported sample rates and whether it can transmit test signals. The plan assumes B200/B210-class defaults until confirmed.
2. How many **simultaneous receiver streams** and what **end-to-end latency** must the system sustain? These decide the GPU (Section 9.2).
3. Must **wide signals** (NBFM, several-kbaud digital) also be separated at 1 kHz? Section 2.2 shows this is probably not possible from spectral shape; the requirement may need to be limited to narrow and carrier-bearing signals.
4. Is **PSK vs QAM** a required distinction, or is "linear digital" enough? A spectrogram can barely separate them (Section 3.1); if required, IQ input is likely needed.
5. Which **burst durations matter operationally**? The dataset assumes a mix (Section 3.2) and reports results per duration; if the real signals are mostly long, the shortest-burst cases can be de-emphasized.
6. Is a **sample rate above 256 kS/s** needed later (wider monitoring)?
