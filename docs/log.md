# Work log

- **2026-11-14 Fixed the Omarchy-readiness "must fix" review findings (branch omarchy/must-fix, offline only).** VM names validated everywhere and XML-escaped; persistent disks use cache=writeback with locking on the virtio-blk opens; experimental Apple services (identity=on, OMVM_MAILBOX, ID_*) are opt-in per VM via `omvm virt NAME --experimental-apple-services` (a VM already defined with identity=on keeps them), and the helpers' gate runs only for omvm-owned VMs; owner-specific defaults (guest user, Honeykrisp ICD paths, wayland-1, MacBook panel, sapoepsilon XML namespace, vmapple_runner key) replaced with configurable neutral ones, with the old namespace still read; `omvm virt rm` confirms, stops the watchdog and shuts down cleanly; the libvirt hook ships as /etc/libvirt/hooks/qemu.d/50-omvm and virt-manager URIs are appended, not overwritten; runtime root actions go through a validated pkexec `omvm __priv` entry point with static packaged udev rules; M1/M2 hardware gate and an interim warning plus confirmation on `omvm kernel default`; complete aarch64 PKGBUILD. No VM, libvirt, sudo or host configuration was touched; offline syntax checks and the 105 offline unit tests passed.

- **2026-11-14 Completed the two-VM account-service test and durable handoff.** Recovered the authoritative current Kentra local credential from two matching authorized Mac bootstrap records, validated once against the guest, and stored it in OS Secret Service; native Terra login then succeeded and pinned SSH confirmed both console users. Closed the source-recovery Mac SSH connection; all runtime helpers remained on Linux. Concurrent trusted-device-list requests at22:43UTC returned valid JSON, exit0, HTTP200 and cache_hit=false in both guests. Two live guests, two bound slots, no pending starts and healthy Linux helpers were verified before/after and at final audit. UID1 completed_ops stayed4, so this establishes existing-account service use, not live AES contention or simultaneous first-time sign-in. Preserved raw evidence privately at the latest-auth-test pointer; no credentials or account/device values were published. Stopped the completed native operator, verified no unused credential JSON, and left both desktops running. Updated and validated Apple-services and both VM-ops skills, including current native access and historical-state corrections. Synced public acceptance guides; draft PR2 remains stacked on PR1 for owner manual testing before upstream submission. CKV, first-attempt sign-in repair, Kentra messaging and two-VM host reboot remain unproven.

- **2026-11-14 Verified live two-VM admission and native display access.** Source63cb7cd now runs both guests through the normal gate with two exact v3 PID/start bindings, zero pending slots and healthy Linux helpers. A synthetic third-slot call to the installed gate was rejected before any guest creation/hardware work. Lab local login passed native and pinned-SSH checks. To expose Kentra to the existing native controller, saved its inactive XML and selected the lab-tested X11 SDL/Honeykrisp pair; verified unchanged domain UUID/QEMU args/other environment and cold-booted Kentra while lab stayed up. Both checkpoints remained separate; no provider reset. Kentra local login revealed ~/Work/macos-vm/guest-password.txt is a stale Nov8 password for an older VM, not this Nov13 guest; one GUI attempt and one explicit dscl check failed, so retries stopped. Original bootstrap credential provenance is being recovered read-only from the authorized source Mac. Fresh concurrent account requests remain pending. Private display backup and native reports stay outside the publication branch.

- **2026-11-14 Matched the real Omvm QEMU machine options.** The e53a77b started hook refused the normal property-only second machine clause, then libvirt shut the attempted lab launch down and cleared its reservation. Provider stayed READY; Kentra was never started. Applied exact source/test fix 63cb7cd to ignore property-only clauses while retaining duplicate/conflicting type refusal; all105 root offline tests pass. Both guests are off before helper replacement.

- **2026-11-14 Synced reviewed two-VM launch correction into the active CLI.** Applied the exact six runtime/test source files from clean feature tip e53a77b, preserving private operational history. The v3 gate binds started/begin to a stable QEMU PID/start after canonical PID-file/lock/UUID checks, so reparenting no longer double-counts a completed launch. Unbound/ambiguous records remain occupied. All104 root offline tests, seven independent focused review checks and CLI syntax passed. Both guests/helpers are off and the ledger is empty; the root helper/hook upgrade and new live test follow this source checkpoint. The complete source overlay, provenance and current public guides remain in ~/Work/omvm-two-vm.

- **2026-11-14 Began authorized two-VM Apple Account support.** Owner connected AC and authorized implementation/live testing after clearing the prior CKV goal. Created clean feature worktree ~/Work/omvm-two-vm and reconstructed the Go adapter from the published source. Source commit df38783 adds transaction flock, pinned client capabilities and conservative two-slot admission; 84 root fake-only tests, eight Go packages, focused race tests and exact patch reconstruction passed. Preserved matched offline guest/helper backups at before-two-vm-20261114T213519Z and installed new immutable binaries plus max_active_vms=2 without provider reset. First lab cold boot and helper/SSH readiness passed, but live QEMU reparenting to user systemd left its pending reservation counted separately, so no second guest launch was attempted. Cleanly shut down lab and stopped its helper; both guests/helpers now off, both stops successful, reservations empty. A reviewed started-hook process binding correction is in progress. Private installation receipt: /var/lib/omvm/apple-helpers/two-vm-install-20261114/receipt.json. Skills/native focus launcher updated for explicit two-VM scope; no operator launched or credentials submitted in this stage.

- **2026-11-14 Advanced isolated QEMU reproducibility without changing the lab.** Reconstructed public fd4794f in a new detached worktree under ~/Work/omvm-build-validation-20261114, matching30 integration files and prerequisite hashes. Fresh configure completed with KVM/Reims/GnuTLS/VNC; all seven identity/FairPlay sources are in its compile database and ninja dry-run resolves2314 steps. Existing Reims library reused; no full compile/kernel build/deploy or account change. Host was on battery with other active work, so heavy compilation was not started. Public documentation commit ae288dd and draft PR#1 record the exact scope; local docs/skill preserve the resume path. Owner explicitly answered that manual input/message testing has not started yet.

- **2026-11-14 Consolidated GitHub review and owner manual testing.** Published a component/status hub, manual checklist and Omarchy/Aurora submission plan as fd4794f on the existing source branch; draft PR sapoepsilon/omvm#1 targets main with no requested reviewers. Current upstream repository metadata and Mac-package contribution routing were checked, and existing discussion/proposal links retained. No upstream message, release, merge, account or host mutation occurred. Offline validation: 42 discovered, 34 passed and eight root-only skips; both CLI scripts passed separate shell syntax checks. Documentation links and privacy review passed. Synced the reviewed documentation locally while preserving the different private README, and updated the private skill to prioritize the owner manual pass, keeping CKV deferred and fresh-source builds/first-attempt sign-in explicitly unproven.

- **2026-11-14 Added a read-only sign-in phase observer; CKV deferred by owner.** The standalone parser separates secondary/account authentication from later local-password/CDP recovery, requires a timezone-aware capture boundary, and emits only allowlisted labels/timestamps/typed codes. Ten synthetic tests cover phase separation, historical-event exclusion, textual no-error handling and private-payload suppression. Replay of five saved evidence sets reproduced the distinct authentication/recovery stages without a new account request. This is diagnostic groundwork, not a proven first-attempt repair; clean-flow acceptance remains pending. Updated the private skill to honor CKV deferral and use the observer with current native-screen/request correlation. Simulator runtimes were inventoried read-only on the source Mac; trusted CKV support remains unverified and no simulator was booted or signed in.

- **2026-11-14 Confirmed CKV's actual encrypted-data prerequisite screen.** Read-only native navigation reached Contact Key Verification. Parent reviewed the actual01:33:52 frame and its VoiceOver caption: account settings must be updated for this device to use end-to-end encryption. No separate managed-account or OS-version error was displayed, but later prerequisites remain untested. No CKV/sync toggle, credential submission or recovery retry occurred. The temporary host redraw width was restored. Awaiting the trusted-device type to select a supported device-side trust/escrow diagnostic; completed messaging and reboot results are preserved.

- **2026-11-14 Refined the Keychain failure boundary from saved evidence.** The completed renewal flow's SecureBackup account-info results at00:27:28 and00:29:02 explicitly say no error; the earlier parser only checked null/domain-code patterns and missed that success wording. The earlier EscrowProxy401 was therefore not reproduced after renewal. Empty-cache fallback did check Cuttlefish yet still returned no recoverable records/devices, and Octagon remained Untrusted. Saved boolean templates also report no configured Octagon recovery key in that attempt. These findings do not justify another password renewal, cache reset or backend patch. Existing private reports/skill were corrected; no live account request or mutation was made for this analysis. A bounded read-only native CKV-pane inspection is in progress to obtain its exact prerequisite message.

- **2026-11-14 Completed post-reboot iMessage send/receive acceptance.** The owner confirmed a new reply, backend logs show fresh incoming encrypted iMessage processing at01:22:29–30, and parent independently inspected the readable01:23:47 native frame showing the requested reply below the outgoing test in the same conversation. Combined with the verified normal reboot, automatic shared/per-VM Linux helper startup, preserved state and fresh authenticated Apple request, this completes authenticated messaging recovery without a Mac runtime relay. Keychain/CKV remains unresolved and first-attempt sign-in reliability remains unproven. The prior mostly black capture was explicitly rejected as evidence; no message was resent. Current skill/evidence handoff preserves completed acceptance.

- **2026-11-14 Confirmed post-reboot outgoing iMessage delivery.** After the native tool required action-time confirmation, the owner approved the exact prepared test. An incidental Force Quit dialog was safely canceled, and one Return submitted the message at01:17:31. Parent observed its blue iMessage bubble and empty composer. Private in-memory GUID correlation confirms matching iMessage delivery receipts with success=YES at01:17:34 and a matching read receipt at01:18:22; identifiers and payloads were discarded. A fresh incoming reply remains pending, separate from old content. Keychain remains Untrusted despite owner-confirmed same-account trusted-device syncing without warnings; one read-only AuthKit trusted-device-list request succeeded but does not resolve Octagon recovery. A diagnostic developer-tool shim requested installation unintentionally; no install was approved/performed, and native observation will cancel any visible prompt. Updated the private skill with these limits and UI coordination corrections.

- **2026-11-14 Verified automatic Linux-helper and authenticated recovery after a normal host reboot.** The next-boot-only vmapple selection reached the pinned kernel. Host audit passed before manual guest/helper intervention; shared UID1/SEP started automatically. Starting only lab through normal session libvirt automatically started its static FairPlay instance. Guest audit passed unchanged identity/checkpoint/provenance, local endpoints, expected build/clock and kentra off. One saved local-password submission unlocked the desktop and its private input was deleted. A newly signed device-list request explicitly fetched from Apple servers and completed HTTP200 at01:05:37. Preboot iMessage exchange remains accepted; a new postboot exchange is being tested separately. Octagon remains Untrusted and CKV unfinished. Updated the private skill handoff; no account reset, re-enrollment, provider reset, public-history push or permanent boot-default change.

- **2026-11-14 Corrected the reboot-test kernel selection.** The normal reboot reached a new host boot, but the owner selected the existing stock aurora kernel. Read-only audit confirmed the wrong kernel and failed shared helpers while all private identity/checkpoint/configuration comparisons passed; both guests stayed off. Explained the existing vmapple kernel requirement and preserved the stock fallback. Selected the actual firmware-advertised vmapple entry for the next boot only with bootctl and verified readback. Coordinated continued hold of unrelated host jobs. A second normal reboot is next; authenticated recovery is still unverified.

- **2026-11-14 Prepared the authorized host-reboot acceptance test.** Normal account-update UI was reached through temporary stock VoiceOver Item Chooser; VoiceOver and host geometry were restored. Fresh passwordless SRP/IDMS requests succeeded, but one matching local approval again ended with zero viable escrow records and unresolved encrypted-data trust. The attempt is terminal and all native credential inputs are deleted. Other host work was checkpointed and paused through the VM-ops coordination pane. Guest sudo required its saved local credential, passed only over stdin to fixed shutdown. Both guests then shut down cleanly; managed helpers stopped afterward, and matching offline reflinks, identity/XML and root-private checkpoints/configuration were verified under one UTC stamp. Next kernel and external-key metadata were rechecked without reading key contents. Reboot and authenticated recovery remain unverified; durable handoffs/read-only audit scripts are prepared. Original v22 volatile rollback state will be lost on the authorized full reboot.

- **2026-11-14 Keychain approval reached a concrete trust-recovery failure.** Owner explicitly answered the prepared cloud-data confirmation and reiterated completion without redundant permission requests. Native input found the normal local-Mac password prompt already open and submitted the matching saved credential once; private handoffs were deleted. The local-secret stage completed, but recovery fetched no viable escrow records, repair returned false, and the native switch returned Off. Read-only Octagon status remains Untrusted. The framework posted its normal account-update follow-up; native inspection of that notice is underway. No repeated toggle, account reset, signout, helper restart or reboot occurred. Existing Apple Account and iMessage acceptance remains valid. Skills now record current authorization and the failed stage so resumption does not repeat the same approval/password cycle.

- **2026-11-13 Reached the native Keychain sync control.** One authorized local unlock succeeded and its private input was deleted; independent console state verifies unlocked. A bounded display-awake assertion prevents idle-lock interference without persistent preferences. Native keyboard search reached the iCloud overview (PasswordsOff, MessagesOn), then the iCloud Passwords & Keychain sheet with Sync this Mac off and focused. Parent inspected the actual images and corrected an overly broad black-frame interpretation where the full foreground pane remained visible. The dedicated native operator stopped before toggling under its action-time cloud-data access policy; owner confirmation was requested for that concrete control. No sync change, Apple password/MFA retry, account reset or reboot occurred.

- **2026-11-13 Identity source preservation completed for the audited scope.** Independently reviewed prerequisite patches reconstruct the earlier SEP changes and QEMU build/register wiring without personal data. Compiler/parser, provenance, exact-credential and whitespace checks passed. Public follow-up d3558bb was pushed to the existing apple-services-source-20261113 branch with public/noreply metadata; remote SHA and clean worktree verified. Experimental source behavior remains explicitly documented and was not activated. The skill now has a concise current handoff with the old timeline archived separately. Apple Account/iMessage acceptance stands; Keychain/CKV, first-attempt reliability and host-reboot recovery remain incomplete, with the native operator idle for the requested owner UI handoff.

- **2026-11-13 Published a reviewed source checkpoint without private operational history.** Owner requested preserving the existing Mac work in the existing project and explicitly excluding personal information. Original remaining changes were committed locally; a clean source snapshot based on public origin/main was independently reviewed and pushed only to apple-services-source-20261113 as17ad9fa, with public-login/noreply author and committer. Remote SHA matches. The58-path snapshot includes the application, Linux helper lifecycle, identity/FairPlay/provider source and v23 durable-state patch; provenance/license notices and generic docs replace private operational histories. Offline tests, source reconstruction, patch application and compiler/syntax checks pass within documented platform limits. Additional prerequisite SEP/QEMU source gaps are being preserved separately. Native atomic-focus keyboard navigation reached the System Settings menu item, but stale/black capture prevents reliable Settings inspection; operator is idle for the requested owner UI handoff. No credentials, helper resets or reboot occurred.

- **2026-11-13 Preserved the Apple-services source checkpoint.** Committed the existing ID_BO4 domain-generator default, retained explicit environment overrides, and removed a hardcoded streaming-host address from the GUI fallback. The GUI now reports an unavailable address when Tailscale discovery fails. Source publication is prepared from the existing public base with reviewed code and general documentation only; local operational history and account evidence remain private. Offline lifecycle/provider tests pass (32 tests, eight root-only skips); synthetic domain XML verifies the default and override without touching a VM.

- **2026-11-13 Owner confirmed iMessage send and a new inbound reply on the Linux-hosted lab.** Recorded both directions as owner-observed acceptance, supported by earlier IDS com.apple.madrid registration success; native screenshots have not independently captured both bubbles. Live domain inspection confirms local SEP/FairPlay Unix sockets and active Linux services, with no Mac relay at runtime. Native troubleshooting verified QEMU button receipt and restored all input tracing, corrected the private credential-handoff schema and allowed in-task verified focus recovery; one local unlock then succeeded, with private input deleted. Keychain timeline now establishes zero viable recovery records before the local-password prompt, so that password did not cause the initial failure. Normal trusted-device approval remains the next test; no speculative permission repair/reset, Apple sign-in retry or reboot occurred. A GitHub backup audit found105 unpushed main commits, additional helper history/branch work, dirty source and unversioned skills/launchers; a private local source backup is being prepared, with no remote publication yet.

- **2026-11-13 Supervision caught an unsupported native screen report.** The parent's direct image review found that Terra described the earlier Messages introduction while its current native capture was mostly black. Terra corrected that report. Following the documented guest display-wake command, two read-only captures showed the introduction and then a mostly black frame; both were reviewed and preserved privately. Capture inconsistency remains separate from unproven input delivery. Bounded logs additionally confirm IDS registration and callback success for com.apple.madrid at22:14:57UTC; actual message exchange, Keychain/CKV and reboot acceptance remain outstanding. Native input is idle for the pending owner manual-click comparison; no credentials were retried or messages sent.

- **2026-11-13 Added actual Terra supervision and verified operator focus.** At the owner's request, the private service skill now requires parent review of native screenshots/actions every3–5 minutes and immediately on errors. Added a tested transcript-image review helper and a verified lab/operator workspace5 focus helper; the dedicated launcher runs the latter and tasks check focus before input. This corrected observed host placement/focus drift, but a later click and Return still did not dismiss the Messages introduction. Source already accounts for letterboxing, and X11 geometry matches native screenshot pixels; no coordinate patch is justified. Messages has reached its introduction after one credential submission, but activation/delivery remain unverified. A bounded sample finds its main thread idle in the event loop. The earlier Apple Account extension exit is identified as SIGTERM with unknown sender/trigger. Preserved private reports and updated the skill; no guest/helper restart, account reset or message send occurred.

- **2026-11-13 Account authentication completed; first-attempt reliability added to goal.** The owner explicitly expanded acceptance to fix repeated MFA/final-password behavior. A bounded independent timeline shows secondary auth succeeded at21:47:38UTC, authenticated account HTTP200 at21:48:01UTC, and primary account addition at21:54:01UTC; the later incorrect-code alert does not establish initial-MFA failure. Native overview at22:03:09UTC confirms sign-in. The final prompt requested this Mac's local password; one native submission advanced into CDP recovery, which found no escrow records and ended with -5305/-5308 before allowing sign-in to continue. A separate single private dscl authonly check validates the saved local credential. iCloud still shows Loading; a VM feature-limit notice is observed but individual service behavior remains to be tested. Saved sanitized templates, codes and UI reports, updated acceptance/skill, and started a bounded Messages activation task. No account/keychain reset or guest/helper reboot occurred; first-attempt cause/remedy, Messages, CKV and host-reboot acceptance remain open.

- **2026-11-13 Recorded SMS and final-password preferences; prepared local recovery.** At the owner's request, updated the service skill to prefer SMS MFA, accept either a privately relayed chat code or direct owner entry, allow a bounded resend with fresh input after delay/rejection, and inspect/complete an explicit final post-MFA Apple Account or this-Mac password prompt. Native read-only evidence first showed a rejected-code alert, then an already active SMS attempt with entered code/spinner; these operators submitted no code or resend and do not establish the rejection cause. A bounded final-password native task is now active. Saved the previously verified original local-login credential in Omarchy's OS keyring and removed its temporary recovery file, so later unlock needs no source Mac lookup. Read-only reboot preflight confirms the pinned next-boot kernel matches its installed image, external-key unlock is configured, manifest validates, shared helpers are enabled, managed FairPlay is on demand, and obsolete/current guest watchdogs remain disabled/inactive. Saved the private baseline; no reboot or runtime restart occurred.

