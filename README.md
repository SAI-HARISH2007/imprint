# Imprint

Register an image once. A re-compressed, resized or screenshotted copy still proves who registered it and when, and an edited fake is flagged as altered.

Built for the Monad Metropolis hackathon (Track 4: Trust, Identity and AI Infrastructure).

Status: work in progress.

- `phase1/`: does an invisible watermark survive ordinary sharing? Yes, on our simulated tests.
- `service/`: image service (mark, check) and the verdict logic, with tests.
- `contracts/`: `ImprintRegistry`, the public record. Deployed on Monad testnet at `0xF88Ab1f3E04Df4C8A6d5EAf3a64E3AC55095b664` (chain 10143), source verified. See `deployments/monad-testnet.json`.

## Phase 1

`phase1/robustness.py` marks 24 test photos, damages each in 21 ways, and checks whether the watermark still decodes and how far a perceptual hash drifts. `phase1/extra.py` covers flips, rotation, double-marking and edit separation. Raw numbers are in `phase1/results/`.

Known limits so far: heavy crops and rotation break the watermark, and the transforms were simulated, not sent through real messaging apps.
