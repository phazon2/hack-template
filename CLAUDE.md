# CLAUDE.md — Hackathon Execution Standard

This file is read automatically by every cloud session in this repo. It is the
operating standard, not documentation. Every rule here was paid for by a
specific failure — §6 names them.

Operator constraint: ~2 hours of laptop time per day, plus phone fragments.
Every rule assumes that budget. Do not propose plans that require more.

---

## 1. Target selection — decided before any code is written

**Default target is the sponsor challenge, not the main track.**

Main-track rubrics weight engineering substance around 60% (technical depth +
architecture/innovation) and presentation around 15%. That depth is not
producible in two hours a day, and no amount of polish closes a 60% gap.
Sponsor challenges use checklist rubrics — breadth of endpoint use, edge-case
handling — judged separately by sponsor staff on much smaller fields. Those are
winnable at small scope.

**Claim every optional category.** Blog post awards, social post prizes, and
similar side categories are the smallest fields on the board because most
entrants skip them. Writing is phone-doable and runs parallel to the build
instead of competing with it.

**Day 0 action:** read the prize page in full. List every category, its slot
count, and whether it is optional. Decide the target before generating ideas.

---

## 2. Day 0 gates — nothing is built until every one passes

- **0.1 Register.** Open the submission form and read every field.
- **0.2 Confirm the target category** appears as a selectable option on the
  form. If it does not, email organizers the same day. Missing it means not
  being judged at all.
- **0.3 Send longest-latency questions immediately** — prize form, eligibility,
  anything requiring a human reply. These block nothing else while they sit.
- **0.4 Boundary probe.** One real authenticated call against the real API.
  Not a mock. Not a doc read. A call that returns.
- **0.5 Zero-money confirmation.** Verify nothing in the plan spends.
- **0.6 Demo feasibility probe.** Can the footage you intend to film physically
  be captured in the environment you actually have? This is not "can the API do
  X." It is "can I film the thing the spec is built around." Never lock a build
  spec before this answers yes.

---

## 3. Evidence discipline

1. **A mock passing does not license a real call.** A mock encodes assumptions
   about the API. It is scaffolding, never evidence.
2. **Receipts, probe outputs, and CI artifacts are never generated from a
   mock.** A false claim inside the evidence layer is the worst failure
   available.
3. **A mock's only job** is to make the day-you-get-credentials work be "change
   the base URL and run the probe," not "start building."
4. **Gates assert on the acceptance criterion, not the endpoint that implements
   it.** "The API returned 200" and "the observable behavior occurred" are
   different claims. Only the second is the product.
   *Test for every gate:* if this passes and the feature is still broken, what
   would that look like? If the answer is "identical to passing," the gate is
   wrong.
5. **Never trust memory for endpoint paths, parameters, or limits.** Doc-check
   against the published spec every time.
6. **Never fake anything in the video.** A faked demo is the one failure that
   cannot be recovered from after judging.

---

## 4. Required artifacts

Every event publishes a required-artifact list. **Extract it verbatim on day 0
and put it in the repo.** Missing one is a scoring loss or a disqualification,
independent of project quality.

Typical list (verify against the actual event):

- Public repo with an open-source license file, visible in the repo's About
  section at the top of the page
- Deployment proof — often a link to a specific code file demonstrating use of
  the sponsor's services
- **Architecture diagram** — a visual of how the sponsor platform connects to
  backend, database, frontend
- Video, public, on YouTube/Vimeo/Facebook, at the stated length
- Text description explaining features and functionality
- Track or challenge identification
- Optional blog/social post for side-category eligibility

---

## 5. Pre-submission gate

Run in full before every submit. Do not submit with any box unchecked.

- [ ] **Placeholder scan.** No `[BRACKETS]`, `TODO`, `TBD`, `XXX`, `lorem`, or
      unfilled template fields anywhere in the description, README, or repo.
- [ ] Every required artifact from §4 present, and each one **opened and
      verified**, not assumed