- **2026-11-13 Lab sign-in reached trusted-device verification.** The single owner-confirmed native credential submission produced stock akd Successful SRP! at21:43:59.749019UTC and the verification-code prompt at21:44:28UTC with no visible error. No MFA was submitted; the owner was asked to enter it directly in the visible VM. The private temporary input JSON is deleted, and the authorized OS keyring entry persists. Sanitized UI/authentication metadata is retained privately. Apple Account completion, Messages, CKV and host-reboot acceptance remain unverified; no password retry or helper restart occurred.

- **2026-11-13 Verified visible Terra control and local desktop login.** Resumed the dedicated native CLI as GPT-6.1 Terra, using the owner-requested per-invocation --yolo and installed computer-only CUA runtime. Matching the app-managed trusted module path resolved the custom-launcher discovery error without altering package code, global policy or access checks. Native screenshot/click/type/clear succeeded; one private original-credential submission reached the lab desktop at21:33:26UTC, independently confirmed by pinned SSH console/Finder/Dock checks. VM and operator are visible together on workspace5. The temporary local-login secret was deleted. The owner separately confirmed the lab Apple Account and requested password storage; OS keyring storage/read-back verification succeeded, and a bounded private sign-in task is underway. Updated the service skill and removed stale native-control blockers from current docs. The source snapshot evidence wrapper was sanitized after finding a hardcoded local credential, with transformation/checksums recorded privately. No guest/helper restart, provider reset, host reboot or push occurred.

- **2026-11-13 Located the existing native computer-use session.** Following the owner's native-app recollection, verified the separate computer-enabled Sol CLI is still running and preserved its five launcher/task files with matching SHA256 in the private groundwork directory. The installed public CUA documentation supports its computer-only mode; this chat's failed Terra probe does not establish that separate client's capabilities. No discovery result exists; the latest handoff records an MCP permission prompt, whose current screen was not inspected. Also identified the Mac's OMVMNativeControl apps as Virtualization-framework test-VM hosts, not established Linux control bridges. Updated the private service skill with exact artifacts and these distinctions. No session was relaunched, approval accepted, VM changed or credential entered.

- **2026-11-13 Terra native-control probe and login-source handoff recorded.** At owner request, a GPT-6.1 Terra worker performed fresh approved computer-use discovery; it exposed no apps/browsers and reported the browser host unavailable, matching the prior Sol limitation. Native VM control remains unverified. Updated the private service skill with the Terra preference and evidence. A bounded read-only Mac source check identified the original local-login bootstrap environment-variable name; no stored password was recovered, exposed, guessed or reset. Existing lab public-key SSH remains available; no guest, account, provider or display change occurred.

- **2026-11-13 Owner-authorized switch from kentra to omvm-lab completed.** Under both VM operation locks, requested a clean kentra shutdown through its pinned SSH connection and waited for shut off before starting the lab through normal session libvirt. Fresh pinned SSH verified 27.3/26C5035r at21:08UTC, and compositor inventory showed the native Reims XWayland window mapped. Inactive domain/profile hashes and managed/original-v22 helper PIDs stayed unchanged; both guest watchdogs remain disabled. Updated both skills and local discovery copies with the explicit switch authorization and resulting state, superseding the earlier no-shutdown interpretation. No enrollment, account input, host reboot or GitHub push occurred; both locks were released after checks.

- **2026-11-13 Recovered Mac groundwork and established the lab service skill.** Verified trusted SSH to the source Mac and confirmed its clean omvm revision already exists in the newer local history. Imported 27 selected source/notes/original-skill files into a private local snapshot with matching remote SHA256 receipts; no checkout or private runtime asset was overwritten. Created the focused omvm-apple-services skill with separate authentication, messaging, CKV and host-reboot acceptance, then reconciled all three local VM-operations skill copies with the newer lab evidence. Recorded the owner's explicit kentra protection, disabled-watchdog launch path, unavailable native control surface, and loss of the old in-memory v22 rollback control on a future host reboot. Skill validation and read-only behavioral review passed. Kentra remains running, the lab stopped, helper PIDs unchanged, and the pre-existing domain-generator edit preserved; no service/account test, reboot or GitHub push occurred.

- **2026-11-13 Returned Kentra while native control awaits permission.** The remote Sol CLI remains at its one-time native MCP tool permission prompt. Cleanly shut down the lab without changing its X11 configuration, disks or independent managed state, then requested the existing coordinated worker to return Kentra. It verified unchanged domain/profile, started Kentra normally, checked pinned SSH on27.2.1/26B131 and released both locks. A second pinned SSH check after worker exit passed; the development pane was notified. No Apple password/MFA attempt or host/provider reboot occurred. Further lab input requires a fresh coordinated slot and native-window verification after the permission is resolved.

- **2026-11-13 Native X11 cold boot retains push-service health.** A bounded read-only check after the display switch verified pinned guest SSH on27.3/26C5035r, production APNs connected, two BAA certificate acquisitions, one host VM nonce signature and zero recorded BAA failures in this boot. Sanitized evidence is retained privately under the lab evidence/after-x11-20261113 directory. This verifies the tested guest cold-boot push path, not Apple Account/Messages acceptance or full host-reboot recovery. Native CUA remains at its one-time session permission prompt.

- **2026-11-13 Reconciled helper deployment documentation.** Live systemd inspection confirms the shared provider and SEP signer are enabled, both managed FairPlay instances are static/on-demand, and both guest watchdogs remain inactive. Corrected the stale installation section that still described the already-deployed policy as source-only. This inspection does not replace the pending real host-reboot/account acceptance test; no unit or guest changed.

- **2026-11-13 Lab native X11 boot verified.** Under the existing coordinated VM locks, retained the current Wayland XML, shut down the lab cleanly and changed only its Vulkan driver prefix plus SDL3 X11/DISPLAY environment. The independent X11+Wayland Mesa build uses the same verified patched source; all non-display XML, VM profile and Kentra configuration remained unchanged. Normal libvirt boot reached pinned SSH on27.3/26C5035r, and Hyprland confirmed exactly one Reims XWayland window owned by the lab QEMU. No VNC or Mac relay is involved. The separate remote Sol CLI reached its native MCP tool approval prompt; discovery and actual native input await that session permission. No account password or MFA was submitted. Kentra remains off within the owner-released slot; clean return is still required.

- **2026-11-13 Prepared an isolated X11 native renderer and remote Sol operator.** Live Hyprland inventory confirmed both the OMVM manager and Reims display were native Wayland windows, not XWayland. Copied the existing patched Mesa source into a separate lab tree, verified matching source revision and patch hash, and built/installed X11 plus Wayland WSI with four compiler jobs into a new private prefix. Existing drivers, QEMU and Kentra configuration were untouched; build receipt and library hash are retained beside the new source. SDL3 exposes its X11 backend. Prepared an isolated GPT-6.1 Sol CLI with the installed public computer-only CUA launcher and actual graphical-session environment; fixed its initial heredoc/TTY launch plumbing. Direct native discovery, X11 lab boot and input remain acceptance checks. VNC and local Moonlight remain retired.

- **2026-11-13 Returned lab to native OMVM display at owner request.** Closed the separate agent's headless browser and stopped the noVNC static service plus all three task-owned SSH forwards. Under the existing coordinated slot locks, cleanly stopped the lab, preserved its VNC XML and converted only its display back to native Reims 3024x1964@254. Normal boot reached pinned SSH on27.3/26C5035r; identity, disks, helper attachment and kentra domain were preserved. VNC input had lost case/shifted symbols, so no Apple password was submitted. The lab's built-in Accessibility Keyboard was enabled and a nonsecret A@2.Z mouse-entry test succeeded before the owner ended that approach. A separate Linux GPT-6.1 Sol worker is investigating direct native window control; opening the ChatGPT app was a misunderstanding of "native app" and does not establish that capability. Apple Account/Messages/CKV and full host reboot acceptance remain outstanding. Kentra is still cleanly off during the owner-authorized lab slot.

- **2026-11-13 Isolated lab helper enrollment and browser VNC route.** After owner authorization and development-pane release, cleanly stopped kentra and retained matched offline guest/public-artifact backups plus its quiesced managed checkpoint. Enrolled omvm-lab once with its own actual UUID and empty state; deployed the reviewed on-demand per-VM startup policy. Both helper starts reached READY with separately retained checkpoint copies; kentra's checkpoint stayed byte-identical, and its domain/defaults, the original v22 rollback helper, SEP and pinned UID1 provider were preserved. Converted only the lab display to loopback VNC/WebSocket. Initial VNC launch exposed broken custom-QEMU keyboard-map symlinks; preserved the directory and installed 35 hash-verified regular QEMU-source maps in the existing data directory, without replacing QEMU or Apple firmware. Lab subsequently booted through normal libvirt to pinned SSH on 27.3/26C5035r with unchanged actual UUID and -0.2s clock skew. Official noVNC v1.6.0 is served on loopback through SSH; a separate GPT-6.1 Sol task verified headless browser screenshots and logged into the local lab desktop through VNC. QEMU requires WebSocket path /; noVNC 1.6 needs path=. to avoid its leading-slash double-slash behavior. Post-helper cold-boot APNs also passed: production connected, two BAA acquisitions, one host VM nonce signature and zero BAA failures in current-boot logs. Apple Account/Messages/CKV and full host reboot acceptance remain pending. Kentra remains off only for this coordinated slot; no host reboot/reset occurred.

- **2026-11-13 Fresh 27.3 lab clears the push-certificate hurdle on Linux.** Completed stock local Setup Assistant in independent omvm-lab with Apple Account skipped, enabled Remote Login, installed the runner public key and pinned the guest SSH host key. Verified 27.3/26C5035r, SetupDone, sub-second clock agreement and an actual IOPlatformUUID distinct from kentra. First-boot sanitized logs contain two BAA certificate successes, one host VM nonce signature, production APNs connected and received push tokens, with no recorded BAA failure. This establishes push-service progress; separate FairPlay enrollment, account sign-in, Messages and CKV remain pending. Lab shut down cleanly. The first kentra return boot reached SSH then shut down ten seconds later for undetermined reason; a normal restart remained reachable over repeated pinned SSH and was explicitly returned to the development pane. Host/helper processes and kentra identity/profile/build stayed unchanged. Future lab work requires a new coordinated guest slot.

- **2026-11-13 Independent omvm-lab restored and staged shut off.** Downloaded the official 27.3/26C5035r IPSW, restored a new native factory identity and blank disk, and verified stopped completion without a native Setup Assistant boot. The compressed sparse transfer verified its paired disk/auxiliary/profile receipt. Staged separate reflinks and a 4CPU/8GiB native session-libvirt domain with its own distinct ECID, native default serial and network address; only same-physical-host public SEP certificate files were reused. No signed-in account state or FairPlay checkpoint was copied. Lab remains shut off without FairPlay until local setup and actual guest UUID capture. Kentra domain, running state, watchdogs and saved launcher defaults were unchanged. The pinned 27.2-era booter is an unverified 27.3 compatibility candidate; Linux boot, APNs/Messages and reboot acceptance remain pending.

- **2026-11-13 Prepared on-demand per-VM helper startup.** Source audit found that enabling every enrolled FairPlay instance at boot bypassed the existing one-guest startup lock; an idle-READY check can fail during overlapping hardware use. This is a startup gap, not proof that ordinary helper initialization performs an AES transform. The installer now enables SEP/UID1 prerequisites only and removes old/current per-VM boot links without --now; static helper instances still start automatically through the existing libvirt gate and readiness check. Independent review found no blockers. Real systemctl --root migration removed only the selected old boot links; systemd unit validation and all 18 lifecycle tests passed. Source committed for the stopped-guest lab enrollment window; not yet deployed, and kentra/helper/provider processes remain unchanged.

- **2026-11-13 Resumed service work in a separate lab.** Recorded the owner's updated goal to preserve kentra and create omvm-lab with independent restored identity/disks and managed-helper state. Both hosts passed resource/power checks; kentra remains the only running Omarchy guest. Started an official 27.3/26C5035r IPSW download for a fresh restore, avoiding the previously failed in-place upgrade handoff. Lab creation, Linux boot, APNs/Messages, Contact Key Verification and host-reboot acceptance remain pending. Added the lab acceptance sequence and retained the separate deferred Keychain-sync scope. No kentra/helper/provider or boot configuration changed.

- **2026-11-13 Private VM skill updated for retained kentra.** Updated and reconciled the local omvm-vm-ops skill and all three Omarchy discovery copies. Live commands and helper paths now select kentra; the skill records retired guests, preserved shared dependencies, matched rename backups, verified signed-in desktop and deferred beta/Keychain work. It distinguishes the unrelated UTM kentra and retains the unverified full-host-reboot boundary. Frontmatter, relative references and matching-copy checks passed.

- **2026-11-13 Retained development VM renamed to kentra; other Omarchy VMs removed.** At the owner's request, cleanly stopped macos-fresh, saved a matched offline guest/helper backup, and renamed its domain, directory, managed service/socket/state, manifest key and staged identifier to kentra. Apple/platform and libvirt identity, checkpoint bytes, disks and SSH port were preserved. The cold boot reached SSH on macOS 27.2.1/26B131, Xcode reported 27.2/27B52, and the native desktop showed the existing signed-in Apple Account. No new credential/MFA attempt, provider reset or host reboot occurred. Deleted stopped macapps, macos, macos-modern-net and macos27, their isolated backups, obsolete native-comparison copies and cancelled transfer. Retired the old macos27-v22 helper, stale per-VM Sunshine configuration and verified obsolete clipboard watchers. Only kentra remains defined/running; actual free-space gain was about 237 GiB. Kept current-VM backups, restore templates/provenance, the original fresh-v22 control and all shared runtime assets, including the misleadingly named shared identity/macos SEP key directory. Watchdog/autostart remain disabled.

- **2026-11-13 Saved launcher defaults follow the retained VM.** The CLI and GUI now honor saved OMVM_VM with explicit environment precedence; the GUI loads preferences before choosing its VM, including when every guest is off. omac reads saved OMAC_VM/OMAC_SOURCE, and GUI installation preserves those preferences. Configured all three local defaults as kentra. Missing config remains nonfatal. Bash/Python syntax, focused saved/missing/override and GUI-fallback checks, the existing headless GUI self-test and diff checks passed. Updated current helper documentation and TODO target while retaining historical evidence and deferred beta/Keychain work.

- **2026-11-13 Beta attempt returned to the original OS; development VM retained.** The owner-approved 27.3 installer completed preparation/apply, but Messages blocked its initial restart. After the owner handed over the desktop, a normal guest reboot returned 27.2.1/26B131; the updater records Failed Backward and target-manifest mismatch. The boot-handoff cause remains unproven, and no beta APNs success is claimed. Stopped the observation job and released the VM lock after the owner prioritized development. The VM and original managed-helper process remain running; Xcode27.2/27B52 responds using its full developer directory. No further installer attempt, firmware change or host reboot is planned now.

- **2026-11-13 Deferred iCloud Keychain recovery investigation.** Recorded the owner-reported Passwords & Keychain sync failure in docs/TODO.md. Bounded logs show account authentication succeeded, but CDP recovery did not establish encrypted-sync trust membership and the daemon explicitly kept sync disabled. The cause and relationship to APNs remain unproven. At the owner's request, no sync retry or repair is being performed now.

- **2026-11-13 Removed an obsolete VM boot race.** The old macos service and watchdog timer were enabled despite being inactive. Disabled both and verified disabled/inactive, leaving only macos-fresh running with its own watchdog/autostart off. This prevents the old guest from claiming the single experimental-helper slot after a host reboot. Read-only inspection of the actual next-boot UKI also confirmed the pinned vmapple kernel and configured external-key LUKS auto-unlock; manual disk unlock is not an inherent requirement, but a new full reboot remains untested. No running guest or helper was restarted.

- **2026-11-13 Owner-approved 27.3 beta APNs experiment started.** After explicit acceptance of the separate pre-release licence, rechecked the matched offline rollback, unchanged domain/identity, active managed helper, AC power and available guest/host resources. Launched the verified startosinstall executable for an in-place 27.3/26C5035r upgrade using the local volume-owner credential through private stdin. Preparation reached 9.7 percent with the installer process live. The existing QEMU and Linux helpers remain running through internal updater reboots; no host reboot, account retry or security-policy change was made. OS completion, APNs/Messages and Contact Key Verification remain unverified.

- **2026-11-13 Temporary recovery-test capture settings restored.** Ended the validation Desktop stream, restored the prior Moonlight custom 120 FPS and disabled shortcut capture, and removed only the runtime Sunshine eDP-1 override created for this test. The primary Sunshine service is active with its original command. The native VM remains running and reachable over SSH on 27.2.1/26B131; no OS upgrade or guest/helper restart occurred during cleanup.

- **2026-11-13 Installed the synchronized-clock launch check.** The full Linux-root lifecycle suite passed all 18 tests after integration. Reinstalled through the reviewed helper installer with the unchanged manifest; the installed script matches source, its read-only clock check passes and live helper readiness is verified. The managed helper PID is unchanged and no guest or helper was restarted. New VM launches now fail with an actionable diagnostic if the host clock remains unsynchronized. Normal host-reboot acceptance is still pending coordination with other host work and encrypted-root unlock.

- **2026-11-13 Private VM operations skill reconciled with managed recovery.** Updated the local omvm-vm-ops skill and all three Omarchy discovery copies after verifying identical starting content. The notes now identify managed v23 paths, verified helper-stop/cold-guest authenticated recovery, fail-closed checkpoint handling, preserved v22 rollback helpers and the current 3024x1964@254 native display. Full host reboot, Messages/APNs and Contact Key Verification remain open. The staged macOS 27.3 beta installer still awaits separate licence acceptance; no OS upgrade or runtime change was made by this documentation update.

- **2026-11-13 VM launch waits for a synchronized host clock.** Added a bounded 30-second NTPSynchronized readiness check in the vmapple prepare gate before helper starts or new VM reservation. An unavailable/unsynchronized clock fails with a network/time-service diagnostic; helper boot and release remain independent of clock/network state, with no provider reinitialization or clock mutation. Four focused clock tests and five existing gate tests pass through persistent HC terminals. The unsynchronized-launch regression fails against the previous implementation because it admits the launch. Syntax and diff checks pass; the current host reports NTP synchronized. No live units or guests were changed by this commit.

- **2026-11-13 Managed helper process restart recovered authenticated access.** Cleanly stopped macos-fresh, retained a paired offline VM backup and quiesced private helper checkpoint, then restarted only its managed helper and cold-booted the same domain. Helper PID changed, checkpoint bytes and SEP/provider ownership were preserved, and guest UUID/native ADI file remained unchanged before local unlock. Fresh queue-0/3 replies succeeded; stock akd completed fresh SRP and AppleIDSettings accepted an uncached HTTP 200 device-list response after the restart. No Apple password/MFA was entered. Other service errors remain, and normal Linux-host reboot acceptance is still pending. Updated lifecycle status without enabling automatic crash retry.

- **2026-11-13 Official 27.3 beta installer prepared for the APNs experiment.** Copied the Apple package into the guest with matching SHA256, verified its Apple package signature, and staged the installer application. The startosinstall executable passes strict signature validation and SharedSupport metadata identifies 27.3/26C5035r with VM support. Outer bundle verification rejects its custom omit rules; this limitation is recorded rather than suppressed. No OS upgrade has started. The installer carries a separate pre-release licence, so acceptance is pending owner confirmation.

