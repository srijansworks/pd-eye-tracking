# pupilnet.pt: neural pupil-centre detector (research prototype)

- **What:** a tiny U-Net (0.39 M parameters) that outputs a heatmap of the pupil centre in a near-eye
  infrared image (input resized to 160×120). It's used in `--ir-method hybrid`, where the network finds the pupil
  and the classic ellipse fit refines it.
- **Training data:** LPW, "Labelled Pupils in the Wild" (Tonsen, Zhang, Sugano & Bulling, ETRA 2016,
  doi 10.1145/2857491.2857520). 16 participants for training, 2 for model selection, 4 held out (2, 5, 10, 17).
- **License: CC BY-NC 3.0, inherited from LPW.** Non-commercial research and education only; credit LPW.
  A commercial product would need a model retrained on our own (consented) data.
- **Held-out test (4 unseen people, 2,400 frames), within 5 px at 640×480:** classic 45.7%,
  network 59.8%, **hybrid 65.5%** (within 10 px: 48.8% / 79.0% / 79.5%). Validation people: 93.9%.
- **Known weaknesses:** washed-out pupils behind glasses frames, heavy blur. About 16 ms/frame (hybrid) on an
  8 GB Apple-chip laptop, which isn't yet real-time at 120 fps.
- **Not a medical device.** Measures pupil position only; says nothing about any disease.
- Reproduce: `python -m eyetrack.nearir.nn_data --data ../data/lpw --out ../data/lpw_cache`, then
  `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.45 PYTORCH_MPS_LOW_WATERMARK_RATIO=0.35 python -m eyetrack.nearir.nn_train --cache ../data/lpw_cache --epochs 4 --bs 32 --lr 1.5e-3`
  (about 15 min on an 8 GB Mac; the memory caps stop it swapping), then `python -m eyetrack.nearir.nn_eval --data ../data/lpw`.