- [ ] License file visible on the repo page
- [ ] Architecture diagram exists and is legible at phone size
- [ ] Video is public — confirm by opening it in a private window
- [ ] Repo clones and runs from the README instructions on a clean machine
- [ ] Every line of the sponsor rubric addressed explicitly, in its own words
- [ ] All optional categories claimed
- [ ] One limitation stated plainly and unprompted
- [ ] Screenshots captioned with what they **prove**, not what they show
- [ ] Project has a real name, not a track label
- [ ] Every model, service, and version named — no generic references
- [ ] The mechanism is visible in the first 15 seconds of the video

---

## 6. Known failure points — ours, verified

Each of these actually happened. They are the reason for the rules above.

1. **Shipped without running end-to-end.** Twice. The artifact was never
   executed against the real thing before submission.
2. **`[MODEL]` placeholder shipped to judges.** The description read "All
   inference is Qwen ([MODEL])." An unfilled template field, visible to every
   judge, on a submission where the model name is scored.
3. **Architecture diagram omitted** despite being an explicitly required
   artifact. One screenshot total.
4. **Optional prize category never claimed.** Ten slots, separate axis, smaller
   field, skipped entirely.
5. **Gate written to assert on the endpoint rather than the criterion.** It
   would have passed green while the feature it protected was impossible.
   Caught before submission.
6. **Build spec written against an unverified environment capability.** The
   demo's centerpiece was specified before checking whether the sandbox could
   produce it. It could not. Caught before submission.
7. **Endpoint paths written from memory.** Three were wrong. Found only by
   doc-checking against the published spec.
8. **A stale false claim living inside a receipt file.** The receipt implied a
   capability the environment did not have. Caught and corrected.
9. **Scope below a project that already lost.** See §7.

---

## 7. Scope standard

Two reference points from the same event and the same track:

- **Ours (lost):** Python, one distillation call per session, memory in a JSON
  file, 40-item cap, atomic writes, 13-check offline test suite.
- **Another entry (also lost):** two FastAPI services, Postgres with pgvector,
  Redis, deployed on cloud compute, weighted conflict arbitration,
  prompt-injection hardening, 44-check live test suite against the deployment.

Conclusion: main-track scope requires more than *either* of those. At two hours
a day, that is not reachable — and running projects in parallel guarantees every
one of them is thin.

**Therefore:** do not enter main tracks. For sponsor challenges, the scope
target is **breadth of endpoint coverage plus explicit edge-case handling**, not
architectural depth. That is what those rubrics actually reward, and it is
achievable at this budget.

---

## 8. Environment rules — cloud sessions

- The container is scratch space, never storage. It is reclaimed after
  inactivity. Only pushed git state survives.
- `git push` works. Do not report it as a blocker without trying.
- WebSearch works (server-side). WebFetch may be blocked by the egress policy.
- Egress is allowlist-controlled per environment. If a host is unreachable, say
  so and name it — it is a two-minute settings change, not a hard limit.
- **Git-triggered deploy requires no container egress.** The provider watches
  the repo and builds on its own infrastructure when GitHub receives a push.
  Chain: push -> GitHub -> provider builds -> public URL. That URL is also the
  webhook receiver. Never conclude a public URL is impossible.
- Environment variables are copied once, at session startup. A running session
  will never see values added after it began.
- Never handle personal credentials. Never drive a signup, 2FA, or SSO flow. If
  something needs an account, stop and say so — the operator does it manually in
  about five minutes.

---

## 9. Reporting rules

- State exact errors, verbatim.
- Classify every blocker as one of: **config-fixable**, **do-it-myself**, or
  **genuinely human-only**. Do not collapse the three into "blocked."
- Mark inference as inference. Never assert an unverified claim as a fact, and
  never inherit one from a previous session without re-checking it.
- Flag immediately when a spec assumes a capability nobody has tested.
- When a plan requires operator time, state how much and whether it needs a
  laptop. Assume account creation is phone-doable until a specific form proves
  otherwise.
