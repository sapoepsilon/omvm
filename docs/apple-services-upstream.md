# Apple-services upstream plan

Keep the source consolidated in `sapoepsilon/omvm` while the owner runs the
[manual test](apple-services-testing.md). This document proposes the split for
later review; it is not an upstream submission or a production-readiness claim.

## Existing conversations

The broader VM work already has an
[Omarchy discussion](https://github.com/omacom/omarchy/discussions/18195) and an
[Omarchy Mac package proposal](https://github.com/omacom/omarchy-mac-pkgs/issues/107).
Use those existing threads after the manual results and contribution scope are
ready; do not create duplicate proposals. No new upstream message is part of
organizing this branch.

## Proposed split

| Change | Likely destination | Before submission |
| --- | --- | --- |
| omvm CLI, helper lifecycle, app integration and diagnostics | This repository | Manual results, focused contracts, complete installation and recovery instructions |
| New Mac-only runtime package / persistent Mac boot integration | [omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs) | Confirm scope through the existing proposal; one focused change with package/integration tests |
| Package recipes, source pins and publication | [omacom/omarchy-pkgs](https://github.com/omacom/omarchy-pkgs) | Buildable reviewed source, dependency licenses, reproducible package inputs |
| Shared desktop behavior or a generic platform hook | [omacom/omarchy](https://github.com/omacom/omarchy) | Demonstrate the core change independently of experimental Apple-service internals |
| SEP/AES/UID1 kernel work | [omacom/linux-aurora](https://github.com/omacom/linux-aurora) | Maintainer routing, full exact-kernel build, hardware review, logging/guard policy, suspend and ownership behavior |
| QEMU identity/mailbox/FairPlay changes | Relevant QEMU fork, starting from the [recorded source chain](../contrib/apple-services/prerequisites/README.md#qemu) | Separate coherent patches, clean configure/link, protocol tests and attribution |
| Linux FairPlay adapter | Its own pinned dependency / source project | Clean build, durable-state tests and explicit runtime asset boundaries |

These destinations are proposals based on the current source and published
project boundaries. They do not establish maintainer acceptance of the
experimental service design.

## Current contribution guidance

Repository metadata checked on 2026-11-14 shows `quattro` for Omarchy,
`integration/aurora` for linux-aurora, `main` for omarchy-mac-pkgs and `master`
for omarchy-pkgs. A default branch is not automatically a maintainer-approved
patch target; recheck the relevant instructions before preparing submissions.

The current [Mac package contribution guide](https://github.com/omacom/omarchy-mac-pkgs/blob/main/CONTRIBUTING.md)
routes Mac-only installed services and boot support to that repository, shared
desktop/platform interfaces to Omarchy, and recipes/publication to
omarchy-pkgs. It requests an issue before a new Mac-only package, focused PRs
against `main`, integration coverage where package/runtime interfaces change,
and cold-boot evidence for boot-critical releases. The existing package proposal
is the starting point for confirming where this work fits.

The older [upstream drafts](upstream-drafts.md) retain prior graphics work and
discussion history. Their old version numbers, local paths and posting plans
are historical context, not the acceptance record for this source checkpoint.

## Review gates

- [ ] Owner's manual desktop, messaging and normal-reboot results recorded.
- [ ] Complete kernel/QEMU/helper source builds reproduced outside active trees.
- [ ] SEP signer installation and private-input provisioning documented without
      bundling credentials, VM identity, Apple assets or checkpoints.
- [ ] Fresh artifacts reviewed against explicit provider pins; no validation
      bypasses or automatic re-enrollment.
- [ ] Raw SEP/QEMU diagnostics and the xART guard policy reviewed for deployment.
- [ ] Suspend veto, hardware lifetime and restart boundaries made suitable for
      the proposed integration, or accepted as explicit experimental limits.
- [ ] Dependency licenses and source attribution checked, including the existing
      [PAC patch distribution boundary](../LICENSING.md).
- [ ] Claims scoped accurately: CKV and first-attempt sign-in remain unfinished.
- [ ] Split into focused component changes and recheck each target's contribution
      rules before any external proposal or PR.

The kernel, desktop and helper pieces should not be submitted as one enormous
Aurora patch. A lifecycle or diagnostic improvement can be reviewed independently
if it makes no unsupported account, CKV or general-hardware claim.
