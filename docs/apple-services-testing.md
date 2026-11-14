# Manual Apple-services test

Use this checklist for the owner's manual pass before upstream submission.
The first pass exercises the existing working installation. A later pass must
exercise artifacts rebuilt from the published source; record those separately.
The [status and source map](apple-services.md) describes the current limits.

## Before testing

- [ ] Choose the explicit lab VM name; do not rely on a saved default pointing
      at another development VM. Keep other macOS guests shut off.
- [ ] Record the source commit, installed kernel/QEMU/helper versions and guest
      OS/build privately. A Git checkout revision alone does not identify the
      installed binaries.
- [ ] Use AC power, keep the stock kernel available, and confirm the matched
      offline guest/helper backup before any restart or rebuilt-artifact test.
- [ ] Keep the existing signed-in account and its VM-bound helper state.
      Do not sign out, re-enroll, delete a dirty marker or reset Keychain to
      make this checklist green.

From the reviewed checkout, these offline checks do not start a VM, contact
Apple, or activate SEP/AES hardware:

```sh
git rev-parse HEAD
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash -n bin/omvm
bash -n bin/omac
```

Record skipped tests explicitly. Linux root ownership/socket checks are a
separate offline test pass; a non-root success with skips is not full coverage.

## 1. Current desktop and account

- [ ] Inspect the lab in its native window. Mouse targeting, typing, scrolling,
      resizing and switching back to the Omarchy workspace behave correctly.
      Separate human-input results from any automation-only input problem.
- [ ] Lock and unlock the guest once with its local password. The desktop
      returns without losing the session.
- [ ] Open System Settings and observe the signed-in Apple Account; then open
      Messages. Record any account-update notice separately from login state.
- [ ] Exercise the normal Omarchy desktop: terminal, launcher, workspace
      switching, network and audio still work while the guest is running.
- [ ] Record the known suspend limitation. The activated provider vetoes host
      sleep; do not count that as a normal suspend pass or try forced suspend,
      module removal, hardware reset, or kexec as a workaround.

## 2. Fresh iMessage exchange

- [ ] Send a harmless unique message manually to your chosen test contact.
      Confirm iMessage transport rather than SMS forwarding.
- [ ] Confirm it reaches the other endpoint. A locally displayed bubble alone
      does not prove delivery.
- [ ] Have the contact send a new reply and observe it in the lab. Old synced
      history or a read receipt is not inbound-message evidence.
- [ ] Record only pass/fail and a private reference to the run. Do not paste
      contact details, message bodies or conversation screenshots into GitHub.

## 3. Host and helper readiness

Set the variable to the actual lab name before using these read-only commands:

```sh
LAB_VM='your-lab-name'
uname -r
timedatectl show -p NTPSynchronized --value
virsh -c qemu:///session domstate "$LAB_VM"
systemctl is-active omvm-uid1-provider.service omvm-sep-identity.service
systemctl is-active "omvm-fairplay@$LAB_VM.service"
omvm helpers status "$LAB_VM"
```

The last command uses the installed narrow helper status permission. Missing
installation or denied access is a setup result; do not install/reconfigure
services during this manual pass merely to suppress an error.

- [ ] Confirm the reviewed vmapple kernel and synchronized host clock.
- [ ] Confirm the active guest's SEP and FairPlay endpoints are local Unix
      sockets, with the expected Linux services. Review domain/service details
      privately because they can contain machine-specific information.
- [ ] Confirm no runtime Mac relay is needed for the fresh message exchange.
      Closing an SSH controller alone does not prove this; inspect endpoints and
      service provenance. Do not interrupt unrelated Mac work for this check.

## 4. Planned normal reboot

Earlier development evidence already passed this sequence. Repeat it only as
the owner's planned manual test, after saving work and confirming rollback.
Do not reboot automatically as part of the checklist.

- [ ] Save work, coordinate other host jobs, stop the lab cleanly and confirm
      every macOS guest is off. Preserve the matched VM/helper checkpoint.
- [ ] Record the current boot identifier privately. Reboot normally into the
      reviewed vmapple kernel; retain the stock fallback. Kernel selection is
      separate from a permanent default change.
- [ ] After reconnecting, confirm a new host boot and the expected kernel.
      Check shared SEP/UID1 service state before manually starting any helper.
- [ ] Start only the lab through its normal session-libvirt path. Confirm its
      FairPlay instance starts automatically. An inactive per-VM instance before
      guest launch is expected; guest autostart is not part of this test.
- [ ] Confirm unchanged VM identity and matching durable helper state. Unlock
      the guest, observe the signed-in account and obtain fresh authenticated
      service activity. A cached account sidebar is insufficient.
- [ ] Repeat a new send/reply exchange from section 2.
- [ ] Recheck the ordinary Omarchy desktop. Record every manual intervention;
      a manually repaired helper does not count as automatic recovery.

Do not run Omarchy updates during the test. Existing project guidance requires
updates from the stock kernel. On failed startup, preserve the failure evidence
and inspect it before another attempt; follow the [helper lifecycle rules](apple-helpers.md).

## Deferred and separate tests

**CKV:** deferred because encrypted-data trust is unresolved. Enabling the
switch and verifying a contact are distinct future checks. Do not mark either
passed based on iMessage delivery, a simulator login or ordinary account access.

**First-attempt sign-in:** leave the working account signed in. A controlled
fresh flow needs a separately prepared test state, current UI/request
correlation and a fresh authenticated result. Record one valid MFA submission
and one submission for each explicitly required password prompt. The
[phase observer](auth-phase.md) can help distinguish stages; replay does not
prove the retry issue fixed. SMS MFA and a later legitimate local-password
approval remain normal parts of the supported flow.

**Rebuilt artifacts:** reconstruct the exact chains in the
[overlay](../contrib/apple-services/README.md) and
[prerequisites guide](../contrib/apple-services/prerequisites/README.md), complete
the full builds, review logs/policy/artifact pins, then repeat this checklist
after a planned deployment. Never overwrite the active helper or provider to
test a build.

## Result format

Keep a private working copy outside the repository. Share only a reviewed
summary in the review PR:

```text
Source revision:
Installation: existing development build / fresh published-source build
Hardware family and public OS/kernel versions:
Installed artifacts match reviewed build: yes / no / not checked
Offline tests: passed / failed / skipped counts
Native guest input and Omarchy desktop: pass / fail / not tested
Fresh iMessage send and receive: pass / fail / not tested
Linux-only runtime endpoints: pass / fail / not checked
Normal reboot and automatic helper startup: pass / fail / not tested
Fresh account service and send/reply after reboot: pass / fail / not tested
Suspend: known provider limitation / changed behavior separately reviewed
CKV: deferred
First-attempt sign-in: not tested / separately evidenced result
Manual interventions and nonsecret failure descriptions:
Next issue to resolve:
```

Never attach passwords/MFA, account/contact identifiers, serials, raw domain XML,
raw logs, private manifests/checkpoints, VM disks or Apple assets. References to
private evidence can remain in the private copy; omit their paths from GitHub.
