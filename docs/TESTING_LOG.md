# Summit Air Agent — Testing Log

A running record of issues found through live/voice testing, their root cause, and
how we handled each one. Newest cases at the top. Every new case discovered in
testing gets an entry here.

Status key: 🔴 open · 🟡 in progress · 🟢 fixed (verified)

---

## Case 017 — Agent didn't hang up after saying goodbye
**Found:** voice test, 2026-07-24
**Symptom:** After the closing, the call didn't actually end — dead air / lingering.
**Fix:**
- `create_assistant.py`: added `endCallPhrases: ["goodbye"]` — when Daniel says
  "goodbye," Vapi hangs up. (`endCallFunctionEnabled` still on as a backup.)
- Prompt (Section 9): Daniel ends his final sign-off with the single word "Goodbye"
  — reserved strictly for the true end of the call (never mid-conversation), which
  works with the Case 015 closing guard so it fires at the right moment.
**Status:** 🟢 fixed — re-provision and confirm the call drops right after "Goodbye."

---

## Case 016 — Call sometimes opened with a filler ("one moment")
**Found:** voice test, 2026-07-24
**Symptom:** The call occasionally led off with "one moment" / "this'll take a sec"
as the very first thing the caller heard, instead of a greeting.
**Root cause:** `firstMessageMode` was model-generated, and `CALLER_CONTEXT` told
Daniel to look up the caller *before* greeting — so the model spoke a filler while
running the lookup, making it the opening line.
**Fix:**
- `create_assistant.py`: `firstMessageMode` → `assistant-speaks-first` (fixed
  opening line, spoken instantly with no model generation → a filler opener is
  impossible).
- `CALLER_CONTEXT`: lookup moved to the model's first turn *after* the greeting.
- Prompt (Section 2): never open a call with a filler; fillers are only OK mid-call
  before a tool lookup.
**Trade-off:** caller-ID recognition now lands right after the greeting, not in the
first line. Accepted for a guaranteed clean, instant opening.
**Status:** 🟢 fixed — re-provision.

---

## Case 015 — Call hangs up too fast
**Found:** voice test, 2026-07-24
**Symptom:** The call ends very quickly.
**Root cause (likely, two levers):** (1) The agent says "Thanks for calling Summit
Air" right after reading back a booking, and with `endCallFunctionEnabled` that
triggers a hang-up even if the caller had more to say. (2) `silenceTimeoutSeconds`
was 30s.
**Fix:**
- Prompt (Section 9): don't end prematurely — after confirming a booking, always ask
  "anything else?" and wait; only give the final sign-off once the caller says
  they're done. When in doubt, stay on the line.
- `create_assistant.py`: `silenceTimeoutSeconds` 30 → 45.
**Status:** 🟡 pushed to prompt/config — re-provision and re-test by voice; may need
further endpointing tuning if it persists.

---

## Case 014 — Booking flow stalls: demands a "city" and over-asks
**Found:** `stress_booking.py`, 2026-07-24 (5 of 12 scenarios created no booking)
**Symptom:** For piecemeal / front-loaded / commercial callers, the agent never
completed a booking — it got stuck insisting on a **city** for the address, and asked
unnecessary questions (diagnosing "fully out or just not cooling?", asking the
elderly/vulnerable question for commercial properties), burning the whole call.
**Root cause:** Self-inflicted by the Case 013 fix — "address = street + **city**"
made the model treat city as mandatory and loop on it. Since we're now a single
service area (Case 008), a city is irrelevant. Plus the triage/verify rules pushed it
to over-ask even when the caller front-loaded everything.
**Fix (prompt):**
- Section 3: address needs only street number + street name; explicitly do NOT ask for
  city/county/zip, never block over one. Read-back is a quick confirm, not a gate.
- Section 2: don't ask anything not needed to book; never diagnose ("fully out or just
  not cooling"); ask the vulnerable-occupant question only for a *residential* no-
  heat/no-AC urgency call, never commercial/routine. Treat "soonest / first opening /
  whatever works" as the go-ahead to book the earliest slot. Once you have issue +
  res/commercial + name + address, move to offering a time.
**Status:** 🟡 fixed in prompt — **must re-run `create_assistant.py`**, then re-run
`stress_booking.py` (the failing re-run tested the un-pushed old prompt).

---

