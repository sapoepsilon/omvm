# Genuine host issuance contract: static evidence, 2026-11-11

Reference build: owner's native macOS 27.2 (26B123). Read-only cache and disassembly inspection; no issuance request, key creation, entitlement change, or system mutation performed.

## Request topology

The observed host caller does not send a PKCS#10 CSR. It provides a UIK attestation of its host key to DeviceIdentity, which prepares another reference key for request signing. `_create_baa_info_macos` (0x1B7E3622C) produces the following graph:

- `RKCertification` = original `ClientAttestationData`, the committed-UIK attestation for the host key. Assignment 0x1B7E36A8C–36A9C.
- `RKSigning` = system attestation of the helper signing key. Generation at 0x1B7E3699C, assignment 0x1B7E36AA0–36AB8.
- `RKProperties` = XML plist data described below. Generation 0x1B7E36A28.
- `RKPropertiesSignature` = helper-key ECDSA/SHA256 signature over the exact `RKProperties` bytes. 0x1B7E36AD4–36B0C.

`RKCertificationPub` within the properties is the original host key's public bytes: generic builder selects ClientAttestationPublicKey at 0x1B7E35DA0–35DD0, stores it into properties offset 0x50 at 0x35ED0–35EDC. `RKSigningPub` is the helper public bytes at properties offset 0x58 (0x35EE0–35EEC).

No local check requiring these public keys to differ was found in the property validation and serialization paths. Whether Apple's server permits the same existing hardware key in both roles is unknown. Native code creates a separate helper; that fact alone does not establish server rejection of a same-key request.

## HTTP request

`_baa_request_create_with_body` at 0x1B7E45610 constructs the request; `_createXMLRequest` at 0x1B7E4B018 serializes a root XML property list, uses POST, and sets application/xml and Content-Length.

- Physical-host issuance URL: `https://humb.apple.com/humbug/baa`.
- Guest issuance URL: `https://humb.apple.com/humbug/vmbaa`; selection uses `_is_virtual_machine` at 0x1B7E457F8–45830.
- Root keys: RKCertification, RKProperties, RKPropertiesSignature required; RKSigning optional. `_baa_request_body_create_dictionary` at 0x1B7E452A4. RKSigningPub is not copied as a root HTTP key.
- User-Agent native format: `macOS Device Activator (MobileActivation-1145.40.5.0.4) - <process basename>[#<ClientNameSuffix>]`. Format helpers 0x1B7E4B270 and 0x1B7E4B300. This identifies the observed implementation; no server-side acceptance claim follows from reproducing it.
- `x-jmet-deviceid`: uppercase `%08X-%016llX`, with physical ChipID and UniqueChipID, derived from inner properties at 0x1B7E454D8–45538.
- The HTTP DATA fields contain actual bytes, represented as base64 by XML plist serialization.

## RKProperties

`_baa_rkproperties_create_data` at 0x1B7E4A0C8 builds a dictionary, then serializes with NSPropertyList XML format 100 at 0x1B7E4A54C–4A568. Sign and transmit exactly those same resulting bytes; do not deserialize and reserialize after signing.

The six local serializer requirements (0x1B7E49F40) are UniqueChipID, ChipID, BoardId, SecurityDomain, RKCertificationPub, SIKPub. Native host path additionally supplies the listed fields:

| Key | XML type | Native value/source |
|---|---|---|
| UniqueChipID | INTEGER | physical host MobileGestalt UniqueChipID |
| ChipID | INTEGER | physical host ChipID |
| BoardId | INTEGER | physical host BoardId |
| SecurityDomain | INTEGER | physical host SecurityDomain |
| SerialNumber | STRING | physical host SerialNumber |
| scrtAttestation | INTEGER | 0 in observed host path |
| CertType | INTEGER | 0 = BAA; static constant at 0x1B7E60890 |
| Validity | INTEGER | 7,889,238 in host plugin (0x100002398–239C); units not established here |
| CACert | INTEGER | default 0 |
| OIDSToInclude | ARRAY of STRING | five selectors below |
| RKCertificationPub | DATA | original host-key public representation |
| RKSigningPub | DATA | helper signing-key public representation |
| UIKPub | DATA | `aks_system_key_get_public(2,2,NULL,0,...)`, returned bytes verbatim |
| SIKPub | DATA | `aks_system_key_get_public(1,1,NULL,0,...)`, returned bytes verbatim |
| OsBuildVersion | STRING | native MobileGestalt BuildVersion (0x1B7E34784–347B8) |

The native host plugin passes false NSNumber for scrtAttestation. Generic code converts it with unsignedIntegerValue followed by numberWithUnsignedInteger:, so inner properties contain INTEGER 0 rather than XML false. CACert/Validity receive the same unsigned-number normalization. Without host override, generic Validity is 2880.

