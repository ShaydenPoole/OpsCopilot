---
date: 2026-05-19
topic: aviation-ops-copilot
---

# Aviation Ops Copilot

## Summary

A production-grade aviation operations LLM copilot — a tool-using agent that answers operational questions by orchestrating historical flight data queries, live weather and NOTAM lookups, and document retrieval over a curated aviation corpus. The project ships as a deployed public demo with a first-class eval suite running in CI, full agent observability, and a polished portfolio surface. Audience and primary success criterion: ML engineer recruiters and technical reviewers conclude that the candidate builds real production systems.

---

## Problem Frame

The candidate is targeting ML / AI engineer roles in 2026, a market where the modal job description is "build evaluated LLM agents and RAG systems in production." Their current visible footprint is a single notebook-based Flight Delay project (3 commits, no deployment, no tests, no API) plus a LinkedIn profile and a resume. A recruiter clicking through finds no shipped artifact, no evals, no production engineering signal — exactly the gap that filters candidates out of ML engineer pipelines before any conversation happens. The candidate's BA experience and aviation-flavored portfolio piece create an underexploited narrative angle in a domain the candidate is genuinely interested in. The portfolio surface needed to compete for these roles does not exist today; the brainstorm exists to define what to build to close that gap.

---

## Actors

- A1. Recruiter / hiring manager — opens the deployed demo URL, asks 1–3 sample aviation operations questions, decides in under a minute whether the project feels real.
- A2. Aviation ops practitioner persona (dispatcher, ops controller, analyst) — the role the copilot pretends to serve. Anchors which questions are plausible and which answers are useful.
- A3. ML engineer technical reviewer — clicks through to the GitHub repo, reads the README, inspects tests, evals, CI, deploy config, and code organization to judge whether the work is competent.

---

## Key Flows

- F1. Public demo question-and-answer
  - **Trigger:** A1 or A3 opens the deployed demo URL.
  - **Actors:** A1, A3.
  - **Steps:**
    1. Visitor sees a chat surface with curated example questions visible.
    2. Visitor submits a question (typed or example-tapped).
    3. Agent plans tool calls, executes them, observes results, optionally iterates.
    4. Agent streams the response with citations and a tool-call trace visible / expandable.
    5. Visitor can drill into the trace to see which tools were called, with what arguments, and what they returned.
  - **Outcome:** Visitor has an answer plus visibility into how the agent reached it.
  - **Covered by:** R1, R2, R4, R5, R7.

- F2. Eval suite execution
  - **Trigger:** Push to main, scheduled run, or manual local invocation.
  - **Actors:** A3 (consumes results indirectly through the README and CI status).
  - **Steps:**
    1. Eval runner loads the versioned question bank.
    2. For each question, runs the agent end-to-end and captures the full trace.
    3. Scores tool-call correctness, retrieval quality, and answer quality (LLM-as-judge).
    4. Writes a results report and updates the CI status / README badge.
  - **Outcome:** Reproducible, regression-detectable evaluation visible to reviewers.
  - **Covered by:** R8, R9, R10.

- F3. Code and repo inspection
  - **Trigger:** Reviewer clicks the GitHub link from the resume, LinkedIn, or demo footer.
  - **Actors:** A3.
  - **Steps:**
    1. Reads README — demo GIF, deploy link, architecture diagram, eval results table, "what this demonstrates" section.
    2. Skims source layout (modular packages, not a single notebook).
    3. Opens tests and evals directories; checks CI workflow.
    4. Opens one or two source files to gauge code quality.
  - **Outcome:** Reviewer concludes the candidate ships real systems.
  - **Covered by:** R13, R15, R16.

---

## Requirements

**Agent core**
- R1. The system MUST be an LLM-driven tool-use agent that decides which tools to call and in what order — not a deterministic pipeline or single-shot prompt.
- R2. The agent MUST support multiple tools with clearly-typed input / output contracts, including at minimum: historical flight data query, weather (METAR / TAF) lookup, NOTAM lookup, and RAG retrieval over the aviation document corpus.
- R3. The agent MUST handle tool failures gracefully — retry, fall back to an alternative plan, or acknowledge the missing data in the user-facing answer. It MUST NOT fabricate facts to fill gaps.
- R4. The agent's final response MUST include citations or provenance for any factual claim derived from tool output or retrieval.
- R5. Every agent run MUST produce a structured, programmatically-inspectable tool-call trace, consumable by both the UI "show your work" panel and the eval scoring code.

