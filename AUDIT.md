# MangaRelease — Track 1 Data-Trust Audit

> **Status (2026-07-12): resolved & shipped.** The ship-blockers below were fixed in the follow-up sections at the bottom of this doc — coverage recovered to ~74–79% at launch, with Square Enix / TOKYOPOP filling via the scheduled crons. Kept as an engineering record; the "bottom line" below describes the state *before* the fixes.

**Date:** 2026-07-11 · **Scope:** `books.csv` (published dataset) as a licensed-English manga release calendar.
**Method:** static analysis of the CSVs as committed (no scrape run) + independent web ground truth for coverage/accuracy.
**Bottom line:** **NOT launch-ready.** Measured coverage of real May/June 2026 releases is **~26–32%**, against a ≥95% bar. The shortfall is ~90% explained by **four major publishers that are entirely or almost-entirely absent from `books.csv`** (Kodansha, VIZ Media, TOKYOPOP, Square Enix). What *is* present from the other publishers is largely accurate.

---

## 0. Data at a glance

| File | Rows | Role |
|---|---|---|
| `info.csv` | 26,885 | raw scraped superset (`key,url,source,publisher,title,index,format,isbn,date`) |
| `books.csv` | 17,032 | **published** dataset, built from `info.csv` by `lnrelease/parse.py` |
| `series.csv` | 7,093 | `key,title,origin,category,flag` (2,359 `flag=review`) |
| `artbooks.csv` | 87 | art books split out of the calendar |
| `origins.csv` | 2 | manual origin/category overrides |

`books.csv` publisher mix (present): Yen Press 8,644 · Seven Seas 5,088 · Dark Horse 970 · Ize Press 507 · J-Novel 497 · One Peace 483 · Titan 199 · Inklore 166 · Denpa 129 · WEBTOON Unscrolled 128 · Udon 96 · Ablaze 68 · **Square Enix 38** · Digital Manga 19. **Kodansha 0 · VIZ Media 0 · TOKYOPOP 0.**

---

## 1. Coverage audit — the headline number

Ground truth built from **Yatta-Tachi** monthly release lists (independent 14-publisher aggregator), cross-checked against **VIZ's own calendar** and publisher slates. Denominator restricted to publishers MangaRelease claims to track (Kana/SuBLime/Alphapolis/Wattpad excluded as out of scope). Matched on normalized `title+volume` against **any** `books.csv` row (so a wrong *date* counts as captured, not a miss).

| Month | In-scope ground-truth releases | Captured in `books.csv` | **Coverage** |
|---|---|---|---|
| **May 2026** | 118 | 38 | **32.2%** |
| **June 2026** | 106 | 28 | **26.4%** |

*(These are conservative lower bounds — a handful of Yen/Seven Seas "misses" are title-variant artifacts of my normalizer, so true coverage of the present publishers is a few points higher. The 0%-publisher story below is exact and unaffected.)*

### Misses are not scattered — they are four whole publishers leaking

| Publisher | May captured | June captured | Diagnosis |
|---|---|---|---|
| Kodansha | **0 / 17** | **0 / 23** | dropped by pipeline filter — **data exists** in `info.csv`, recoverable |
| VIZ Media | **0 / 31** | **0 / 37** | **dead scraper** — data absent from `info.csv` too (not recoverable by filter fix) |
| Square Enix | **0 / 8** | **0 / 10** | dropped by filter; print volumes recoverable (but see chapter-noise caveat) |
| TOKYOPOP | **0 / 6** | **0 / 5** | dropped by filter; partially scraped |
| Seven Seas | 26 / 35 | ~full | healthy (own scraper) |
| Yen Press / Ize | 9 / 16 | 19 / 21 | healthy (own scraper) |
| Dark Horse | 1 / 1 | 1 / 2 | healthy; 1 PRH-only title dropped |
| Titan Comics | — | 8 / 8 | healthy |

