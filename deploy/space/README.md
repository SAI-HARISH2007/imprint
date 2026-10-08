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

Endpoints: `/health`, `/config`, `/mark`, `/check`, `/challenge`, `/register`, `/verify`, `/record/{id}`, `/records`, `/stress`.

Secrets: `IMPRINT_RELAYER_KEY` (a testnet-only wallet that pays gas).