- **2026-11-13 Managed Linux helpers activated for macos-fresh.** Installed and enabled the pinned provider and per-VM helper units, then cleanly stopped the guest and retained a matched offline rollback before switching only its FairPlay socket to the managed v23 service. The libvirt readiness gate started the same guest with an unchanged UUID. After local GUI login, its existing Apple Account details loaded; real queue-0/queue-3 requests returned transport status zero, and stock akd logged successful SRP. The saved ADI envelope is still empty, so durable provisioned-state reuse is not established. Original v22 helpers remain alive for rollback. Helper-process and host-reboot acceptance tests remain pending. A temporary runtime Sunshine capture override exposes the physical display for GUI validation; no guest display configuration changed.

- **2026-11-13 Helper readiness accepts the SEP socket ownership contract.** The existing SEP signer intentionally owns its mode-0600 socket as the permitted client UID while serving from a root process. Split filesystem owner validation from SO_PEERCRED checks and now require the actual SEP service MainPID, retaining root ownership and exact peer PID checks for FairPlay. Five focused Linux-root socket/readiness tests pass, including a client-owned socket served by root and rejection of wrong peers. A read-only live connection verified the real SEP owner/service PID without a signing request. No service restart, domain or account mutation occurred in this fix.

- **2026-11-13 Persistent Linux helper lifecycle prepared.** Added a root-owned artifact manifest, repeatable installer, pinned UID1 initialization service and per-VM FairPlay units using durable backend state. Libvirt prepare/release gates preserve phase/XML, require exact Linux sockets and serialize all vmapple guest starts without recursive libvirt calls. READY provider reuse, poisoned-state refusal, explicit empty-state enrollment, private assets/state and separate managed runtime paths preserve existing in-memory helpers for migration. Thirteen Linux-root offline tests pass, along with Bash/Python syntax, diff checks and structural systemd validation using the staged executable path. No units were installed or started, no guest/domain/account was changed, and host/helper reboot recovery remains to be tested.
- **2026-11-13 Durable Linux helper candidate staged without activation.** Added a root-owned v23 backend and manifest-pinned private cache alongside the live v22 helper. The candidate persists identity-bound ADI state with atomic writes, a pending-operation marker, and explicit first initialization; synthetic Linux file/socket tests cover restart roundtrips, corrupt/wrong-identity rejection, actual short-write failure and commit-before-reply. Live account recovery and host reboot are not yet tested. Both existing helper processes and the running guest remain unchanged. An official Apple 27.3 beta installer download is being staged separately for the APNs regression experiment; no guest upgrade has begun.

- **2026-11-12 Messages failure narrowed to guest key generation.** Read-only current-boot logs show CryptoTokenKit key generation rejected with `0xe00002e2`, wrapped by `SecKeyCreateRandomKey_ios` as `-25308`; the BAA certificate fails and both APNs environments remain disconnected. The guest correctly advertises a VM. Native-host 27.2.1 reports match this chain; 27.3 beta is an unverified candidate fix. Added `docs/messages.md` with evidence, sources and user-facing acceptance criteria. No account, guest, helper or host state changed.

- **2026-11-12 VM operations skill refreshed after Linux sign-in success.** Updated the private Mac skill and Omarchy Claude/Agents/Codex copies with fresh-guest targeting, native display details, verified Linux-only runtime sign-in, owner-reported Xcode sign-in, and separate certificate/app acceptance criteria. Added dated Messages push-certificate/system-keychain evidence and preserved the unresolved cause, MFA and host/helper-restart limits. Documented pinned-provider and live-helper preservation, consistent rollback, and the macOS restore dependency; removed obsolete blanket sign-in failure claims. Validated frontmatter/references and matching installed contents. No VM, display, helper, credential or account state changed.

- **2026-11-12 omvm-gui follows the running VM.** The window was fixed to `$OMVM_VM` or `macos`, so it showed `macos` as off while `macos-fresh` ran. It now defaults to the one running (or paused) libvirt domain when `OMVM_VM` is unset, and the header has a menu of all session domains; choosing one re-executes the window for that VM. `--selftest` passes against `macos-fresh`. No VM, domain or service was changed.

- **2026-11-12 Fresh VM opened in a native half-screen window.** After the Xcode application installation finished, cleanly stopped the guest, retained a paired offline signed-in rollback and selected the existing Wayland-capable Mesa/native display path. A non-fullscreen native window was positioned in a centered landscape window covering about half of the active desktop with a supported HiDPI density. Window mapping/geometry, guest SSH and unchanged guest UUID were verified; the same Linux FairPlay process remained active and identity-provider configuration was preserved. VNC was replaced by the native view. No host reboot, account reset or backend restart occurred. Xcode first-launch/licence and development-certificate tests remain pending.

- **2026-11-12 Xcode installed in fresh signed-in VM.** Copied the cached owner-sourced Xcode 27.2 image directly from the Linux host to the running guest, verified identical SHA256 and application signatures before/after installation, and selected its developer directory. First-launch status exit 69; licence/setup and Xcode account/certificate checks remain pending. No account submission, certificate creation or reboot occurred.

- **2026-11-12 Linux-only blank-disk installation scoped separately.** Read the current restore scripts and fresh-restore controller: they still use native Virtualization.framework for new machine identity, auxiliary storage and IPSW installation, before Linux setup/sign-in. Added a TODO to investigate official-asset download/extraction, recovery/restore transport, personalization and a genuinely new blank-disk install on Linux. SEP authentication success alone does not prove this path. The checked upstream Ambrosia/KVM example still requires an installed guest. No download, VM creation, restore, reboot or provider change was performed.

- **2026-11-12 Fresh-identity sign-in succeeds; automatic helper startup queued.** The new factory-restored guest logged successful secondary authentication, completed Apple Account authentication, a valid account, and primary iCloud account addition using its own Linux-only helper. The owner then confirmed the Apple Account overview was signed in and showed the normal VM feature notice in the local Omarchy VNC viewer. A later IDMS check-in returned HTTP 401 after account addition; the exact cause of the repeated verification prompt is unproven, and dismissal after a second incorrect code does not establish that code was accepted. The same isolated Linux backend remains running. Added `docs/TODO.md` with installation/startup ordering, per-VM identity and service readiness, safe hardware concurrency, state lifetime, and guest/helper/host restart acceptance checks. Fresh post-sign-in guest restart and helper/host restart recovery have not been tested. No running guest, account or provider was changed for this documentation update.

- **2026-11-12 Fresh factory VM reaches Linux-only sign-in readiness.** A new 27.2.1 restore uses a new machine identity, its own native serial and network addresses, and an empty disk rather than the signed-in control image. Restore completed on the native SDK without a native Setup Assistant boot; the stopped sparse transfer and paired artifacts passed verification. On Linux, a missing QEMU VNC keymap resource path was corrected. Automated single-user boot setup timed out, so the owner-created local account completed normal GUI setup and SSH access; SIP remains enabled and boot arguments empty. After clean shutdown and paired rollback, the distinct actual guest UUID was retained and a separate v22 Linux FairPlay process was attached. Clock drift is zero and the guest NAC context succeeds with both error codes zero. An early owner sign-in attempt before FairPlay attachment failed; the configured sign-in attempt is now handed to the owner and is not yet proven. The original signed-in control is stopped with its same helper process preserved; only one guest runs because concurrent hardware requests may return EBUSY. A local TigerVNC window was opened on the Linux desktop for owner demonstration/recording, with its mapped title and authenticated connection checked. No host reboot, provider reload, account reset or Mac signing helper was used.

- **2026-11-12 Linux-only Apple Account sign-in survives a guest restart.** Owner-entered credentials and MFA completed through stock System Settings with Linux SEP and v22 FairPlay providers. Native logs establish SRP/secondary-auth success, a valid primary account and primary iCloud account addition; the actual account overview was observed. After a clean shutdown and matching offline rollback, the guest returned with a new boot session, unchanged platform UUID and the same signed-in account. The same Linux backend remained active, so host/backend restart resilience is not proven. The encrypted-data verification notice remains, and network timeout diagnostics do not establish full syncing. No account or encrypted-data reset was performed. The helper's temporary test expiry was removed without restarting it; socket-only isolation, resource limits and no-restart policy are unchanged. The owner then requested a newly restored VM with a new machine identity; that independent repeat is pending. The obsolete native comparison VM was stopped to free a native restore slot, leaving the working Linux guest unchanged.

- **2026-11-12 Linux-only guest NAC/Absinthe prerequisite passes.** The independently reviewed v22 adapter adds only the native supported-options slot with a restricted baseline mask when an ordinary hardware provider exists; unsupported higher capabilities remain clear. Focused ARM64 modes, prior slot regressions, adapter tests, vet and clean cumulative patch verification pass. The formerly failing 224-byte guest request now completes and the backend remains active. The spare was missing virtual Wi-Fi metadata: after clean shutdown and matched offline rollback, an own stable locally administered address was added, while its actual platform UUID remained unchanged. On the cold guest with a fresh Linux-only backend, the real NAC/Absinthe context returns present with both error codes zero. The stock sign-in form is ready for owner input; account sign-in and restart persistence remain unverified. The comparison VM stays off during the spare test, and the Mac relay is not selected. No host reboot, account reset, or additional AES operation was needed for this step. A runtime-only unit override extends the helper test ceiling to 90 minutes for owner entry; the same process remained active.

- **2026-11-12 Next guest boundary identified as getSupportedOptions.** The reviewed v21 diagnostic assigns distinct fixed IOAES vtable stubs and logs only bounded slot offsets, preserving all existing methods and failure behavior. All 285 registrations, eight actual synthetic ARM64 calls, metadata/privacy/wire checks and review passed. A new backend/guest session completed nine queue-0/queue-3 requests before the 224-byte request identified slot 0x8a0 (getSupportedOptions). The provider remains READY with no new hardware operation this round. Exact native capability bits and caller use are under review before adding the method; no account input or host reboot was needed.

- **2026-11-12 Hardware DSB decrypt passes; standalone guest advances.** After a third owner-authorized normal reboot coordinated with the HC Omarchy pane, the reviewed v3 provider reported DSB available and passed actual public hardware encrypt/decrypt checks, software CBC checks and both UID1 derivations. No boot image/default change; both watchdog units were temporarily disabled. The independently reviewed v20 adapter implements only the observed fixed descriptor through a separate opt-in and corrects native decrypt buffer direction. Opening the spare guest's stock Apple Account pane with no credentials completed six queue-0 and four queue-3 requests, including the former blocker; the hardware counter advanced by one and remained READY. The next 224-byte queue-0 request reaches an unsupported IOAES virtual method, so the backend exits without state reuse. Standalone sign-in is not established. Exact-kernel build, sanitizer tests, fake-client and ARM64 shim cases, independent review and clean cumulative patch application passed. Fresh post-reboot SEP signatures also verify. The spare is stopped and original comparison VM/relay restored, SSH verified, both watchdog units enabled; the new driver remains pinned until platform reset. A bounded method-slot diagnostic is next, requiring no host reboot.

- **2026-11-12 Extended guest descriptor fields confirmed without hardware execution.** The independently reviewed v19 metadata-only test reports first word128, extension length32, readable76-byte descriptor, presentIV and zero offsets for the observed selector3000/op1/16-byte request. Both prior queue-0 completions still succeed; the unsupported guard then stops the backend before provider access or copyback. No credentials, opaque key/DSB bytes or raw error strings were logged. Nine ARM64 boundary cases plus earlier regressions pass. Native inspection confirms a separate hardware-disable bit3 that earlier snapshots discarded, and operation1 descriptor roles reverse for out-of-place decrypts. An isolated successor provider and strict optional client are being prepared; nothing new has been loaded or executed on the hardware. The unchanged comparison guest is restored between tests.

- **2026-11-12 Guest blocker localized to extended IOAES descriptor 3000.** Reviewed v18 source metadata and real ARM64 failure tests identify the third 352-byte queue-0 request as IOAES operation1 on16bytes using selector3000/0xbb8. The shim rejects it at the purpose guard before any hardware-provider ioctl; it is not the suspected Mach-RPC boundary or an account/password failure. The first96/352-byte calls still complete with status0. No credentials or raw buffers were logged, and the existing hardware provider remains unchanged/READY. Initial native inspection shows3000 is outside the generated-key purpose interval and requires descriptor extension bytes omitted by the current40-byte shim read; complete native DSB semantics are being reviewed before implementation. Main comparison restored between controlled spare tests.

- **2026-11-12 Guest failure classification remains outside the typed Mach-RPC guard.** The reviewed v17 metadata-only adapter preserves all wire/crypto/failure behavior and logs only typed framing scalars or a fixed unknown class. Tests, vet, ARM64 build, independent review and clean pinned patch application pass. A new backend session and cold guest boot repeated two successful queue-0 completions followed by a 352-byte internal failure, classified kernel_unclassified. The restored stock sign-in pane triggered it without any account identifier/password input. This does not prove a Mach-RPC failure; broader structured source diagnostics are being prepared. Main comparison is restored between tests; no security settings, hardware owner or boot files changed.

- **2026-11-12 First standalone guest transport test reaches a specific error.** The existing local spare was booted with 8 GiB/4 CPUs after paired offline reflinks; its actual guest IOPlatformUUID was captured privately and remained unchanged after switching only the spare to the isolated OFR2 QEMU, local SEP identity device and Linux FairPlay socket. Firmware and stored guest identity remained intact. Root-only device access was retained; a deliberate execute-only directory ACL and socket-connect ACL allow only the VM owner to reach that backend. Both guests initially fit with 27 GiB available, but their shared restore ECID was confirmed, so the comparison VM was stopped before the request test. Opening the stock System Settings Apple Account pane, with no email/password entered and no entitlement/security changes, produced queue-0 completions of 96 and 352 bytes with status zero, then an internal error on another 352-byte request. The backend exited as designed; no account sign-in or guest provisioning success is claimed. The spare was stopped and the unchanged comparison restored while a metadata-only diagnostic class is prepared. No Mac disk copy or remote-base dependency was introduced.

- **2026-11-12 Fresh Linux provisioning and OTP generation pass.** After the authorized second normal reboot, the v2 fixed-purpose UID1 provider passed the real hardware AES known-answer test, kernel CBC encrypt/decrypt test and both derivations. Offline FairPlay daemon initialization and fresh credential-free machine provisioning then succeeded, including purpose 0x89c encrypt/decrypt of 592 bytes and OTP proof generation. Two Apple HTTP200 responses; 1.4 seconds, 395.7 MiB peak. No Mac relay, account credentials or previous provisioned state were used; new state/proofs were not printed or retained. Fresh SEP message/digest signatures also verify. Boot files and default entry were unchanged. Temporary network retry units were removed; prompt reconnect does not establish that they were needed. The original comparison VM, relay and enabled service/timer were restored and guest SSH verified. Its enabled service can auto-start independently of the timer, an operational detail for future reboot tests. The experimental AES module remains pinned until platform reset. Standalone VM account sign-in remains unverified; isolated guest integration is next.

- **2026-11-12 Fresh Linux provisioning finalizes; OTP generation exposes required decryption.** The offline FairPlay daemon starts with real purpose 0x899 encryption (32 bytes). A fresh credential-free client receives two usable Apple HTTP200 responses, completes real purpose 0x89c encryption (592 bytes), and returns successfully from EndProvisioning. RequestOTP then stops at unsupported operation1/decrypt592; no login proof or account sign-in is claimed and no provisioned state was saved. The staged second provider revision adds native-confirmed CBC decryption without changing key derivation or ABI layout. Review caught and fixed a stack scatterlist buffer and uninitialized crypto-request metadata before activation. Exact-kernel build, independent review, sanitizer harnesses, ARM64 shim/client tests and clean patch application pass. Root-private v2 artifacts are hash-verified; a normal reboot is required to replace the pinned first revision. Boot files remain unchanged. Prior reboot logs show automatic root unlock in 6.5 seconds, followed by a Wi-Fi DHCP failure until a later reconnect; a bounded next-boot-only existing-profile retry is enabled for recovery, without touching the current connection. A separate OFR2 QEMU executable was linked and inspected without overwriting any live build or VM; no guest activation yet.

- **2026-11-12 Real Linux AES and UID1 derivations pass.** Canonical 331d298 adds the reviewed root-only fixed-purpose provider, frozen UAPI, optional Linux client and board IRQ patch. The exact matching-kernel LLVM18 build, source-level independent reviews, fake-MMIO/UBSan failure checks and Linux ARM64 client tests passed. Main guest stopped cleanly in 16 seconds with matching offline disk/aux/profile/domain reflinks; the read-only snapshot owner was unloaded normally. The explicitly gated standard AIC2 mapping avoided a second reboot or boot-image change. Actual public AES128 CBC hardware KAT passed, followed by both pinned UID1 derivations: READY, completion status 0x20, tag 3, three completed hardware operations. No raw derived key left the kernel. The unchanged main guest restarted and SSH was verified; original Mac comparison relay and local SEP service remain available. Fresh post-reboot message/digest signatures independently verify. The experimental provider permanently retains module/power/DMA and vetoes sleep until full platform reset; kexec loading was disabled with no loaded image. A persistent test-component cache was restored from official sources using 241,561,760 network bytes and 854 MiB peak memory; an intended assets-only Go overlay missed a canonical path, so the pre-existing synthetic offline queue-3 probe also ran and returned its expected -43006, with no credentials or provisioning request. The overlay path and artifact label were corrected. No fresh account sign-in was attempted; hardware success still requires fresh Apple provisioning and guest integration validation.

- **2026-11-12 Approved host reboot and powered AES observation succeeded.** The new boot and expected kernel were verified; live device-tree checks match both AES banks, paired SIO DART stream 1 and the power gate. The manually loaded read-only diagnostic reports full readiness 0x3f80 and UID1-disable clear (GID0 set, GID1 clear). This proves powered availability, not a transform. Main guest SSH, Linux SEP service and the original macOS comparison relay are operational again. Canonical 2ca87d0 adds an explicit synchronous provider interface with IV-presence semantics, bounded copied buffers and rejection of incomplete/malformed results. Ten prior ARM64 ABI cases, twelve provider cases and ownership/default checks pass; clean pinned-source application, socket protocol tests and ARM64 build also pass. Test providers do not implement cryptography. No AES command, DMA transfer, derivation or fresh account attempt has run; standalone sign-in remains incomplete.

- **2026-11-12 Owner-approved AES diagnostic boot image activated.** The main guest stopped cleanly in 12 seconds under its operation lock. The reviewed activation command passed live hash, board, kernel and rollback checks, installed the candidate through normal update-m1n1, and verified the exact expected boot image. Default entry and Limine remain unchanged; no snapshot module has been loaded. Owner explicitly authorized the host reboot and continued use. Reboot and live hardware observation are next; standalone sign-in remains incomplete.

- **2026-11-12 Corrected the standalone IOAES descriptor ABI while reboot approval remains pending.** Canonical e313117 fixes valid NULL-IV calls, preserves supplied-IV copyback ordering, rejects unsupported asynchronous completion, and checks metadata/data address overflow. Native bad-argument status is used only where proven; descriptor-capacity limits remain explicit diagnostic errors after review corrected an alignment-versus-capacity interpretation. Ten production-shim cases pass on Linux ARM64 with synthetic buffers; clean pinned-source patch application, adapter protocol tests and ARM64 build pass. These checks use no Apple assets or hardware-key operation and do not prove successful crypto. The current VM, boot image and boot configuration remain unchanged; the device-key operation and standalone sign-in remain incomplete.

