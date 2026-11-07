# Agent instructions

This is a standalone CV builder. Read README.md and docs/content-guide.md first.
Run commands from this repository root. Use a local `.venv`; do not install
packages globally. Generation is local and needs no LLM service.

## Content workflow

- The bundled Joe Doe biography is fictional. Never treat it as a real user's
  experience, evidence, achievements, contact details, or education.
- Ask the user for missing real facts. Do not invent employers, dates, metrics,
  titles, credentials, or verification. Preserve supported meaning when tailoring.
- Prefer data edits over changes to renderers or templates for content requests.
- Keep reusable statements in inventories, selections in `data/cv_data.yaml`,
  presentation in policies, and role-specific tailoring in sparse overlays.
- Use `candidate` for unconfirmed statements; promote to `verified` only with
  user confirmation, provenance, and a verification note. Do not confuse the
  fictional fixture's `verified` state with real-world verification.
- Private disclosure prevents rendering, not exposure in Git. Do not add private
  evidence, vacancy correspondence, commercial terms, or real personal data to
  the public sample. Keep private overlays in `data/private/` or outside the repo.
- Do not copy other repositories' history, assets, exports, research, or caches.
- Do not publish, submit applications, or contact employers without explicit instruction.

## Validation

After content edits, validate and build HTML. Review every intended variant;
an edition applies only to freelance. For code changes, run relevant tests and
the full suite before handoff. PDF tests require Chromium. Do not weaken page-fit
or evidence/disclosure checks just to make changed content pass.

```bash
python scripts/validate.py
python scripts/build.py --format html
python -m pytest
```

For exports, inspect every PDF page visually, check selectable text and contact
links, and inspect editable Word layout in the intended editor. Report checks
that could not run. Keep generated documents and environments out of Git.