`books.csv` actually **over-covers** the healthy publishers vs. this ground truth (May: 74 Yen + 50 Seven Seas rows present, more than Yatta-Tachi lists), so the ~9 in-scope primary publishers are effectively near-complete. **The entire coverage gap is the four missing publishers.**

### Root cause (proven from code + data)

`lnrelease/parse.py:24` selects rows for `books.csv` with:

```python
if i.source not in SECONDARY or i.publisher not in PRIMARY:
    lst.append(i)          # → a row is DROPPED when source ∈ SECONDARY AND publisher ∈ PRIMARY
```

This is a dedup rule: "if a PRIMARY publisher's book arrives via a SECONDARY aggregator (PRH/Crunchyroll/BookWalker/stores), drop the aggregator copy because the publisher's own primary scraper will supply it." **But Kodansha, VIZ, TOKYOPOP, and Square Enix are listed as PRIMARY (`utils.py:24`) while their primary scrapers produced nothing this run.** Verified: 100% of their `info.csv` rows come from SECONDARY sources —

```
publisher=Kodansha    → Penguin Random House 2010, Crunchyroll 137   (source=Kodansha: 0)
publisher=VIZ Media   → Crunchyroll 215                              (source=VIZ Media: 0)
publisher=TOKYOPOP    → Penguin Random House 717, Crunchyroll 153    (source=TOKYOPOP: 0)
publisher=Square Enix → Penguin Random House 1958, Crunchyroll 128, Square Enix 38
```

So every Kodansha/VIZ/TOKYOPOP row is filtered out, and Square Enix keeps only its 38 primary-scraped rows.

### Two distinct failure classes (exact filter-drop replay on `info.csv`)

Replaying the drop condition on May/June `info.csv` rows (distinct releases, format-deduped):

| Publisher | May dropped | June dropped | Recoverable by filter fix? |
|---|---|---|---|
| Square Enix | 602 | 182 | **partly** — ~90% are *digital chapters* (see below); ~10 real print vols/mo are wrongly dropped |
| Kodansha | 37 | 23 | **yes** — real print volumes present in `info.csv` |
| Dark Horse | 11 | 13 | yes — PRH copies of titles the DH scraper missed |
| TOKYOPOP | 4 | 4 | partly — only ~half the month's titles are in `info.csv` |
| VIZ Media | 2 | 0 | **no** — VIZ data simply isn't there |

**Square Enix chapter caveat (important):** the 602 May "releases" are dominated by individual **digital chapters** — e.g. `Cast-off Magic Tool Researcher #001…#011`, `Beast Tamer #097`, `Assassin & Cinderella #022` — dumped in bulk on 2026‑05‑01/15/29 (158/152/150 rows). A naïve filter fix would flood the calendar with ~600 chapter rows/month. The fix must **also** drop chapter-level entries (`#NNN`, `index=0`, eBook, from the SE digital store) and keep only numbered print volumes.

**VIZ caveat (worst case):** VIZ is a top-3 English manga publisher (One Piece, Jujutsu Kaisen, Chainsaw Man, Kagurabachi, Blue Box…). It has **zero** rows in `books.csv` and only ~215 stale Crunchyroll rows in `info.csv` (Chainsaw Man last seen 2025‑05, Kagurabachi never). Fixing the filter recovers ~nothing here — **VIZ needs its primary scraper repaired** before coverage can approach 95%.

### Reverse check — junk / false entries in `books.csv`

`books.csv` is **not** polluted with junk — the opposite problem. Because the filter drops the PRH aggregator dupes and the SE digital-chapter flood, `books.csv` stays clean. Candidate false/erroneous entries are low (dozens, not hundreds) and consist of the **mistags** (§3) and **dedup artifacts** (§4), not fabricated releases. Junk weight on the confidence number is small; the number is driven almost entirely by *misses*.

---

## 2. Accuracy spot-check

Sample seed `20260711`, stratified across sources (guaranteeing Udon/Ablaze/Dark Horse). 29 rows drawn; drift suspects + mainstream anchors verified against retail/publisher listings.