- **2026-11-12 AES diagnostic activation bundle and rollback copies prepared.** Root-owned staged module, reviewed board DTB, guarded candidate boot configuration and candidate boot image are ready. Independent verification confirms the candidate changes only the intended board tree among 115, with identical m1n1 and U-Boot components. Four dated backups and an ESP recovery note were created; live boot image, configuration, default entry and running guest remain unchanged. Both kernel entries share the device tree, so a DTB rollback requires restoring the saved image. Current auto-unlock configuration was checked without reading key contents. Host reboot approval is pending; no activation or hardware sampling has occurred.

- **2026-11-12 AES powered-state diagnostic built and reviewed; activation pending.** Canonical research commit e0886b6 preserves the default-disabled resource binding, separate diagnostic driver, optional verified-board enablement and validation notes. The module builds against the exact cached running kernel with its original Clang 18.1.8, including MODPOST and BTF; independent source/object review found only the intended guarded reads. An isolated current-source build reproduces the installed baseline DTB byte-for-byte; both diagnostic variants pass compilation, binding/example/schema checks and YAML lint. Independent DTB comparison confirms only the new AES node semantically, with exact verified banks, paired DART stream 1 references and the AES-to-SIO power dependency. The initial integration patch used a different existing source copy; only its Kconfig/Makefile context was rebased onto canonical current source, preserving the owner's changes and other AES draft. Build artifacts are retained privately; no module installation/load, AES register access, boot-file activation or host reboot occurred. The hardware state and standalone sign-in remain unverified.

- **2026-11-12 Standalone FairPlay diagnostics identify a required derived-key operation.** The local Linux SEP signer independently verifies a fresh challenge; the remaining live macOS dependency is FairPlay. Canonical research commit e1604e3 adds a pinned Linux backend experiment and explicit queue-0 error-buffer completion, with clean patch application, focused tests, ARM64 builds, real socket checks and separate QEMU object compilation. A credential-free fresh machine-provisioning probe received both usable Apple responses, then local finalization failed at IOAES handle 0x89c (operation 0, 592 bytes, 128-bit descriptor). No replacement key or success status was supplied. Modern driver analysis maps this special key to a UID1/SIO AES derivation; a preserved host ADT supplies resource metadata for a bounded snapshot, but actual disable state remains unknown. The exact matching cached kernel build was found, avoiding a full rebuild solely to obtain headers. A separate 8 GiB guest booted with external networking blocked and the Linux backend selected, but generated no FairPlay traffic, so provisioning was not validated there. Matching offline reflinks were retained; the spare's previous domain and the main guest's original backend were restored, with main SSH verified. No account credentials, AES register accesses, module loads or host reboot occurred. Standalone sign-in remains incomplete.

- **2026-11-11 Direct Linux SEP certificate/signature proof succeeds with zero VMs.** At owner request, stopped all guests and the exclusive-open signer service, then used the existing-only kernel path directly. Fresh UIK attestation1200B and the pinned physical M1 key produced an Apple BAAHTTP200 response with two certificates. OpenSSL validates the BAAUCRT chain and leaf/public-key match. A fresh32-byte random challenge gets a71-byte ECDSA/SHA256 signature that verifies with the new certificate; a changed challenge fails. No new key, private-key export or macOS signing host; existing reference hash unchanged. The direct test took5.13seconds. Signer service is restored, original macos runs its exact prior binary and SSH27.2 is verified. Private proof artifacts and rollback pairs are preserved; Apple Account login is still incomplete.

- **2026-11-11 AES corrections pass real-guest boot but do not resolve ADI.** Canonical b1d6afc builds isolated QEMU a37f244b; default0486edfc is restored exactly. Existing macos27 boots to desktop/SSH27.2.1 with the genuine SEP bridge, but background provisioning still produces End-43004 and an empty ADI store before any account credential submission. Live AES requests are256-bit with DATA IV0, so the verified128/192/context bugs do not explain this observed path. Six StartHTTP200/1414B→EndHTTP200/1849B failures destroy their contexts;12 fallback StartHTTP503/477B responses explain-8007 independently. Private logging redacts required End fields, and the existing akd network cache has no provisioning response. Test guest stopped, diagnostic traces removed; main restored after the isolated test. Matching offline disk/aux/profile/domain reflinks and original/test binaries are retained. ID_BO4 source edit remains untouched.

- **2026-11-11 Fresh modern user reproduces ADI -43004; VNC handed to owner.** Read-only logs identify akdPID2138/userID502: finalization -43004 at18:04:48Pacific, Start18:04:54 and another End-43004 at18:04:58. The active ADI store is0B after isolation; native1112B state remains preserved. This establishes fresh-user provisioning failure on the modern Linux control, so v1alone does not explain the Linux failure. UID502 has an Aqua domain and Setup Assistant, but completed desktop login was not verified; the owner reports copied UID501 GUI login fails despite its password working for sudo. Mac Screen Sharing required VNC authentication; a clean test-only restart enabled password auth on the loopback VNC listener, with the forwarded client connection verified. The owner controls the VM; no UI input is sent during handoff. Main macos remains running and unchanged; other existing guests remain off.

- **2026-11-11 Modern control boots on Linux; isolated fresh provisioning is ready.** Decoded the prior stop from auxiliary panic text: unencrypted data volume is not allowed, apfs_vfsops.c2399. The existing apple-vendor-cap mode is required for this fresh non-FileVault27 image; enabling it only in the separate test domain resolves boot, verifies27.2.1/26B131 over SSH, and displays the login screen. Original upgraded guests keep their storage flags. A clean offline overlay check and matching reflink rollback precede a new UID502 local user. Native1112B ADI state is preserved in a renamed directory; active state is recreated empty and the guest cold-started. New-user console/SSH checks show no Apple Account preferences and no active ADI file, so retained native login state will not count as fresh provisioning proof. No fresh account submission yet. All three preexisting guests are descriptorv1; static native tracing does not establish v1alone as a Linux ADI cause because QEMU supplies identity independently. The bounded modern test runs first, with the existing second guest available for comparison. Available host RAM remains33GiB; main guest unchanged and the other two existing guests remain off. ID_BO4 source edit remains untouched.

- **2026-11-11 Extra modern control stopped; existing omvm guest remains the target.** The modern network-backed guest reached XNU but shut down before SSH, with no established cause and no sign-in/provisioning attempt. At owner direction, the extra domain stays off; both NBD servers and the SSH reverse forward were stopped, separate artifacts preserved and native source size/mtime/ctime/header hash revalidated. The detached NBD helper had inherited the staging lock FD; stopping it released the lock, so future launchers must close it before detaching. Existing macos responds over SSH; its ADI file is still empty and staged serial/MLB are non-placeholder values. Read-only checks changed no original guest state. Omarchy reports41GiB available RAM,768GiB free disk, AC/100percent battery; the native Mac has597GiB free disk and84percent battery. ID_BO4 remains untouched.

- **2026-11-11 Modern control reaches the Linux guest kernel without a bulk VM copy.** A separate no-watchdog test domain uses the stopped native modern disk read-only through loopback SSH/NBD, with all writes in a distinct Linux qcow2 overlay. A disposable fixture proves rejected base writes, persistent overlay writes and unchanged source bytes. Two firmware stages complete and an XNU kernel PC is observed after adding2MiB copy-on-read caching; about273MiB was fetched on demand. Desktop, SSH, fresh ADI provisioning and account sign-in are not yet verified. Ordinary blockstats missed direct BDIF reads, so zero counters alone were a misleading stall signal. Native disk size/mtime/ctime/header hash remain unchanged; the original macos guest remains running. Homebrew QEMU11.1.3 disk-server utilities were installed on the native Mac (729.2MB plus dependencies). The cancelled partial bulk copy remains cancelled. Task scripts stay in/tmp; ID_BO4 is untouched.

- **2026-11-11 Diagnostic native-VM transfer cancelled; focus returns to fresh generic Linux sign-in.** With owner agreement, the operator cancelled the offline copy of the successfully signed-in modern native control by SIGTERM to the verified transfer-pipeline processes. The source modern VM remains stopped and intact. The separate partial artifact destination is retained and marked `TRANSFER_CANCELLED.txt`; it was not imported or booted, and nothing was deleted. Receiver shutdown verification remains with the operator. Native factory-v2 sign-in is verified, but Linux cloud authentication and signed-in identity portability are unproven. The implementation goal is a fresh generic VM with the Linux identity bridge, using the corrected factory hardware-model restore default. This documentation-only update starts/imports nothing and preserves the preexisting ID_BO4/libvirt edit.

- **2026-11-11 Restore wrapper now preserves the factory hardware model.** Canonical experimental source commit `6d317bd` removes the silent Tahoe legacy-v1 override from `images/host/macos-restore.sh`. The historical descriptor is available only with explicit `MACOSVM_COMPAT_HWMODEL_V1=1`, warns that strong identity is disabled and the mode is not iCloud eligible, and records truthful bundle provenance. Explicit caller hardware-model overrides are honored without logging their values; conflicting/invalid options fail. Updated image instructions and control findings distinguish the successful fresh factory-v2 native Apple Account sign-in from still-unverified Linux cloud authentication. Seven temporary mock scenarios passed through the real provisioning script: factory default, legacy warning, custom override, conflict, invalid option, existing-disk refusal, and restore failure without fallback/retry. Syntax/whitespace checks passed. No actual restore, live image, firmware, guest, original upstream checkout or unrelated libvirt source was changed.

- **2026-11-11 Factory-modern native Apple Account MFA succeeds; Linux migration remains unproven.** The owner completed MFA in the fresh ordinary-public-SDK macOS27.2.1/build26B131 VM using the factory DataRepresentationVersion2 model. System Settings displays the signed-in account; the remaining Some iCloud Data Isn't Syncing warning follows deferring Keychain setup and did not prevent login. The ADI store is1112B, versus the legacy control's empty store and repeated ADIEnd -43004. Native shutdown completed with VM_STATE=0/VM_GUEST_STOPPED and exited controller/VM processes. Offline sparse/zstd transfer of its stopped paired disk/aux/profile is running to a separate modern-native-27.2.1-20261111 artifact bundle. This verifies native modern-profile account login only; transfer completion, Omarchy boot and account portability are still unproven. No active domain/disk was changed by this documentation update; the preexisting ID_BO4 edit is preserved.

- **2026-11-11 Modern auxiliary export footer bug fixed in the experimental source.** Native v2 auxiliary files append metadata after the fixed32MiB flash region; the old skip-only dd exported the observed8348-byte footer into the QEMU drive. Added a validated atomic extractor for native v1/v2 headers and sizes, preserving the complete native file, and wired provisioning/docs through it. Actual stopped v1/v2 files produce exact32MiB matching their source flash windows with0600 permissions and unchanged sources. In-place/truncated inputs fail while preserving existing output; shell syntax passes. Current modern setup remains with the owner; no live disk/auxiliary body was read or copied and no guest/domain was changed by this fix.

- **2026-11-11 Factory-modern native restore completed and booted Setup Assistant.** Downloaded official Apple27.2.1/build26B131 IPSW in eight validated HTTPS byte ranges, exact25,595,954,706B; completed in502seconds. The public-SDK controller independently loaded image metadata, required factory DataRepresentationVersion2, created a fresh machineID/auxiliary/disk on local SSD (4CPU,8GiB RAM,160GiB sparse disk), and installed successfully. It then stopped normally; a separate GUI app booted the resulting GPT disk and CUA observed Setup Assistant. No legacy model override or private identity override is used. Owner asked to complete Apple terms/local-account creation and test Apple Account in the new omvm Modern VM window. No fresh sign-in result yet; no Linux modern-profile boot/integration result yet. Original Omarchy VM and prior paired backups are preserved.

- **2026-11-11 Legacy hardware descriptor disables native strong identity; modern startup succeeds.** Original restore README, source override and both saved profiles agree: the Tahoe disk was freshly restored using the hardcoded Ventura hardware-model descriptor (135 bytes, DataRepresentationVersion1, PlatformVersion2, minimumOS13), replacing the IPSW factory descriptor after a historical host-key -9 error. Current native framework disassembly directly shows `_isStrongIdentityEnabled` defaults to descriptor version greater than1. This establishes a capability difference, not proof of the numeric ADI cause. On the current physical Mac17,9, ordinary public-SDK latest metadata returns the supported modern132-byte v2 descriptor; fresh aux/ID/config initialization AND a bounded new blank-disk VM start/stop all succeed without -9. Downloading the official27.2.1/build26B131 Apple IPSW in validated parallel ranges; preparing a fresh4CPU/8GiB/160GiB restore on local SSD. Failed legacy native control was cleanly stopped and its matching disk/aux/profile preserved privately. Original Omarchy VM remains running and unchanged by these control operations. Fresh restore/sign-in and Linux modern-profile integration are not yet verified.

- **2026-11-11 Native same-build manual sign-in reproduces ADI -43004.** The owner entered the account directly in the native Mac-hosted 27.2/build26B123 control. Live akd capture records provisioning-start success at16:19:05.790 MDT followed by ADIProvisioningEnd -43004 at16:19:06.144; a second start/end pair repeats at16:19:09.410/.870. AuthKit wraps -8004, then a fallback returns -8007 and final -7018. The initial route lookup also reports -8025/-45061. The ADI file remains zero bytes. CUA visually confirms Verification Failed with the correct full email displayed. Thus this failure is reproducible without the experimental Linux identity bridge; common guest/profile/provisioning state and native VM-support requirements need separating before more bridge changes. Native control success is not claimed; Omarchy Apple Account login remains incomplete. Raw diagnostic capture remains private owner0600; only event classes/codes/times are summarized.

- **2026-11-11 Native same-build control now boots to desktop; comparison sign-in pending.** Stock 26.4 restore and the paired 27.2 snapshot both reached native networking. Initial DHCP lookup had failed to normalize zero-padded MAC octets; corrected lookup found the control. The 27.2 control now verifies build 26B123 over SSH and a UID-501 Aqua desktop. Its initial black display resolved as boot/session loading finished; System Settings sign-in form is visible. The external network disk is slow. Native v1 auxiliary wrapper layout was independently verified against the parser and fixed 0x4000 flash offset; its header has no OS/identity binding. A separate ordinary-SDK app adds the original launcher entropy/serial devices. Native ADI store is still empty before an account attempt. Owner asked to enter credentials in the visible comparison window because automated input is unreliable; a private owner0600 live akd diagnostic capture is running. This is a diagnostic Mac-hosted copy; Omarchy account sign-in remains incomplete.

- **2026-11-11 `omac seamless`: each macOS app window of `macapps` as its own Hyprland window, verified on a headless output.** Added `share/omac/seamless.py` (Python 3 + GTK 4 via PyGObject; its own RFB 3.8 client, one VNC connection, framebuffer kept by a reader thread; one `omac windows --watch` child; one `omac shell /bin/sh` for `open -b`; both children die with it via `PR_SET_PDEATHSIG`) and `omac seamless [APP...]`, `omac seamless --stop`, `omac run --seamless APP` (starts it detached unless it runs; pid in `$XDG_RUNTIME_DIR/omac-seamless-macapps.pid`) and `omac desktop --seamless APP` (entry "APP (macOS)", passes `desktop-file-validate`). Each guest app window gets an undecorated toplevel, app id `org.omvm.omac`, title = app name, painting the live crop (only when VNC damage touches it) under a strip of the guest menu bar (30 pt), letterboxed when the host size differs, rounded 10 pt corners; menus, tooltips, prompts and same-app sheets become xdg popovers of their window at the right offset, menu shadow margin (75 pt) trimmed; closing a host window clicks the guest title bar and sends Cmd+W (the host window returns after 3 s if the guest window stays, e.g. a save sheet); focusing one runs `open -b BUNDLE`. Input keysyms as omvm's viewer does (Super = Cmd, Alt = Option, Ctrl = Control); `share/hypr-macos-vm.lua` now puts `org.omvm.omac` windows in the "macos-vm" passthrough submap too. Tested on a Hyprland headless output (`hyprctl output create headless OMACSEAM` at -20000,-20000 so eDP-1 kept 0,0 and focus; windows sent there with a temporary `workspace 61 silent` + `no_initial_focus` rule; never on eDP-1, no real pointer/keyboard use): grim shows TextEdit and Calculator as separate windows with only their app (`/tmp/omac-shots/seamless-1.png`); a click and "Hello from Hyprland 42" typed through the control socket (same `input_*` methods as the GTK handlers) appear in a fresh `virsh screenshot` and the host capture (`seamless-typed.png`); File menu from the strip, a context menu outside the window, the Chess Game Center sheet and TextEdit's save sheet shown attached (`seamless-menu.png`, `seamless-context-menu.png`, `seamless-sheet.png`, `seamless-savesheet.png`). Numbers: windows mapped 2–4 ms after their watch line (`omac run --seamless Chess` to window 4.2 s, the app's launch), Cmd+Q to host window gone 284 ms, typing 27 VNC updates/s and 27 repaints/s of that window only at 5.8 % of a core, idle 0–1.4 %, RSS ~145 MB, key-to-pixels over VNC 81–88 ms. Fixed while testing: a popover created before the compositor mapped its parent hung GTK (it waits for the popup's first configure), now overlays wait until 200 ms after the window's first paint; `Gdk.Rectangle(x=...)` silently ignores keyword arguments. Not working: wheel scrolling (RFB buttons 4/5 reach QEMU at the right place, TextEdit does not scroll; QEMU's VNC has no horizontal wheel). Not tested: real GTK key/pointer events and Hyprland focus changes on the live seat, local-mode refusal (domain not switched). `macos` untouched, `macos27` off, `macapps` stopped, headless output and rules removed.

- **2026-11-11 Empty ADI-state reset is a negative control; account sign-in remains incomplete.** After owner authorization, stopped macos and saved a fresh matching disk/aux/profile reflink backup (`*.pre-empty-adi-20261111` plus inactive domain XML). Revalidated `/var/db/fpsd/adi` contained exactly two zero-byte regular files, atomically renamed the directory without deletion, and restarted normally. Apple recreated the same two empty files with UID 265/mode 0666; the original directory remains preserved in the guest. A single controlled System Settings submission at 15:54:19 MDT used the visually verified correct account address; provisioning-start succeeds but finalization still returns -43004 at 15:54:30 and 15:54:40, wrapping to -7018 before 2FA. This reset does not establish the cause. The native-host comparison reached a running Virtualization.framework VM with a black display, not a proven OS boot; that control was stopped. Preparing the intact original Apple 26.4 restore bundle as a separate native baseline. No account login success is claimed.

- **2026-11-11 `omac windows`: guest window geometry for a future seamless mode, verified on `macapps`.** Added `share/omac/winlist.swift` (CGWindowListCopyWindowInfo to JSON: id, pid, owner, bundle id, layer, bounds in points, alpha, on-screen, title; display size in points/pixels and scale; `--apps` splits app windows from same-pid overlays and UserNotificationCenter prompts, drops talagentd placeholder windows; `--watch [--hz N]` prints one line per change) and `omac windows [--all] [--watch [--hz N]]`, which sends the source over SSH, compiles it in the guest once per source sha256 (~3 s) into `~/Library/Application Support/omac/winlist` and runs it there (~0.3 s per call). Plain SSH works: no `launchctl asuser`/LaunchAgent and no Screen Recording grant needed; only titles are missing without it. Pixel proof on `virsh screenshot` (1920x1080 = display 1920x1080 pt, scale 1 in VNC mode): TextEdit window rectangles crop exactly (a 1-px dark outline sits just outside, rounded corners show background, shadow excluded); menus (layer 101) carry a ~75 pt transparent margin on each side. List order is front to back and matched the screen with five overlapping windows of four apps. Watch: SSH adds 2–5 ms per line; `open -a TextEdit file` to line 150–400 ms (app time included); guest CPU ~4 % of a core at 30 Hz, ~10 % at 60 Hz. Fixed during testing: a killed host reader left `ssh` and the guest watcher running forever (bash backgrounded a function in a subshell; macOS gives no POLLHUP on the pipe), now omac forwards the signal to ssh and winlist exits on kqueue EV_EOF or a changed parent. Not possible without new grants: AppleScript `set bounds` over SSH blocks on an Automation prompt ("sshd-keygen-wrapper wants access to control TextEdit"; left unanswered), arbitrary windows need Accessibility. `macos` was restarted by another agent at 15:38 (pid 288093 to 297705), not by this work; `macos27` stayed off; `macapps` stopped.

