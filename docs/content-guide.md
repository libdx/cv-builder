# Content model and editing workflow

The pipeline is YAML → Pydantic validation → audience transformation → Jinja HTML,
Chromium PDF, or native Word export. There is no database or web editor.

| File | Owns |
| --- | --- |
| `data/cv_data.yaml` | Identity, contacts, profiles, education, consultancy, career records, selected inventory IDs |
| `data/inventory/attributes.yaml` | Skills, capabilities, languages, interests |
| `data/inventory/career-evidence.yaml` | Career statements, provenance, verification lifecycle, open questions |
| `data/inventory/practice-evidence.yaml` | Cross-career practices, evidence, disclosure |
| `data/policies/sidebar.yaml` | Sidebar section visibility, placement, detail, ordering |
| `data/policies/career.yaml` | Position/engagement representation, identity, placement, detail, ordering |
| `data/applications/*.yaml` | Public fictional tailoring examples |
| `templates/` | HTML structure and print CSS |

## Add a role

Give the career record a unique ID, company, title, location, `YYYY-MM` dates
(`present` is supported as an end date), employment type, and relationship.
`employment_type` describes capacity; `relationship` is `employment` or
`freelance_contract`. The latter drives the contracting label and freelance
engagement presentation.

Create evidence IDs beginning with `evidence.<record-id>.`. Set `career_record_id`
to that role ID. Choose `scope`, `responsibility`, `contribution`, or `outcome`.
Keep evidence atomic and include provenance. Verified evidence requires a
verification note; rejected/retired evidence requires a reason. Reference only
matching verified evidence from the career record. Unselected or unverified
items stay out of exports. This is a validation workflow, not an automatic fact checker.

The default freelance policy selects contract engagements and specific prior
roles. When replacing record IDs, update policy selectors and overlay references
as well. Unknown references fail validation. Generic policies apply in this order:
defaults, audience variant, freelance edition, application overlay.

## Tailor for a vacancy

Copy the example overlay to an ignored private path. Set its vacancy, target,
safe lowercase kebab-case `id` and `output_id`, optional headline/profile,
ordered sidebar selections, career evidence selections, and presentation rules.
Select cross-career practice IDs only when they are verified and approved for
external disclosure. Keep unsupported requirements as open questions rather
than introducing stronger claims in the headline or profile.

Run validation, build with `--application`, inspect HTML, then export the reviewed
variant. Engagement terms are retained for review and are not rendered. They
still need private storage. Inspect contact hyperlinks, chronology, sidebar
placement, and every PDF page. Page-fit regression tests describe this bundled
sample; substantial biography changes may require a deliberate layout adjustment.

## Manual Word editing

DOCX exports contain native paragraphs, tables, hyperlinks, and a repeating
header. They can be edited without this tool. YAML remains the source for future
builds; there is no DOCX import or round-trip synchronization.