**Data and corpus**
- R6. Historical flight data MUST come from a real public dataset (e.g., BTS / DOT On-Time Performance) loaded into a queryable store. Hardcoded examples are not acceptable.
- R7. The RAG corpus MUST be a curated set of public aviation documents (FAA AIM, ACs, publicly available ops references) with a fixed version pinned to the repo so eval runs are reproducible across commits.

**Eval suite (first-class artifact)**
- R8. A versioned eval suite MUST live in the repo, with a question bank covering at minimum: factual retrieval, multi-tool coordination, edge cases (ambiguous question, no data available, conflicting sources), and refusal scenarios where the right answer is "I don't know."
- R9. The eval suite MUST report at minimum: tool-call correctness (right tools called in a reasonable order), retrieval quality (recall@k or MRR for RAG-flavored questions), and answer quality via LLM-as-judge with a published rubric.
- R10. The eval suite MUST run in CI on every push to main, and its summary results (pass / fail, headline metrics) MUST be visible in the README.

**Production engineering surface**
- R11. The agent MUST be deployed to a publicly accessible URL with no authentication required, behind appropriate rate limiting and cost guards.
- R12. The agent MUST be callable as an HTTP API endpoint independent of the UI — frontend and agent service are decoupled.
- R13. The repo MUST include automated tests (unit tests for individual tools, integration tests for end-to-end agent runs against recorded LLM responses), a CI workflow that runs them on every push, and a README that visibly displays test / eval / deploy status.
- R14. Observability MUST be present — every agent run produces a structured trace of tool calls, LLM calls, latencies, and token costs, viewable via a hosted observability tool or a project-local dashboard.

**Communication / portfolio surface**
- R15. The README MUST include: a short demo GIF or video, the deploy URL, an architecture diagram, a sample eval-results table, install / run instructions, and a "what this project demonstrates" section written explicitly for recruiters.
- R16. A technical writeup MUST accompany the project — either in the README, a `docs/` page, or a linked blog post — covering agent design, eval methodology, and one or two non-trivial engineering decisions explained with their trade-offs.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R5.** Given the deployed demo, when a visitor asks "What's been driving delays into Newark over the past three months?", the agent calls the flight data query tool and optionally the weather tool, returns an answer naming top contributing causes, and the trace panel shows each tool call with its arguments and returned data.
- AE2. **Covers R3, R4.** Given the NOTAM data source is unavailable, when a visitor asks "Any current NOTAMs for KORD?", the agent acknowledges the missing data, answers what it can from alternative sources (or says so plainly), and does not invent NOTAM contents.
- AE3. **Covers R8, R9, R10.** Given a push to main, when the CI eval suite runs, the results report contains tool-call accuracy, retrieval recall, and LLM-judge answer-quality scores against the published rubric, with pass / fail thresholds applied; the README badge or table reflects the latest run.
- AE4. **Covers R11, R12.** Given the deployed demo URL, when a developer hits the documented `/query` API endpoint with a POST request, they receive a structured JSON response containing the agent's answer and its tool trace.
- AE5. **Covers R3.** Given a question with no relevant data in any tool ("What's the on-time rate for a fictional airline FlyZ?"), when the agent processes it, the response explicitly states that no data was found rather than producing a fabricated answer.

---

## Success Criteria

- A recruiter or technical reviewer landing on the GitHub README without prior context can, within 90 seconds, see what the project is, see it working (GIF), open the live demo (link), and see that it's measured (eval results). The page reads as a production system, not a notebook in a repo.
- The candidate can confidently discuss every architectural decision (why a tool-use agent, why these tools, why this eval design, why this deployment shape) in an interview and articulate the trade-offs rejected.
- The downstream `ce-plan` invocation can break this document into shippable phases without needing to invent product scope, capability set, or quality bars.

---

## Scope Boundaries

