# OpenAlex: keys, budget, and finishing the corpus

`build_corpus.py` resolves each manuscript's reference list against OpenAlex to
find open-access PDFs. OpenAlex became a metered, paid API in February 2026, and
that is why the retrieval eval currently covers **4 of 15 topics**.

**Read this first, because it probably saves you the money:** the single biggest
lever is not paying, it is getting a **free API key**. An unauthenticated caller
gets **$0.10/day**. A free key — no credit card — gets **$1.00/day**, ten times
as much, and the entire remaining build is estimated at **~$0.38**. On the
measured numbers below, a free key finishes the job in one run for $0.

Add prepaid credit only if you want headroom against the estimate being wrong.

---

## 1. Sign up and (optionally) add funds

| Step | URL |
|------|-----|
| Create an account (free, ~30 seconds) | <https://openalex.org> |
| Get your API key | <https://openalex.org/settings/api> |
| Buy prepaid usage, if you want it | <https://openalex.org/pricing> |
| Watch spend | <https://openalex.org/settings/usage> |

**What I verified and what I did not.** The URLs above are the ones OpenAlex's
own documentation and launch blog post give. I could **not** load
`openalex.org/pricing` or `openalex.org/settings/api` to check the on-page flow —
both return **HTTP 403** to non-browser clients (bot protection). So I cannot
confirm, from my own observation, what the checkout looks like, which payment
methods are accepted, or whether prepaid credit is bought per-key or per-account.
OpenAlex's blog states you can "buy prepaid usage in 1min with your credit card,
whenever you want, however much you want," but **I am relaying that, not
confirming it.** Open the page in a browser and trust what you see there over
this file.

What I *did* confirm live is that prepaid balance is a real, separate pool: the
API returns an `X-RateLimit-Prepaid-Remaining-USD` header alongside the daily
allowance, and `--check-budget` reports both.

## 2. Where the key goes

OpenAlex authenticates with an **`api_key` query parameter** — not a bearer
token, not a custom header.

Confirmed two ways:

- <https://developers.openalex.org/api-reference/authentication> — *"add
  `api_key=YOUR_KEY` to your API calls"*, example
  `curl "https://api.openalex.org/works?api_key=YOUR_KEY"`.
- Live, on 2026-07-30: a bogus key on `?api_key=` returns
  `401 {"error":"Invalid or missing API key"}` — so the parameter is genuinely
  read and validated, not ignored.

Set it as an environment variable:

```bash
export OPENALEX_API_KEY=<your key>
```

or add a line to `services/backend/.env`:

```
OPENALEX_API_KEY=<your key>
```

**Never commit the key.** It is a credential that spends money. Note that
because OpenAlex puts it in the *URL* rather than a header, it is unusually easy
to leak — it would otherwise show up in any logged request URL. `build_corpus.py`
routes every printed message, raised exception and written file through a
redaction step, and there are tests asserting the key appears in none of them. If
you add code here, keep it that way.

`mailto` is unrelated and unchanged: it is the old *polite pool* convention, not
authentication. The script still sends it either way.

## 3. Verify the key worked

```bash
python3 scripts/eval/build_corpus.py --check-budget
```

One cheap request, then it exits. Funded and working looks like:

```
[build-corpus] OpenAlex: authenticated
[build-corpus]   daily allowance remaining: $1.0000 of $1.00
[build-corpus]   prepaid balance: $1.0000
[build-corpus]   spendable now: $2.0000 (~2000 title searches)
```

The state you are in *right now*, with no key, is this real output:

```
[build-corpus] OpenAlex: unauthenticated (free tier)
[build-corpus]   daily allowance remaining: $0.0000 of $0.10
[build-corpus]   prepaid balance: $0.0000
[build-corpus]   spendable now: $0.0000 (~0 title searches)
[build-corpus]   daily allowance resets in 2.9h (midnight UTC)
[build-corpus] Budget is spent. Add prepaid credit at https://openalex.org/pricing
               or wait for the midnight-UTC reset.
```

Exit codes: `0` fine, `1` key rejected or OpenAlex unreachable, `2` budget spent.
A mistyped key reports `API key rejected (401)` rather than silently falling back
to the unauthenticated tier.

## 4. Finish the remaining 11 papers

```bash
export OPENALEX_API_KEY=<your key>
python3 scripts/eval/build_corpus.py --check-budget     # confirm first
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0
```

`--openreview-all` walks every OpenReview topic that has cached claims and skips
the four already done, so this one command is the whole job.

**Measured, not guessed.** Parsing the 11 outstanding manuscripts offline gives:

| | |
|---|---|
| References still to resolve | **418** (+19 `pending` in `BQvbL2sFQx`) |
| Of those, carrying a DOI | 90 |
| Estimated OpenAlex requests | **~463** |
| Estimated cost | **~$0.38**, worst case ~$0.43 |
| Wall clock | **~30–40 min**, set by the 0.12s throttle and PDF downloads, not by budget |