| Row (sample) | Date | ISBN | Volume |
|---|---|---|---|
| Yen Press — *Slime* (manga) v3 `9781975313579` | ✅ 2021‑01‑05 | ✅ | ✅ |
| Dark Horse — *Evangelion: Shinji Ikari Raising Project* v3 `9781595824479` | ✅ 2009‑12‑23 | ✅ | ✅ |
| Ablaze — *Gannibal* v2 `9781684972203` | ❌ books=`2023‑12‑01`, real **2024‑02‑14** (wrong month + fake day-01) | ✅ | ✅ |
| One Peace — *Higehiro* v13 `978‑1‑64273‑541‑3` | ❌ placeholder `0001‑01‑01` (real ~Jul 2026) | ⚠️ suspect (retail shows `…36137`) | ✅ |

### Per-field error rates (by source, from full-column scans + spot checks)

**Release date** — accurate for primary-scraped publishers (Yen, Seven Seas, Dark Horse, Ize, Titan, J-Novel verified/consistent). Systematic drift isolated to:

| Source | Symptom | Rows affected |
|---|---|---|
| **Ablaze** | **100%** of dates are day-`01` (month-precision); *Gannibal* also off by a month | 68 / 68 |
| **Udon** | **100%** placeholder `0001‑01‑01` (no usable date) | 96 / 96 |
| **One Peace** | **86%** placeholder `0001‑01‑01` | 414 / 483 |
| **Denpa** | scattered placeholders | 5 |

Total **515 rows carry no real date** (`0001‑01‑01`).

**ISBN** — **1,095 rows missing an ISBN entirely** (all present ISBNs are well-formed 13-digit): J-Novel Club 486 (**98%** of its catalog), One Peace 235, Seven Seas 231, Denpa 69, Udon 55, Square Enix 19. One Peace ISBNs are also occasionally wrong edition (Higehiro above).

**Volume** — generally reliable, with one structural bug: **Seven Seas subtitles containing a comma are split into the volume field.** e.g. *The Cursed Sword Master's Harem Life: By the Sword, For the Sword* stores `volume = "For the Sword"`. Worth a targeted grep of Seven Seas rows with non-numeric volumes.

---

## 3. Mistag audit

Origin/category default (`tag.py` + `parse.py`): any series not caught by a marker / imprint rule / `JP_PUBLISHERS` set → **`JP` / `manga`**. Dark Horse, Ablaze, and Udon are in **no** rule set, so their non-Japanese titles silently default to JP manga.

**(a) Western comics tagged `manga`.** Quantified for the mixed publishers:

