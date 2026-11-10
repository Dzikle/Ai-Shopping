"""Assistant package: bounded guest shopping assistant (M13).

Layered as:
- providers.py  provider-neutral LLM adapters (mock + user-configured)
- coordinator.py grounded turn orchestration over the shared MCP tool registry
- rate_limit.py in-process bounded unauthenticated request controls
- (route wired in app/routes/assistant.py)

The model is only a language interpreter / explanation layer. It never invents
prices, identities, stock or totals: every numeric output in a response comes
from the allowlisted deterministic tools or is absent.
"""
