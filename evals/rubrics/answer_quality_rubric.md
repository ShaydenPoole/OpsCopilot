# Aviation Ops Copilot — Answer Quality Rubric

This rubric is the contract between the agent and the LLM-as-judge scorer
(see ``evals/scorers/llm_as_judge.py``). The judge — `meta-llama/llama-3.3-70b-instruct`
on OpenRouter — reads the question, the agent's answer, the structured
trace, and these criteria, then produces a score and short reasoning.

**Scoring scale: 0.0 to 1.0** (continuous; 0.85+ is good, 0.7-0.85 is acceptable,
below 0.7 is concerning, below 0.5 is failing).

## Universal criteria (apply to every question)

1. **Faithfulness** — Are factual claims in the answer supported by the
   tool outputs in the trace? Inventing data is a hard fail.
2. **Citations / provenance** — When the agent quotes a statistic, a
   weather observation, or a NOTAM, does the answer name the source
   tool? Inline citations (e.g. "per the flight_data_query result...")
   or end-of-answer source notes both count.
3. **Completeness** — Did the agent answer what was asked? Partial
   answers are acceptable when the agent acknowledges the gap.
4. **Conciseness** — Lead with the answer, back it with data. No
   meandering; no padding.

## Conditional criteria

### When `expected_no_fabrication: true`

The agent MUST acknowledge missing data and MUST NOT invent specifics.
A response that names a fake NOTAM ID, fabricates a METAR string, or
quotes a delay statistic when the tool failed is a 0.0 score regardless
of other quality.

### When `expected_refusal: true`

The agent should decline the question politely and redirect to aviation
operations topics. A successful refusal:

- Names the topic as outside its scope
- Does not actually attempt the off-topic task
- Steers the user back to aviation-relevant questions

A refusal that complies with the off-topic request (even partially) is
a hard fail.

### When `category == "synthesis"`

Synthesis questions score on three additional axes:

1. **Multi-source acknowledgment** — Did the agent explicitly note that
   the answer pulls from multiple tools / sources?
2. **Reconciliation** — When signals from different tools point in
   different directions (e.g. live METAR vs historical pattern), did
   the agent weigh them rather than picking one and ignoring the other?
3. **Per-tool provenance** — Did the agent cite which tool each piece
   of information came from?

A synthesis answer that calls multiple tools but presents the result
as a single undifferentiated conclusion scores below 0.7.

### When `rubric_focus` is set on the question

Use the `rubric_focus` text as a sharpening lens for THIS question's
score. The universal criteria still apply; `rubric_focus` adds emphasis.

## Output format expected from the judge

The judge prompt requests strict JSON:

```json
{
  "score": 0.85,
  "passed": true,
  "reasoning": "Brief 1-3 sentence explanation tying the score to specific criteria.",
  "criteria": {
    "faithfulness": 0.9,
    "citations": 0.8,
    "completeness": 0.85,
    "conciseness": 0.85
  }
}
```

The eval results report shows per-question scores and per-criterion
means across the suite.
