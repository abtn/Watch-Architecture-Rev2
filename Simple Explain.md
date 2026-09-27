# Watch in plain language — second edition

  

## 1. What changed since the last explanation

  

The first version of this explanation was written as if AI agents were a competing idea. They're not. The right way to see it:

  

**AI agents solved the wrong half of the problem — brilliantly.**

  

In two years, agent software learned to *do* things: use tools, browse, write code, run multi-step work. It also grew "memory" and "skills" — files and notes that persist between conversations. So today you can build an assistant that watches crypto news and remembers yesterday.

  

What agent software did **not** solve is the question that matters once you rely on it for months:

  

> **Who is allowed to change what the system believes, under what rules, and how do you know the changes were earned?**

  

Every agent product makes one of two choices about its memory:

  

- **Frozen.** A human edits the skill file or system prompt. The system never learns on its own.

- **Ungoverned.** The agent updates its own memory whenever it feels like it. No provenance, no verification, no review, no unlearning. It accumulates cruft the way a junk drawer does.

  

There is no third option on the market: *memory that changes, but only through earned, verified, reviewable change.* That missing third option is Watch.

  

## 2. The five floors of memory

  

Your own observation — "internal memory is like a skill that isn't fixed and updates over time" — turns out to be the key to the whole design, once you split "memory" into the different things people mean by it. Watch separates them into five floors, each with a different rule for **who may write it and when**:

  

| Floor | What it is | In Watch | Who changes it | Does time fade it? |

|---|---|---|---|---|

| **Instinct** | What the AI just knows | The model's weights | Nobody here | No — and it's explicitly not ours |

| **Doctrine** | How the team operates | TeamPolicy | Human approval only | No — reviewed, not decayed |

| **Skill** | What the team learned about its own methods | KnowledgeItems (practices, playbooks) | Only through evidence + evaluation + approval | No — versioned and revised, never rots on a clock |

| **Belief** | What we think is happening out there | Threads, Hypotheses, evidence | Any worker — with cited evidence | **Yes — beliefs decay on a schedule** |

| **Perception** | Raw observations of the world | Signals (immutable photocopies) | Nobody — append-only | No — but they stop being *current* |

  

Here's the correction to your sentence that makes the design work: **skills don't update in time. Beliefs do.** A belief like "leverage is building, a squeeze is coming" *should* fade if the world goes quiet — silence erodes it, automatically. A skill like "register a price *level*, not a direction" should *not* fade after a quiet month — it was paid for with a real mistake. If lessons decayed like beliefs, the team would forget its hard-won knowledge every quiet month. If beliefs never decayed, the board would ossify into a museum of stale hunches. Same mechanism — change over time — needs opposite policies. That's why there are two memory systems, not one.

  

## 3. The news desk still explains it best

  

Think of a **crypto research desk** at a news organization:

  

- **The desk** is the durable thing: files, a wall of current beliefs, a binder of methods, a logbook. *In Watch: a database.*

- **The reporters** are brilliant but temporary — new one every shift, complete amnesia overnight. *In Watch: AI model calls.*

- **The mailroom** photocopies everything that arrives and stamps it with a fingerprint. The original might vanish tomorrow; the photocopy can't change. *In Watch: Signals and Snapshots.*

- **The wall** holds the current story: "What we're confident about. What's disputed. What's still open." Losing explanations stay pinned up with their reasons. *In Watch: Threads with competing Hypotheses.*

- **The clerk** is dumb, slow, and utterly reliable. Every suggestion from a reporter gets checked: is that quote *actually* in the photocopy, word for word? Does this change have a stated reason? One failed check → REJECTED stamp, logged, with the reason. *In Watch: validation code, the heart of the system.*

- **The binder** holds what the desk learned about its own work — and it can only be edited through a formal process: something happened → we assessed it honestly → we propose the change → a human approves → the old version is archived, never erased. *In Watch: Outcome → Evaluation → LearningChange → KnowledgeItem.*

- **The expert** can walk in and pin their own theory on the wall — but it passes the same clerk. No quote-check exemption for seniority. And the desk can call the expert mid-story, ask a question, and pin the *answer* as evidence — photocopied, stamped, quotable. *In Watch: `operator_update` and Consultations.*

  

The motto unchanged: **reporters leave; the desk remembers.** New in this edition: *the expert is one of the workers, not a bystander.*

  

## 4. One day at the crypto desk (the whole system in one story)

  

This is the actual first team we're building — Bitcoin market desk.

  

**Morning.** The mailroom fetches the daily market snapshot and renders it into a fixed-format photocopy: `close 67412 | funding_rate 0.0125 | open_interest 18.4B | spot_etf_net_flow +214M …`. Notice: even a *number* arrives as text with a fingerprint — so when a reporter later quotes "funding_rate 0.0125," the clerk can verify it letter by letter. No special numeric privileges.

  

**Triage.** A wire repost of an ETF story gets stamped `duplicate` of the original publisher's version — because last time (on another desk, another story), a repost absorbed a canonical source and the desk missed the one signal that mattered. That lesson was carried in through the binder.

  

**A reporter works the wall.** It suggests: "The funding and open-interest lines *support* the leverage-squeeze theory — raise it to high." The clerk checks the quotes, the stance, the reason. Accepted. It also tries to raise confidence based on an article that merely *mentions* the theory — rejected: mention is not argument.

  