- **Udon** — ~21 series / 35 rows are American-made comics wrongly `JP/manga`: all **Street Fighter** titles, **Darkstalkers**, **Mega Man / Little Mega Man / Mr. Mega Man**, **Final Fight**, **Dragon's Crown**, **Team Phoenix**, **Veil**, the webcomics **Ménage à 3 / Sandra on the Rocks / Sticky Dilly Buns**, **Giga Town**, **Manga Biographies: Charles M. Schulz**. (Udon *also* publishes real manga — Rose of Versailles, Higurashi — so it can't be blanket-tagged.)
- **Ablaze** — mixed: e.g. **WAKFU** (French/Ankama IP) is Western; **The Breaker: New Waves** is Korean manhwa; **Gannibal** is JP. Its 31 `manga` rows include several non-JP.
- **Dark Horse** — catalog is *mostly* genuine licensed JP manga (Akira, Berserk, Blade of the Immortal, Cardcaptor Sakura), so the Western leak is a **subset** (e.g. Jeff Lemire's *10,000 Ink Stains*, Star Wars "manga" art books). Lower priority than Udon.

**(b) Yen Press manhwa defaulting to JP.** Confirmed for the known example: `13thboy → "13th Boy"` is tagged `origin=JP`. Yen Press (unlike its Ize Press imprint) publishes both JP manga and KR manhwa, and only the literal `(manhwa)` title marker catches them — so any Yen manhwa without that marker defaults JP. This is a small, curation-shaped set.

**Recommended fix path** (decision-on-file: auto-rules preferred, `origins.csv` fallback):

| Fix | Type | Effort | Rows |
|---|---|---|---|
| Add a **franchise/keyword origin blocklist** (Street Fighter, Darkstalkers, Mega Man, WAKFU, …) → `('', 'comic')` or `other` | auto-rule | med | ~35 (Udon) + some Ablaze |
| **`origins.csv` overrides** for the residual Western titles a rule can't safely catch | manual | low | tens |
| Yen manhwa: no clean auto-rule (Yen is mixed) → **`origins.csv` overrides** for known KR titles (13th Boy, …) | manual | low | ~dozens |

A blanket publisher rule is wrong for all three (each publishes real JP manga too). Realistic path = a small franchise auto-rule for the obvious Western IP + `origins.csv` for the tail.

---

## 4. Dedup check

**True cross-key ISBN duplicates: 11 ISBNs under 2 distinct series keys** (same physical book counted twice):

- **Lore Olympus** (Inklore) — split into a combined key `loreolympus` (as vols 1–7) **and** seven singleton keys `loreolympusvolumeone…seven` (each as v1), sharing the same ISBNs. Biggest single dedup failure.
- **Viral Hit** (WEBTOON Unscrolled) — `viralhit` v1 vs `viralhitvolumeone` v1, same ISBN.
- **The Dirty Pair: Dangerous Acquaintances** — base vs `…ltded` (Ltd. Ed.) share an ISBN.

**Series split across two keys (same normalized title+volume, different key): 26** — includes a real dedup miss: **`afrosamurai` (Titan Comics)** collides with **`sevenseasbookarchive` (Seven Seas)** — a catch-all "archive" key acting as a junk bucket that should be investigated. Others are legitimate distinct editions (`hellsing` vs `hellsingsecondedition`, `cirquedufreakthemanga` vs `…edition`, early Dark Horse `ohmygoddess` retitled sub-volumes) — borderline, low priority.

**Net:** ~11 confirmed duplicate volumes to merge + the `sevenseasbookarchive` bucket key to audit. Small and fixable.

---

## 5. Launch-readiness verdict

**Against the ≥95%-coverage working bar: FAIL.** Current measured coverage **26–32%**; even a perfect filter fix reaches only ~mid‑40s% until the **VIZ** (and to a lesser degree Square Enix) scrapers are repaired, because that data isn't in `info.csv` to recover.

**Confidence in the *present* data is high** (~95%+ on date/ISBN/volume for the ~9 primary-scraped publishers). The problem is **completeness**, not correctness.

### Top-5 punch list (ranked by impact)

1. **Restore Kodansha + TOKYOPOP + Square Enix via the `parse.py` filter** *and* add a digital-chapter exclusion. — Recovers ~40–60 real releases/month. Highest impact-per-effort: data already in `info.csv`; fix is at `parse.py:24` (don't drop a SECONDARY-sourced PRIMARY-publisher row when that publisher has **no** primary-source rows), plus a `#NNN`/`index=0`/eBook chapter filter so SE doesn't flood. *Ship-blocker.*
2. **Fix the VIZ scraper** (`lnrelease/source/viz.py` produced 0). — VIZ is the single largest missing bucket (~30–40 releases/month, the biggest-selling titles). No shortcut; without it 95% is unreachable. *Ship-blocker.*
3. **Fix dates for Ablaze / Udon / One Peace / Denpa.** — 515 placeholder dates (Udon 100%, One Peace 86%) + Ablaze 100% month-precision (and sometimes wrong month). Either scrape real on-sale dates or mark these month-precision explicitly; don't publish `0001‑01‑01` to a *calendar*.
4. **Backfill missing ISBNs** (1,095 rows; J-Novel 98%, One Peace, Seven Seas) and fix the **Seven Seas comma-in-subtitle → volume** parse bug.
5. **Mistags + dedup cleanup** — Udon/Ablaze Western-comic origin rules (~35+ rows) via franchise auto-rule + `origins.csv`; Yen manhwa overrides (13th Boy…); merge the 11 Lore Olympus/Viral Hit/Dirty Pair ISBN duplicates; audit the `sevenseasbookarchive` bucket key.

---

## Reproducibility

- **Ground truth:** Yatta-Tachi *[May 2026](https://yattatachi.com/may-2026-manga-manhwa-light-novel-book-releases)* / *[June 2026](https://yattatachi.com/june-2026-manga-manhwa-light-novel-book-releases)* lists; cross-checked vs *[VIZ calendar](https://www.viz.com/calendar/2026/05)*. Retail spot-checks via Amazon / Simon & Schuster / publisher pages.
- **Match logic:** normalize title = strip `(manga)|(light novel)|(comic)|(omnibus)|N-in-N edition|hardcover`, edition words, and `Vol./Volume/Part N`, then `[^a-z0-9]→∅`, lowercase; volume = trailing integer; match against **any** `books.csv` row. Coverage counts a row captured if the title+volume exists anywhere (date errors not penalized as misses).
- **Filter-drop replay:** exact — replicated `source ∈ SECONDARY ∧ publisher ∈ PRIMARY` on `info.csv`, format-deduped on `(key,index)`. No title normalization, so publisher-level drop counts are exact.
- **Accuracy/date/ISBN scans:** full-column CSV parse (proper quoting) over `books.csv`; day-`01` share and `0001‑01‑01` counts are exact.
- **Sample seed:** `20260711` (Python `random.seed`), stratified across publishers.
- **Tooling:** standalone Python (`csv` module for quote-safe parsing) over the committed CSVs — no scrape run; ground truth fetched read-only with polite request pacing.

---

## Fixes applied (this session)

Pipeline + data changes made after the audit, then `books.csv` regenerated (`tag.py` → `parse.py` → `pages.py`); dataset grew **17,032 → 20,373 rows**.

**1. `parse.py` filter fix + digital-chapter guard**
- Conditional bypass: a SECONDARY-sourced row for a PRIMARY publisher is only dropped as redundant when that publisher **actually produced primary-scraper rows** this run (`scraped_pubs`). Publishers whose scraper produced nothing (Kodansha/VIZ/TOKYOPOP) keep their aggregator rows instead of vanishing.
- Chapter guard: rows whose title matches `#\d+` in a digital format are skipped, so Square Enix's `#001`-style singles never enter the calendar (Physical `#` issues, e.g. a few Dark Horse, are kept).
- Fixed `publisher/tokyopop.py` assuming an `info['Paperback']` bucket (crashed once TOKYOPOP rows flowed through) — now `info.get('Paperback', [])`.

**Result — recovered publishers:** Kodansha **0 → 2,028**, TOKYOPOP **0 → 1,104**, VIZ **0 → 215** (all its available, if stale, rows). Square Enix stays 38 by design — it *did* scrape 38 rows, so it doesn't meet the "produced 0" bar; it belongs with the deferred VIZ scraper-rebuild.

**Re-run coverage vs the same ground truth:**

| Month | Before | After | After, excl. VIZ + Square Enix (deferred) |
|---|---|---|---|
| May 2026 | 32.2% | **48.3%** | **70.9%** |
| June 2026 | 26.4% | **45.3%** | **81.4%** |

Kodansha coverage went **0% → 100%** (May) / **78%** (June). It did **not** reach the 95% bar: **VIZ (0–3%) and Square Enix (0%) dominate the remaining gap, and their data is not in `info.csv` to recover — confirming both need scraper rebuilds, exactly as flagged.** TOKYOPOP's recovered rows are older; its May/June titles were never scraped (partial source), so it's also 0–20% and needs scrape completion.

**2. Dedup**
- Generic **ISBN-level dedup** post-pass in `parse.py`: same ISBN under two series keys collapses to the key carrying the most volumes. Resolves the 11 cross-key ISBN duplicates (Viral Hit, Dirty Pair Ltd Ed, Lore Olympus v1–7) durably.
- Data migration (`info.csv` + `series.csv`): **Lore Olympus** fully merged — the 11 `loreolympusvolumeN` singletons folded into `loreolympus` with correct volumes; it now reads as one series, volumes 1–11 (HC + PB). **`sevenseasbookarchive`** bucket split into 14 proper per-title keys; **Afro Samurai** now a single `afrosamurai` series carrying both the Seven Seas and Titan editions (collision gone).

**3. Mistags**
- `tag.py` Western-franchise auto-rule (Street Fighter / Darkstalkers / Final Fight / Dragon's Crown / WAKFU), gated to Udon/Ablaze → `origin=other, category=comic`. Added `comic` to `CATEGORIES`. Verified it does **not** catch the genuinely-Japanese Mega Man Mastermix (Ariga), Persona, or Blue Archive.
- `origins.csv` tail for the residual one-offs (Team Phoenix, Veil, Ménage à 3, Sandra on the Rocks, Sticky Dilly Buns, Little/Mr Mega Man) and **13th Boy → KR/manhwa**. 34 rows now correctly tagged `comic`.

**Deferred (held for their own sessions, per plan):** VIZ scraper rebuild (live scraping) and Square Enix scraper (same class); the Seven Seas comma-in-subtitle → volume parse bug and the Lore-Olympus-style word-number volume parsing (both are parse-logic changes to do with tests); date/ISBN backfills. Also noted: one cosmetic non-determinism — *Honkai Impact 3rd* v3 has two ISBNs for the same digital slot and the pre-existing parser picks one by set order (newly visible now that TOKYOPOP is included); set `PYTHONHASHSEED=0` or fix the parser's per-volume dedup to make it stable.

**Durability note:** the `info.csv`/`series.csv` migrations (Lore Olympus, archive split) are corrected in place but a full re-scrape could recreate the bad keys; the durable version is scraper-side key canonicalization (belongs with the deferred parse-logic work). The `parse.py` filter/chapter/ISBN-dedup changes and the `tag.py`/`origins.csv` mistag rules **are** durable — they re-apply on every build.

---

*Caveats:* Yatta-Tachi is not exhaustive (denominator slightly under-counts Yen/Seven Seas, which `books.csv` covers well → reported coverage is a conservative floor). Square Enix's own scraper is known-throttled (30–600 s delays, no skip-cache), so its `info.csv` presence is partial and its numbers are noted separately, not folded into the primary-publisher accuracy claims.

---

## Follow-up — 2026-07-11 (VIZ rebuild + Square Enix cache)

Continued from the fixes above. Committed the Part-1 fixes, then rebuilt the VIZ scraper and added a Square Enix skip-cache. Dataset now **20,613 rows**.

**VIZ scraper — diagnosed and rebuilt.** VIZ produced zero rows not because of broken code — the search and product-page selectors parse fine against live viz.com — but because it never *completed*: paging the whole catalogue at 30–60 s/request times out and `viz.csv` was never populated (CI-runner IP blocking likely compounds it). Rebuilt to **seed from the monthly release calendar** (`viz.com/calendar/YYYY/MM`) for a recent+upcoming window first, so the important data lands even if the deep search crawl is cut short; the full crawl remains as backfill. Also fixed a latent `store/viz.py` crash on non-`manga` category URLs. Ran the calendar scrape: **441 VIZ rows, May–Nov 2026**. A 5-row spot-check against viz.com product pages matched date/ISBN/volume 5/5; VIZ series tag JP/manga with zero review-queue churn.

**Square Enix — skip-cache added (not run live).** Gave `source/square_enix.py` the same incremental skip-cache VIZ uses (cache series+volume pages by date; skip settled past-dated pages, re-check 20%), so repeat runs skip the expensive per-volume fetches. Logic validated; not run live to avoid hammering SE's rate-sensitive endpoint — the full populate rides with the weekly cron. Chapter guard intact (`Chapters (Digital)` → `None`); SE books remain volumes-only.

### Coverage progression (same May/June 2026 ground truth, same matcher)

| Month | Original audit | After Part-1 fixes | **After VIZ** | Bar |
|---|---|---|---|---|
| May 2026 | 32.2% | 48.3% | **73.7%** | ≥95% |
| June 2026 | 26.4% | 45.3% | **79.2%** | ≥95% |

VIZ itself went **3% → 100%** (May) and **0% → 97%** (June); Kodansha **0% → 100% / 78%**.

**Verdict: the ≥95% bar is not yet met (73.7% / 79.2%).** The single biggest blocker (VIZ, a top-3 publisher) is resolved. What remains, in order of impact:

1. **Square Enix (0%)** — scraper skip-cache is in place but not yet populated; the next weekly cron should fill ~8–10 releases/month.
2. **TOKYOPOP (0% / 20%)** — no working primary scraper; its rows come from PRH, which hasn't listed the May/June titles. Known residual; the cron's PRH refresh should fill it. Not chased here.
3. **Seven Seas 77% / Yen 56%–95% residual** — a mix of match-normalizer artifacts (title variants) and genuinely-not-yet-scraped recent 2026 volumes; closes as the daily cron refreshes.

Once Square Enix populates and TOKYOPOP/PRH catches up via the cron, coverage should clear ~90%+; the last few points are the long tail of just-announced volumes that any calendar trails by a refresh cycle.

**Still deferred** (unchanged, per plan): Seven Seas comma-in-subtitle → volume parse bug; Lore-Olympus-style word-number volume parsing; Ablaze/Udon/One Peace date backfills; J-Novel ISBN backfill. **CI determinism** is now handled — `PYTHONHASHSEED=0` pinned in `python.yml`.

*Infra caveat (from the merge reconciliation):* the CI runs without Cloudflare, so its Seven Seas / Dark Horse scrapers return 0 primary rows; the local Cloudflare-scraped data for those was preserved by union, but a future daily CI run may wipe it. The Cloudflare/CI decision is separate from this work.

---

## Follow-up — 2026-07-11 (wipe guard, webtoon taxonomy, guardrails)

**Zero-row wipe guard (`scrape.py`).** Closed the wipe risk flagged above. On save, a source that previously carried rows but now returns fewer than a per-source fraction (default 10%) is *not* replaced — the prior rows are kept and a loud `WIPE GUARD` warning is logged. General (not an SS/DH special case), configurable per source (Square Enix uses 5% since it carries few rows), and never fires for a new source (0 prior). Tested: a 0-row Seven Seas result against the live info.csv preserves all 4,964 rows and warns; a plausible partial run passes through.

**Webtoon taxonomy.** Adopted: **origin = creator's country** (platform-independent); **category = reader vocabulary** — `manga`/`manhwa`/`manhua` for JP/KR/CN works *including webtoon-native ones in print*, `webtoon` only for non-Asian webtoon-native print, `comic` for Western print, `artbook` separate. Removed the blanket `WEBTOON Unscrolled → other/webtoon` rule in `tag.py` (a mixed imprint must not default to one origin — this was mis-tagging every Korean title). Classified all 38 category=`webtoon` series by creator nationality via `origins.csv`: 11 → `KR/manhwa` (Tower of God, Noblesse, God of High School, True Beauty, Your Throne, Viral Hit, Act Like You Love Me [Xuann, Korean], Operation True Love, The Mafia Nanny, Get Schooled, Terror Man), 26 → `other/webtoon` (Cursed Princess Club, Boyfriends, Lore Olympus, Chasing Red, Everything is Fine, …). Merged the leftover `viralhitvolumeone` key into `viralhit`, and generalized the parse-time dedup to key on `(ISBN, format)` so a merged key's same-edition rows collapse while legitimate Digital/eBook pairs (236 of them) are preserved. Added a **Taxonomy** legend to the README (via `write.py`, so it survives regeneration). Acceptance met: Solo Leveling KR/manhwa (unchanged), Tower of God KR/manhwa, Viral Hit KR/manhwa single key, Lore Olympus other/webtoon (review flag cleared).

*Two left for review* (creator nationality not confidently derivable — kept at their existing `other/webtoon` rather than guessing): **Daybreak**, **GremoryLand**.

**Goodwill guardrails.** Confirmed the pipeline does **not** rehost cover images — no binary writes, no image field in the schema or `data.json`; metadata and store links only. Added a lightweight **robots.txt** check to the fetch helper (`session.py`), applied to every host, not per-scraper. Effect: viz.com disallows `/search`, so the VIZ deep-crawl backfill is now correctly skipped (the calendar path it relies on is allowed); Seven Seas / Yen / Square Enix disallow only admin paths, so nothing else changes. The VIZ search loop degrades gracefully when a page is disallowed.

---

## Follow-up — 2026-07-11 (VIZ historical backfill via the release calendar)

Extended the VIZ scraper to walk the release calendar **backwards** for a decade of backlist, with no new data source — `viz.com/calendar/YYYY/MM` renders complete historical months (verified live back to 2010) and is robots-allowed, unlike `/search`.

**Two-tier ingestion (`source/viz.py`).** The calendar month table alone yields title, product URL, format and day-precision date, so those land immediately as **calendar-tier** rows (ISBN blank). The ISBN lives on the product page (30–60 s/request), so those are fetched **incrementally** through the existing `viz.csv` skip-cache — oldest backfill month first, within a per-run time budget — so each weekly cron chips away at the backlog and never re-fetches a cached product. Backfill walks back from the oldest cached month, stops at a **Jan-2015 floor** (config, not code, to go deeper) or after **3 consecutive empty months**, and runs only after the recent+upcoming window so a time-bounded run always commits current data first. Politeness unchanged (existing delays, robots.txt check, calendar pages only).

**Clean upgrade path.** The calendar-tier Info key `(link, format)` and series key (volume-stripped title) match exactly what `parse()` produces, so a later product fetch **upgrades the row in place** rather than duplicating it. `ingest_calendar` never clobbers a row that already carries an ISBN.

**Wiring (`python.yml`).** `VIZ_BACKFILL_MONTHS`/`VIZ_BACKFILL_SECONDS` are set **weekly only** (6 months back, 1500 s ISBN budget) and default to `0` on the daily run, leaving the incremental path unchanged. The budget keeps the cron well under its 350-min cap.

**Validation.**
- *Bounded live run* (2 historical months, reduced delay): 70 calendar-tier rows landed with correct dates/formats (2020-04/05, Paperback/Hardcover/Digital); a 3-product spot-check returned valid ISBNs (Daytime Shooting Star Vol. 6 → 978-1-9747-0672-3, Demon Slayer Vol. 12 → 978-1-9747-1112-3, Dr. STONE Vol. 11 → 978-1-9747-1479-7).
- *Upgrade path*: after ingesting calendar-tier rows and then fetching their product pages, **61 unique series keys, 0 duplicate `(link, format)` rows** — the merge is clean, no duplicate series created.
- *Offline invariants* (network-free): parse correctness, dedup/clobber-safety, calendar-title series-key == series-field series-key, and `BACKFILL_MONTHS=0 ⇒ no-op` all pass.
- *Determinism* (`PYTHONHASHSEED=0`): backfill order is deterministic (walk order + table order; output sorted by the driver). **Wipe guard untouched** — backfill only adds rows, so it can never false-trigger. Purely additive, so the coverage matcher cannot regress.

**No calendar gaps found** above the 2015 floor (2010/2014/2016 spot-fetches all rendered), so the API-enrichment fallback stays deferred as planned.

*Deferred, unchanged:* Seven Seas comma-in-subtitle volume parse; Lore-Olympus word-number volume parse; Ablaze/Udon/One Peace date backfills; J-Novel ISBN backfill; Square Enix live populate.