- No dependency on the candidate's existing Flight Delay prediction model. Linking the two projects is a deliberate future effort, not part of v1.
- No predictive ML model training inside this project. The agent reasons with retrieved data; training a new model is out of scope.
- No real-time integration with restricted airline-internal, air-traffic-control, or paid commercial systems. All data sources are public.
- No safety-critical or operational-decision claims. The README explicitly frames the project as a portfolio research copilot, not a tool any real ops user should rely on.
- No multi-user accounts, persistent user history, or login flow in v1. Single-session, anonymous demo only.
- No mobile-native UI in v1. Web-only, with a responsive layout sufficient for desktop and tablet.
- No human-in-the-loop annotation tooling. Evals use LLM-as-judge plus deterministic checks rather than a labeling pipeline.
- No paid LLM hosting infrastructure (own-GPU model serving). Inference is via commercial LLM APIs in v1.

---

## Key Decisions

- **Topic is aviation operations.** Extends the candidate's existing aviation narrative; differentiates from the saturated "doc-chat over generic PDFs" portfolio category; supplies genuinely interesting multi-tool questions a real persona would ask.
- **Architecture is a tool-use agent, not RAG-only or a chat wrapper.** Agents force integration of the engineering concerns ML engineer reviewers care about (tool routing, error handling, observability, evals), which single-purpose apps don't exercise. RAG is one tool inside the agent, not the whole product.
- **Evals are a first-class artifact, not a side experiment.** Most portfolio LLM projects ship without evals. Visible evals in CI are the single highest-leverage signal of production ML maturity available in the project.
- **Public data, public deploy, zero-friction demo.** Reviewers must be able to interact with the system within seconds of clicking a link, with no setup, login, or proprietary access.
- **Standalone from the Flight Delay project.** v1 success cannot depend on the older project's results being impressive. A future "linkage" project can connect them once each stands on its own.

---

## Dependencies / Assumptions

- Assumes commercial LLM API access (OpenAI, Anthropic, Gemini, or similar) is available within a modest self-funded budget (low tens of dollars for development plus ongoing demo-traffic costs).
- Assumes public aviation data sources remain accessible and reasonably rate-limit-friendly: BTS / DOT on-time performance data, FAA documents (AIM, ACs), NWS aviation weather products (METAR / TAF), and a public NOTAM search endpoint.
- Assumes the 2026 ML engineer hiring market continues to weight evaluated production LLM agents as a strong portfolio signal. Validated by current job descriptions; an explicit assumption rather than a proven claim.
- Assumes the candidate self-funds modest hosting (~$5–20 / month) and is comfortable with the project being publicly accessible.
- Assumes the candidate's existing skill set (Python, SQL, basic React / TS, Docker, AWS) is sufficient to execute the engineering surface; new learning (agent frameworks, eval frameworks, observability tooling) is expected and welcomed.

---

## Outstanding Questions

### Resolve Before Planning

None. All product-level decisions are resolved; remaining open items are technical or naming choices that planning can answer.

### Deferred to Planning

- [Affects R1, R2][Technical] Which agent orchestration approach? Vanilla provider-native tool-use APIs (Anthropic / OpenAI), a framework (LangGraph, LlamaIndex, Pydantic-AI), or a custom orchestrator. Trade-off: code simplicity vs feature surface vs lock-in.
- [Affects R2][Needs research] Final v1 tool list. Confirm which tools ship in v1 vs are deferred (e.g., should "explain a flight delay" be its own tool or an emergent pattern over base tools).
- [Affects R6][Technical] Where does historical flight data live at runtime? SQLite or DuckDB shipped with the repo, hosted Postgres, or parquet on object storage. Depends on dataset size after filtering and on deploy target constraints.
- [Affects R7][Needs research] Exact aviation document corpus selection. Which FAA AIM chapters, FARs, ACs, NTSB summaries, etc., make the v1 corpus — substantive enough to be useful, small enough to chunk cleanly and evaluate against.
- [Affects R8, R9][Technical] Eval framework choice (Inspect AI, Promptfoo, LangSmith evals, custom) and observability tool choice (LangSmith, Langfuse, Phoenix / Arize, custom).
- [Affects R11, R14][Technical] Hosting target — Modal, Fly.io, Railway, Render, or Vercel-plus-worker. Depends on cold-start tolerance, cost, and ease of background job support.
- [Affects R15][User decision] Final project name (working title: "Aviation Ops Copilot"; alternatives worth considering: "FlightDeck", "Captain", "ControlTower", "Ramp").
- [Affects R15][User decision] UI framework choice — Streamlit (faster to ship, less polish), Gradio (similar trade-offs), Next.js (more polish, more work).
