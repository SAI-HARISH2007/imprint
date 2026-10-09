---
title: Imprint API
emoji: 🔏
colorFrom: purple
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

Image service and relay for Imprint, an image registry on Monad testnet.

Endpoints: `/health`, `/config`, `/mark`, `/claim`, `/check`, `/challenge`, `/register`, `/receipt/verify`, `/verify`, `/record/{id}`, `/records`, `/status`, `/stress`.

`/mark` withholds the marked image and returns a short-lived claim token; the pixels are revealed by `/register` (matching claim) or `/claim` (only once the ID is on chain). See `docs/enforcement.md`.

Secrets: `IMPRINT_RELAYER_KEY` (a testnet-only wallet that pays gas).