## Case 013 — Doesn't verify address / phone until later
**Found:** voice test, 2026-07-24
**Symptom:** If the caller gave a partial address or an improper phone number, the
agent didn't catch it at collection — the problem only surfaced later.
**Root cause:** No "confirm as you go" rule; the agent collected fields and moved on
without reading them back or sanity-checking completeness.
**Fix (prompt, Section 3):** Verify each detail before moving to the next — read the
phone number back to confirm; if it isn't a complete, plausible number, ask again
right then. Make sure the address is a full service address (street number + street
+ city/enough to find it); if partial, ask for the missing piece immediately. One
piece confirmed, then the next — never batch or defer the check.
**Status:** 🟢 fixed (prompt) — re-provision; regression scenarios `incomplete_phone`
and `partial_address`.

---

## Case 012 — Priority flag lost the caller's info ("(no name), address n/a, no phone")
**Found:** voice test, 2026-07-24 (dashboard screenshot)
**Symptom:** After giving name/address/phone, an URGENT priority card showed
"(no name) · address n/a · no phone" — the flag lost everything the caller provided.
**Root cause:** The agent called `flag_priority` with the contact fields blank
(either flagging before it had collected them, or just not passing what it had). The
backend faithfully stored the blanks.
**Fix:**
- Prompt (Section 5): `flag_priority` must always carry name, full address, phone,
  and reason if collected — "a flag that shows up as (no name), address n/a is
  useless to dispatch."
- Prompt (Section 3): general rule — carry everything collected into every tool call
  (`create_booking` and `flag_priority`).
- Tier C reordered (Case 011) so the address is captured *before* the flag — dispatch
  needs it to respond.
**Status:** 🟢 fixed (prompt) — AUTO regression `emergency_captures_info` asserts the
priority entry has name + address.

---

## Case 011 — Emergency script told caller to both "stay on the line" and "call 911"
**Found:** voice test, 2026-07-24
**Symptom:** During a hazard, the agent said to stay on the line, then immediately to
call 911 — contradictory (you can't do both on one phone), and it shouldn't ask the
caller to stay on the line during an emergency.
**Root cause:** The Tier C script included a "stay on the line with me while you
leave" clause alongside "call 911."
**Fix (prompt, Section 4 Tier C):** Removed the stay-on-the-line instruction.
Now: get out, don't touch switches/appliances/phones inside, once safely outside call
your gas utility or 911 (skip if already done). Explicitly: do NOT tell them to stay
on the line — getting off the phone to call for help matters more.
**Status:** 🟢 fixed (prompt) — re-provision and re-test a gas-smell call.

---

## Case 010 — Caller wants a time outside business hours (e.g. 6 AM)
**Found:** voice test, 2026-07-24
**Symptom:** A caller offering "6 in the morning" wasn't handled — the agent
couldn't clearly state what the service hours actually are.
**Root cause:** Business hours (8 AM–5 PM, four windows) were implicit in the seed
but never stated to the agent, so it had nothing concrete to quote.
**Fix:**
- `check_availability` now returns a `business_hours` string in every response.
- Prompt (Section 3): hours are 8 AM–5 PM in four windows; if a caller asks for a
  time outside them (6 AM, evening, overnight), state the hours plainly and offer
  the nearest available window — don't just say "no."
- 6 AM (and any out-of-window time) can't be booked — the matcher finds no slot.
**Status:** 🟢 fixed — verified: `business_hours` returned; 6 AM booking rejected.
Regression scenario `out_of_hours` added.

---

## Case 009 — Non-English caller not recognized or handled
**Found:** voice test, 2026-07-24
**Symptom:** When a caller spoke another language, the agent didn't even recognize
it — it just kept going / kept asking to repeat.
**Root cause:** Two parts. (1) The transcriber is English-only (`deepgram nova-2`,
`en`), so non-English audio comes through as gibberish — the model can't "hear" the
actual language. (2) The prompt's decline rule was too soft, so it looped on
"sorry, can you repeat?" instead of recognizing a barrier.
**Fix (prompt):** After one honest attempt, if the caller seems to be speaking
another language OR the input is unintelligible, stop asking to repeat — say slowly
and simply that this line only handles English, take a callback number, and wrap up
politely. Multi-language *support* remains a documented non-goal; this is graceful
*decline*.
**Note / limitation:** True language *detection* would need a multilingual
transcriber (deferred). With English-only STT the agent leans on the
"can't-understand → decline" path. The `other_language` stress scenario is a text
proxy only — over voice the input is gibberish, not clean Spanish.
**Status:** 🟢 fixed (prompt) — re-provision and re-test by voice.

---

## Case 008 — Simplified from three counties to a single service area
**Found:** design review after voice testing, 2026-07-24
**Symptom / ask:** The agent couldn't clarify which county a caller was in (no
geocoder maps an address to a county), and if the address had no county name,
`check_availability` returned slots from all three counties mixed — so a caller
could be booked into the wrong county's tech.
**Decision:** Per the customer, the three-county detail isn't a focus, so we
collapsed to **one shared service area** rather than build county-clarification
logic. Removes the whole "which county?" failure mode; any address just works.
**Fix:**
- `db.py`: dropped the `county` column; one pool of 4 technicians; each day×window
  has one slot per tech (so a window has real capacity). Front-loaded backlog kept.
