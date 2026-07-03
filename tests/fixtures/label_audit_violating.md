# Session 7 Handoff

Salesforce application status codes observed in the export:

| Code | Meaning |
|---|---|
| AD | Accepted Fully |
| RJ | Rejected by underwriter |
| WD | Withdrawn by applicant [verified: docs/references/sf_status.md:14] |

## Key Decisions

| Decision | Resolution | Rationale |
|---|---|---|
| Token storage | httpOnly cookies | XSS protection vs localStorage |
