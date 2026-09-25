# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's "Report a vulnerability" (Security
advisories) on this repository rather than in a public issue.

## What unwedge is and is not

unwedge is a **cost and liveness guard**, not a security control. Its "gate" questions notice
tool output that talks to the reader (injected instructions, fake approvals); unwedge then stops
acting on that window's judgments and records the event in its ledger, but it does not warn the
agent or block anything, and a typed-decision model can itself be influenced by adversarial
text. Do not rely on unwedge to detect or block prompt injection.

## Data handling

- Commands and tool output are scrubbed of common secrets (API keys, tokens, JWTs, private keys,
  credentials in URLs, `password=`-style assignments) before they are stored or sent anywhere.
  Scrubbing is pattern-based and cannot be complete.
- With `provider=jev`, a clipped digest of the session (task, recent steps, latest output) is
  sent to TypeSafe's API in the US. With `provider=laya` or `none`, nothing leaves your machine.
- Session state lives in `~/.unwedge/` and is deleted after 7 days; the ledger keeps only
  decisions and numbers, not tool output.
- `unwedge serve` binds to 127.0.0.1 and refuses other addresses without a bearer key.
