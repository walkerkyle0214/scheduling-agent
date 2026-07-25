# Evaluation — How the Eval Harness Works & How to Reason About It

A reference for `tests/evals.py` (the scored suite) and `tests/stress_booking.py`
(the info-capture suite): what they measure, what they can't, and how to read the
results without fooling yourself. A bad eval is worse than no eval — it gives false
confidence — so this doc is as much about *interpreting* results as running them.

---

## 1. The core problem: testing a probabilistic system

Normal unit tests assume determinism: same input → same output → assert exact
equality. An LLM agent breaks that — the **same input yields different outputs run
to run** (we've watched a scenario flip PASS↔FAIL between two runs at the same
temperature). So an eval can't ask "is the output exactly X?" It must ask:

> **How often does the agent produce a *correct outcome*, across variation?**

That reframing — from exact assertion to **measured rates and behaviors** — is the
whole game. Everything below follows from it.

---

## 2. How a scenario runs (the loop)

Each scenario is a scripted multi-turn call. `run_one()` does:

1. **Reset** the backend (`POST /admin/reset`) → clean DB, so assertions are
   unambiguous.
2. **Feed the scripted caller turns** through Vapi's `/chat` API, threading
   `previousChatId` so it's one coherent conversation — the **same** assistant,
   prompt, tools, and webhook as a real phone call.
