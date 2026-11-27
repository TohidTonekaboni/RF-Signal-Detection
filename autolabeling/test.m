%% matlab-test.m
% Test of the MathWorks "Automated Labeling of Time-Frequency Regions for
% AI-Based Spectrum Sensing" workflow on the IQ files in ./matlab_iq,
% scored against the ground truth stored in each .mat file.
%
% Pipeline (same stages as the MathWorks example):
%   1. stft -> |S|^2 image                       (2048 pt Hann, hop 1024)
%   2. ROI localization: noise-floor threshold OR adaptthresh, + dilation
%   3. False-alarm filter on the median magnitude of each region
%   4. Region features: Duration, Spread, Skewness, Entropy (+ extras)
%   5. z-score + kmedoids (cityblock, over-clustered: k > #classes)
%   6. Cluster naming by majority ground-truth class (simulated expert)
%   7. Evaluation: pixel-level mask metrics, box-level matching, ROI
%      classification accuracy, all versus SNR.
%
% Required: Signal Processing Toolbox (stft), Image Processing Toolbox
% (imgaussfilt, adaptthresh, imdilate, regionprops), Statistics and Machine
% Learning Toolbox (kmedoids, zscore, confusionchart).
% Not included: the SAM localization option (needs Computer Vision Toolbox
% + support package, and is slow). Add it as another value of cfg.methods.
%
% Run with:  run("matlab-test.m")   (file name has a hyphen, so it cannot be
% called by typing its name).
%
% NOTE: written without MATLAB available to execute it; tune cfg if the
% first run shows over/under-segmentation.

clear; clc; close all;

%% ---- Configuration ----------------------------------------------------
here = fileparts(mfilename("fullpath"));
if isempty(here), here = pwd; end
cfg.dataDir   = fullfile(here, "matlab_iq");
if ~isfolder(cfg.dataDir)                       % fallback if run from elsewhere
    cfg.dataDir = pwd;
end

cfg.scenes    = ["LTE" "DMR" "P25" "TETRA" "MIXED"];
cfg.snrList   = 0:5:30;
cfg.methods   = ["noisefloor" "adaptthresh"];   % ROI localization options
cfg.gallerySNR = [0 10 20 30];                  % MIXED scenes shown in the gallery

% STFT: README warns the 256-pt window of the MathWorks example makes
% narrowband signals (DMR/P25) 1 bin wide, so use 2048.
cfg.nfft      = 2048;
cfg.hop       = 1024;

% Localization
cfg.sigma        = [2 1];    % imgaussfilt sigma [freq time] on |S|^2
cfg.marginDb     = 5;        % noisefloor method: threshold above noise (dB)
cfg.edgeGuard    = 0.10;     % ignore outer 10% of band (anti-alias roll-off, up to -20 dB)
cfg.close        = [41 5];   % imclose [freq time]: merges fading holes in wideband signals
cfg.adaptSens    = 0.5;      % adaptthresh sensitivity
cfg.adaptNbhDiv  = 8;        % neighborhood = 2*floor(size/div)+1
cfg.minArea      = 20;       % bwareaopen (pixels)
cfg.dilate       = [3 3];    % imdilate structuring element
cfg.occ          = 0.99;     % ROI refinement: fraction of energy kept in frequency
cfg.timeFrac     = 0.10;     % ROI refinement: time columns >= this fraction of peak energy
cfg.imageDb      = 12;       % drop mirror-image ROI if the mirrored one is this much stronger (dB)
cfg.minMedianDb  = 4;        % false-alarm filter: median region level over noise (dB)

% Evaluation / clustering
cfg.iouMatch     = 0.3;      % box IoU needed to call a GT box "detected"
cfg.iouLabel     = 0.1;      % min IoU to give an ROI a ground-truth class
cfg.features     = ["Duration" "Spread" "Skewness" "Entropy"];  % as in the example
% cfg.features   = [cfg.features "Bandwidth"];   % optional extra feature
cfg.k            = 7;        % over-clustering (4 signal classes + false alarm)
cfg.replicates   = 100;      % example uses 1000
cfg.classes      = ["LTE" "DMR" "P25" "TETRA" "FalseAlarm"];

rng(0);

%% ---- Run localization + scoring on every file -------------------------
roiAll = cell(0,1);
metAll = cell(0,1);
demo   = struct();

for m = cfg.methods
    for sc = cfg.scenes
        for snr = cfg.snrList
            fname = sprintf("%s_snr%02ddB.mat", sc, snr);
            fpath = fullfile(cfg.dataDir, fname);
            if ~isfile(fpath)
                warning("Missing file: %s", fpath); continue
            end
            R = analyzeFile(fpath, m, cfg);

            nR = height(R.roi);
            R.roi.File   = repmat(string(fname), nR, 1);
            R.roi.Scene  = repmat(sc,  nR, 1);
            R.roi.SNR    = repmat(snr, nR, 1);
            R.roi.Method = repmat(m,   nR, 1);
            roiAll{end+1,1} = R.roi; %#ok<SAGROW>

            M = R.metrics;
            M.File = string(fname); M.Scene = sc; M.SNR = snr; M.Method = m;
            metAll{end+1,1} = struct2table(M); %#ok<SAGROW>

            if sc == "MIXED" && ismember(snr, cfg.gallerySNR)
                demo.(m).("s" + snr) = R;
            end
        end
    end
end

ROI = vertcat(roiAll{:});
MET = vertcat(metAll{:});
MET = movevars(MET, ["Method" "Scene" "SNR" "File"], Before=1);

%% ---- Localization results ---------------------------------------------
disp("=== Localization metrics (mean over scenes, by method and SNR) ===");
G = groupsummary(MET, ["Method" "SNR"], "mean", ...
    ["PixPrecision" "PixRecall" "PixF1" "PixIoU" "BoxRecall" "BoxPrecision"]);
disp(G);

%% ---- Plots: heatmaps (scene x SNR) ------------------------------------
metricsToShow = ["PixF1" "BoxRecall" "BoxPrecision"];
metricTitles  = ["Pixel F1" "GT box recall" "ROI precision"];
for m = cfg.methods
    figure("Name", "Heatmaps - " + m, Position=[100 100 1300 380]);
    tl = tiledlayout(1, numel(metricsToShow), TileSpacing="compact");
    title(tl, sprintf("Localization quality, method = %s", m), FontWeight="bold");
    for q = 1:numel(metricsToShow)
        Z = nan(numel(cfg.scenes), numel(cfg.snrList));
        for a = 1:numel(cfg.scenes)
            for b = 1:numel(cfg.snrList)
                r = MET(MET.Method==m & MET.Scene==cfg.scenes(a) & MET.SNR==cfg.snrList(b), :);
                if ~isempty(r), Z(a,b) = r.(metricsToShow(q)); end
            end
        end
        nexttile
        h = heatmap(string(cfg.snrList), cfg.scenes, Z, ...
            ColorLimits=[0 1], Colormap=parula, CellLabelFormat="%.2f", ...
            MissingDataColor=[0.8 0.8 0.8]);
        h.Title = metricTitles(q); h.XLabel = "SNR (dB)"; h.YLabel = "Scene";
    end
end

%% ---- Plots: method comparison, mean and min-max over scenes ---------------
figure("Name","Method comparison", Position=[100 100 1300 380]);
tl = tiledlayout(1, numel(metricsToShow), TileSpacing="compact");
title(tl, "Method comparison (mean over scenes, band = min..max)", FontWeight="bold");
cols = lines(numel(cfg.methods));
for q = 1:numel(metricsToShow)
    nexttile; hold on; grid on; box on
    for k = 1:numel(cfg.methods)
        mu = nan(size(cfg.snrList)); lo = mu; hi = mu;
        for b = 1:numel(cfg.snrList)
            v = MET.(metricsToShow(q))(MET.Method==cfg.methods(k) & MET.SNR==cfg.snrList(b));
            if ~isempty(v), mu(b) = mean(v); lo(b) = min(v); hi(b) = max(v); end
        end
        fill([cfg.snrList fliplr(cfg.snrList)], [lo fliplr(hi)], cols(k,:), ...
            FaceAlpha=0.15, EdgeColor="none", HandleVisibility="off");
        plot(cfg.snrList, mu, "-o", Color=cols(k,:), LineWidth=2, ...
            MarkerFaceColor=cols(k,:), DisplayName=cfg.methods(k));
    end
    xlabel("SNR (dB)"); ylabel(metricTitles(q)); title(metricTitles(q));
    ylim([0 1.02]); xlim([min(cfg.snrList) max(cfg.snrList)]);
    if q == 1, legend(Location="southeast"); end
end

%% ---- Plots: per-scene curves vs SNR -----------------------------------
figure("Name","Per-scene F1 vs SNR", Position=[100 100 1300 380]);
tl = tiledlayout(1, numel(cfg.methods), TileSpacing="compact");
title(tl, "Pixel F1 vs SNR per scene", FontWeight="bold");
mk = ["o" "s" "^" "d" "p"]; sceneCols = lines(numel(cfg.scenes));
for m = cfg.methods
    nexttile; hold on; grid on; box on
    for a = 1:numel(cfg.scenes)
        s = sortrows(MET(MET.Method==m & MET.Scene==cfg.scenes(a), :), "SNR");
        plot(s.SNR, s.PixF1, "-" + mk(a), Color=sceneCols(a,:), LineWidth=1.8, ...
            MarkerFaceColor=sceneCols(a,:), DisplayName=cfg.scenes(a));
    end
    yline(0.5, "k:", HandleVisibility="off");
    title(m); xlabel("SNR (dB)"); ylabel("Pixel F1"); ylim([0 1.02]);
    legend(Location="southeast");
end

%% ---- Plots: MIXED gallery, ground truth vs detections -----------------
for m = cfg.methods
    if ~isfield(demo, m), continue; end
    figure("Name", "MIXED gallery - " + m, Position=[50 50 1400 800]);
    tl = tiledlayout(2, 2, TileSpacing="compact");
    title(tl, sprintf("MIXED scene, method = %s   (green = ground truth, red dashed = detected ROI)", m), ...
        FontWeight="bold");
    for snr = cfg.gallerySNR
        key = "s" + snr;
        if ~isfield(demo.(m), key), continue; end
        R = demo.(m).(key);
        nexttile
        D = 10*log10(R.P2);
        imagesc(R.t*1e3, R.f/1e6, D); axis xy; colormap(gca, turbo);
        clim(prctile(D(:), [5 99.5]));
        xlabel("Time (ms)"); ylabel("Frequency (MHz)");
        mt = MET(MET.Method==m & MET.Scene=="MIXED" & MET.SNR==snr, :);
        title(sprintf("%d dB  |  F1 %.2f, recall %.2f, %d ROIs", snr, ...
            mt.PixF1, mt.BoxRecall, mt.nROI));
        hold on
        for i = 1:size(R.gt, 1)          % [tlo thi flo fhi]
            rectangle(Position=[R.gt(i,1)*1e3, R.gt(i,3)/1e6, ...
                (R.gt(i,2)-R.gt(i,1))*1e3, (R.gt(i,4)-R.gt(i,3))/1e6], ...
                EdgeColor=[0.2 1 0.2], LineWidth=2);
            text(R.gt(i,1)*1e3 + 0.5, R.gt(i,4)/1e6, R.gtClass(i), ...
                Color="w", FontWeight="bold", VerticalAlignment="bottom", ...
                BackgroundColor=[0 0.4 0 0.6], Margin=1);
        end
        for i = 1:size(R.boxes, 1)
            rectangle(Position=[R.boxes(i,1)*1e3, R.boxes(i,3)/1e6, ...
                (R.boxes(i,2)-R.boxes(i,1))*1e3, (R.boxes(i,4)-R.boxes(i,3))/1e6], ...
                EdgeColor="r", LineStyle="--", LineWidth=1.5);
        end
    end
    cb = colorbar; cb.Layout.Tile = "east"; cb.Label.String = "Power (dB)";
end

%% ---- ROI clustering and cluster naming per method ---------------------
for m = cfg.methods
    T = ROI(ROI.Method == m, :);
    if height(T) < cfg.k
        warning("%s: only %d ROIs, skipping clustering.", m, height(T)); continue
    end
    X = zscore(T{:, cfg.features});
    X(~isfinite(X)) = 0;
    idx = kmedoids(X, cfg.k, Distance="cityblock", Replicates=cfg.replicates);

    % Simulated expert: name each cluster by its majority ground-truth class
    predClass = helperMapClusterLabels(idx, T.Class);
    T.Cluster   = idx;
    T.PredClass = predClass;
    acc = mean(predClass == T.Class);

    fprintf("\n=== %s: %d ROIs, k=%d, ROI-label accuracy = %.1f%% ===\n", ...
        m, height(T), cfg.k, 100*acc);
    disp(groupsummary(T, ["Cluster" "Class"]));

    figure("Name", sprintf("ROI classification - %s", m));
    confusionchart(categorical(T.Class, cfg.classes), ...
                   categorical(T.PredClass, cfg.classes), ...
                   RowSummary="row-normalized", ...
                   Title=sprintf("%s: clusters named by majority GT class (acc %.1f%%)", m, 100*acc));

    % Accuracy by SNR
    [g, snrs] = findgroups(T.SNR);
    accBySNR = splitapply(@(a,b) mean(a==b), T.PredClass, T.Class, g);
    disp(table(snrs, accBySNR, VariableNames=["SNR" "ROI_label_accuracy"]));

    % Visualise clusters in feature space (first two features)
    figure("Name", sprintf("Feature space - %s", m));
    gscatter(T.(cfg.features(1)), T.(cfg.features(2)), string(T.Class));
    xlabel(cfg.features(1)); ylabel(cfg.features(2)); grid on
    title(sprintf("ROI features coloured by ground truth - %s", m));
end

%% ---- Save results -----------------------------------------------------
writetable(MET, fullfile(here, "matlab_test_metrics.csv"));
writetable(ROI, fullfile(here, "matlab_test_rois.csv"));
fprintf("\nSaved matlab_test_metrics.csv and matlab_test_rois.csv in %s\n", here);

%% ======================== Local functions ==============================
function R = analyzeFile(fpath, method, cfg)
% Localize ROIs in one file and score them against the embedded GT.
    S  = load(fpath);
    x  = double(S.iq(:));
    fs = double(S.fs);

    [s, f, t] = stft(x, fs, "Window", hann(cfg.nfft), ...
        "OverlapLength", cfg.nfft - cfg.hop, "FFTLength", cfg.nfft, ...
        "FrequencyRange", "centered");
    P2 = abs(s).^2;                     % power image, rows = freq, cols = time
    [nF, nT] = size(P2);
    df = f(2) - f(1);
    dt = cfg.hop / fs;

    % Remove the DC spike (a constant horizontal line) by interpolation
    dc = find(abs(f) == min(abs(f)), 1);
    if dc > 4 && dc + 4 <= nF
        P2(dc-1:dc+1, :) = repmat(0.5*(P2(dc-4,:) + P2(dc+4,:)), 3, 1);
    end

    Ps    = imgaussfilt(P2, cfg.sigma);
    % Robust noise reference from the central band only (the band edges roll
    % off by up to 20 dB and would bias the estimate low -> many false alarms)
    r1g = max(1, round(cfg.edgeGuard*nF)); r2g = nF - r1g;
    noise = prctile(reshape(Ps(r1g:r2g, :), [], 1), 30);

    % ---- ROI localization ----
    switch method
        case "noisefloor"
            mask = Ps > noise * 10^(cfg.marginDb/10);
        case "adaptthresh"
            I   = mat2gray(10*log10(Ps));
            nbh = 2*floor(size(I)/cfg.adaptNbhDiv) + 1;
            T   = adaptthresh(I, cfg.adaptSens, "NeighborhoodSize", nbh, ...
                "ForegroundPolarity", "bright", "Statistic", "gaussian");
            mask = imbinarize(I, T);
        otherwise
            error("Unknown method: %s", method);
    end
    mask([1:r1g-1, r2g+1:nF], :) = false;
    mask = imclose(mask, strel("rectangle", cfg.close));
    mask = bwareaopen(mask, cfg.minArea);
    mask = imdilate(mask, strel("rectangle", cfg.dilate));

    CC    = bwconncomp(mask);
    stats = regionprops(CC, "BoundingBox");

    % ---- Ground truth (TF units) ----
    gt      = [S.gt_t_start_s(:) S.gt_t_end_s(:) S.gt_f_lo_hz(:) S.gt_f_hi_hz(:)];
    gtClass = string(S.gt_class(:));

    % ---- Features + false-alarm filter ----
    keepBox = zeros(0,4);     % [c1 c2 r1 r2]
    tf      = zeros(0,4);     % [tlo thi flo fhi]
    feat    = struct("MedianDb",[],"Duration",[],"Bandwidth",[],"CenterFreq",[], ...
                     "Spread",[],"Skewness",[],"Kurtosis",[],"Entropy",[]);
    for i = 1:numel(stats)
        bb = stats(i).BoundingBox;      % [x y w h], pixel edges at .5
        c1 = ceil(bb(1)); c2 = min(c1 + bb(3) - 1, nT);
        r1 = ceil(bb(2)); r2 = min(r1 + bb(4) - 1, nF);
        reg = Ps(r1:r2, c1:c2);
        medDb = 10*log10(median(reg(:)) / noise);
        if medDb < cfg.minMedianDb, continue; end   % false-alarm filter

        % Refine the box: at high SNR the threshold also captures spectral
        % skirts, so shrink to the band holding cfg.occ of the ROI energy
        % (same definition as the ground-truth "99 % occupied band") and
        % trim bursts in time to where the energy is >= cfg.timeFrac of peak.
        seg = max(P2(r1:r2, c1:c2) - noise, 0);
        if any(seg(:) > 0)
            cp = cumsum(sum(seg, 2)) / sum(seg(:));
            a  = find(cp >= (1-cfg.occ)/2, 1, "first");
            b  = find(cp >= 1-(1-cfg.occ)/2, 1, "first");
            tp = sum(seg(a:b, :), 1);
            tp = movmean(tp, 3);
            cols = find(tp >= cfg.timeFrac * max(tp));
            r2 = r1 + b - 1; r1 = r1 + a - 1;
            c2 = c1 + cols(end) - 1; c1 = c1 + cols(1) - 1;
            reg = Ps(r1:r2, c1:c2);
            medDb = 10*log10(median(reg(:)) / noise);
        end

        ft = regionFeatures(P2(r1:r2, c1:c2), f(r1:r2), df, dt, noise);
        ft.MedianDb = medDb;
        feat(end+1,1) = ft; %#ok<AGROW>
        keepBox(end+1,:) = [c1 c2 r1 r2]; %#ok<AGROW>
        tf(end+1,:) = [max(t(c1) - dt/2, 0), t(c2) + dt/2, ...
                       f(r1) - df/2,         f(r2) + df/2]; %#ok<AGROW>
    end
    feat = feat(~arrayfun(@(q) isempty(q.Duration), feat));

    % ---- Image rejection: the I/Q imbalance of the receiver puts a weak
    % mirror image at -f of every strong signal. Drop an ROI if a mirrored
    % ROI that is >= cfg.imageDb stronger overlaps it in time and frequency.
    n0 = size(tf, 1); drop = false(n0, 1);
    for i = 1:n0
        for j = [1:i-1, i+1:n0]
            fMir = [-tf(j,4), -tf(j,3)];
            fOv  = min(tf(i,4), fMir(2)) - max(tf(i,3), fMir(1));
            tOv  = min(tf(i,2), tf(j,2)) - max(tf(i,1), tf(j,1));
            if fOv > 0.5*(tf(i,4)-tf(i,3)) && tOv > 0 && ...
               feat(j).MedianDb - feat(i).MedianDb >= cfg.imageDb
                drop(i) = true; break
            end
        end
    end
    tf = tf(~drop,:); keepBox = keepBox(~drop,:); feat = feat(~drop);
    n = size(tf, 1);

    % ---- Assign a ground-truth class to every ROI (by IoU) ----
    roiClass = repmat("FalseAlarm", n, 1);
    roiIoU   = zeros(n, 1);
    IoU = boxIoU(tf, gt);               % n x nGT
    for i = 1:n
        if ~isempty(IoU) && any(IoU(i,:) > 0)
            [v, j] = max(IoU(i,:));
            roiIoU(i) = v;
            if v >= cfg.iouLabel, roiClass(i) = gtClass(j); end
        end
    end

    % ---- ROI table ----
    if n > 0
        roi = struct2table(feat);
        roi = [table((1:n)', 'VariableNames', "Index"), ...
               table(keepBox(:,1:2) ,'VariableNames',"BoundingBoxCols"), ...
               table(tf, 'VariableNames', "BoundingBoxTF"), roi];
    else
        roi = table(zeros(0,1), zeros(0,2), zeros(0,4), ...
            zeros(0,1), zeros(0,1), zeros(0,1), zeros(0,1), zeros(0,1), ...
            zeros(0,1), zeros(0,1), zeros(0,1), ...
            'VariableNames', ["Index" "BoundingBoxCols" "BoundingBoxTF" ...
            "MedianDb" "Duration" "Bandwidth" "CenterFreq" "Spread" ...
            "Skewness" "Kurtosis" "Entropy"]);
    end
    roi.Class  = roiClass;
    roi.BestIoU = roiIoU;

    % ---- Pixel-level evaluation (boxes -> masks vs GT mask) ----
    predMask = false(nF, nT);
    for i = 1:n
        predMask(keepBox(i,3):keepBox(i,4), keepBox(i,1):keepBox(i,2)) = true;
    end
    gtMask = false(nF, nT);
    for i = 1:size(gt, 1)
        rows = f >= gt(i,3) & f <= gt(i,4);
        if ~any(rows), [~, r] = min(abs(f - mean(gt(i,3:4)))); rows(r) = true; end
        cols = t >= gt(i,1) & t <= gt(i,2);
        gtMask(rows, cols) = true;
    end
    TP = nnz(predMask & gtMask);
    FP = nnz(predMask & ~gtMask);
    FN = nnz(~predMask & gtMask);
    M.PixPrecision = TP / max(TP + FP, 1);
    M.PixRecall    = TP / max(TP + FN, 1);
    M.PixF1        = 2*TP / max(2*TP + FP + FN, 1);
    M.PixIoU       = TP / max(TP + FP + FN, 1);

    % ---- Box-level evaluation (greedy IoU matching) ----
    nGT = size(gt, 1);
    Mtx = IoU;  matchedGT = 0; matchedPred = 0;
    if ~isempty(Mtx)
        while true
            [v, k] = max(Mtx(:));
            if isempty(v) || v < cfg.iouMatch, break; end
            [i, j] = ind2sub(size(Mtx), k);
            Mtx(i,:) = 0; Mtx(:,j) = 0;
            matchedGT = matchedGT + 1; matchedPred = matchedPred + 1;
        end
    end
    M.nGT          = nGT;
    M.nROI         = n;
    M.BoxRecall    = matchedGT / max(nGT, 1);
    M.BoxPrecision = matchedPred / max(n, 1);

    R = struct("roi", roi, "metrics", M, "P2", P2, "t", t, "f", f, ...
               "boxes", tf, "gt", gt, "gtClass", gtClass);
end

function ft = regionFeatures(reg, fvec, df, dt, noise)
% Spectral-shape features of an ROI, computed on its noise-subtracted
% time-averaged spectrum (treated as a distribution over frequency).
    psd = mean(reg, 2) - noise;
    psd = max(psd, 0) + eps;
    p   = psd / sum(psd);
    fv  = fvec(:);
    cf  = sum(p .* fv);
    sp  = sqrt(sum(p .* (fv - cf).^2));
    if sp > 0 && numel(p) > 1
        sk = sum(p .* (fv - cf).^3) / sp^3;
        ku = sum(p .* (fv - cf).^4) / sp^4;
    else
        sk = 0; ku = 0;
    end
    if numel(p) > 1
        en = -sum(p .* log2(p)) / log2(numel(p));    % normalised 0..1
    else
        en = 0;
    end
    ft = struct("MedianDb", NaN, ...
        "Duration",  size(reg, 2) * dt, ...
        "Bandwidth", size(reg, 1) * df, ...
        "CenterFreq", cf, "Spread", sp, "Skewness", sk, "Kurtosis", ku, ...
        "Entropy", en);
end

function IoU = boxIoU(A, B)
% A, B: [tlo thi flo fhi]; returns size(A,1) x size(B,1) IoU matrix.
    IoU = zeros(size(A,1), size(B,1));
    for i = 1:size(A,1)
        for j = 1:size(B,1)
            dtI = min(A(i,2), B(j,2)) - max(A(i,1), B(j,1));
            dfI = min(A(i,4), B(j,4)) - max(A(i,3), B(j,3));
            if dtI > 0 && dfI > 0
                inter = dtI * dfI;
                uni = (A(i,2)-A(i,1))*(A(i,4)-A(i,3)) + ...
                      (B(j,2)-B(j,1))*(B(j,4)-B(j,3)) - inter;
                IoU(i,j) = inter / uni;
            end
        end
    end
end

function predClass = helperMapClusterLabels(idx, trueClass)
% Simulates the expert: every cluster is named after the majority
% ground-truth class of its members.
    predClass = strings(size(idx));
    for c = unique(idx(:))'
        members = idx == c;
        predClass(members) = string(mode(categorical(trueClass(members))));
    end
end
