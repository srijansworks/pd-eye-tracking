# Literature review: starting shortlist (Srijan: eye movements + wrist data)

Week 1 asks for 6–7 relevant papers per person, actually read. This list is a **starting point**
found during the dataset search. I haven't checked these against each other, and the "what to extract" column
says what to pull out while reading, not what the papers conclude. All links are legal, open-access copies
where available (PMC, publisher open access).

| # | Paper | Why it matters for us | What to extract while reading |
|---|---|---|---|
| 1 | [Eye Tracking in Parkinson's Disease: A Review of Oculomotor Markers and Clinical Applications (PMC, 2025)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12025636/) | Recent overview of which eye metrics differ in PD | Table of markers (saccade latency, gain, antisaccade errors, pursuit gain, square-wave jerks, blink rate) with the direction of change and reported accuracies, which gives us our "benchline" |
| 2 | [Smooth pursuit and memory saccades are impaired in early-stage PD (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12873708/) | Early-stage effects matter most for screening | Effect sizes for pursuit gain; task parameters (target speed) we could copy into `eye_v1` |
| 3 | [Classification and staging of PD using video-based eye tracking (Brien et al., 2023)](https://www.researchgate.net/publication/368373682_Classification_and_staging_of_Parkinson's_disease_using_video-based_eye_tracking) | Closest to our idea: video eye tracking with ML classification | Camera frame rate, task (pro/antisaccade), classifier accuracy/AUC, how they validated |
| 4 | [Exploring eye movement abnormalities as objective biomarkers for PD using VR-based eye tracking (BMC Neurology, 2026)](https://link.springer.com/article/10.1186/s12883-026-04634-w) | A consumer-grade headset (not a lab tracker), much like our planned glasses | Which metrics still separate PD from controls at headset-grade sampling rates |
| 5 | [Eye movement control during visual pursuit in PD (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6109371/) | Pursuit mechanics; has raw data files | How they compute pursuit gain and catch-up saccades (compare with our `features.py`) |
| 6 | [Eye movements in Parkinson's disease (Oxford Research Archive)](https://ora.ox.ac.uk/objects/uuid:22cfb125-4db7-46f9-90eb-8c638e378a1b/files/rwm117p93d) | Background on why PD changes eye movements (basal ganglia) | Mechanisms, for the Conrad write-up |
| 7 | [Machine learning in the PD smartwatch (PADS) dataset (Varghese et al., npj PD 2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10770131) | Wrist-sensor baseline on the dataset we'll likely use | Reported accuracy for PD vs controls and vs other movement disorders; the features that worked |

Also useful for validating our pipeline: [GazeBase data descriptor (Scientific Data 2021)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8285447/).

Paywalls: use the PMC/arXiv version, the "Request full text" button on ResearchGate, your school or
public library access, or email the authors (most will send a copy).
