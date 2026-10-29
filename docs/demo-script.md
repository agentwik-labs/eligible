# 60-second demo

Start the app (`uv run uvicorn eligible.api:app`) and open http://localhost:8000.

**0:00–0:10 · The question.** "Which lines on this receipt can an FSA or HSA pay for? The
rules are in IRS publications that contradict each other." Click **Pharmacy run**.

**0:10–0:25 · The answer.** Click **Check receipt**. Point at the total ("$122.76 of $275.71,
plus conditional items"), the highlighted receipt lines, and one card: "dual purpose, covered
only with a medical reason". Click a citation: "the actual IRS text, retrieved, not invented."

**0:25–0:35 · What it cost.** Scroll to **How this answer was made**: five steps, two model
calls, tokens and cost for each. "About two cents a receipt; Haiku reads, Sonnet decides."

**0:35–0:50 · How I know it's right.** Open **How it's built**. "98.2% accuracy on 441
labelled items, zero ineligible items approved, zero invented citations reaching a user,
zero verdicts changed by prompt injection." Point at the ablation: "retrieval failed at 53%;
following each rule's own citations fixed it."

**0:50–1:00 · Observability.** Open **Traces**: "every request, span by span; extraction is
55% of the time, which is the next thing I'd fix." Close on the repo link.
