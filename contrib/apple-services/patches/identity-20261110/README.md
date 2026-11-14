# Experimental QEMU identity and FairPlay sources

These GPL-2.0-or-later snapshots extend the VMApple device model. They are
research source for local integration, not an upstream QEMU submission.

- `apple-identity.c` and `.h`: identity exchange and explicit provider boundary.
- `dma-mailbox.c` and `.h`: mailbox transport.
- `vmapple.c`: machine integration snapshot; preserve existing QEMU licensing.
- `cfg-host-identity.patch`: host build/serial register population; see
  [the register contract](hostcfg-contract.md) for its required baseline.
- `qemu-aes-command-context.patch`: AES command-context corrections.
- `apple-fairplay.c`: OFP1/OFP2 queue-0/queue-3 socket transport. Add the source
  to the QEMU VMApple Meson source set under `CONFIG_VMAPPLE`.
- `virtio-qmp-backend-features.patch`: initialize required QMP backend features.
- `linux-sep-export/`: incremental kernel/public-attestation export patch.

The FairPlay frontend and QMP patch were checked against the QEMU Reims fork
at `760d1d0d29b07341409825eb55e760a52fd7d58f`. The earlier register changes and build wiring are preserved in
[the prerequisite directory](../../prerequisites/README.md), together with the
public patch series that reconstructs that local integration revision. Follow
its destination mapping and patch order rather than copying into an unrelated
QEMU checkout.

For the Linux FairPlay adapter, apply
`../standalone-fairplay/qemu-ofr2-completion.patch` to the frontend as well.
The original OFR1 frontend is also preserved for the historical macOS relay.
The identity source retains experimental `ID*` diagnostics; inspect log output
and keep private identity material outside public logs and repositories.