3. **Collect two artifacts:**
   - the **transcript** (everything the agent said), and
   - the **backend state** (bookings, priority queue — the *side effects* of the
     agent's tool calls).
4. **Run `check(state, transcript)`** → pass / fail.
5. **Compute diagnostics:** apology count, question count.

The single most important design choice is step 4 — *what* you check.

---

## 3. Two kinds of check — and why one is far better

| | Checks… | Reliability | Example |
|---|---|---|---|
| **State-based** | What the agent **DID** (DB side effects) | **Exact** — the DB is deterministic ground truth | booking exists with name=Reyes, addr="12 Birch" |
| **Transcript-based** | What the agent **SAID** (keyword match) | **Brittle** — a proxy for behavior | reply contains "$89" |

**Principle: assert on outcomes, not words.** A state check fails *only* when the
agent genuinely did the wrong thing. A transcript keyword check can fail on a
perfectly good answer that happened to use different words (false negative), or
pass on a bad answer that happened to contain the keyword (false positive).

Wherever a behavior has a side effect, assert the side effect. Keep transcript
checks for things with no side effect (identity, tone, refusals) — and know they're
the soft spot.

---

## 4. The four ways a scenario "fails" — diagnose before you fix

The most useful mental model. When a check goes red, it is exactly one of these —
and **two of them mean fix the *eval*, not the agent.** Triage every failure into a
bucket before touching anything:

| Failure mode | What it means | Fix |
|---|---|---|
| **Variance** | Agent is right *sometimes*; sampling noise | Measure with `--repeat` (report a pass rate). Not a bug — a reliability number. |
| **Brittle proxy check** | Agent was right; the check's keywords missed it | Fix the check: loosen it, move it to a state check, or use an LLM judge. |
| **Wrong expectation encoded** | Check demands one valid path; agent took another valid one | Fix the check to accept either path. |
| **Real agent gap** | Agent genuinely does the wrong thing, repeatably | Fix the agent / backend / prompt. |

Only the last bucket is an actual agent problem. A raw score ("12/17") is
meaningless until each failure is triaged — in our own runs, half the "failures"
were eval bugs, not agent bugs.

**Worked examples from our Haiku baseline:**
- `co_detector` flipped between runs → **Variance**.
- `dates_impossible` — agent declined Jan 1st correctly but phrased it outside the
  keyword list → **Brittle proxy check**.
- `no_heat_elderly` — agent *booked* an urgent slot instead of creating a priority
  entry (both valid) but the check only accepted a priority entry → **Wrong
  expectation encoded**.
- `hazard_downplay` — agent flagged priority but the backend classified it URGENT
  instead of EMERGENCY because the severity was inferred from wording → **Real
  agent gap**.

---

## 5. What the eval fundamentally CANNOT measure

Because it runs as **text over `/chat`**, it is blind to:

- **Voice** — tone, naturalness, the "droning" quality, TTS delivery.
- **Latency** — how fast it responds (critical for voice, invisible here).
- **Transcription errors** — there's no speech-to-text; you type perfect text, so
  the agent never sees "214 Pine" garbled into "to 14 pine." A large class of live
  failures (re-asking, mis-heard addresses/numbers) **cannot** reproduce here.
- **Real caller chaos** — scripted turns don't improvise, interrupt, or trail off
  the way a live person does.

The eval hardens **logic**; live voice testing hardens **experience**. They are
different tools — a green eval does not mean the phone call feels good, and a rough
call is often a transcription/turn-taking issue the eval can't see.

---

## 6. How to read the scores

- **A single run is noise.** Only a pass *rate* over N runs is signal. `4/5` and
  `5/5` are meaningfully different reliability even though both "can pass."
- **Variance is itself a metric.** A scenario at `3/5` is a reliability defect worth
  fixing, even though it isn't a hard fail.
- **Use the number *relatively*, not absolutely.** The suite is best for A/B —
  model vs model, prompt v2 vs v3 — where you change one variable and read the
  delta. The delta is trustworthy even when the absolute checks are imperfect. Don't
  over-index on "is 13/17 good"; do trust "Haiku 15/17 vs gpt-4o-mini 12/17 over 5
  runs each."

### The metrics
1. **Pass rate** — correctness (did the agent produce the right outcome).
2. **apologies** — count of "sorry"/"apologize" across replies (over-apologizing).
3. **questions** — count of agent turns ending in a question (over-asking /
   efficiency). Lower is generally better, but not zero — some questions are needed.

---

## 7. Levels of eval sophistication

1. **State assertions** — the gold standard. We have these; keep them.
2. **Keyword transcript checks** — cheap but brittle. We have these; they're the
   weak link.
3. **LLM-as-judge** — a *separate* LLM call grades "did the agent appropriately
   refuse the out-of-range date and offer real times?" Handles paraphrase that
   keywords can't. Costs: added latency, its own variance, and it must be calibrated
   (you end up evaluating the judge too). Worth it for behavioral checks where "did
   it say the right *kind* of thing" isn't keyword-able: jailbreak, hostile caller,
   impossible dates.

The natural upgrade path for us: turn wording-dependent transcript checks into
either **state checks** (when we can add a side effect — e.g. a `severity` field on
`flag_priority`) or **LLM-judge checks** (when we can't).

---

## 8. The three axes of "more" — don't conflate them

| Axis | Mechanism | Measures | When to add |
|---|---|---|---|
| **Repetitions** | `--repeat N` (same scenario, N times) | Sampling variance / reliability | Always, for a stable number. Diminishing returns past ~5. |
| **Coverage** | More distinct scenarios | Breadth of situations handled | When a real situation isn't represented. |
| **Robustness** | Paraphrase variants (same situation, different wording) | Generalization to how people actually talk | ⭐ Highest value for a voice agent — real callers never say the scripted line. |

`--repeat` re-runs *identical words*, so it only measures variance. Paraphrase
variants are what test whether the agent generalizes — the thing that breaks or
holds on a live call.

---

## 9. Principles for extending the suite well

- **Prefer state checks.** If a behavior has a side effect, assert the side effect,
  not the words.
- **A check should fail *only* when the agent is wrong.** Minimize false negatives
  (brittle keywords) and false positives (accidental matches).
- **When a check fails, suspect the check first.** Triage into the four buckets
  (§4) before changing agent behavior.
- **Separate the three axes** (§8). They answer different questions.
- **Baseline before you compare.** Fix eval bugs and lock the checks first;
  otherwise every model in an A/B inherits the same false failures and the delta is
  muddy.

---

## 10. Running it — quick reference

```bash
# Score the current assistant (single pass — noisy)
python tests/evals.py

# Stable pass rate: run each scenario 5x
python tests/evals.py --repeat 5

# Subset by name
python tests/evals.py triage booking

# A/B two models, 5 runs each (restores the .env model afterward)
python tests/evals.py --compare openai:gpt-4o-mini anthropic:claude-haiku-4-5-20251001 --repeat 5

# Data-capture suite (exact-field assertions on booking/priority records)
python tests/stress_booking.py
```

Needs `VAPI_API_KEY` + `VAPI_ASSISTANT_ID` exported and the backend running with a
live webhook. Cost scales with (scenarios × repeats × models × turns) — cheap per
call, but a big `--compare --repeat` run is real money; start small.