Five host OIDs, plugin 0x100002488–24E0:

1. 1.2.840.113635.100.8.3 — DeviceIdentifiers
2. 1.2.840.113635.100.8.7 — DeviceOSInformation
3. 1.2.840.113635.100.8.4 — HardwareProperties
4. 1.2.840.113635.100.8.5 — KeyUsageProperties
5. 1.2.840.113635.100.10.1 — UCRTDeviceIdentifiers

Generic physical path explicitly initializes properties offsets 0xA0/0xA8 (ucrt/scrt) and 0x110 (RequestVersion) to NULL, so those are omitted in this inspected path. It checks the existence of `/System/Volumes/Hardware/MobileActivation/ucrt/ucrt.pem` when scrtAttestation=0, but that does not mean the file contents are included as a property. Do not confuse this per-device artifact with the BAAUCRT root CA.

Image4Manifest/LocalPolicy and other manifest fields can be populated conditionally by requested OIDs and platform boot-policy state. This pass does not establish an authentic Linux OsBuildVersion mapping or which server policy accepts Linux's custom boot environment. Do not borrow identifiers or software claims from the reference Mac.

## System public-key protocol

DeviceIdentity's `_libaks_system_key_get_public` 0x1B7E3BDAC calls the six-argument AKS function, then wraps its output with `NSData initWithBytesNoCopy:length:` without converting the representation. SIK(1,1) call site 0x1B7E3413C–34144; committed UIK(2,2) 0x1B7E34520–34528.

The embedded `_aks_system_key_get_public` 0x1B7E53A40 emits:

    SET { o: UTF8 "oskgp", skt: INTEGER type, skg: INTEGER generation }

No `rk` target is included. Exact constant `0c056f736b6770` at VA 0x1B7E61DA6. `skt` is `0c03736b74`; `skg` is `0c03736b67`. System call uses keybag -1. Raw SEP response framing is below the native IOKit boundary and must be established from Linux's actual reply; this userspace static code only proves that final AKS bytes are used verbatim. Do not substitute an encrypted attestation envelope's ephemeral point for a system public key.

## Native exports and access checks

- `DeviceIdentityCreateClientCertificateRequest(SecKeyRef *outKey, NSDictionary *options, NSError **error)` checks process allowlist at 0x1B7E3ED98. First parameter is OUTPUT, established by copying generated key into it at 0x1B7E3F1EC–3F1F8.
- `DeviceIdentityCopyAttestationDictionary(SecKeyRef key, NSDictionary *options, NSError **error)` requires com.apple.mobileactivationd.spi at 0x1B7E3DB4C–3DB94, plus device-identifiers entitlement for the host's identifier OIDs at 0x1B7E3DCA4–3DCF4.
- `DeviceIdentityCreateClientCertificateRequestWithBody` only formats an existing body; it does not generate missing proofs or issue certificates.

At the time of the initial static pass, no successful standalone Linux issuance was established. Subsequent integration evidence reported by the primary agent: following the approved host reboot, committed UIK attestation and SIK/UIK public-key exports work; an authentic same-key request returned HTTP 200 with two PEM certificates, the leaf matches the SEP point, and its chain validates against the native BAAUCRT root. This is working experimental protocol evidence, not a documented Apple-supported Linux API. VM sign-in remains to be established.

## Authoritative original-host facts

The primary agent located the original Apple Device Tree in phram `/dev/mtd1ro` (approximately 508 KB; `/dev/mtd/by-name/adt` points to mtd1). The read-only parser at `~/Work/macos-vm/linux-aurora/tools/aurora-sep/aurora-adt-extract.py` validates device binding with `check_binding('/dev/mtd1ro', Host())`, then uses `parse_adt(read_device(...))`. The ADT provides `/chosen/unique-chip-id` (8 bytes), board-id/chip-id/security-domain (4 bytes each), root serial-number (32 bytes); `/chosen/manifest-properties/ECID` independently corroborates ECID. Values are little endian. No disk mounts or guest/reference-Mac identifiers are needed.

## Integration: keep three representations separate

### Physical host identity versus host-key-derived guest identity

The physical host certificate extension `1.2.840.113635.100.10.1` property `udid` is compared to physical host MobileGestalt UniqueDeviceID in plugin validator 0x100001504–1578. It is distinct from the host key object's 20-byte identifier.

`AppleVirtualPlatformHostKey.uniqueDeviceIdentifier` is SHA256 of `SecKeyCopyPublicBytes(hostPublicKey)`, first 20 bytes (0x100005AB0–5AF4). A public-only probe on the native reference Mac imported the standard NIST P-256 generator point and proved that SecKeyCopyPublicBytes returns all 65 X9.63 bytes, including leading 0x04; it does not return coordinate-only 64 bytes. Probe: `/tmp/omvm-publicbytes-probe.m`. No private key was created or imported.

