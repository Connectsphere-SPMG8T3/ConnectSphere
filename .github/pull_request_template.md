<!--
Title: feat(area): what a user can now do (PBI ID)  ·  fix(area): what was wrong (Dn)
Keep every heading. A section that doesn't apply says "None." in one line.
Aim for about 1–2k characters for a fix and 3–5k for a story. CI shows test counts and the diff shows changed files, so leave both out.
-->

## <PBI ID> — <story title>

<!-- For a fix: "## Dn — <defect summary>" and the backlog's Bug fix PBI ID if there is one.
     2–4 sentences: what a user can now do, or what was wrong.
     Migration? Say whether it's already applied to the shared project, and when. -->

### Acceptance criteria

<!-- "Proven by" names a test class or TC ID. Never restate the implementation there.
     For a fix, replace the table with: What was wrong · Root cause · Fix · Regression test. -->

| AC | How it's met | Proven by |
|---|---|---|
| AC1 … | … | `TestX`; TC-XXX-001 |

### Decisions and changed requirements

<!-- Each one is also recorded in REQUIREMENTS.md and the PBI's Customer clarification or Notes column. -->
- QA-<row> / CR-<n>: …
- **[Assumption]** / **[Team decision]** …: why

### Design

<!-- Only for a new table, module, pattern or contract; otherwise "No design change."
     What and why, the alternative you rejected, and what it reuses (ADR-000n). -->

### Testing

- **Scenarios:** normal … · boundary … · conflict … · failure … · authorisation denial (active role) …
  <!-- Each with its TC ID or test. If a category doesn't apply, say why. -->
- **Coverage:** new and changed code fully covered, or the uncovered lines and why.
- **Recorded runs:** [API/DB](https://github.com/chasingsunsets/ConnectSphere/blob/<sha>/docs/test-cases/runs/<file>.md) · [browser](…) · [manual](…)
  <!-- Full blob URLs with a commit SHA. A relative link like docs/test-cases/runs/… breaks in a PR description. -->
- **Existing tests changed:** the test's name and the AC, QA row or decision that changed its behaviour. "None." if none.
- **Not verified:** … and why.

### Risk

<!-- Migration or shared-database change only; otherwise "None."
     Can it be undone? What else does it touch? Deploy order. -->

### For teammates

<!-- Contract changes other stories rely on, naming who is affected.
     Also add them to IMPLEMENTATION_MAP "Know before you build". "None." if none. -->

### Defects found, not fixed here

<!-- Dn: one line each, also in DEFECTS.md. "None." if none. -->

### Screenshots

<!-- Each page or state this PR changes; for a fix, before and after. Embedded here or posted in a comment below.
     Seeded or throwaway data only. Omit if nothing visible changed. -->