**The prediction.** The desk's strongest belief implies a falsifiable claim. The binder's playbook forces the numeric form: *"Any daily close below $62,000 between June 20 and July 4."* Registered **before** the result is known — a promise with a deadline.

  

**Two weeks later: reality.** BTC never closes below $62,000. The check is recorded. And now the step that almost no AI system takes: the **missed** prediction goes back up on the wall as *challenging evidence*, and the desk's own highest-confidence belief drops from high to low — in one auditable step, with the full paper trail.

  

**The learning.** An evaluation asks *why* the call missed. The verdict is written honestly: the prediction failed, but the **method** worked — registration was clean, the check resolved unambiguously, self-correction took one day. From that: a new playbook page — *"funding extremes are a regime indicator, not a reversal timer."* Approved, versioned, archived. Next week's reporters carry it automatically.

  

That last sentence is the product. **The desk got experienced.**

  

## 5. "A skill that updates" vs. "a skill that learns"

  

When any agent system updates its skill file, seven questions go unanswered: Who changed it? Why — which experience? Was that experience assessed or just *felt* successful? What stopped a bad day from becoming bad doctrine? Can you see the diff? Does it come up for review? Can you undo it?

  

In Watch, that same update is a formal pipeline with all seven answers — and it borrows its discipline from something you already trust: **version control.** A proposed lesson is a pull request against the team's own mind. The clerk is the CI that must pass. Human approval is the code review. Old versions are the revert. The logbook is the commit history. Watch is *git for lessons* — and beliefs that expire on top of it.

  

## 6. So what *is* Watch, next to an agent framework?

  

The cleanest division:

  

- **Agent frameworks orchestrate behavior** — how work gets done, step by step, with tools.

- **Watch governs belief** — what may be believed, on what evidence, for how long, and how the team's own methods improve.

  

Watch has no interest in replacing the hands. It is the **ledger** the hands must write into. Four things in Watch have no equivalent in any agent product, because they didn't come from AI research — they came from newsrooms, science, and forecasting:

  

1. **Beliefs that expire.** No agent memory has a half-life.

2. **Competing explanations kept on the board.** Agents collapse to the latest answer; Watch keeps the losers pinned with their reasons.

3. **Grounded assertions.** Not "claims," but claims whose every quote is checkable against an immutable photocopy.

4. **A closed loop.** Agents almost never ask "was what I said last month true?" Watch registers predictions *before* results exist and grades itself after — including its misses. Without that, "learning" is just vibes.

  

One honest boundary: Watch does **not** manufacture trading edge. It structures belief, accountability, and improvement. If raw predictive power is the goal, quantitative tooling stays a specialized job — Watch wraps it; it doesn't replace it.

  

## 7. Where AI agents fit — the answer at the end

  

Now the part you asked to be taken seriously. AI agents appear in this project in **four roles**, in order of arrival:

  

**Role 1 — the builders (already true).** The documentation set is written for an AI workforce: `AGENTS.md` is the employee handbook, the glossary fixes vocabulary, invariants are the law, ADRs are the meeting minutes. Coding agents build Watch the same way Watch's teams work: read the binder, propose changes, pass the checklist. The project is a small demonstration of its own philosophy.

  

**Role 2 — proven before trusted (the plan's spine).** The first milestone builds the entire desk with **no AI at all** — a scripted FakeWorker makes hard-coded suggestions so the clerk, the ledger, and the concurrency rules are proven with zero model unpredictability. Only after the gates work do we let a real model near them.

  

**Role 3 — the workers (from M1 onward).** The AI's runtime role is precisely defined: a **worker** that reads a context assembled from the database, *proposes* changes, and never touches the ledger directly. The connection is deliberately thin — a `ModelClient` protocol — so Claude today, another model tomorrow, or an agent framework the day after, without the desk noticing. Waiting for a human (a Consultation) happens *between* tasks, so agents never block on people and people never block on agents. Escalating autonomy is a dial: manual intake → scheduled ingestion → full automation with human gates on anything that matters.

  

**Role 4 — the customers (future, deliberate).** The end state this points toward: a Watch desk is an **experience engine for agents**. Its KnowledgeItems are validated, versioned, outcome-tested skills. The natural export is compiling them into skill files or prompt fragments for *any* agent system — Watch mints the skills; other agents spend them. That's genuinely on the horizon, deliberately not in v1, and it would need its own decision record because "knowledge leaves the kernel" touches several laws.

  

The one-line summary of the whole relationship: **agents give Watch its labor; Watch gives agents their experience.** Neither is interesting alone. A desk with no reporters does nothing; a reporter with no desk is a brilliant amnesiac.

  

## 8. The whole thing in one paragraph

  

Watch is a small software organization that behaves like a research desk: an AI (or a human, or both) does the reading and the thinking as temporary workers, while everything durable — the beliefs, the evidence, the confidence, the predictions, the lessons — lives in a governed ledger with one strict rule at its heart: *nobody writes to the ledger directly; everything is proposed, checked against immutable sources, and committed with a recorded cause.* Beliefs rise and fall with evidence and expire with silence. Predictions are promised before they can be graded, and misses feed back in. Lessons enter the binder only through evaluation and human approval, versioned and reversible. Agent frameworks and their memory features are welcome inside — as workers behind a narrow interface — because Watch isn't competing with them for the work. It's doing the thing they've left undone: turning brilliant, forgettable effort into a team that remembers, checks itself, and gets better.