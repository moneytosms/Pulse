# Design Direction — Options

Typography and colour, researched and narrowed but **not chosen**. Choosing is the first task of the frontend slice, because screens are cheaper to judge than to describe.

Everything below was verified on 2026-08-22 — font coverage by inspecting the actual woff2 binaries, contrast ratios by computing them. Where something could not be verified, it says so. Claims about which fonts cover which scripts are the ones most worth trusting here, because several widely repeated ones turned out to be wrong.

The constraints that decide this: four locales (Latin, Devanagari, Tamil, Malayalam), a mobile-first patient portal on mid-range Android over patchy connectivity, data-dense desktop portals for clinicians, older users on cheap screens in bad light, and light **and** dark mode.

---

## Typography

### What the research eliminated

Half the obvious candidates cannot do the job at all:

| Font | Reality |
|---|---|
| **Inter**, **Nunito Sans** | Zero Indic coverage. Latin only. |
| **Poppins**, **IBM Plex Sans** | Devanagari only. No Tamil, no Malayalam. |
| **Mukta** family | Mukta Vaani is **Gujarati**, not Malayalam. The set does not complete. |
| **Hind** family | No Malayalam member exists. Hind Guntur is Telugu. |
| **Catamaran** | Tamil only — binary inspection found no Devanagari and no Malayalam glyphs, contradicting a widely repeated claim. |
| **Manjari**, **Gayathri**, **Chilanka** | Malayalam only. Useful as a Malayalam pairing, not as a system. |

Only **Noto** and **Anek** cover all three Indic scripts, plus **Baloo**, which is a display family and wrong for body text.

### Two facts that change the shape of the decision

**Indic subsetting does not work like Latin subsetting.** Every family ships its whole Devanagari (or Tamil, or Malayalam) block as one chunk. There is no "core" versus "extended" split, because the shaping engine needs the entire GSUB table to form conjuncts it cannot predict. Content-aware subsetting is possible but fragile here specifically — patient names and free-text clinical fields are unpredictable input, and a dropped conjunct silently mis-renders somebody's name.

**The Indic files contain no ASCII digits.** Western digits live in each family's Latin chunk. So any Hindi, Tamil or Malayalam page showing a date, a lab value or a phone number fetches the Latin chunk too. Budget Indic chunk **plus** Latin chunk per non-English locale, always.

And a third, smaller: **none of the Devanagari, Tamil or Malayalam files carry `tnum`** (tabular figures) — confirmed by GSUB inspection across every candidate. Table numerals come from the Latin font, so the Latin font must have `tnum`. Inter and plain Noto Sans do. IBM Plex Sans does not. Poppins' Latin chunk has *no* GSUB features at all.

Indian lakh/crore grouping has no font implication — `Intl.NumberFormat('en-IN')` just moves separators.

### The three options

**Option A — Noto Sans across all four scripts.** *(the low-risk pick)*

Noto Sans Devanagari + Noto Sans Tamil + Noto Sans Malayalam + plain Noto Sans for Latin and numerals. All variable, all OFL, and plain Noto Sans has real `tnum`, so lab tables need no second font. It is the most widely deployed and tested implementation of these three scripts anywhere.

Against: Noto's per-script faces were developed by different teams over years, so x-height and stroke weight may visibly mismatch when two scripts sit side by side — which happens constantly in an EHR (an English drug name inside a Hindi sentence). Nobody has looked at that yet.

Payload, single weight: Devanagari 50 KB · Tamil 15 KB · Malayalam 24 KB · Latin 11 KB.

**Option B — Anek.** *(the designed-for-this-problem pick)*

Ek Type's Anek is one coordinated multiscript system with matched axes across Devanagari, Tamil and Malayalam — built by one team to solve exactly the mixing problem Option A risks.

Against: no `tnum` in its Indic files, and whether Anek's own Latin has it was **not confirmed** — so a numeral font may still need sourcing. And its full variable range is the heaviest asset in the whole comparison: Anek Devanagari at `wght 100–800` is **258 KB**, versus 94 KB for a single pinned weight. On a mobile-first portal that is a code-review rule, not a footnote — pin the two or three weights actually used.

**Option C — Inter for Latin, Noto per Indic locale.** *(the payload-optimal pick)*

English-locale desktop sessions download zero Indic bytes. Inter is excellent at dense tables and has `tnum`.

Against: real engineering cost in locale-scoped font loading, and the honest visual risk — an Inter English label beside a Noto Devanagari Hindi label on the same screen may read as two products stitched together. This is the option most in need of a side-by-side look before committing.

### Recommendation to start from

**Option A.** It is the only one that covers all three scripts with confirmed glyphs, is variable, is unambiguously OFL, and solves tabular numerals without a second font — and it carries the least typographic risk for a team with no in-house native-script type reviewer.

**Switch to Option B if** a side-by-side rendering shows Noto's three faces visibly mismatched when mixed. That is the specific condition; check it before deciding rather than after.

Whichever wins: **pin specific weights**. Requesting a full variable range instead of two or three weights is the difference between 94 KB and 258 KB on the exact page a patient loads over a bad connection.

---

## Colour

### Token source

**Radix Colors**, not a hand-rolled Tailwind palette. Radix UI is already the component stack, the 12-step scales ship tuned light *and* dark variants, and Tailwind v4's CSS-first `@theme` maps them cleanly.

One caveat, verified rather than assumed: Radix's documented "steps 11 and 12 pass 4.5:1" guarantee **does not hold for Amber, Orange and Yellow**. Treat step numbers as strong defaults, never as an accessibility guarantee.

### Three directions