- **2026-11-11 `omac` verified live end to end on `macapps`.** `omac init --remote` cloned the shut-off `macos27` in 1.4 s (btrfs reflink: 160 GiB apparent, 0 B exclusive; `vms/macapps` holds only disk.img, aux.img.trimmed, vm.json, guest_major, guest_user, ssh_port 46539, domain.xml, agent-notes.log, .agent.lock; autostart and `omvm-vm@macapps.timer` off). `omac up` reached SSH in ~19 s wall clock (a second cold boot after the fix: 16 s, reported as 16 s), macOS 27.2.1 (26B131) arm64, user `aquarat`, already logged in to the desktop (no autologin change needed). Over SSH: `omac run TextEdit` (by name), `omac run "Icon Composer.app"` (host .app with a space, rsync into `~/Applications`, no quarantine, `codesign --verify --deep --strict` ok, running) and `omac run x.dmg` (UDZO image built in the guest: installed, detached, no `/tmp/omac-*` left, running) each took 1–5 s. `list`, `desktop` (both entries pass `desktop-file-validate`), `status`, refusals for `OMAC_VM=macos`, `.pkg`, a second `init` and `--from macos`, and `omac stop` (18 s) all checked. Cost while running: QEMU RSS 16.3 GiB, disk grew to 517 MiB exclusive. Fixed in `bin/omac`: the boot wait counted only sleeps (each failed SSH probe adds up to 10 s, so "5 min" could be ~15), `run` failed with a jq error after the app had opened when there was no display (now skips the show without `WAYLAND_DISPLAY`/`DISPLAY`, and a failed show only warns), a missing host path fell through to `open -a /path` in the guest after booting (now refused before boot), and `list` missed `/System/Applications`. Found, not fixed: copies of built-in apps (Calculator) cannot launch outside the system volume (POSIX 162), Xcode's nested apps need Xcode's frameworks; `omvm show` in remote mode focuses the first `vncviewer` window of any VM; `hdiutil attach -mountpoint` prints a deprecation warning on 27. `macos` (pid 288093) untouched throughout.

- **2026-11-11 `omac`: macOS apps on Omarchy (code only, not yet run).** Added `bin/omac`, a launcher over omvm: `omac init` reflinks exactly `disk.img`, `aux.img.trimmed` and `vm.json` from the shut-off `macos27` (never `macos`) into `vms/macapps`, writes `guest_major`, `guest_user` and a unique `ssh_port`, runs `omvm virt macapps` and switches it to local window mode; `omac run App.app|App.dmg|NAME` boots it with plain `virsh start` (no watchdog) after power/RAM/two-guest checks, copies the app over SSH into `~/Applications`, clears quarantine, `open -a`s it and runs `omvm show`; plus `list`, `desktop`, `show`, `stop`, `status`, `shell`. The whole macOS desktop is one window, not seamless. Limits in `docs/omac.md`. `bash -n` and shellcheck pass; `omac --help` and `omac status` checked; no VM was created or started.

- **2026-11-11 Native host-configuration layout mismatch corrected for testing.** Existing cached provisioning replies have status ec=0 and valid base64 SPIM/PTM/TK lengths 347/567/16 bytes, ruling out the unchecked nil-decode hypothesis for those replies. Native Virtualization config mapping proves offset 0x560 is SHA-256 of the complete host build string, not the custom QEMU MLB label; native host serial/build live at 0x650/0x670, absent from the old QEMU structure. In explicit external-identity mode, the experimental patch now supplies the same truthful Linux uname release as the identity archive, hashes it before register truncation, and reads the real DT serial previously corroborated against Apple ADT. Guest identity and legacy behavior remain byte-identical. Production-function sanitizer, atomicity/layout/reset tests and full build pass. Native SHA-256 instruction-slice fixtures match independently. Activated after a stopped-VM paired backup. Live QMP register reads match the expected build digest, host serial and host build fields. The controlled 15:13:16 MDT account attempt still ends ADIProvisioningEnd -43004. Native host-attribute sharing defaults to zero, so the zero host-os-information template does not establish a missing required property. This contract correction did not resolve sign-in.

- **2026-11-11 BAA material succeeds; actual account login reaches a separate ADI failure.** All observed software-PKA operations now succeed, including direct P-384 signing. Native akd receives usable two-certificate BAA material, builds its attestation and reports a new BAA cache hash; its next network request returns HTTP 200. One owner-authorized account login was attempted through System Settings. It ends with Verification Failed before two-factor authentication: provisioning-start succeeds and both provisioning HTTP requests return 200, but `ADIProvisioningEnd` returns -43004 (wrapped as AKAnisetteError -8004/-8001). No further credential submissions have been made. Read-only checks show correct clocks, writable/free guest storage and a present but empty ADI store; these do not establish the cause. The MobileGestalt SysCfg warning also occurs on the physical Mac and is not evidence for a speculative fix. Account sign-in remains incomplete.

- **2026-11-11 Native ordinary digest signing prepared.** Added subsystem-5/type-5 direct signing for the observed 32-byte context and 48-byte digest, using the same native deterministic P-256/P-384 key derivation and no extra hashing. Eight native public-fixture curve/digest combinations, 76 helper checks, malformed/fragmented wire cases, and original message/SIKA async regressions pass under sanitizers. A real maximum-size 104-byte P-384 DER signature fits a 156-byte reply; one byte less returns a complete error rather than truncation. Direct-mode flag 0x2 and unsupported host-slot requests fail explicitly. Full build passes; activation and overall Apple attestation remain pending.

- **2026-11-11 Real SEP digest signing and guest SIKA replies verified live.** With the VM stopped and reflink backups taken, atomically installed the reviewed operation-2 provider, preserving the old executable under `/var/lib/omvm/provider-rollback-20261111`. A real UID-1000 client verified both message and prehashed signatures against the root-owned public pin, rejected double hashing, and received EINVAL with no signature for 31/33-byte digests. The restarted guest now receives successful type-6 DER signatures (70–72 bytes), plus successful query 8. Its next unsupported request is direct software-key signing, type 5, carrying a 32-byte context and 48-byte digest. Overall Apple attestation and account sign-in remain unverified.

- **2026-11-11 Native SIKA hardware-signature bridge prepared.** Guest identity, chip revision and measurements 0/2/3 now succeed live; the next request is type 6 with signer flags 0x16, attested flags 0x78d8, two 32-byte contexts and a 48-byte nonce. Added exact native TBS serialization, SHA-384 followed by the native last-32-byte normalization, and asynchronous provider operation 2 for the existing certified host key. Native ordinary/host fixtures, fragmented buffer/socket tests, signature failures, timeout/reset/capacity cases, and the original message-signing certificate-pair regression all pass under sanitizers; full build passes. No direct ordinary-key signing operation is added. Provider deployment/live hardware probe and overall attestation remain pending.

- **2026-11-11 Measurement query succeeds live; guest identity response prepared.** The guest now receives a successful measurement-0 reply and advances to type 10. Added the native 25-byte guest identity response from the validated initialization message's ChipID and ECID, with state cleared on device reset. It does not use physical-host facts or the host-key identifier. Added bounded type-6 metadata diagnostics that omit context and nonce contents. Native-format/lifecycle/bounds sanitizer checks and the full build pass; activation and overall attestation remain pending.

- **2026-11-11 Live public-key requests succeed; native measurement/security queries added.** After the guest restart, both the certified-host and ordinary P-384 public-key requests return status zero. The next observed unsupported request is software-PKA type 2 (measurement). Added its native 52-byte reply for selectors 0–6, plus native fixed AON/security and chip-revision queries 8/9. Thirty-six actual-production sanitizer cases pass against native serialized fixtures, malformed descriptors, fragmented buffers and short capacity; full QEMU build passes. Guest ID and SIKA/signature operations are not part of this batch. Activation/overall attestation remain pending.

- **2026-11-11 Native software PKA contracts reconciled with public fixtures.** Expanded `docs/identity-swpka.md` with exact ordinary selector semantics, primary Apple corecrypto derivation sources, direct digest signatures, complete SIKA packed fields and digest serialization, guest ECID provenance, and two-stage digest normalization. Native public-seed software fixtures match independent P-256/P-384 derivation and SIKA hashes; native ephemeral software P-256 host-slot signatures prove a final 48-byte digest is equivalent to its first 32 bytes, with no extra hash. No actual guest contexts, account credentials, persistent private keys or SEP state were used by these fixtures. Native serialized query fixtures additionally confirm all seven valid measurement selectors return identical 52-byte 0xff data, plus exact AON/chip-revision/guest-ID reply layouts. These native probes did not modify the running VM.

- **2026-11-11 Native deterministic software public-key bridge verified.** Added the exact HMAC-DRBG SHA-256 plus legacy little-endian scalar derivation for observed 32-byte contexts, with P-256/P-384 selected by the native curve flag. Four native public fixtures and four fixtures using the guest's actual selector/flag metadata match. Twenty-seven actual-production wire sanitizer cases pass, including the existing certified-host slot, fragmented buffers, malformed descriptors and P-384 reply capacity. The full QEMU build passes. Activation and overall attestation remain to be checked; no account credentials submitted.

- **2026-11-11 Distinct prehashed SEP signing operation prepared.** Added provider operation 2 for an exact 32-byte digest, passed unchanged to the existing pinned hardware key; operation 1 still hashes message bytes once. Both share the same bounded worker. Independent OpenSSL digest verification and fourteen root tests pass, including rejection of double-hashed signatures, invalid digest lengths, truncated frames and concurrent operations. Source only: the running provider remains unchanged until guest traffic requires this operation. No account credentials submitted.

- **2026-11-11 Native host signing succeeds; guest software-PKA support is the remaining observed gap.** Corrected the signature response to carry both `Value.RKSignature` and `Value.RKCertification`, as required by the native guest parser. Raised the bounded async deadline to 15 seconds after measuring ~1.88 seconds per serialized SEP operation (three queued calls exceed five seconds). The native guest now reports `VMHostBAASigning Error=0` at ~3.78/5.67 seconds; the overall attestation request still receives Apple error 29 (ECC signature verification). The captured boot contained a discarded subsystem-5/type-1 software-PKA handshake. Implemented that exact native 36-byte query response in external mode, verified against the native Mac and ten sanitizer cases. Live negotiation now succeeds and exposes real subsystem-5/type-3 public-key requests (29/13/1 descriptor, 32-byte contexts); the exact certified-host getter is being implemented next. No Apple Account credentials have been submitted. Disk/aux/identity reflink snapshots preserve both the pre-provider and pre-PKA-query states.

- **2026-11-11 Root SEP signing provider exercised live; persistent files prepared.** Added a bounded Unix-socket provider for the existing SEP key: allowlisted peer UID, bounded framing/deadlines, one hardware worker, pinned-point validation, and independent OpenSSL verification of every signature. Startup requires the new existing-only attestation export to load and match the persisted key before legacy signing is allowed; no key-generation fallback. Eleven tests pass, including bad startup exports, old-driver rejection, protocol errors and socket permissions. A real UID-1000 client received a 71-byte SEP signature and verified it independently; unsupported operations were rejected. The hardened transient provider is active. A persistent unit, root-owned executable/config and root-private public-point pin are installed and pass systemd unit verification, but persistent activation awaits completion of the QEMU connector test. Per-VM `identity-provider.json` now preserves the four provider bindings through domain regeneration; normal-domain output stays byte-identical, and incomplete configurations fail before XML output. The earlier user edit enabling `ID_BO4` remains unstaged. Account sign-in remains unverified.

- **2026-11-11 Reboot completed; genuine Linux SEP host certificate issued and verified.** The owner-approved reboot returned on the same vmapple kernel; the macOS guest restarted and SSH reports 27.2 with the correct clock. The SEP module required its initial `modprobe` (with new-keybag provisioning disabled), then reported attached/open/present/usable. Both new APIs work live: committed UIK attestation (1200 bytes), its matching 65-byte target public point, and 65-byte SIK/UIK public data. Physical-host facts passed ADT/manifest/live-DT corroboration again. The SEP signed the exact request-property XML, independently verified by OpenSSL. A genuine same-key BAA request returned two PEM certificates: the leaf matches the existing SEP key and the chain verifies against the native Apple BAAUCRT root. Issuance used TLS hostname verification with Apple Root CA G3 downloaded from Apple's PKI site; no system trust-store changes. The public chain is archived in the owner's Touch ID vault; private material stays in SEP. The actual Linux host build was omitted rather than a macOS build being fabricated. VM integration and Apple Account sign-in remain unverified.

- **2026-11-11 Owner-approved host reboot initiated.** Cleanly stopped the `macos` guest under its agent lock and confirmed it is shut off, then requested a host reboot to activate the built/reviewed SEP export module. Previous module remains in `~/vm-artifacts/rollback-sep-export-20261111`. Post-boot driver and guest checks are pending; no successful certificate issuance or Apple Account sign-in is claimed.

- **2026-11-11 Identity certificate reply bounds corrected while reboot approval is pending.** The experimental PCI BAR was only 4096 bytes, but tunnel certificate replies were copied at offset 4096, beyond the allocation. Enlarged it to 16384 bytes, added compile-time scratch-window coverage and runtime copy bounds, and kept wide receive-room arithmetic saturated for short buffers. An isolated AddressSanitizer harness using the actual production copy blocks reproduced a 918-byte heap overflow before the change and passed five boundary cases after it. The full QEMU build passes; the running VM and SEP driver remain untouched. Account sign-in and genuine certificate issuance remain unverified.

- **2026-11-11 Genuine SEP export prepared; Apple Account sign-in remains unverified.** Built and reviewed two bounded administrator-only APIs for committed UIK `(2,2)` attestation plus its matching existing host key public point, and SIK/UIK system public data (`oskgp`, system keybag `-1`). Existing references are loaded read-only; no key creation, replacement or persistence is allowed by these paths. Compilation, module linking/modpost, ABI checks and six userspace boundary tests passed. The matching module is staged at the existing active-kernel module path with a rollback copy under `~/vm-artifacts/rollback-sep-export-20261111`; the running module is untouched, and a host reboot awaits owner approval. A live pre-activation export returned ENOTTY and created no output directory, as expected. Correction to earlier notes: the saved “UIK” sample is actually GID `(3,1)`; committed UIK returns an encrypted version-2 envelope, also seen on the native Mac. The new APIs' live firmware behavior, host certificate issuance, and account sign-in are still unproven.
- **2026-11-11 Host identity signature bug fixed and independently verified.** The experimental QEMU device now returns ECDSA/SHA-256 X9.62 DER for the request's `Value`, avoids argument-order-dependent plist lengths, and returns an error on signing failure. Native macOS Security.framework rejected the old raw 64-byte signature, accepted the corrected 72-byte DER signature, and rejected it for a different challenge. The full QEMU build passed; the currently running VM retains its previous process. Parent source commit `bf2a772`.
- **2026-11-11 Physical host facts verified from the original boot ADT.** `share/identity-host-facts.py` reads the validated read-only `adt` MTD region, obtains the five required physical-host facts, corroborates ECID against the boot manifest and serial against Linux's live DT, and writes only a new private JSON file. Real host collection passed both corroborations without printing identifiers. `docs/identity-issuance.md` records the typed two-key native request, system-key operations, API gates and the remaining server-policy unknowns. No identity from the reference Mac or guest is substituted.