Native 4/3 handler loads HostKey data from its request at 0x100007220, obtains uniqueDeviceIdentifier at 0x10000723C, passes it alongside separate guest chip ID/ECID into sw_pka_set_params at 0x100007290, and returns the derived 20 bytes at 0x1000072A4–72D0. Preserve guest ECID separately from physical host identifiers.

Native HostKey.dataRepresentation is kSecAttrTokenOID NSData from SecKeyCopyAttributes (0x1000050FC–5160), not its 20-byte identifier. The mailbox/syscfg HostKey slot's full semantics are not proven by the nonzero-length kernel assertion alone.

### Tunnel certificate result

`_libavp_copy_host_key_and_certs_with_data` appends raw leaf DER followed by intermediate DER at 0x1B7E47308–47350. Runtime dladdr of the imported copy stub at 0x1B7E146370 proved it is SecCertificateCopyData. The result goes under `Value.RKCertification` at 0x1B7E48BA4–48BEC. No ASN.1 enclosing SEQUENCE, PEM wrapper, or archive wraps the two DER objects in this tunnel value.

### Strong-identity archive for 4/4 and 4/6

This is a separate binary property list (format 200), serialized by AppleVirtualPlatformHostCertificate.dataRepresentationWithCachedData:error: at 0x1000032F0 / serialization 0x100003500–3518:

| Archive key | Type | Meaning |
|---|---|---|
| BuildVersion | STRING | software build of serialization host |
| ProductVersion | STRING | software version of serialization host |
| HostKey | DATA | provider's host-key representation |
| LeafCertificate | DATA | leaf DER |
| IntermediateCertificate | DATA | intermediate DER |

These host software metadata are separate from certificate property 1403. Native constructor compares archive BuildVersion to current MG BuildVersion at 0x100001B20–1B34; mismatch only logs, then continues (0x1B38–1B7C). ProductVersion is serialized but not consulted by that constructor. Honest Linux strings avoid fabricating a macOS host version.

In the observed DeviceIdentity guest path, `_vm_copy_host_certificate` gets the archive as opaque NSData at 0x1B7E397A8 and forwards it under request Value at 0x397C4–397FC. Native key/archive import occurs in a host-only function that rejects virtual-machine context first at 0x1B7E4718C–471BC. Thus a custom Linux provider can own an opaque stable context representation for this path without exporting its wrapped private ref-key. No claim is made that every other possible AppleVirtualPlatform consumer ignores the HostKey representation.

Native serialized inner reply framing:

- **4/4 success:** header 32 bytes; messageLen 16, buffersOffset 0, numBuffers 1, bufferLen N, transportLen 48+N. Body one iovec `{base=0,len=N}`, followed by the N-byte archive. Descriptor source 0x10000929C–92D8; archive body 0x100007620–765C.
- **4/6 success:** header 32 bytes; messageLen 48, buffersOffset 16, numBuffers 2, bufferLen N, transportLen 80+N. Body u64 flags (bit0 validation/refresh indicator), u64 reserved=0, archive iovec `{0,N}`, error iovec `{0,0}`, followed by archive bytes. Fresh validated identity can use flags 0. Descriptor source 0x1000094D0–9510; body source 0x10000784C–7924.
- Native ProtocolMessage serializer copies inline payload bytes and zeros serialized iovec base fields at 0x100006394. Do not put host pointers in serialized bytes.
- These are **inner ProtocolMessage** descriptors, not proof of any outer virtio envelope shape. Existing QEMU ID_S3/mirroring-request experiments differ from the native 4/6 descriptor and must be evaluated separately.

## Physical Linux host facts: verified source

The original boot ADT is exposed by m1n1 as the `adt` phram MTD region.
Use its read-only `/dev/mtdNro` node, with the region binding and size checked
by the host's `aurora-adt-extract.py` parser. The current Linux device tree
is a transformed tree and omits these chosen properties.

The original ADT provides `/chosen/unique-chip-id` (8-byte little-endian),
`chip-id`, `board-id`, `security-domain` (each 4-byte little-endian), and
root `serial-number` (NUL-terminated ASCII). These map to UniqueChipID,
ChipID, BoardId, SecurityDomain, and SerialNumber. On the target host, the
ECID was checked against `/chosen/manifest-properties/ECID` and the serial
against the running Linux DT's root serial; both matched. No identifier
values were printed. `share/identity-host-facts.py` performs these checks
and writes a new mode-0600 JSON file.

This establishes the physical identifiers only. A genuine Linux equivalent
for native OsBuildVersion and acceptance of this host boot policy remain
unverified. Neither a macOS build string nor values from another host may
be substituted.
