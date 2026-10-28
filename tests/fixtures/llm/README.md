# LLM fixtures

Responses keyed by `<prompt_name>-<first 16 hex chars of the request hash>.json`, replayed by
`ReplayClient` so unit tests never touch the network.

`smoke-*.json` is synthetic: it was produced by the fake SDK in `tests/conftest.py`, because M0
has no prompts yet. It pins the fixture format and the cache-key hash. Fixtures recorded from
real API calls arrive with the first prompts in M2 (`ELIGIBLE_LLM_MODE=record`).
