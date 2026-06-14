# Security

## The one thing to know

**`charter check` executes shell commands defined by the repository under
test.** Assert enforcers in CHARTER.md are arbitrary shell. Only run `check`
in a repo whose CHARTER.md you have personally reviewed.

## The trust model

- A committed `.charter/charter.sha` proves *someone* approved the index —
  in a repo you cloned, that someone is the repo's author, who may not have
  your interests at heart. It is **not** a security boundary against a
  malicious committer (anyone who can edit CHARTER.md can also re-stamp the
  hash). It exists to catch *accidental* unapproved edits.
- Because of that, assert **execution** requires approval from your own
  machine: `charter approve` records trust in a per-user store **outside** the
  repo (`~/.charter/trust`, keyed by the repo's absolute path). Nothing a repo
  can ship — a committed sentinel, a forged in-repo marker, a tarball file —
  can stand in for it. A freshly cloned repo will not execute its asserts until
  you review CHARTER.md and approve it locally. (Earlier 0.4.0 betas kept this
  marker inside the repo, where a committed copy could forge trust; 0.4.1 moved
  it out of the tree.)
- CI is the exception you opt into deliberately: set
  `CHARTER_TRUST_ASSERTS=1` (or `check --trust`) only in CI you control, and
  treat a PR that modifies CHARTER.md with the same suspicion as a PR that
  modifies your CI workflow files.

## Data leaving your machine

`annotate` and `audit` send content to the configured LLM backend
(`CHARTER_LLM_CMD` or the Anthropic API): `annotate` sends your design doc;
`audit` sends the contents of files cited by or watched under supervise-tier
decisions. If those files contain secrets, they leave the machine. `check`,
`trace`, `graph`, `digest`, `explain`, and `doctor` never make network calls.

## Prompt injection

`audit` verdicts come from an LLM reading repo files; the prompt frames file
contents as untrusted data, but a determined injection in governed code can
still influence a verdict. Deterministic rungs (structure/type/test/lint/
assert) carry the real authority — supervise+audit is the advisory tier.

## Reporting

Open a GitHub issue for non-sensitive reports. For anything sensitive, use
GitHub's private vulnerability reporting on the repository.
