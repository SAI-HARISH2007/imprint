# Validating the paying use case

Imprint's paying hypothesis: *creators who monetize images want a durable,
trustless, public receipt proving an image existed from a moment in time — one
clients can check without trusting a vendor.* Hackathon builds rarely validate
this with real money, and this repo only contains a plan: **running the pilots
below requires actual creators, platforms and a few weeks, and is external to
this repository.** The plan is written so that anyone can execute it verbatim.

## The hypothesis to falsify

1. A working photographer or studio has been burned by image reuse (someone uses
   their photo without credit/payment, or scrapes it to train a model) **at least
   once this year**.
2. That person believes a *machine-checkable, timestamped, public* claim of
   first-publication changes the outcome of future disputes or licensing — i.e.,
   it is worth paying for, not just nice to have.
3. The funnel survives first contact: registering with a passkey, in under a
   minute, and getting back a marked copy that still looks publishable, is
   actually achievable for a non-technical creator.

If any of the three is false cheaply (interviews), the product changes before
code is written.

## Who to talk to (8-10 candidates)

- Stock / microstock contributors (Shutterstock, Adobe Stock, Dreamstime) who
  already track stolen usage.
- Solo sellers on Fiverr/Upwork who deliver images and get disputes over whether
  the delivered file is "theirs".
- Small studios that publish and license photos and need a chain-of-custody line.
- Users of AI-content detectors — they are the ones already paying for a weaker
  answer (a per-image probabilistic "AI or not").

Each interview is 30 minutes, recorded with permission, structured around the
three falsifiable claims, ending with a **price ladder**: free, $5/mo, $50/mo,
$100+/mo — which does the registrations-per-month stop at, and why.

## Two-week pilot (3-5 creators, ~50-200 images each)

Testnet is free, so the pilot costs nothing to run:

1. Creator registers 20 "back-catalog" images (already published): we can show
   they now carry a dated, public, passkey-signed record + receipt.
2. Creator registers 20 "hot" images (new work) before publishing, then starts
   publishing them at full resolution with the mark **and** unmarked — the pilot
   measures whether a visible-quality mark at working resolution is acceptable.
3. Each week the creator does the *real-loss scenario*: a client/team sends back
   a phone screenshot of the image or a message-app re-download of it, and the
   creator checks it against the record live. This feeds
   `docs/real-world-testing.md` as real WhatsApp/Telegram/screenshot captures.
4. Weekly check-in: which images, what friction (WebAuthn? mark quality? speed?),
   what they would actually pay, and — deliberately — who they think would *not*
   pay and why.

## Success metrics

- ≥60% of registered images get exercised through the real-loss scenarios;
- ≥50% of participants reach "$50/mo" or above on the ladder unprompted;
- every "not worth it" answer is captured verbatim (the negative results are the
  product lesson, not a failure to hide).

## What the pilot would produce for the product (and what it must not)

- **Allowed:** a paid *convenience* tier — relayer throughput, higher rate
  limits, an API key with predictable RPC-backed lookups, dashboards, SLA —
  priced from the ladder.
- **Not allowed:** any tier that weakens the trust model. Records stay on the
  same permissionless registry everyone can read with plain calls; a paid tier
  is wrappers and capacity, never a private walled registry or a soft-borrow in
  the duplicate guard.

## Current status

**Open — external.** The interviews, the pilot participants and the weeks belong
to humans with a market. Everything in this repository serves the plan: the
live registry is up, `service/bench_verify.py` measures the read latency a tier
would promise, `docs/real-world-testing.md` defines the capture protocol the
pilot feeds, and the `WebAuthn` registration path is already a one-tap flow. The
moment a pilot produces its numbers, the "is anyone paying" question stops being
an assumption.