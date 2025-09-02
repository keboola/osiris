


# Milestones in Osiris

## Purpose
Milestones capture the **incremental, iterative development progress** of Osiris.  
Each milestone (e.g., M0, M1a, M1b, …) documents the scope, implementation details, and validation of a development step.

While **ADRs (Architecture Decision Records)** capture *why and how* architectural decisions were made, **Milestones** capture *what was delivered and when*.

## Methodology
- We use **milestone-driven planning**, with milestones representing incremental stages of delivery.
- Milestones are documented in this directory (`docs/milestones/`) as Markdown files.
- Each milestone document should describe:
  - The problem being solved
  - The implementation details
  - Validation/acceptance criteria
  - Status (planned, in-progress, complete)

## Relation to Changelog
Milestones are the **single source of truth** for the **CHANGELOG**.  
Before preparing a PR for merge into `main`, ensure that:
1. All milestone documents are up-to-date.
2. The changelog has been generated or updated based on these milestone documents.

## Workflow
1. Design decisions → recorded in `docs/adr/` as ADRs.
2. Incremental implementation → recorded here as Milestones.
3. Before merge into `main`:
   - Verify Milestones are complete and consistent.
   - Update the `CHANGELOG.md` from Milestones.
   - Only then proceed with the PR merge.