| | (a) Blue | (b) Jade | (c) Sand + Iris |
|---|---|---|---|
| Accent | Blue | Jade | Iris (indigo-violet) |
| Neutral | Slate | Sage | Sand (warm, paper-toned) |
| Step-9 solid + white text | 3.26:1 — **fails AA** | 3.15:1 — **fails AA** | **5.37:1 — passes** |
| Signals | Trust, institutional, every hospital portal ever built | Calm, wellness-adjacent, still generically "digital health" | Considered, academic — a research institution's system rather than a consumer app |

Of every accent tested, only **Iris** (5.37:1) and Plum (4.75:1) let white text sit on the step-9 solid and pass AA. A Blue or Jade primary button as Radix ships it needs a darker step or dark text — real engineering hours, not an aesthetic argument.

Direction (c) is the technical recommendation; (a) is the safe fallback if someone vetoes a non-blue clinical product. If Jade is wanted, note it beat Teal only because Teal 11 lands at 4.47:1 — a fail by a hair, but a fail.

### Semantic colours

These carry meaning, so they need a redundant non-colour cue — colour alone is a WCAG 1.4.1 failure, and this is read by clinicians under time pressure on cheap screens.

| Meaning | Colour | Redundant cue | Light contrast |
|---|---|---|---|
| Critical / abnormal lab | Red 11 | Triangle-exclamation icon, 4px left border, "CRITICAL" / "OUT OF RANGE" | 5.08:1 ✅ |
| Consent active | Green **12** on cards | Filled check-circle, solid border, "Active" | Green 11 fails on cards (4.48:1) |
| Consent revoked | Red 11 | Circle-slash icon, strikethrough, "Revoked" | 5.08:1 ✅ |
| Consent expired | Amber **12** | Hourglass icon, dashed border, "Expired" | Amber 11 fails (4.49:1) |
| Audit normal | Gray 11 | Dot, thin border, "Info" | 5.79:1 ✅ |
| Audit denied | Orange **12** | Shield-slash, thick border, "Access Denied" | Orange 11 fails (4.40:1) |
| Break-glass | Crimson 11 | Filled shield-alert, 4px border, uppercase "BREAK-GLASS", stripe badge | 5.25:1 ✅ |
| Superseded | Gray **11** | Strikethrough or reduced opacity, "Superseded — see corrected entry" | Gray 9 fails even 3:1 |

Three fixes that only appeared by computing: **Green, Amber and Orange step 11 fail AA on card surfaces** — use step 12 there. **Step-9 solids are not safe with white text** for any of these hues — pair with black, or use step 9 only for icons and borders. **Superseded must be step 11, not 9.**

Break-glass is deliberately Crimson rather than Red, so the two "critical" meanings never collide in a mixed audit view.

### High versus low lab values must not be red versus green

Roughly 1 in 12 men have red-green colour deficiency, and red and green collapse into similar brownish tones for the commonest form. So:

- One alert hue (Red) for "outside reference range".
- Direction encoded elsewhere: ▲ + "H" + the word "High", ▼ + "L" + the word "Low". Never glyph-only — a lone triangle at small size on a cheap screen is its own legibility problem.
- If a second hue is genuinely wanted for scanning speed in dense tables, use red versus **blue/indigo**, which survives both protanopia and deuteranopia. That also happens to be free if Direction (c) wins.
- Never encode severity as light-red versus dark-red without also saying it in words. Subtle lightness is the first thing a sun-glared Android screen destroys.

### Dark mode is a real requirement

Clinicians document on night shifts in dim rooms; patients check results at night on phones that are disproportionately OLED at the mid-range price point. Both modes get built to the same bar.

**Never use `#000000` as a surface.** White text on pure black computes to 21:1 and passes everything — and still produces halation, a glow around text edges on OLED, which is worse for readers with astigmatism, a meaningful share of the older users this portal targets. This is the clearest case in the whole research of a problem a contrast calculator cannot see.

Use the Radix dark ramp as intended: step 1 as the page, step 2 for cards, steps 3–4 for popovers, and step 12 (`#edeef0`) for body text rather than pure white.

### How the tokens ship

Two layers in one `tokens.css`: primitives (the raw Radix scales, referenced by nobody directly) and semantic aliases (`--color-critical`, `--color-consent-active`, `--color-superseded`) mapped into Tailwind's namespace via `@theme`. Components write `text-critical`, never a hex and never `red-500`.

Add a lint rule banning hex literals in component directories, and a tokens-reference page rendering every semantic token with its live contrast ratio — so a future change that reintroduces one of the AA failures above is caught in review rather than in the demo.

---

## What still needs a human eye

Nothing above settles these, and none of them can be settled by more research:

- **Malayalam orthography — traditional versus reformed.** This is a real fork; Noto and Manjari target the reformed script. The highest-stakes open question here, and it needs a Malayalam-literate reviewer testing against words the actual audience uses.
- **Cross-script metric matching.** Render real Pulse strings — a nav label, a lab-table header, a patient name — in Noto's three faces side by side, then Anek's. Look for x-height and weight mismatch. This is the decision between Options A and B.
- **Chillu rendering from legacy ZWJ input sequences**, not just the atomic codepoints that were confirmed present.
- **Devanagari matra placement** in conjunct clusters from real Hindi medical vocabulary. Feature tags being present is not proof of correct visual reordering.
- **Whether the product wants native Indic digits anywhere.** Western digits everywhere was assumed throughout. That is a content decision.
- **Halation, on a real mid-range OLED Android at night**, on a long clinical note.
- **A colour-blindness simulator pass** over the finished high/low lab flags, on the rendered component rather than the palette.
- **Glare legibility** of the light palette on a cheap, low-brightness panel outdoors.
- **Whether anyone has a hard veto on "not blue"** for a healthcare product. That single answer decides between directions (a) and (c).
