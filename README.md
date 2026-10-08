# Imprint

Register an image once. A re-compressed, resized or screenshotted copy still proves who registered it and when, and an edited fake is flagged as altered.

Built for the Monad Metropolis hackathon (Track 4: Trust, Identity and AI Infrastructure).

Status: work in progress. Phase 1 (does an invisible watermark survive ordinary sharing?) is done: see `phase1/`.

## Phase 1

`phase1/robustness.py` marks 24 test photos, damages each in 21 ways, and checks whether the watermark still decodes and how far a perceptual hash drifts. `phase1/extra.py` covers flips, rotation, double-marking and edit separation. Raw numbers are in `phase1/results/`.

Known limits so far: heavy crops and rotation break the watermark, and the transforms were simulated, not sent through real messaging apps.