- **2026-11-11 Host identity certificate: AVH shape and Apple property extensions.** The identity XPC service connects to its peer, then runs a local host-certificate validator before it will keep the UserClient: `SecCertificateCopyKey`, `CFEqual(hostPublicKey, leafPublicKey)`, and `DeviceIdentityCopyCertificateProperties` for `1.2.840.113635.100.10.1`, whose `udid` must equal MobileGestalt's `UniqueDeviceID`. A bare `CN=AVH` self-signed leaf satisfied none of it. The device now signs a leaf from a per-VM CA: `CN=AVH` issued by `CN=AVI`, CA:FALSE, keyUsage, SAN, SKI/AKI, the `udid` extension as `SET{PRIVATE "udid" -> SEQUENCE{IA5String, OCTET STRING <20 raw bytes>}}` and `1403` under `1.2.840.113635.100.8.7`. A plist in the extension is rejected; it is FourCC-tagged ASN.1. Both private keys persist (`.pem`, `.pem.ca`) so the chain is byte-identical across boots, where before a fresh key was minted every boot because `OMVM_IDENTITY_KEY` was never set. The local validator is now silent; Apple's server still returns `400 // 123 (75:RKProperties: VMHostIdentityCertificate is incorrect)`, so the remaining suspect is the unaudited non-Apple intermediate. Device commit `3fe87fd`.
- **2026-11-11 Identity device: 4/4 and 4/6 finally decode; next wall is a missing XPC peer.** The identity replies never parsed. `ProtocolMessageKernel.cpp:114` hands the reply buffer to `decodeAndTakeOwnership`, which decodes a transport header, then the message, then each buffer, so the 20 raw UDID bytes were never a message. Serving a serialised 68-byte message instead (header `02000000 04000000 <type> 44000000`, `mlen 16`, `blen 20`, `nb 1`, `boff 0`, the iovec and the data) takes `ProtocolMessage.cpp:142` and every downstream assert to zero, and the service walks on to set `UDID` on the platform expert and write `AppleVirtualPlatformSealedRegisters`. Two traps cost real time: the payload buffer was fixed at 64 bytes while the message is 68, so the overflow stamped `buffer_len` back to 20, and using the request's `transportLen` as a cap makes the caller ratchet its next descriptor down by 2 every round — that ratchet *is* the retry loop. Both types settle at zero requests once the payload is a message and the outer body is `boff 0 / mlen 16` (4/6) and `boff 8 / mlen 17` (4/4). Remaining wall: the identity XPC service looks up `com.apple.AppleVirtualPlatform.IdentityService.peer`, gets XPC error 3 "No such process", and cancels, so `AppleVirtualPlatformIdentityUserClient` is never created and 4/2 never runs; `akd` then fails with "Failed to create BAA info" and "Failed to create host key signature" and loops on `AKAnisetteError -8007` with `StartProvisioning` 503. Notable: `akd` reaches the kext path directly, so this is not a guest-entitlement problem. State in `research/identity/STATE-2026-11-11.md`.
- **2026-11-11 Root unlocked without a passphrase.** Root LUKS2 (`nvme0n1p7`) now has a 4096-byte random keyfile in slot 0, `/boot/omarchy/luks-key` (0400 root), and the cmdline carries `rd.luks.key=a731e475-…=/omarchy/luks-key:UUID=4f4d5801-424f-4f54-8000-000000000001`. The passphrase stays in slot 1, so a human can still unlock if the keyfile or Boot partition is lost. This is the design the vendor already shipped for: `/usr/lib/systemd/system/run-systemd-cryptsetup-keydev\x2droot.mount.d/omarchy-mac-encrypt.conf` documents `rd.luks.key=…:UUID=<Boot>` and `keydev-root-umount.service.d` orders the unmount before switch-root. Only `/etc/default/grub` needs editing (Limine derives `KERNEL_CMDLINE` from it); regenerate with `omarchy-mac-boot-update`, not `grub-mkconfig`, which is not installed. Backups: `/etc/default/grub.pre-lukskey-20261111`, `/etc/default/limine.pre-lukskey-20261111`. Trade-off: the key sits on the unencrypted Boot partition, so disk access now implies root; enrol a TPM later if one ever exists on this platform.
- **2026-11-10 SEP verified working from Linux; attestation ACL support added.** On the host, `apple_sep` attaches and the enclave key store opens: `diag/` shows `attach=attached endpoints=12 keybag=present keystore=open matching=usable abi=2`, and `/dev/sep-bio` `IOC_ATTEST` (0xc0b0b10a, 176-byte struct) returns a real DER P-256 signature with the 65-byte point, which `openssl pkeyutl -verify` accepts; the key is stable across calls and comes from `/var/lib/aurora-sep-refkey.bin`. Found doing so that the module did not build at all: `der.rs` lacks the `RV::Bool` variant `key.rs` already used, so a `Bool` variant and DER BOOLEAN tag were added, and the machine ref-key can now be created with an ACL permitting attestation (`refkey_attest_acl=1`), since `acl` is only settable at create time. The SEP attaches once per boot, so the probe reload left it unattached: a host reboot activates the change. Ops `oc`/`osgn`/`oecd` exist; `oa` attestation-chained needs the SEP device attestation key, still absent.
- **`macos` slow / input late: QEMU's main thread pinned by `identity_fdt_poll`, plus two
  orphaned host loops; fixed without a VM restart.**
  - **Measured 17:28.** QEMU main thread (tid = pid) 96 % CPU; HMP `info status` 9-16 ms
    but every ~4th call 1430-1445 ms; `IDFDT` lines in the QEMU log ~7/s. Two orphaned
    `python3` processes from 2026-11-09 each held a full host core: pid 20996 (19:18, an
    `MLB` scan of the live `disk.img` whose `seek(s-4)` re-reads forever, 22 h CPU, 241 TB
    read) and 132240 (23:04, an empty `for va in range(...)` over a kernel VA range, 18 h
    CPU). Killed both. Guest itself idle (load ~1, 92 % memory free, no thermal warning).
  - **Cause.** `hw/vmapple/apple-identity.c` (uncommitted identity research in
    `build/qemu-sb-bdifw/src`) arms `identity_fdt_poll` on a 50 ms `QEMU_CLOCK_REALTIME`
    timer at realize. After try 500 every tick runs `identity_dt_find` / `memmem` / 4-byte
    loops over all 16 GB of guest RAM on the main loop under the BQL (~1.4 s), never finds
    its target (no `IDFDT set`/`stop`/`gave up` in any log), and re-arms for up to 6000
    tries (~2.5 h at that speed). Input BHs, the monitor and vCPU MMIO exits wait on it.
    Every new QEMU process restarts it, which is why `/tmp/nofdt` "stopped working" after
    each restart (it had been removed again each time).
  - **Fix.** `/tmp/nofdt` touched under the lock at 17:30 and **left in place**: main
    thread 96 % -> 0-0.3 %, HMP 9-12 ms x20 (max was 1445), IDFDT lines 0/s. Durable: the
    timer is now armed only when `OMVM_IDENTITY_FDT` is set in the domain's `qemu:env`
    (not set by `libvirt-domain.py`); rebuilt `qemu-sb-bdifw/build/qemu-system-aarch64`
    17:31 (sha 124ecc20). The running QEMU keeps the old binary until its next start.
    Rollback: `~/vm-artifacts/rollback-fdtpoll-20261110/` (old binary sha 78cee06a +
    `apple-identity.c` as of 17:08).
  - **`overrun write ... > max:4194304` spam** is `audio/pwaudio.c`
    `capture_on_process`: the PipeWire mic stream pushes 940 B per 5 ms quantum into
    QEMU's 4 MB capture ring while nothing drains it, one `error_report` per quantum (on the
    PipeWire thread, cheap). Bursts 16:31-16:33 and 17:13-17:16, none since. It is what
    "truncates" the log: virtlogd rotates `macos.log` at 2 MB and keeps 3
    (`macos.log.0..2`), so a burst rotates away the identity traces within minutes.
  - **QEMU restarts 17:00-17:09** were `reason=destroyed` (virtqemud SIGTERM = `virsh
    destroy`, monitor tainted `custom-monitor`) once a minute during the identity rebuild
    loop, not the watchdog or a crash. Guest panics at 15:31/15:36/15:59/16:07 are all
    `DebuggerXCallEnter: Debugger synch pending on cpu 0` (debug boot-args era; a vCPU
    stuck behind the BQL during a 1.4 s scan would also miss that cross-call).
  - fps / pointer latency not re-measured: `lat.py` injects input and another agent was
    driving the guest.

- **Apple Account sign-in script (`/tmp/w/signin.sh`, `research/signin/`): review findings.**
  - `.` was mapped to QMP qcode `period`, which QEMU does not have (`qapi/ui.json` uses `dot`), so
    the email reaches Apple without its dot (17:29 run). `pw.sh` also passes `shift-2` as one
    qcode. Use `dot` and split chords.
  - Each keystroke was 2-4 separate `virsh qemu-monitor-command` processes; with `identity_fdt_poll`
    holding QEMU's main loop (~97 % CPU, about one HMP call in five stalls ~1.4 s) typing an email
    takes 30-60 s, and tool timeouts killed runs silently at "type username". QMP abs input needs no
    host window focus or geometry (0..32767 maps to the guest display).
  - The 17:00-17:09 QEMU restarts were `virsh destroy` (`reason=destroyed`) from the apple-identity.c
    `dbg*.py` edit/rebuild loop (each ~10 s after a dbg script), not signin.sh.
  - Credentials are hardcoded in `research/signin/signin.sh` and `pw.sh` (gitignored); move them to
    a 0600 file. A stdin-fed `virsh` shell keeps keystrokes out of `ps`.

- **Identity device: the service now starts and the guest completes the handshake
  and UDID exchange.** The wall recorded in `research/identity/KICK.md` (no
  descriptor is ever added, because `IdentityService::start` dies on
  `_hostKey->getLength()`) is broken.
  - **The actual blocker was the host key.** `AppleVirtualPlatformARMPE::start`
    fetches it over the config DMA mailbox at GPA `0x4ffff8`; without it the
    service asserts and nothing is ever queued, which is what every earlier trace
    showed. The mailbox only exists when `OMVM_MAILBOX=1` is in the domain's
    `qemu:env` (it is not part of the default domain), and `_hostKey` must be the
    **20 raw UDID bytes**, not an opaque blob - the kext hex-expands them and
    `getLength()` is asserted non-zero.
  - **Second blocker, the reply header.** A reply's `version` is 1 for the `4/1`
    handshake and **2 for every other type** (`0xfffffe0008a9310c`), and
    `transportLen` must equal `32 + messageLen + bufferLen`. A `4/3` reply also
    has to match the fixed descriptor `{messageLen 16, buffersOffset 0,
    numBuffers 1}` exactly. Sending version 1 is what kept the service from ever
    starting.
  - **Result.** Status walks `00 01 03 0b 0f`, the driver arms the queue, the
    device serves `4/1` then `4/3`, the guest echoes the UDID back inside its next
    request, `AppleVirtualPlatformIdentityService` registers and matches, and the
    guest moves on to `4/4` + `4/6`.
  - **Still open.** `IdentityUserClient` stays 0 and the `4/4` + `4/6` exchange
    loops, so no consumer opens the device yet and sign-in is not reached.
  - Full contract and proof addresses: `research/identity/PROTOCOL-REPLY.md`.

- **Identity: an unrelated stage1 panic was corrupt NVRAM, not the device.**
  Both SysCfg variable regions of `aux.img.trimmed` were zeroed, which halts iBoot
  stage1 at `0x7006c4c0` (the `hint #0x45; b .` panic stub). Restoring
  `aux.img.trimmed.pre-kdp2-20261110` fixes it, and the stock `qemu-sb` build
  halts at the same PC, so the identity device was never the cause. Restore the
  clean image (`/tmp/aux.pre-dbg`) before each boot: the booter clears
  `boot-args` in place.

- **Identity device correctness fixes, all found by measurement.**
  - `ecid` was never wired from the machine into the device, so the UDID was 16
    zero bytes; `create_identity()` now sets it from `vms->uuid`.
  - Feature bit 40 (`VIRTIO_F_RING_RESET`) leaked in from the generic virtio-pci
    defaults and Apple's driver does not know it; it is cleared now.
  - `APPLE_IDENTITY_CONFIG_SIZE` had lost its definition while still being used.
  - The mailbox was mapped with `qdev_new` + `sysbus_mmio_map`, which asserts
    because `qdev_new` alone never realizes; it uses `sysbus_create_simple` now.
  - The mailbox region overlapped the `pcie-ecam` alias, so the ECAM alias stops
    one page short.

## 2026-11-09

- **`macos` ssh dead (port 42541 open, no banner): the guest clock was in 2083, fixed
  inside the guest.**
  - **Symptom.** slirp `info usernet` showed every connection to 10.0.2.15:22 in
    `SYN_SENT`; inside the guest (driven over VNC with HMP `sendkey`) sshd was listening,
    Remote Login on, firewall off, but `netstat -an` held the same connections in
    `SYN_RCVD` and `netstat -I en0` showed Opkts frozen at 155 while Ipkts grew: RX worked,
    virtio-net TX was dead (ping 10.0.2.2 and curl out failed too). `date` said
    Sat 18 Sep 2083. The vCPU PC `...21b4` that looked like a spin is the idle loop: the
    GUI ran, uptime 12 min, load ~1.
  - **Cause.** After the battery-empty power-offs the Asahi RTC (macsmc-rtc) had lost the
    time: this host boot started at 1970-01-01T10:05:15 UTC and NTP corrected it only at
    18:48:59. `macos` started in that window; the vmapple `avp-rtc` device returns
    `QEMU_CLOCK_HOST` (host system time, `-rtc base=` does not apply to it), so the guest
    saw RTC ~36326 s. Its `timed` then learned NTP time and stored
    `com.apple.System.rtc-offset` = +1794238993 s in NVRAM plus a TDTF sample in
    `/var/db/timed/com.apple.timed.plist`. That boot was fine; every boot after it (from the
    19:22 OOM kill on) read the correct RTC, added the offset and landed in 2083, and with
    that clock the TX queue stalls.
  - **Not the QEMU binary or the serial/MLB work.** A control boot of the same domain on the
    saved 18:12 build (the one that served ssh at 18:54) reproduced it; clearing the clock
    state alone fixed it on that build.
  - **Fix (guest):** `sudo nvram -d com.apple.System.rtc-offset`, move
    `/var/db/timed/com.apple.timed.plist` away (kept as `~killerisya/timed.plist.bad-20261109`),
    `sudo date <now>`, `sudo killall timed`, clean shutdown + `omvm start`. Deleting only the
    NVRAM key is not enough: timed rewrites it from its plist at the next boot. Verified:
    `omvm ssh macos` -> 27.2 / killerisya at 20:47, 20:48 and, after a clean reboot into
    local mode, 20:50 and 20:51; rtc-offset now -2 s.
  - **Host side:** `hwclock` now matches the system clock and `save-hwclock.service` writes
    it back at shutdown (added by another agent). It cannot help after a full battery
    drain; a guard in `ensure-vm` that waits for NTP sync (or a year >= 2026) before
    starting a VM would. Not done yet.
  - State left: `build/qemu-sb-bdifw/build/qemu-system-aarch64` is the 18:12 build
    (`~/vm-artifacts/rollback-ssh-20261109/`), the serial/MLB build is parked beside it as
    `qemu-system-aarch64.omp-serial-mlb-20261109`; `macos` in local mode, watchdog on; iPhone
    not on the host bus.

- **AGENTS.md: "Agents: read this first" quick start for a stalled VM** (stray QEMU,
  live-disk mounts, memory/battery, lock + agent-notes.log, `omvm restart`, banner vs open
  port, firmware-loop check). An agent had hand-launched QEMU twice and mounted the live
  disk (systemd-oomd killed it at 67 GB). The full runbook is the owner's `omvm-vm-ops` skill.

- **GPU gaps of `macos`: ProRes exports fixed; Metal 3 and the M2 scaler are the guest's
  limits, with evidence.**
  - **Green ProRes (FCP GAP-1): fixed.** `patches/graphics/metal2vulkan/0004` (metal2vulkan
    `87c471ce` on `latency-20261109`): a 4:2:2 texture over a surface is a shadow with a
    decoded twin, decoded on the CPU from the surface's bytes at each bind of a sampled view
    that finds them changed. 10 s 1080p clips through `AVAssetExportSession`, compared with
    their sources (`share/bench/gputest.sh`): ProRes 422 / 422 HQ / 4444 went from 1.5 s of
    solid green (SSIM 0.00003) to 5-13 s with SSIM 0.979-0.981, level with the H.264 control
    (0.979); HEVC 10-bit 4:2:0 and 4:2:2 were never affected (0.980). The fcp.md repro (30 s)
    exports in 11.4 s (2.6x realtime), 17.0 s with the CoreImage effects; no refusal in the
    VM's log since, VM stays up. reims-vgpu is unchanged (rebuilt and QEMU relinked).
    Rollback: `~/vm-artifacts/rollback-gpu-20261109/`.
  - **Metal 3: not ours to give.** reims-vgpu already tells the guest Apple9 (device-info key
    37 = 1009, key 44 = 0x1f; read back from the guest driver's `_deviceInfo` with
    `share/bench/pvinfo.m`), and the 27.2 driver still answers Apple5, `featureProfile` 6, no
    ray tracing, mesh shaders, sparse textures, function pointers or dynamic libraries. Guests
    on Apple's own hosts report the same Apple5 without Metal3 (Tart 1032, Godot 124859, riff
    76). Nothing advertised, nothing changed; details in docs/graphics.md.
  - **M2 scaler: the 27.2 guest has no driver for it.** `AppleM2ScalerParavirtDriver.kext` on
    disk is codeless, and the boot kernel collection has neither the class nor a
    `0x1a0b106b` match (it does have `AppleVideoToolboxParavirtualization`, 106b:1a03); the
    "resets" seen earlier were QEMU's own. `OMVM_M2SCALER=1` stays opt-in for other guests.
  - **The watchdog killed its own VM after every host reboot.** `omvm-vm@NAME.service` is a
    oneshot; its first `virsh` call spawned virtqemud inside the unit, QEMU under it, and
    systemd ended both when the unit finished ("terminating on signal 15 from pid ...
    (systemd)", then `reason=crashed` every minute). `stream-host.sh ensure-vm` now starts
    virtqemud in `omvm-virtqemud-PID.scope`. Seen working after the 18:22 power loss (battery
    empty) and the 18:47 reboot.
  - Guest Metal after the change (`metalbench`): 0.29 ms compute round trip, 0.051 ms per
    pipelined 1080p pass, 319 GB/s, 1.22 TFLOP/s, 2.5 ms first use of a new pipeline: as before.
  - Open: the iPhone is not on the host's USB bus since the 17:31 reboot (`omvm usb list`:
    none), so it is not attached; FCP itself is still behind the Apple Account wall.

- **`macos` local-mode latency: profiled stage by stage; reims-vgpu's share is ~1.4 ms; a
  refused 4:2:2 dispatch no longer kills the VM.** reims-vgpu got a run-time trace gate and
  tune file (`patches/graphics/reims-vgpu/0002`; local mode sets `REIMS_VGPU_TRACE`,
  `_TRACE_GATE`, `_TUNE`) and window-stage events. Medians at 120 Hz (docs/graphics.md
  "Pointer latency" has the table): move -> guest NSEvent 1.3-1.6 ms, -> guest present
  5.5-6.5 ms, -> `vkQueuePresentKHR` 7.0 ms; the window copy ~0.9 ms of GPU; Hyprland + DCP
  commit -> scanout 11-13 ms for any client (`floor2.py`, presentation-time). Not kept: 240 Hz
  guest modes (slower to present), IMMEDIATE/tearing (Hyprland refuses tearing at scale 2),
  Hyprland `new_render_scheduling`/`async_commit`/cm/fp16, CPU deep idle off. Guest Metal
  (`share/latency/metalbench.swift`): 0.25 ms per small command buffer round trip, 0.05 ms per
  pipelined 1080p pass, ~320 GB/s, ~1.2 TFLOP/s, 2.8 ms for a new pipeline's first use;
  display link 120.0/s.
  - End-to-end on screen with the grim rig was 19.3 ms (p90 30.3) at 15:40 and 30.7-34.1 ms
    (p90 ~60) at 16:50, after the iPhone passthrough joined the tablet's xHCI and the guest
    ran Xcode; the stage timings up to the host present did not grow, and Hyprland's own
    floor showed 30 ms spikes in the same hour, so the grim number tracks the box's load and
    the rig's own screencopy cost more than this change.
  - FCP GAP-1 (docs/fcp.md): the dispatch that samples a 4:2:2 `BGRG422` IOSurface plane
    through an `RGBA8Unorm` view (no decoded twin for a surface-backed texture, image made
    without `SAMPLED`) is now skipped with an error line (`reims-vgpu/0003`,
    `REIMS_VGPU_SOFT_UNSUPPORTED_STATES`); the export finishes, but those frames come out
    green. `metal2vulkan/0003` logs what the refused view is. `REIMS_VGPU_LOG=error` is now in
    every domain so such lines reach the VM's log.
  - The M2 scaler (`apple-m2scaler-pci`, which VideoToolbox would use instead of that Metal
    kernel) starts on the host (kernels made on the M1 Max) but the 27.2 guest's
    AppleVirtIOPCITransport only resets it and never attaches; `libvirt-domain.py` offers it
    behind `OMVM_M2SCALER=1`.
  - Rollback: `~/vm-artifacts/rollback-latency-20261109/` (the QEMU binary and reims dist from
    before; HEADS lists the commits). QEMU itself has no change (relinked only).

- **Xcode → iPhone from the `macos` guest: everything but the signing identity
  (docs/xcode-device.md).** Phone `connected` with DDI services usable and Xcode's
  6.8 GB symbol copy for iPhone18,1 27.2 complete over the patched xHCI; a SwiftUI
  test app (`share/ios-hello/`) builds unsigned for `generic/platform=iOS`, and
  `devicectl device install app` reaches the phone's `installd`, which only rejects
  the signature. Xcode's Apple Account sign-in is not viable: `akd` fails anisette
  provisioning for every client (`AKAnisetteError -8007`, `ADIGetIDMSRouting
  -45061`, no body from Apple's start-provisioning call). Guest prepared for manual
  signing: the owner's Xcode-managed team wildcard profile (lists the phone, valid to
  2027-10-06) copied in, Apple WWDR G3 intermediate added to the login keychain.
  New `share/ios-run-on-device.sh` (guest `~/bin`): automatic signing (optionally
  with an App Store Connect API key; flags checked, a throwaway key gets a 401 from
  ASC), else unsigned build + `codesign` with a local identity and matching profile,
  then `devicectl` install + launch; the fallback path was tested with a self-signed
  identity up to the phone's profile check. Waiting on the owner to export the
  Apple Development .p12 (route and steps in the doc).

