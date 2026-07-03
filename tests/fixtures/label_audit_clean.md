# Session 8 Handoff

Salesforce application status codes observed in the export:

| Code | Meaning |
|---|---|
| AD | Accepted Fully [verified: docs/references/sf_status.md:12] |
| RJ | Rejected by underwriter [HYPOTHESIS] |
| WD | Withdrawn by applicant [verified: docs/references/sf_status.md:14] |

## Key Decisions

| Decision | Resolution | Rationale |
|---|---|---|
| Token storage | httpOnly cookies | XSS protection vs localStorage |
