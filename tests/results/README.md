# Test results (generated)

| Artifact | Produced by | Purpose |
|----------|-------------|---------|
| `athena-ui-audit.json` | `make test-ui-audit` | Structured UI audit + API snapshot |
| `athena-ui/screens/*.png` | same | Full-page screenshots per tab (gitignored) |
| `claude-review-ui-prompt.md` | `make claude-review-ui` | Paste into Claude Code |

Run a full loop:

```bash
make test-ui-audit && make claude-review-ui
```