- **iPhone in the `macos` guest is usable: QEMU xHCI fix + host-side USB mode
  switch.** After pairing, devicectl showed the phone `unavailable`: macOS posts NCM
  receive buffers as two-TRB TDs, and on a short packet QEMU's `xhci_xfer_report`
  skipped the IOC event of the TD's last TRB, which macOS waits for (4 receive
  completions per NCM function, 0 packets in `netstat -I anri0`, `remoted` connect
  timeouts, empty `usbmuxd` list). Patched `hw/usb/hcd-xhci.c` to send that event
  (commit `760d1d0d29` on `sb-kvm-bdif-write`, copy in `patches/usb/`), rebuilt in
  `build/qemu-sb-bdifw/build` (old binary `qemu-system-aarch64.pre-xhci-ioc`), two
  `macos` restarts under the lock. Now: devicectl `connected`, paired, wired, tunnel
  connected, Developer Mode on, DDI services available; Finder sidebar and
  `xctrace list devices` list it; `usbmuxd` lists it. The stuck mode switch is now
  avoided instead of reset: `share/usb-apple-mode.py` switches the phone to Mac mode
  on the host (0xc0 0x52) before `device_add`, so it re-enumerates natively; the
  watcher re-attaches the same way (no more `usbreset`, which once knocked the phone
  off the bus), and `omvm usb trust` pauses it while the Trust/passcode screens are
  up (a re-attach dismissed the owner's passcode screen once) and for 90 s after.
  Tested: detach → attach → `connected` again in 25 s; `trust` on a paired phone
  returns at once. Proof: Finder sidebar screenshot (host grim) on R2.

- **`omvm usb list|attach|detach|trust`: hot-plug host USB devices into a running VM
  (docs/usb.md); an iPhone reaches the `macos` guest and pairs.** `attach` runs
  `device_add usb-host,...,hostbus=B,hostport=P` on the domain's existing `qemu-xhci`
  (`omvm-usb`) over `virsh qemu-monitor-command --hmp`: no restart, port-based so the
  phone's re-enumerations are followed, plus a udev rule
  (`/etc/udev/rules.d/70-omvm-usb.rules`, OWNER=user) so session QEMU can open it.
  iPhone 17 Pro (iOS 27.2, 05ac:12a8, 10 Gb/s on the host, 5 Gb/s in the guest):
  macOS 27.2 lists it in `system_profiler SPUSBHostDataType` and `ioreg`, sets
  configuration 6 (PTP, usbmux, Apple USB Ethernet, two NCM), and `devicectl list
  devices` showed it `available`, `pairingState: unpaired`. `omvm usb trust` started
  `devicectl manage pair` (the Trust prompt) with host alarm + notification + guest
  `say` every 5 s; the owner tapped Trust within 20 s and the state went `paired`.
  Found on the way: macOS switches the phone's USB mode (vendor requests 0x45/0x52)
  and expects it to drop off and come back; passed through, the host never sees the
  drop and the phone answers every request with EPROTO (usbmon -71) in configuration
  1. A host `usbreset` re-enumerates it in the new mode; `attach` now starts a
  watcher unit (`omvm-usb-watch-VM-BUS-PORT`) that does that when it sits in
  configuration 1 for 12 s (max once a minute, 3 times). Apple devices are attached
  with `guest-reset=off`. Open: after pairing the phone stayed `unavailable` in
  devicectl (no reply on the restricted NCM link `anri0`, `remoted` connect timeouts,
  `usbmuxd` "device connected" but an empty device list); a second `usbreset` a
  minute after a good one left the phone off the bus (USB 2 fallback, -71), which
  needs a physical replug. During the test `macos` crashed once on a reims-vgpu
  fatal from the FCP export (not USB; agent-notes.log).

- **Final Cut Pro in `macos`: runs, but stops at the Creator Studio paywall; one GPU
  gap kills the VM.** Apple dropped the 90-day FCP trial (apple.com/final-cut-pro/trial
  301s to /final-cut-pro/, "Try it free" is the App Store's Creator Studio, which needs
  an Apple Account). The owner's App Store FCP 12.4 copied into the guest verifies
  (`spctl`: Mac App Store), launches and draws its UI with no Metal errors, then asks
  for $12.99/month and "Sign in to your Apple Account", which this VM can't do; import,
  playback, effects and export in FCP are untested. The same work through AVFoundation
  + a Metal CIContext (colour + Gaussian blur + overlay) exports 30 s of 4K H.264 to
  1080p H.264 in 26.6 s, 4K H.264 in 30.2 s, ProRes 422 in 27.2 s; VideoToolbox is
  software-only (no hardware decode for H.264/HEVC/ProRes, no
  `AppleM2ScalerParavirtDriver`). A 10-bit ProRes 1080p -> H.264 export killed the VM:
  `reims-vgpu: fatal: platform call dispatchThreadgroups:threadsPerThreadgroup:: ...
  Format VK_FORMAT_R8G8B8A8_UNORM, usage: SampledImage` (GAP-1, repro and suggested
  fix in `docs/fcp.md`). Guest GUI driven from the host (grim + ydotool relative
  motion), since guest `screencapture` has no TCC grant over SSH.

- **`omvm perf always|ac|off`: the governor switch is a setting.** Default `always`
  (performance while a local-mode VM runs, on AC and battery), kept in
  `~/.config/omvm/perf`; `OMVM_LOCAL_GOVERNOR` still overrides it. `ac` installs a udev
  rule on the Mains supply's change event that starts `omvm-power.service` (user), which
  runs `omvm perf apply`. `omvm-gui` has the same three-way switch under Display ("CPU
  performance (local mode)", with the governor and power source now). `omvm help` now
  prints the whole header, not lines 3-24. Tested with `macos` running local: `off` put
  back schedutil, `always` set performance on all three policies, `ac` on AC set
  performance; with `OMVM_AC_ONLINE=0` set in the user manager, `udevadm trigger
  --action=change` on `macsmc-ac` ran the unit and put back schedutil, `=1` performance
  again; `omvm stop macos` restored schedutil, `omvm start macos` with `off` left it,
  and switching to `always` while running set performance. `omvm-gui --selftest`
  passes with the new perf checks.

- **`macos` pointer lag: the CPU governor; the guest now boots in macOS's default
  scaling.** Measured with a uinput mouse on the host (`/tmp/lat.py`, not in the
  repo) against `~/bin/latprobe` in the guest (a full-screen window that turns
  white or black on the mouse-moved event, clocks matched over its SSH pipe), and
  `grim` polling one pixel (~9 ms a sample): with `schedutil` a move reached the
  guest's NSEvent in 10 ms median (p90 17) and the screen in 51 ms (p90 58); the
  host-drawn cursor showed in 26 ms (p90 34). With the `performance` governor on
  all three clusters: 1.4 ms (p90 2.8), 20 ms (p90 28.5) and 13 ms (p90 17); the
  guest's display link ran 120.0/s with frame gaps of 8.40 ms p95, 8.54 ms max.
  schedutil leaves the cores at low clocks between the guest's bursts, and each
  move waits for them to ramp. Not the cause: the cursor (SDL's colour cursor,
  drawn by Hyprland; reims draws it into the image only while the guest moves it
  on its own), the swapchain (MAILBOX, 4 images), the tablet (1 ms bInterval).
  Hyprland's `render:direct_scanout = 1` changed nothing (the window was never
  scanned out) and was put back to 0.
  - `omvm`'s libvirt hook now sets the `performance` governor while a local-mode
    VM runs (its QEMU has `REIMS_VGPU_WINDOW=1`; checked in `/proc`, since a hook
    must not call libvirt) and puts the saved governors back when the last one
    stops (`$XDG_RUNTIME_DIR/omvm-governor`). `OMVM_LOCAL_GOVERNOR=keep` skips
    it. Needs passwordless sudo.
  - Scaling: `omvm-display-follow` set each new size's native 1x mode, so local
    mode ran 3024x1964 at 1x (tiny UI). It now sets the mode macOS marks default
    (`kDisplayModeDefaultFlag`: 1512x982 points at 2x here), else native 1x, and
    keeps the last size it acted on in `~/Library/omvm/display-follow.state`, so a
    scaling picked in System Settings survives reboots until the host offers
    another size. The agent is now ad-hoc signed as `org.omvm.display-follow`
    after a rebuild; launchd refused its first spawn
    (`OS_REASON_CODESIGNING`) on 27.2.

- **`macos` (27.2, local mode) runs at ~110 fps again; the lag was `macos27`
  sharing the GPU, not the 60 Hz cap.** The domain carried
  `REIMS_VGPU_MAX_REFRESH_HZ=60` from `libvirt-domain.py` (the headless
  remote default, there since the first virt-manager commit), but the
  steelbrain reims that `qemu-sb`/`qemu-sb-bdifw` link never reads it (only
  qemu-fleet's reims does): the guest's modes all read 120 Hz (`ioreg`
  `SyncRate` 7864320) and a CADisplayLink probe (`~/bin/fpsprobe` in the
  guest, NSView display link at 120, animating a layer) ticked 117-120/s.
  What reached the window was the problem: with `macos27` running headless
  (QEMU at ~200 % CPU, host swap 15-28 GB, kswapd busy) reims-vgpu counted
  12-26 guest frames/s, max gaps 120-280 ms, window GPU 16-47 ms per frame.
  `omvm stop macos27` alone brought it to 100-120/s (avg ~110), max gaps
  17-38 ms, window GPU 1.1-1.5 ms, swap 1 GB. Both VMs on the one AGX queue
  starve the local window; keep only one running for a smooth desktop.
  - `share/libvirt-mode.py` now sets `REIMS_VGPU_MAX_REFRESH_HZ` to the
    panel's rate in local mode and back to 60 in remote, so a reims that
    honours the cap also offers 120 Hz locally. `omvm virt macos` rewrote the
    domain (backup `domain-local-pre-120hz-20261109.xml`). Measured after,
    `OMVM_STATS=1`, probe at 3024x1964: guest 99-116 frames/s (first second
    76), window presents the same, window GPU 1.2-1.5 ms.
  - The guest now logs in by itself after a reboot (`sysadminctl -autologin`
    plus `/etc/kcpassword`; `sysadminctl` printed error 22 and wrote only the
    `autoLoginUser` key, so `kcpassword` was written by hand).
  - Still open: the guest runs 3024x1964 at 1x (scale 1.0), not the HiDPI
    1512x982 the docs expect; `mds` indexes after each boot (~47 % CPU).

- **`macos` showed a black Reims window: it was stuck in a macOS 27 upgrade
  reboot loop; it now runs 27.2.** At 09:44 the guest user (uid 501, with
  admin authorization, from Software Update in the guest; automatic installs
  are off) started the 27.2 (26B123) update, and at 09:45:34 the VM rebooted
  into it. `macos` had no `guest_major`, so it ran `build/qemu-sb` and the
  26-era AVPBooter, and first-stage iBoot panicked and reset about twice a
  second from then on (QMP `GUEST_CRASHLOADED`/`RESET`, PC `0x100000`,
  `Duplicate block info` spam from virtqemud, no disk write since 09:45:34).
  The user's restarts at 14:16 looped too, since the aux NVRAM holds
  `boot-command=upgrade`. Not caused by `macos27` running beside it or by
  today's rebuilds: `qemu-sb` was relinked at 09:23 (patch 0004,
  `apple-vendor-cap` default off, same behaviour as before) and never linked
  the 14:05 iOS Simulator library.
  - Fix: `echo 27 > ~/vm-artifacts/vms/macos/guest_major`, `omvm virt macos`
    (local mode kept: `REIMS_VGPU_WINDOW=1`, 120 Hz, the `-wl` Mesa), destroy
    and start. Reflink backups first in `~/vm-artifacts/vms/macos/`:
    `disk.img.pre-27-20261109`, `aux.img.trimmed.pre-27-20261109`,
    `domain-pre-27-20261109.xml` (the 26 domain).
  - ssh answered 2 minutes later on 27.2 (26B123); post-upgrade migration then
    ran behind the Apple logo in the Reims window. `macos` and `macos27` both
    run `build/qemu-sb-bdifw` now. docs/graphics.md "macOS 27 updates"
    describes the failure.
  - First boot on 27.2: the lock screen ignored keys (the known
    first-boot-after-update state; `macos` had no system input source), and
    at 14:36 the guest turned its display off (pmset log) although
    `displaysleep` is 0, which froze the Reims window on its last frame until
    `caffeinate -u` over ssh. Copied macos27's
    `/Library/Preferences/com.apple.HIToolbox.plist` (ABC) into `macos`,
    rebooted the guest (`shutdown -r now`, back in 20 s), and the password
    typed with HMP `sendkey` logged in. After two Setup Assistant panes
    (Liquid Glass, Welcome) the desktop shows in the 120 Hz Reims window.

- **The iOS Simulator runs in `macos27`.** Xcode 27.2 (27B52) was already in
  the guest; `sudo xcodebuild -runFirstLaunch` and `xcodebuild -downloadPlatform iOS`
  (no Apple ID, ~8.3 GB at 10-20 MB/s over Wi-Fi) installed the iOS 27.2
  runtime (24B8117). Metal in the guest is "Apple Paravirtual device"
  (families apple1-5 and mac2, no apple7/metal3); a swiftc compute + render
  test gave exact results. `simctl boot` of iPhone 17 took 38 s cold, 11 s
  warm; the home screen, Settings and a SwiftUI test app (built with
  `xcrun -sdk iphonesimulator swiftc`, ad-hoc signed, `simctl install`) render
  correctly, and Xcode 27's Simulator window (now `Device Hub.app`,
  `Xcode.app/Contents/Applications/DeviceHub.app`) shows the device live.
  - Before the fix, the first `simctl io screenshot`, app launch or Device
    Hub frame killed QEMU: `reims-vgpu: fatal: platform call drawPrimitives...
    the bind state was refused: Unsupported(SamplerBicubicFilter)`. A
    diagnostic build traced it to `bind/heap.rs`: a cubic sampler in an
    argument buffer beside a fragment stage, which metal2vulkan refuses.
    `patches/graphics/metal2vulkan/0002` holds such a sampler as a linear
    VkSampler (a logged degrade, `REIMS_VGPU_CUBIC_ARGUMENT_SAMPLERS_LINEAR=0`
    restores the refusal); reims rebuilt (`cargo xtask dist`, ~10 min
    incremental) and `build/qemu-sb-bdifw` relinked. Only macos27's QEMU
    links it; the `macos` VM's `qemu-sb` binary was not relinked.
  - Speed: CADisplayLink in the app reports 60 Hz, but a serialized Metal
    command buffer round trip is ~85 ms (11.8 full-screen 1206x2622 passes/s
    waited one by one, 672/s pipelined), and `simctl io recordVideo` caught
    37 frames in 10.8 s. Usable for UI checks and tests, not smooth.
  - Something else on the host restarted macos27 within ~30 s after each
    crash (not `on_crash`, which is `destroy`).
  - Backups: VM dir `~/vm-artifacts/vms/macos27.pre-iossim-20261109/`
    (reflinks, before the runtime install); the old `libreims_vgpu.a` and
    `qemu-system-aarch64` in `~/vm-artifacts/rollback-iossim-20261109/`.

- **`macos27` has sound, and `omvm virt` makes macOS 27 domains.** QEMU
  3a14b4eadb on `sb-kvm-bdif-write` (exported as `patches/graphics/qemu/0007`)
  adds `x-ascending-capabilities` to `virtio-sound-pci` and moves the
  capability reordering into `virtio_pci_link_capabilities_ascending()`
  (virtio-net uses it too). macos27 now has `virtio-sound-pci,streams=2` on
  PipeWire again: `system_profiler SPAudioDataType` lists "Apple Virtual Sound
  Device" (2 in, 2 out, mic input), and `afplay Glass.aiff` in the guest showed
  up on the host as the `macos27` output stream (pw-record on it: peak 11759 /
  4901, silent otherwise), linked to the speakers' convolver; the input stream
  is linked to the MacBook mic.
  - `guest_major` (a file in the VM dir, `27`) makes `omvm virt` use
    `build/qemu-sb-bdifw` (`OMVM_QEMU27`), the 27.2 AVPBooter
    (`OMVM_AVPBOOTER27`) and the four capability switches. `guest_env` no
    longer picks the 27 AVPBooter for other VMs (the glob could sort it first).
    Regenerating macos27 with it gave the hand-made domain minus the serial /
    `-d` debug args; macos27 boots from it to the desktop.
  - The bdifw build had no `pc-bios/keymaps` (only `qemu-system-aarch64` was
    built), so QEMU refused to start with its own `-L`; `ninja` of the 32 keymap
    targets fixed it.
  - Login window keyboard: could not reproduce. After a cold boot with autologin
    off, after `pkill loginwindow`, and with the HIToolbox prefs removed, VNC
    typing and HMP `sendkey` both logged in. The failing first boot after the
    OTA had no input menu and SecurityAgent logged "No selected input source
    for user", so it looks like a first-boot-after-update state. Added a
    system `/Library/Preferences/com.apple.HIToolbox.plist` (ABC) in the guest.
    Autologin is back on.
  - Backup before the sound change: `~/vm-artifacts/vms/macos27.pre-sound-20261109/`
    (27.2.1, reflinks). The `.failed-vcap-20261109` images and `~/m27work`
    scratch are deleted.

- **`macos27` is on macOS 27.2.1 (26B131)** and boots to the desktop
  (autologin `aquarat`, Setup Assistant done: Apple Account skipped, no
  FileVault, updates download-only). Two more QEMU fixes on top of the bdif
  write fix below, now committed on `sb-kvm-bdif-write` in
  `build/qemu-sb-bdifw/src` and exported as `patches/graphics/qemu/0005`
  (bdif writes, f7865b7924) and `0006` (`ascending-capabilities`,
  3b875bb399); `0004` (`apple-vendor-cap`, 07279a4a8e) is committed with
  them because `0006` builds on it.
  - The earlier iBEC panic (`99180f7bfe1a22b:991`) did not come back.
    Disassembly of the 27.2 iBoot (`Firmware/all_flash/iBoot.vma2.RELEASE.im4p`,
    linked at 0x7006c000) shows it: the boot-args builder panics when the
    boot type stage 1 handed over is 7 (iBEC) and boot-args lack `rd=`, i.e.
    the upgrade command booted a kernel without its update ramdisk. On the
    27.2.1 attempt a gdbstub breakpoint (`gdbserver` over HMP + `hbreak`)
    showed boot-args `rd=md0 -progress -restore` and no panic.
  - The update ramdisk then hung: all CPUs in the 27 kernel, zero aux/root
    I/O for minutes. Cause: macOS 27's virtio transport needs the PCI
    capability list in address order. `apple-vendor-cap=on` fixed the probe
    but, powered off mid-ramdisk, iBoot fell back to 26.4, which then lost
    its data-protected files (ssh key auth failed) because the vendor cap
    also disables transport encryption. Disk and aux were restored from the
    pre-install reflink backup and `0006` adds `ascending-capabilities`
    (reorder only). With it on both vmapple-virtio-blk devices plus
    `x-ascending-capabilities=on` on virtio-net, 26.4 booted with its data
    intact, `softwareupdate -i ... --stdinpass -R` applied 27.2.1 in about
    5 minutes, and ssh/sudo work on 27.2.1. virtio-sound-pci was removed
    from the domain (no reorder switch yet).
  - HMP `sendkey` and VNC keys did not reach the 27.2.1 login window (the
    mouse did); on the desktop the keyboard works. Autologin
    (`/etc/kcpassword` + `autoLoginUser`) was set over ssh instead.
  - Backups (reflinks): `~/vm-artifacts/vms/macos27.pre-ota2721-20261109/`
    (26.4 with 27.2.1 downloaded); `disk.img`/`aux.img.trimmed`
    `.failed-vcap-20261109` in the VM dir (the vendor-cap fallback, safe to
    delete). Serial logs `logs/serial-20261109-{vcap,asc}.log`.
  - The `macos` VM and `build/qemu-sb` are untouched. To roll out: `git am`
    `0005` + `0006` onto `build/qemu-sb/src` (`0004` is already there),
    `ninja`, then add `ascending-capabilities=on` to both vmapple-virtio-blk
    devices and `x-ascending-capabilities=on` to virtio-net before updating a
    guest to 27 (the new switches default off, so 26 guests are unchanged).

