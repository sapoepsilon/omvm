# Apple services: review and testing

This is the starting point for the experimental Linux-hosted Apple-services
work in omvm. It connects the preserved source, observed results, manual tests
and proposed upstream split.

**Current stage: owner testing and source review.** The existing development
installation has completed Apple Account sign-in, a two-way iMessage exchange,
and another exchange after a normal host reboot with automatic Linux helpers.
That is evidence for one installed configuration, not a clean build/install of
this branch or support for every Apple Silicon machine.

## Next steps

1. Run the [manual checklist](apple-services-testing.md) on the existing lab.
   Begin with the desktop and messaging checks; retain the current account.
2. Record pass/fail results against the source revision and installed build.
   Keep raw logs, account details and machine state private.
3. Reconstruct and build the published source in separate checkouts, close the
   installation and runtime-policy gaps below, then test the resulting artifacts
   in a planned maintenance session with matched rollback state.
4. Prepare narrow changes for the destinations in the
   [upstream plan](apple-services-upstream.md). Complete manual testing before
   sending upstream changes. This branch is a review checkpoint, not a release.

## Status

| Capability | Existing development installation | Published-source acceptance |
| --- | --- | --- |
| Apple Account | Authenticated account and fresh service request observed | Fresh build/install not yet tested |
| iMessage | Outbound delivery and a new inbound reply observed | Owner manual pass pending |
| Normal host reboot | Shared Linux helpers auto-started; normal guest launch started its FairPlay helper; fresh messaging recovered | Owner manual pass and fresh-build reproduction pending |
| No Mac helper at runtime | Local Linux SEP/FairPlay sockets used | Verify installed artifacts/endpoints in each test |
| Keychain / Contact Key Verification | Encrypted-data trust unresolved; work deferred | Not supported by current acceptance claims |
| First-attempt sign-in | Diagnostic added; cause/remedy and clean flow unproven | Saved-log replay is not a sign-in test |
| Desktop / suspend | Desktop regression checks still needed; provider vetoes system sleep after activation | Not ready for general desktop deployment |

The runtime result used the reviewed M1 Max/J314c configuration, the pinned
`7.2.11-15vmapple-1-ARCH` kernel and a macOS 27.3 development guest. Broader board,
kernel and guest-version compatibility remains untested. Macs may still be used
for the initial Apple restore and source preparation; the runtime claim concerns
identity signing and FairPlay service execution on Linux.

## Source map

| Component | Source / guide | Review boundary |
| --- | --- | --- |
| CLI, app and domain integration | [`bin/`](../bin), [`share/libvirt-domain.py`](../share/libvirt-domain.py), [application guide](omac.md) | Keep desktop/app behavior separate from kernel changes |
| Helper lifecycle and libvirt gate | [`share/apple-helpers.py`](../share/apple-helpers.py), [`share/install-apple-helpers.py`](../share/install-apple-helpers.py), [`share/apple-helpers-hook.py`](../share/apple-helpers-hook.py), [helper guide](apple-helpers.md) | Shared SEP/UID1 startup, one active guest, on-demand per-VM FairPlay |
| Linux SEP signer | [`share/sep-identity-provider.py`](../share/sep-identity-provider.py), [`share/omvm-sep-identity.service`](../share/omvm-sep-identity.service) | Existing private signer configuration is an installation prerequisite |
| Kernel, QEMU and identity prerequisites | [reconstruction order](../contrib/apple-services/prerequisites/README.md) | Exact public baselines and dependent patches; separate kernel and QEMU reviews |
| Restore preparation | [upstream source delta](../contrib/apple-services/upstream-source-changes.patch), [auxiliary parser](../contrib/apple-services/scripts/extract-aux.py) | Factory-model defaults and auxiliary storage extraction; separate from Linux runtime helpers |
| Linux FairPlay adapter and UID1 provider | [source overlay](../contrib/apple-services/README.md) | Pinned dependencies, durable VM-bound state and board-specific hardware ownership |
| Sign-in phase diagnostic | [`share/omvm-auth-phase.py`](../share/omvm-auth-phase.py), [usage](auth-phase.md) | Read-only labels and timing; no automatic MFA retry or repair claim |
| Offline contracts | [`tests/`](../tests) | Fake services/signers and synthetic logs; no Apple account or hardware calls |
| Historical relay / AES diagnostics | [overlay component table](../contrib/apple-services/README.md#components-and-dependencies) | Research source, not required Mac runtime services or an activation recipe |

## What must be resolved before wider deployment

- **Fresh source builds:** reconstruction and syntax checks passed during source
  preservation; a full clean kernel build and QEMU configure/link from this
  published chain have not been accepted.
- **Complete installation:** the helper installer expects an already installed
  SEP signer, its private configuration, reviewed Apple cache, per-VM identity
  and provider inputs. A clone alone does not supply a working stack.
- **Reviewed artifact pins:** lifecycle validation deliberately accepts one
  reviewed kernel/module/diagnostic set. A new build needs an explicit review of
  its artifacts; editing hashes to bypass a mismatch is not a deployment test.
- **Kernel policy and diagnostics:** review the preserved xART guard change,
  raw SEP probes and QEMU identity dump logging before general deployment.
  Published source contains no captured values, but prototype runtime logs may
  contain private material. See the [prerequisite caveats](../contrib/apple-services/prerequisites/README.md).
- **Host integration:** the provider retains hardware ownership until a normal
  platform reset and vetoes sleep. There is no supported hot-unload/reset path.
  Decide the supported desktop behavior before offering it as an ordinary
  Omarchy package.
- **Attribution and distribution:** retain [licensing boundaries](../LICENSING.md)
  and verify the permissions of every upstream dependency before packaging.
  Apple software and private identity/checkpoint material are not release assets.

## Validation record

At source checkpoint `90a7837`, the consolidated offline command discovered 42
tests: **34 passed, 8 skipped** because their Linux ownership checks require root.
Shell syntax checks for `bin/omvm` and `bin/omac` passed. The ten sign-in observer
tests are included in that total. Earlier source-reconstruction checks are
recorded in the [overlay provenance](../contrib/apple-services/provenance.json)
and [prerequisite provenance](../contrib/apple-services/prerequisites/provenance.json).

These checks do not establish fresh hardware activation, account sign-in or
reboot recovery for binaries rebuilt from this branch. Use the manual checklist
to record a new run without replacing the earlier evidence.
