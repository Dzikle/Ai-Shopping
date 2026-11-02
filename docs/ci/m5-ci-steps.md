# Required CI workflow additions for M5 (owner action)

**Status:** Pending owner application.
**Reason:** the automated agent's GitHub App token does not carry the `workflows`
permission, so `.github/workflows/ci.yml` cannot be updated by the agent
(`remote rejected ... refusing to allow a GitHub App to create or update workflow
.github/workflows/ci.yml without workflows permission`). All M5 code, tests,
scripts and documentation are committed; only the three workflow edits below
remain for the owner (or a token/PR with `workflows` scope).

The M5 pieces already exist in the repository:

| Artifact | Path |
|---|---|
| MCP server package | `mcp_server/` |
| MCP contract tests (31) | `mcp_server/tests.py` |
| Milestone test script | `scripts/test-m5.ps1` |
| Tool contract | `docs/contracts/mcp-tools-contract.md` |
| Milestone proposal | `docs/milestones/m5-proposal.md` |

## 1. Docs existence check

In the `baseline` job, step **"Check required docs exist"**, add:

```yaml
          test -f docs/contracts/mcp-tools-contract.md
          test -f docs/milestones/m5-proposal.md
```

## 2. MCP unit/contract tests

In step **"Adapter, matcher & search unit tests (Python 3.12, stdlib only)"**, add
(working directory must stay `/w` so `mcp_server` is importable):

```yaml
          docker run --rm -v "$PWD:/w" -w /w python:3.12-slim python -B mcp_server/tests.py
```

## 3. M5 integration step

After the existing M4 step:

```yaml
      - name: M5 integration test (bounded read-only MCP server, tool contract, stdio transport)
        shell: pwsh
        run: ./scripts/test-m5.ps1
```

`scripts/test-m5.ps1` runs without `-ApiBase` in CI (contract suite + `v1` tool
snapshot assertions). To also exercise the live handshake
(`initialize → tools/list → tools/call(get_catalog_health)` compared with a
direct REST call), pass a running backend:

```yaml
        run: ./scripts/test-m5.ps1 -ApiBase http://localhost:8080
```

## Verification before applying

```bash
python3 -B mcp_server/tests.py        # 31/31 OK
python3 -B mcp_server/cli.py --list-tools
```
