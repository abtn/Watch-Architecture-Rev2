# Watch — Architecture Revision 2

Watch is currently in the architecture and specification phase. The repository intentionally contains no implementation code. The purpose of this phase is to establish the conceptual model, invariants, information architecture, reasoning model, and execution semantics before implementation begins.

This repository contains Watch's architecture specifications, invariants, implementation roadmap, glossary, walkthrough, and architecture decision records. The detailed architecture overview is in [Architecture Revision 2 Overview.md](Architecture%20Revision%202%20Overview.md).

Start with [CHANGE_MAP.md](CHANGE_MAP.md) for document authority and [PLAN.md](PLAN.md) for implementation phases. Revision 2 adds a deliberative Control path that converges into the existing Task execution system; workers propose, application code validates, and the Kernel commits durable state.