Two things make this cheaper than a flat "one call per reference" estimate:

- A single-entity lookup (`/works/<doi>`) costs **$0.0001**; a title search
  (`/works?search=`) costs **$0.001** — 10x more. Only 90 of 418 references have
  a DOI, which is why the cost is dominated by searches.
- Downloading the OA PDFs is **free**. Those fetch from the publisher or
  repository at `oa_url`, not from OpenAlex, so they never touch the budget.

Prices confirmed live from `X-RateLimit-Cost-Required-USD` on 2026-07-30.

One caveat I could not settle: OpenAlex's launch blog says single-record lookups
by ID or DOI are *free and unmetered*. The live headers disagree — a DOI lookup
reported a required cost of `$0.0001`. The estimate above assumes the **headers**
are right, i.e. the pessimistic reading. If the blog is right, the run is cheaper
still.

The script now prints the request count, the estimated cost and your remaining
budget **before** it starts each corpus, and warns outright if the budget cannot
cover the estimate — so an under-funded run announces itself in the first second
rather than 429ing twenty minutes in.

## 5. The free route: no money at all

The build is **fully resumable**, so you can simply run it once a day and let the
midnight-UTC reset pay for it.

```bash
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0
```

Re-run after each reset. It picks up exactly where it stopped.

- With **no key** ($0.10/day) that is roughly **4 days**; with a **free key**
  ($1.00/day) it should finish in **one run**.
- Re-running finished work is free: I measured re-checking the three completed
  corpora at **0.4s and zero network calls**. Already-resolved references are
  served from the `references.json` sidecar and never looked up again.
- It is safe to run unsupervised. When the budget runs out mid-run, unlooked-up
  references are recorded as `pending`, **not** as `no_openalex_match`. That
  distinction matters: `no_openalex_match` is a terminal state the resume index
  would skip forever, so mislabelling it would silently and permanently shorten
  the corpus while still counting toward the denominator. `pending` stays in the
  denominator and is retried on the next run.

Given the free key gets $1/day, **section 5 and section 4 are likely the same
run.** The money is optional.

## 6. What was not built: a Crossref + Unpaywall fallback

There is an obvious free alternative — resolve references through Crossref
(metadata, no key, no charge) and Unpaywall (OA locations, free with a `mailto`)
and skip OpenAlex entirely. It was considered and deliberately not built. The
reasons are about correctness of the eval, not effort:

1. **Different id space.** The `references.json` sidecar is specified around
   `openalex_id` — that field is the join key, and `retrieval/labels.py` reads
   the sidecar as the retrieval label set. Crossref returns DOIs and Unpaywall
   returns OA locations; neither yields an OpenAlex work id. Supporting both
   means either a nullable id column, which weakens the schema for every
   consumer, or a translation step that needs OpenAlex anyway.
2. **Different match semantics.** OpenAlex title search and Crossref
   bibliographic search do not agree on what counts as a match, and they fail
   differently on preprints, workshop papers and arXiv duplicates. A corpus built
   half one way and half the other has a *resolution rate that no longer means
   one thing* — and the whole point of the sidecar is that the denominator is
   trustworthy. Mixing resolvers across the 15 topics would quietly make the
   retrieval numbers incomparable between topics, which is worse than having 4
   topics that are comparable.
3. **The cost being avoided is ~$0.38**, or $0 with a free key. Building a
   second resolver to dodge that, at the price of a fuzzier eval, is a bad trade.

If OpenAlex ever becomes genuinely unaffordable, the honest version of this is a
full migration — one resolver, rebuild all 15 corpora, bump
`EXTRACTOR_VERSION` so every sidecar regenerates — not a fallback that mixes the
two.

---

## Quick reference

```bash
# Do I have budget?
python3 scripts/eval/build_corpus.py --check-budget

# Finish everything (skips completed topics automatically)
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0

# One topic
python3 scripts/eval/build_corpus.py --openreview rhgIgTSSxW --max-papers 0
```

| Env var | Effect |
|---------|--------|
| `OPENALEX_API_KEY` | Sent as `?api_key=`. Absent → unauthenticated, $0.10/day. |
| `OPENALEX_EMAIL` / `UNPAYWALL_EMAIL` | Polite-pool `mailto`. Not authentication. Default `contact@noesis.is`. |

Remaining topics: `H9DYMIpz9c`, `cXs5md5wAq`, `eR4W9tnJoZ`, `eUgS9Ig8JG`,
`gYcft1HIaU`, `jx6njBKH8E`, `kKRbAY4CXv`, `miGpIhquyB`, `qBL04XXex6`,
`rhgIgTSSxW`, `rp5vfyp5Np` — plus 19 `pending` references in `BQvbL2sFQx`.