- `macos27` boots again (macOS 26.4 25E246, login window), but the 27.2 OTA
  did not apply. It was never an AVPBooter hang: with a serial console
  (`-chardev file,...,path=~/vm-artifacts/vms/macos27/logs/serial-*.log`
  `-serial chardev:omvmser0` as qemu:arg) the guest showed the OTA's
  precommitted 27.2 iBootStage1 (mBoot-20457.41.3, `illb` at aux offset
  0x220000) panicking in a reset loop (`iBoot Panic: 64383f188f1c630:234`,
  54 resets in 30 s; PC in 0x7007xxxx-0x700bxxxx is iBoot, not the ROM).
  Disassembly of the dumped iBoot (`pmemsave 0x70000000`) shows it bumps a
  counter (3 -> 4) in the aux disk's `virt_pmu_sram` record (`UMPv`) before
  it loads the next stage, and panics when the write fails. QEMU's vmapple
  BDIF backdoor dropped every write (`/* Not needed, iBoot only reads */`).
  Fix: a patched QEMU that implements BDIF writes and asks for write
  permission on the backdoor's drives (without the permission it aborts on
  `child->perm & BLK_PERM_WRITE`). Built separately so `macos` keeps its
  binary: `build/qemu-sb-bdifw/` in apple-macos-arm64-vm-guest (reflink copy
  of qemu-sb/src, branch `sb-kvm-bdif-write`, uncommitted; diff in
  `build/qemu-sb-bdifw/bdif-write.patch`). With it the 27.2 iBootStage1
  writes the counter, resets, then loads the 27.2 iBootStage2 ("Remote boot",
  the upgrade iBEC), which panics too (`99180f7bfe1a22b:991`, iBoot's NVRAM
  code); iBoot then falls back to the 26.4 chain and macOS 26.4 boots.
  `boot-command` is now cleared (not settable from the guest: "not
  permitted"); softwareupdate now offers 27.2.1 (26B131, 11 GB).
  macos27 now runs the 27.2 host's AVPBooter
  (`artifacts/firmware/AVPBooter.vmapple2.macos27.2-26B123.bin`, mBoot-20457.41.3,
  sha256 c9c4fdb8…bec8a, copied from Virtualization.framework on uzi's Mac,
  macOS 27.2 26B123) and the patched QEMU; with the boot chain back on
  26.4 both AVPBooters boot it. Serial and `-d guest_errors,unimp`
  (`logs/qemu-d-20261109.log`) stay on in macos27's domain. Backup of the
  pre-change VM dir + both XMLs: `~/vm-artifacts/vms/macos27.pre-avpbooter-20261109/`
  (reflinks). Next for 27.x: catch the iBEC panic (memory dump at the
  panic, e.g. a second `-qmp` socket and a stop on "iBoot Panic" after
  "Remote boot") on the next OTA attempt.

- `macos27` (26.4 clone) hangs in AVPBooter after the macOS 27.2 OTA's own
  apply-reboot. The OTA finished downloading ~09:55; the guest rebooted at
  09:52:04 (aux.img.trimmed and disk.img mtimes) and never came back: CPU0
  loops in firmware (PC around 0x100000 / 0x700a2xxx), CPUs 1-7 stay at PC=0,
  zero I/O on both the aux and root virtio drives (`virsh qemu-monitor-command
  macos27 --hmp "info blockstats"`; `domblkstat` is useless because the disks
  come in via qemu:arg), VNC frame black. vmapple QEMU does not survive an
  in-guest reboot, so a fresh process was tried: `virsh destroy macos27` +
  `virsh start macos27` at 10:38 (the REIMS_VGPU_* / VK_DRIVER_FILES env lives
  in the domain XML as qemu:env, so plain start reproduces the config). Result:
  same hang. After 5 min: aux and root reads 0 bytes, CPU0 in firmware, other
  CPUs never started, VNC shows "Guest has not initialized the display (yet).",
  no ssh banner on 43757. Firmware is AVPBooter.vmapple2.mBoot-18000.161.10
  (26-era); untested guess is that the 27.2 boot objects/policy staged in aux
  need newer AVPBooter. Left running in that state; no retry, no reinstall.

## 2026-11-08

- Mesa `agx-16bit-flat-varyings` now credits aquarat: the change is byte-identical
  to his `patches/mesa/0001` + `0002` (apple-macos-arm64-vm-guest 9b62919, 636da1e;
  MIT). Message-only amend (tree unchanged) adds a body line and
  `Co-developed-by: Aaron Scheiner <blue@aquarat.co.uk>`; 2b37de4b -> 64c25aa0,
  force-pushed to github.com/sapoepsilon/mesa. Hash references updated.
- **LICENSING.md** added (linked from the README's Legal section): omvm is
  GPL-2.0-or-later; the PAC kernel patch is steelbrain's unlicensed work and is
  fetched from aquarat's repo at build time, not included (steelbrain#1); each
  `patches/graphics/` patch is offered under its upstream's licence (Mesa MIT,
  QEMU GPL-2.0-or-later, reims-vgpu and metal2vulkan GPL-2.0-or-later OR
  LGPL-3.0-or-later); `share/bake-xcode-dmg.sh` is derived from aquarat's
  GPL-2.0-or-later `bake-xcode.sh`; no Apple software is included.
- **Guest user renamed `aquarat` -> `killerisya`** (macOS 26.4 VM `macos`; short
  name, home `/Users/killerisya`, full name; UID 501 unchanged). `dscl` RecordName,
  RealName, `admin` GroupMembership, `/etc/sudoers.d/killerisya` (NOPASSWD; the
  `aquarat` file is gone) and loginwindow `RecentUsers`/`FirstLogins` were changed over
  SSH. The home move and `NFSHomeDirectory` are blocked by TCC on a live system
  (SIP on; `mv /Users/aquarat` = "Operation not permitted" even as root over SSH or
  from a LaunchDaemon), so they ran in a KVM single-user boot (create-account.sh's
  method: `apfs_boot_util`, bootstrap opendirectoryd, `mv`, `dscl -create`) on a
  reflink copy that was then copied back. display-follow LaunchAgent rebuilt for the
  new home. Backups (reflink, VM off): `~/vm-artifacts/vms/macos/{disk.img,aux.img.trimmed,vm.json}.pre-rename-20261108`
  + `domain-pre-rename-20261108.xml`; `disk.img.failed-rename-20261108` = a first
  attempt (record renamed, home not moved) before it was restored from backup.
- **`OMVM_GUEST_USER`** (default `aquarat`): the guest account `omvm` (ssh, run,
  stop, display-follow, clipboard, setup -> upstream `GUEST_USER`, Xcode bake),
  `stream-host.sh` and `omvm-clip.py` log in as. `bin/omvm` and `stream-host.sh`
  fall back to `~/.config/omvm/gui.env` (Sunshine/systemd don't read `~/.bashrc`);
  the libvirt hook exports it. This host: `OMVM_GUEST_USER=killerisya` in
  `gui.env`, `~/.bashrc` and `~/.config/libvirt/hooks/qemu`.
- Mesa branches published on GitHub while the gitlab.freedesktop.org account
  awaits verification: https://github.com/sapoepsilon/mesa (no official GitHub mirror exists, so not a fork;
  full history pushed from `~/src/mesa-upstream-mr`, remote `gh`).
  `hk-fragment-shader-interlock` a3561cde, `agx-16bit-flat-varyings` 64c25aa0;
  compare against upstream main: `https://github.com/sapoepsilon/mesa/compare/1f935e49...<branch>`.
- **`omvm start|stop|restart|pause|resume NAME`** for libvirt VMs (`bin/omvm`,
  `cmd_power`; `omvm start NAME IMAGE` / `omvm stop NAME` of a throwaway run are
  unchanged). stop: watchdog timer *and* its service off first (they used to race
  the shutdown: the GUI stopped the timer and sent `virsh shutdown` in parallel and
  left a running `ensure-vm` alone), resumes a paused guest, then `vm_shutdown`.
  start: `virsh start` (or resume) + watchdog on. pause/resume: `virsh
  suspend|resume`. `vm_shutdown` now treats `in shutdown`/`paused` as still on.
- **`omvm-gui` rework**: power buttons go through the CLI above (no duplicated stop
  sequence); Start / Pause⇄Resume / Stop / Restart show a spinner + "Stopping…" in
  the button and state row, every button is disabled while an action runs, state is
  polled every 2 s during an action and every 10 s idle (polls no longer flash the
  header spinner), success/failure as Adw toasts (stderr's last line; "Force off"
  on a failed stop) + an `omarchy-notification-send` desktop notification for
  start/stop/restart/mode. Confirm dialogs for Stop, Restart, mode switch.
  Omarchy look: colors from `~/.local/state/omarchy/current/theme/colors.toml`
  (accent, backgrounds, red/green/yellow) as libadwaita CSS variables, dark/light
  from its `mode`, the monospace font (`fc-match monospace`, JetBrainsMono Nerd
  Font), follows `omarchy theme set` live; `--install` adds
  `o.window("^dev\\.omvm\\.Gui$", { tag = "+floating-window" })` to
  `~/.config/hypr/looknfeel.lua` (875x600, floating, centered). Esc / Ctrl+W
  close, Ctrl+R / F5 refresh. Open desktop uses `omvm show`. Resolution only in
  remote mode. Fixes: `--install` from a shell without `OMVM_*` wiped
  `~/.config/omvm/gui.env` (now merges); subprocess timeouts kill the whole process
  group; PATH gets `~/.local/bin` for launcher starts; paired-client parsing
  tolerates missing keys and marks disabled clients. `omvm-gui --selftest` checks
  the read-only paths headlessly (19 checks pass).
- Tested in the owner's session (local mode) through AT-SPI clicks + grim:
  Pause→Resume (paused/running), Stop (confirm, spinner, off in ~15 s), Start
  (guest SSH in ~9 s), Restart (off at +14 s, running at +15 s), mode switch confirm
  → Cancel (stays local), Esc closes. VM left running in local mode, watchdog on.

- **Switching keys** (`share/hypr-macos-vm.lua`, installed into
  `~/.config/hypr/bindings.lua`): Ctrl+Alt+M toggles macOS ⇄ Omarchy (from the VM
  to the most recently focused other window, by Hyprland's focus history; from
  anywhere else to the VM's window or VNC viewer, else `omvm show`);
  Ctrl+Alt+1..5 leave the VM for workspace N. Lua bind options
  `dont_inhibit = true` (the old `p` flag: past reims-vgpu's
  keyboard-shortcuts-inhibitor, which SDL takes while input is captured) and
  `submap_universal = true` (past the VNC "macos-vm" submap). Verified with
  ydotool in local mode, uncaptured and captured: Ctrl+Alt+M and Ctrl+Alt+1 left
  the captured window and capture was released. Remote mode not exercised live.
  On this host keyd maps Caps Lock (hold) to Control and turns the physical left
  Control off, so Ctrl here is Caps Lock. wtype input does not trigger Hyprland
  binds; ydotool through keyd does. Never synthesize Ctrl+Alt+F-keys: they
  switch VTs (one test did; `sudo chvt 1` brought the session back).
- **`omvm show [NAME]`** and launcher entry "macOS" (`share/omvm-macos.desktop`,
  copied to `~/.local/share/applications/`): start the VM if it is off, then
  focus reims-vgpu's window (local) or a VNC viewer, opening
  `vncviewer -Shared=1 127.0.0.1:PORT` if none (remote).
- **Guest sound**: virtio-snd moved from `-audiodev none` (output only) to
  `-audiodev pipewire,id=snd0,out.stream-name=macos,in.stream-name=macos` with
  `streams=2`, and `XDG_RUNTIME_DIR` is now kept in both modes so QEMU finds the
  user's PipeWire. `libvirt-domain.py` writes it; `libvirt-mode.py` upgrades older
  definitions on every mode switch (and on its own: `libvirt-mode.py sound`); the
  remote backups in `~/Work/omvm-backups/` were upgraded too (originals:
  `*.pre-sound.xml`). Guest after a restart: "Apple Virtual Sound Device" with
  2 output and 2 input channels. `afplay Ping.aiff` in the guest showed up as a
  running `qemu-system-aarch64` stream (44.1 kHz) into `audio_effect.j314-convolver`
  → `RawSpeakers`; a guest AVAudioEngine capture opened a `qemu-system-aarch64`
  input stream linked from `omarchy_asahi_mic` but read zeros over SSH (TCC
  microphone permission, which a headless SSH process does not have; the first
  GUI app that records will prompt). Both streams close when the guest stops.
- **Host sound** was not broken: speakers (asahi convolver → RawSpeakers,
  speakersafetyd running) verified by playing a 660 Hz tone and finding it in a
  recording from the built-in mic.
- **"Process crashed: mpv"**: Omarchy's screen-recording webcam overlay
  (`omarchy-capture-screenrecording --with-webcam`, mpv on `av://v4l2:/dev/video1`)
  segfaulted every time the overlay closed: FFmpeg's v4l2 input hands out frames
  that point into the camera's mmap buffers, the device unmaps them on close
  while mpv's VO still uploads the last frame (crash in `pl_tex_upload`, on Vulkan
  and on OpenGL alike). Fix in `~/.config/mpv/mpv.conf`: an auto profile for
  `av://v4l2:` paths that appends `vf=lavfi=[copy]`. Reproduced 2/2 before,
  0/2 after.
- **`omvm-gui`** (new, optional): a GTK4 + libadwaita window (`bin/omvm-gui`,
  PyGObject; `sudo pacman -S --needed python-gobject gtk4 libadwaita`) that only
  shells out to `omvm`, `virsh -c qemu:///session`, `systemctl --user`, `hyprctl`,
  `vncviewer` and `lsusb`. Sections: VM state + Start/Stop/Restart (stops the
  `omvm-vm@macos.timer` watchdog first, then `virsh shutdown`, guest
  `sudo shutdown -h now` after ~10 s, like `vm_shutdown`), Open desktop (local:
  focus `class:reims-vgpu`; remote: `vncviewer localhost:59xx`), display mode
  toggle with a confirm dialog (`omvm mode`), resolution (`omvm res`), Moonlight
  hosts :47989/:48989 on the Tailscale IP with paired client names (names only,
  read from `sunshine_state.json`), Pair (`omvm remote [-i macos] pin PIN NAME`),
  USB (`omvm usb attach|detach VID:PID macos`) and shared folders
  (`omvm share add|remove PATH`): both greyed out with "not available yet" until
  `omvm help` lists them. A log pane shows each command and its output (lines
  that look like credentials are hidden). `omvm-gui --install` adds the
  "macOS VM" launcher entry, links `~/.local/bin/omvm-gui`, and saves the shell's
  `OMVM_*` variables to `~/.config/omvm/gui.env` (the launcher doesn't read
  `~/.bashrc`). Installed `usbutils` (this M1 Max lists no USB devices: lsusb
  exits 1). Tested on a temporary headless Hyprland output (VM untouched): state,
  mode, hosts, clients and lsusb render and log; Stop/Restart/mode switch/Open
  were not clicked.
- **`omvm mode local|remote`** (`omvm mode` prints the current one; default VM
  `macos`). local: no libvirt `<graphics>` (QEMU `-display none`), reims-vgpu's
  SDL3/Vulkan window borderless full screen on eDP-1 (`REIMS_VGPU_WINDOW=1`,
  `REIMS_VGPU_WINDOW_REFRESH=120`, resolution `3024x1964@254`), libvirt
  autostart off. remote: the previous XML exactly (VNC + Sunshine), autostart
  on. The mode lives in the libvirt definition (`share/libvirt-mode.py`), so it
  survives reboots. Watchdog `omvm-vm@NAME` now runs `stream-host.sh ensure-vm`
  (local: waits for the Wayland socket); the VM's Moonlight tiles fail in ~25 ms
  in local mode with "macos is in local mode … run 'omvm mode remote'".
  Remote XML backup: `~/Work/omvm-backups/macos-remote-2026-11-08.xml`.
- The window needed Mesa with Wayland WSI: the stack's Mesa is built with
  `-Dplatforms=` ("Installed Vulkan doesn't implement the VK_KHR_wayland_surface
  extension"). Built the same tree (26.2.6 + 3 patches) with
  `-Dplatforms=wayland` into `~/opt/mesa-honeykrisp-sb-wl` (source copy
  `~/src/mesa-honeykrisp-sb-wl`); only local mode uses it.
- Local mode measured: window on eDP-1 at 1512x982 pt x2 = 3024x1964 px; guest
  display timing 120 Hz (ioreg `SyncRate` 7864320 = 120 x 65536; remote is
  60 Hz); `REIMS_VGPU_STATS`: 86-93 guest frames/s = window presents/s at the
  macOS login window (one ~235 ms idle gap a second, 120 Hz pacing otherwise),
  window GPU 1.2-1.3 ms/frame. Remote mode: 54-60 fps in the guest, ~33 fps
  through VNC. Box left in remote mode; tiles and guest SSH verified.
- Commit history: Co-Authored-By/Claude trailers stripped from all omvm commits
  (force-pushed); the old history is on `backup/pre-coauthor-strip-20261108`.
- Mesa upstreaming: branches in `~/src/mesa-upstream-mr` (worktree off
  `~/src/mesa-honeykrisp-sb`, on upstream `main`): `hk-fragment-shader-interlock`
  a3561cde and `agx-16bit-flat-varyings` 64c25aa0. VK-GL-CTS
  `dEQP-VK.fragment_shader_interlock.*` (576 cases): Pass 128, Fail 64,
  NotSupported 384 (without the patch: NotSupported 576). The 64 failures are
  MSAA 4x pixel-interlock cases, still open. Waiting on a
  gitlab.freedesktop.org account (sign in with GitHub) to open the MRs; drafts
  in `docs/upstream-drafts.md`.
- OpenBubbles (iMessage client) runs under muvm + FEX with the Mac's hardware
  info; blocked at iCloud Terms acceptance, which crashes its webview (pending).
- Apple ID sign-in inside the macOS VM: blocked. The guest has no Secure Enclave
  identity on a Linux host, so Apple Account/iCloud sign-in fails.
- Stream performance: Sunshine encodes in software only (libx264, no hardware
  encoder on Asahi). Measured fps by stream size:

  | Stream | fps |
  |---|---|
  | 3840x1080 | 60 |
  | 5120x1440 | ~53 |
  | 7680x2160 | ~24 |

  VNC (QEMU `ui/vnc.c:61`, 30 ms refresh) caps the guest feed at ~33 fps.
- VM always on: linger enabled, libvirt autostart on, `omvm-vm@macos.timer`
  restarts the VM within a minute if it dies (`omvm remote keepalive macos`).
- Sunshine second instance for the VM (`omvm remote -i macos`, base port
  48989, Moonlight host `macos` at 192.168.50.74:48989) with per-device tiles
  (Pixel Fold, Fold cover, iPhone, MacBook 14); clients paired.
- Removed the `sb1` VM.
- Joined Tailscale: the host is `omarchy` at 100.72.93.99.