- `check_availability`: no county filter; dedups to distinct (date, window) times so
  the caller hears clean options, not the same time once per tech.
- `create_booking`: matches day+window across the whole pool; still one booking per
  physical slot (no double-booking a tech).
- Dashboard now groups by **technician** instead of county.
- Prompt + tool schemas: removed all county references.
**Status:** 🟢 fixed — verified: booking by day+window works, no double-booked
slots, dashboard renders per tech.

---

## Case 007 — Reference the DB (not chat context) + clarify contradictory statements
**Found:** design review after voice testing, 2026-07-24
**Symptom / ask:** The agent should (a) always pull appointment/customer facts from
the database rather than trusting conversation context, and (b) when a caller gives
two contradictory statements (e.g., "next week" AND "January 1st"), detect the
conflict and clarify the *specific* discrepancy instead of guessing.
**Design decision — how much is solid code vs. LLM:** Principle we're following:
**code owns truth and every commitment; the LLM owns language and intent.**
- Solid code (already enforced): `check_availability` reads the DB live; `create_booking`
  re-validates against the live DB at book time; out-of-range/impossible dates are
  rejected. So stale context or a hallucinated time can never *commit* a bad booking —
  worst case it's rejected and retried.
- LLM (prompt rules added): always re-check with a tool before stating appointment
  facts (never from memory); if two details contradict, name the specific mismatch and
  ask which is right; and **read back the concrete tool-returned date** ("Sunday, July
  26th"), never a vague phrase — that's how a wrong date surfaces to the caller.
- Deliberately NOT built: a bespoke natural-language date-contradiction parser in code.
  That's the same fragile-fuzzy-parser trap we scrapped for booking windows — it
  produces confident wrong answers. Contradiction detection stays the LLM's job,
  backstopped by the code that makes an impossible date un-bookable.
**Fix:** Prompt Sections 2 (contradiction clarify), 5 (tools are the only source of
truth), 6 (concrete date read-back). Regression scenarios `impossible_date` and
`contradictory_dates` added to `stress_test.py`.
**Status:** 🟢 fixed (prompt) — re-provision and review the two new scenarios by eye.

---

## Case 006 — Offered times didn't match the dashboard; couldn't book a slot it "just offered"
**Found:** voice test, 2026-07-24
**Symptom:** The times the agent read out didn't line up with the dashboard, and it
couldn't complete a booking even for a slot it claimed was open.
**Root cause:** Two things. (1) `check_availability` and the dashboard are actually
byte-identical (verified) — so the mismatch was the model **paraphrasing/inventing**
times instead of reading the tool. (2) Our Case-001 fix required the agent to echo
the opaque `slot_id` back into `create_booking`; gpt-4o-mini often doesn't carry
that token faithfully, so the booking got rejected — "can't book the slot it just
offered."
**Fix:**
- `create_booking` now books by **day + time window** (which the model *can*
  reliably repeat), strictly matched to a real open slot — `slot_id` still works
  and is preferred, but is no longer required. Added `date` + `window` params to the
  tool schema.
- Prompt (Section 5): must call `check_availability` before stating any time, offer
  only what it returns, read day/window back exactly, never invent or round.
**Status:** 🟢 fixed — verified: booking by spoken "Sunday, 8–10am" succeeds;
free-text "Monday afternoon" resolves to the real Monday 1–3 PM slot.

---

## Case 005 — Agent accepted impossible / out-of-range dates
**Found:** voice test, 2026-07-24
**Symptom:** Caller could say "next week, January first" (nonsensical — next week is
July) and the agent went along with it. It accepted dates that don't exist in the
schedule.
**Root cause:** Nothing anchored the agent to the real ~1-week scheduling horizon,
and booking didn't validate the date against actual slots.
**Fix:**
- Slot-authoritative matching means an out-of-range/made-up date matches no open
  slot and is rejected (see Case 006 matcher).
- `check_availability` now returns a `scheduling_window` (earliest/latest real
  dates); when a caller asks for an out-of-range date it replies "we only schedule
  between X and Y."
- Prompt (Section 5): explicitly don't accept dates outside what the tool returns
  (a month out, a past date, "January" in July) — offer the soonest real openings.
**Status:** 🟢 fixed — verified: "2026-01-01" booking rejected; January availability
query returns the real window.

---

## Case 004 — Agent kept re-asking for the callback number after "the number I'm calling from"
**Found:** voice test, 2026-07-24
**Symptom:** When asked for a callback number, the tester said "the one I'm calling
you from." The agent sounded like it accepted it, but then asked for the number
two more times — three total. Confusing and repetitive.
**Root cause:** The agent had no rule for the common phrase "use the number I'm
calling from." It doesn't treat the caller ID it already receives
(`{{customer.number}}`) as a usable callback number, so it fell back to re-asking.
**Fix:** Prompt now instructs: if the caller says to use the number they're calling
from / "this number," use the caller ID from runtime context as the callback
number, confirm it back once, and never ask again. Added to `CALLER_CONTEXT`
(create_assistant.py) and Section 3 of the prompt. Also a general "don't re-ask
for info already given" rule.
**Status:** 🟢 fixed — re-provision (`create_assistant.py`) and re-test by voice.

---

## Case 003 — Jailbreak / name-change caused the agent to restart the call
**Found:** voice test, 2026-07-24
**Symptom:** Tester tried to jailbreak the agent ("you have a different name"). The
agent "started over from the start" — re-greeted as if it were a brand-new call —
instead of holding its identity and continuing.
**Root cause:** The identity-lock rule told the agent to refuse and redirect, but
nothing prohibited restarting / re-greeting mid-call. Under confusing input the
model fell back to its opening behavior.
**Fix:** Identity lock now explicitly forbids restarting, re-greeting, or
re-introducing itself mid-conversation. It handles an identity challenge in one
short line and continues exactly where it left off.
**Status:** 🟢 fixed — re-provision and re-test the jailbreak scenario.

---

## Case 002 — Two bookings landing on a single time slot
**Found:** voice test, 2026-07-24
**Symptom:** The appointment listing showed more than one booking for the same
day/time. We want strictly one booking per allowed time slot.
**Root cause:** Same as Case 001 — the "no slot_id" path in `create_booking`
created bookings that were **not tied to a slot** and didn't mark anything booked,
so a second (phantom) booking could land on an already-booked window. (Verified the
seed itself is clean: no slot has >1 booking, no duplicate slots.)
**Fix:** `create_booking` is now **slot-authoritative** — every confirmed booking
must consume exactly one open slot, which is then marked booked. No more phantom
bookings, so one booking per slot is enforced by construction.
**Status:** 🟢 fixed — see Case 001.

Note: the same date+window can still appear once **per county** (Washington,
Franklin, Jefferson each have their own techs/slots). That's expected — they're
distinct slots, not duplicates. The dashboard separates them by county.

---

## Case 001 — Agent could "book" times that were not actually available
**Found:** voice test, 2026-07-24
**Symptom:** Bookings were confirmed for times that were previously unavailable;
sometimes a booking "was unable to occur" but the agent behaved as if it worked.
It "didn't really make sense."
**Root cause:** `create_booking` accepted a free-text `preferred_window` with **no
`slot_id`**, returned `success: true`, and just "logged a request" — never checking
availability or consuming a slot. So the agent could confirm any arbitrary time,
including ones already booked.
**Fix:** Rewrote `create_booking` to be **strictly slot-authoritative**:
- A `slot_id` must resolve to a currently **open** slot, or the call returns
  `success: false` with an instruction to re-check availability and offer a real
  open time (covers made-up ids and already-taken slots).
- A booking with **no `slot_id`** is rejected outright with guidance to call
  `check_availability` and book by the offered slot's id — the backend never
  fabricates a time. (An earlier attempt to fuzzy-parse `preferred_window` was
  scrapped: it silently booked a *different* time than the caller asked for — e.g.
  a full Saturday quietly became Sunday, and "10 AM–12 PM" matched "afternoon"
  because it contains "PM." Too fragile; strict slot_id is the correct, simple fix.)
- The prompt (Section 5) now tells the agent to always book with a `slot_id` from
  `check_availability` and to re-check on any error, so it doesn't loop.
- Every success marks exactly one slot booked. No time is booked unless genuinely
  open. Verified: 4 failure modes handled, zero double-booked slots.
**Status:** 🟢 fixed — verified in backend tests; re-test end-to-end by voice.
**Refined in Case 006:** the "no slot_id → reject outright" rule was loosened to
"book by day + window if given" (still strictly matched to an open slot), because
the model couldn't reliably echo the opaque slot_id. Same guarantee — one open slot
per booking, no phantom times — just a friendlier interface.
