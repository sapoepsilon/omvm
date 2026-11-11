# Native software PKA wire contract

Source: build26B123 native AppleVirtualPlatform identity plugin, `/tmp/issuance-hostkey.dis`. Initial findings were static; later explicitly authorized fixture sections use only public known contexts and nonpermanent process-local SOFTWARE keys, with no SEP private-key creation or account data. Descriptors below are `(messageLen,buffersOffset,numBuffers)`; every integer little-endian, packed unaligned fields. Wire header is eight u32: version,subsystem,type,transportLen,messageLen,bufferLen,numBuffers,buffersOffset. Serialized iovec = u64zero pointer + u64length; payloads inline in iovec order after fixed body. Never transmit real process pointers.

All subsystem5 headers use version2. Native constructor0x1000060E0–60FC assigns version1 ONLY to subsystem4/type1; everything else2. EncodeReply0x1000065BC–65CC copies request subsystem/type then uses this same constructor.

| Type | Operation | Request descriptor | Reply descriptor | Native dispatch |
| --- | --- | --- | --- | --- |
| 1 | Query protocol version | 4,0,0 | 4,0,0 | A628 -> A968 |
| 2 | Measurement | 4,0,0 | 20,4,1 | A6D8 -> A9D4 |
| 3 | Public key | 29,13,1 | 20,4,1 | A654 -> A7E0 |
| 4 | ECDH | 45,13,2 | 20,4,1 | A680 -> A84C |
| 5 | Sign digest | 45,13,2 | 20,4,1 | A704 -> AA40 |
| 6 | SIKA attestation | 74,26,3 | 20,4,1 | A6AC -> A8C4 |
| 7 | Shared encryption | 73,9,4 | 20,4,1 | A75C -> AB44 |
| 8 | AON security | 1,0,0 | 8,0,0 | A788 -> AC6C |
| 9 | Attested SEP chip revision | 1,0,0 | 5,0,0 | A7B4 -> ACB0 |
| 10 | Guest identity string | 1,0,0 | 20,4,1 | A730 -> AAB8 |

Table decoded from signed jump offsets0x10000AE50 relative0x10000A61C. Types0/outofrange unsupported. Descriptor request type3:0xBDEC–BE6C; type5:0xBF9C–C01C; type6:0xC074–C0F4. Reply public0xB1B0, sign0xB478, attest0xB5DC.

## Query version, type1

Request is body u32 (native parser only checks descriptor, does not inspect value). Successful reply body u32 1, NOT header.version1. Header `{2,5,1,36,4,0,0,0}` and body `01000000`. Request parser0x10000BC90–BCC4; reply body0x10000A988–A998; reply descriptor0x10000AF08–AF40.

## Public key type3; ECDH type4; signature type5

Common packed body:
- offset0 u32 first algorithm/key selector argument, passed as x0.
- offset4 u8 boolean, passed as x3 after normalization nonzero=>1.
- offset5 u32 flags, passed as x4.
- offset9 u32 secondary selector, passed as x5.
- offset13 iovec context, passed as x1/x2 (bytes,length).
- ECDH/sign only: offset29 iovec peer-public-point/digest, passed as x6/x7.

Native public parse0x10000A800–A828, ECDH0xA86C–A8A0, sign0xAA60–AA94. Successful reply fixed body is i32status0 at0, then iovec at4; returned point/sharedsecret/DERsignature bytes inline at body20. `transportLen=52+payloadLen`. Failed status is signed OSStatus; result buffer can empty.

Critical host-key special context: flags bit2/0x4 plus context length20 or32 plus bytes `a6c3602903a3c638eb2991ceabb8dbee5f898c12` (and12zero padding for32) selects REAL retained host SecKey, not software KDF. Selector0x10000C494, literal0x1000108D8. Additional guard flags bit1 requires operation-mode bit1. Public calls selector mode2. Direct sign calls mode0, therefore flags0x2 must not be silently ignored. SIKA uses mode2. Native host point export0xDC38; direct host digest signing0xDF38 uses kSecKeyAlgorithmECDSASignatureDigestX962, no further hashing, output DER. Incoming digest length is passed through to Security; native host helper does not hardcode32 (P256 SHA256 normally32).

## SIKA attestation type6

Packed fixed26-byte prefix, then3iovecs:
- +0 u32 => sw_pka_sika_attest x0 (attestation flags)
- +4 u32 => x1
- +8 u8 bool => x4
- +9 u32 => x5
- +13 u32 => x6
- +17 u32 => x7
- +21 u8 bool => first stacked bool, normalized
- +22 u32 => stacked u32
- +26 iovec0 => x2/x3
- +42 iovec1 => first two stack u64
- +58 iovec2 => later stack bytes/length

Positional mapping is proven0x10000A8E4–A944; semantic names of every field are not all established. This operation computes attestation digest via0x10000E180 then signs that digest via common sign helper0x10000CD30 at0xE0F4 with operation mode2. Special marker context can therefore select certified host key. Reply same status+iovec format as type5.

Do not implement arbitrary operation success from this document alone. Complete exact query1 first, then observe actual subsequent traffic. A successful query advertises capability; ordinary software key generation/KDF and physical host-key slot require distinct handling, and EC operations cannot be replaced with cached hashes.

## Host public-key getter runtime validation

2026-11-11 probe `/tmp/omvm-swpka-getpub-probe.m` loaded native plugin, created one process-local nonpermanent SOFTWARE P256 key using Security (no Secure Enclave token, no keychain persistence), passed it to native sw_pka_set_params, and called native public getter only for the fixed host marker. Every case returned status0,65bytes, byte-equal to the ephemeral software key's public export:

1. keyType0,boolfalse,flags4,secondary0,context32.
2. keyType99,booltrue,flags6,secondary99,context32.
3. keyType0,boolfalse,flags4,secondary0,context20.
4. keyType0,boolfalse,flags0x4004,secondary0,context32.

This confirms keyType, requestbool, secondary, and even P384curveflag do not constrain the special host public getter. Fixed marker full-length equality and flags0x4 do. Selector generic flagsbit2 guard refers bit1/0x2; getpublic operation mode2 permits it. The internal want-private flag is separate from the requestbool; native public wrapper always initializes internal want-private=false at0xCB04. No ordinary-context native getter calls were made; no private bytes or user identities printed.

## Ordinary deterministic software key derivation

Native0x10000A278 sets up NIST HMAC-DRBG factory using SHA256 (`ccsha256_di`, `ccdrbg_factory_nisthmac`). Per-context initializer0x10000A39C requires nonnull context and output, context length<256 (otherwise abort), allocates DRBG state, and calls ccdrbg_init with ENTROPY=raw context bytes/length, NONCE=null/0, PERSONALIZATION=10bytes `drbg seed\0` (literal at0x1000108CC). It exposes DRBG through ccrng wrapper0x10000D9EC. Ordinary public getter0xCC60–CC68 sends request context directly to this initializer. Public generator0x100009FB4 selects P256/P384 by flagsbit14, calls `ccec_generate_key_legacy` at0xA060 using that RNG, then exports public bytes via ccec_export_pub at0xA0BC. Ordinary sign separately recreates the same deterministic key at0xCE74 then ccec_sign. The fully validated scalar derivation is given below; hashing context directly into a scalar would not match.

## Ordinary KDF fully validated against native public fixtures

A native process-local ordinary getter probe used ONLY two public known contexts: bytes0..31, and32bytes0x01. Native call type0,boolfalse,flags0 for P256 or0x4000 for P384,secondary0. All4 calls returned public points65/97bytes. No actual guest context, host identity, account credential, or SEP key was used. Results: `/tmp/omvm-swpka-public-fixtures.txt`; source `/tmp/omvm-swpka-public-fixtures.m`.

Independent Python HMAC implementation plus cryptography EC multiplication matched all4 native public points exactly. Verifier `/tmp/omvm-verify-public-kdf.py`; run from workspace with `python3 -c "exec(compile(open('/tmp/omvm-verify-public-kdf.py').read(), '/tmp/omvm-verify-public-kdf.py', 'exec'))"` to avoid unrelated `/tmp/re.py` shadowing Python standard library.

Exact public-key derivation:
1. Initialize HMAC_DRBG using SHA256, entropy=raw context, nonce empty, personalization10bytes `drbg seed\0`. Standard K=32zero,V=32one; update with seed=entropy||personalization.
2. First generate request emits32bytes for P256 or48bytes for P384.
3. Interpret those bytes as LITTLE-ENDIAN unsigned integer d. If d>=curvegrouporder, subtractorder ONCE. There is no big-endian read and no rehash-to-scalar.
4. Public point=d*G, export uncompressed SEC1/X9.63. Flagsbit14 chooses P384; otherwise P256.

Primary Apple source provenance:
- https://github.com/apple/corecrypto/blob/main/ccec/src/ccec_generate_key_internal_legacy.c : requests curve-sized entropy, computes scalar then public point.
- https://github.com/apple/corecrypto/blob/main/ccec/src/ccec_generate_scalar_legacy.c : copies entropy directly into native cc_unit limbs, truncates excess orderbits if any, conditional subtracts grouporder. On arm64 limbs are little-endian. P256/P384 have no partial top limb.
- https://github.com/apple/corecrypto/blob/main/ccec/src/ccec_generate_key_legacy.c : after creating public/private pair, consumes additional RNG for pairwise consistency check; this does not change the scalar already chosen.
- https://github.com/apple/corecrypto/blob/main/ccdrbg/src/ccdrbg_nisthmac.c : standard NIST HMAC_DRBG init/update/generate behavior.

Apple public main sources inspected2026-11-11; native build26B123 PUBLIC fixture agreement is direct evidence that these essential scalar derivation steps match the deployed native plugin. Exact degenerate scalar0/error behavior and invalid input status matrix not tested. Do not log derived private scalars; verifier only reports public point equality.

## Ordinary metadata and direct-sign fixtures

Native fixtures repeated public contexts bytes0..31 and32bytes0x01 with selector1,bool0,flags0x78d8,secondaryUINT32_MAX. Both public points equal previous selector0,flags0x4000,secondary0 P384 outputs. Companion flags0x38d8 equals P256 output. All4 byte-for-byte matches. Native ordinary getter ignores selector,bool,secondary after common selector gate; curve flag0x4000 controls P256/P384. Source `/tmp/omvm-swpka-selector-fixtures.m`; output `.txt`.

Direct type5 signing under the same metadata was exercised for both public seeds, both curves,32/48byte public test digests. All8 returned DER signatures validated directly with SecKeyVerifySignature DigestX962 against the expected derived public point. No hashing occurs in type5. Flags|0x2 returned-11 with empty output in all4 tested cases, consistent with generic guard mode0. `/tmp/omvm-swpka-sign-fixtures.m` and `.txt`. No private scalar or signature bytes printed.

## Complete SIKA semantic mapping and digest construction

This section supersedes earlier provisional positional names. Native build26B123 functions: packed parsing0x10000A8E4–A944; SIKA0x10000E020; digest builder0x10000E180; common signer0x10000CD30. Type6 reply contains DER signature ONLY, status+iovec20/4/1, transportLen52+signatureLen. The guest constructs any enclosing attestation structure separately.

| Body offset | Type | Meaning |
| --- | --- | --- |
| 0 | u32LE | Signing-key flags (curve and special host-slot selector) |
| 4 | u32LE | Signing-key selector |
| 8 | u8 | Signing-key boolean |
| 9 | u32LE | Attested-key flags, also digest flags |
| 13 | u32LE | Signing-key secondary selector |
| 17 | u32LE | Attested-key selector (determines4B digest label) |
| 21 | u8 | Attested-key boolean |
| 22 | u32LE | Attested-key secondary selector |
| 26 | iovec | Signing-key context |
| 42 | iovec | Attested-key context |
| 58 | iovec | Nonce/external data |

Ordinary signing and attested contexts derive keys independently. Special host context flags0x4 selects retained physical host key; this can be used as SIGNER while the ATTESTED key remains an ordinary software key. Do not confuse the two flags words or two contexts.

Digest builder derives/exports attested key using attested context and flags, then hashes following concatenation, with no lengths/TLVs/separators unless explicitly stated:

1. Attested public point coordinates, omitting initial0x04. P25664bytes orP38496bytes.
2. Four literal bytes according to attested selector:0=`sks `,1=`ssca`,2=`simp`. Other values lead native label resolver to abort; do not emulate abort on untrusted input.
3. Attested flags encoded u32LE.
4. If attested key is selected special HOST key: fixed PUBLIC24byte tag `cc4fa426c2fcb7d64b2f4cb10c1cb6f2c4ad0d5a99c8c6f6` (0x1000108F8), from0xC514; absent for ordinary keys.
5. If flags bit3/0x8: measurement0,52bytes all0xff. Otherwise if flags bit9/0x200: measurement6,52bytes all0xff. Native capability getter0xA518 returns1; first branch takes precedence.
6. If flags bit4/0x10: initialized guest identity25ASCII bytes (see next section).
7. If flags bit7/0x80: attested SEP chip revision, one byte0x01.
8. If flags bit12/0x1000: AON security u32BE value1, then ATTESTED secondary selector u32BE.
9. If flags bit11/0x800: measurement2 then measurement3, each52bytes all0xff (total104).
10. If flags bit13/0x2000: raw nonce/external bytes.

Native capability0xA578 returns0, so later conditional branches for flagsbits15–18 do not execute in this build. Other bits not listed do not add bytes, though they remain included in the flags word itself. Native measurements uniformly emit52bytes0xff for selector0..6 (0xCF40); guest identity and mock security constants are native plugin behavior, not proposed fabrication.

Hash is SHA384 when ATTESTED flags include0x4000, otherwise SHA256 (0xE1E4–1F4). Then normalize digest to SIGNING curve length: signing flags0x4000 yields48bytes; otherwise32. If hash32/sign48: prepend16zero bytes. If hash48/sign32: retain final32bytes. Native emits misleading 'digest was zero padded' diagnostic for both adjustment directions (0xE628–E69C). Common signer signs normalized bytes directly using mode2, so flagsbit0x2 is permitted for SIKA (unlike standalone type5 mode0).

Runtime proof: public attested context bytes0..31, selector1,bool0,secondaryUINT32_MAX, public nonce32x0x01, process-local ephemeral SOFTWARE host key, dummy guest ChipID/ECID bothzero. Flags0 produced SHA256 of72bytes `pub64 || ssca || LE32(0)`, digest `9647d9108335685f872837dcf954bf4fd7d5ed4c044cfe06c9af85d988eb1b9c`. Flags0x78d8 produced SHA384 of326bytes assembled by above rules, digest `c19b8251c81a96219135e455b3d5cc499c4682a3c3a37879799780d87e7a0ba47b52a05d81f780046773373ad851703f`. Independent Python hashes match native exactly. `/tmp/omvm-swpka-sika-digest-fixtures.m` and `.txt`.

Full native SIKA fixtures used signing context32x0x01 and public attested context bytes0..31. Three cases verified DER signature against independently derived signing public key: signing flags0x4000/digestflags0x78d8; signingflags0/digestflags0x78d8 (last32hashbytes); signingflags0x4000/digestflags0 (16zero||SHA256). All returnedstatus0 and direct-digest verification succeeded. `/tmp/omvm-swpka-sika-sign-fixtures.m` and `.txt`.

Error caveats from static/runtime evidence: SIKA rejects nonnull nonce length>=49 with-11 before computing digest (0xE084–E08C/E144). With flags0x2000 but null/empty nonce, builder can returnstatus0 WITHOUT filling output: runtime returned0 and left caller's zeroed digest intact; static0xE524–E528 exits using prior success status. Do not treat status0 alone as evidence of valid populated digest when required input absent. Missing initialized guest identity (bit0x10) returns-11 from0xDABC. Invalid measurements/selector values can abort native, so validate bounds in replacements.

## Guest identity string provenance

Native4/3 initialization loads first packedu32 at requestbody+0 and packedu64 at+4 (0x10000725C–7260) then passes them as x1/x2 to sw_pka_set_params (0x7284–7290). Formatter0xDB38–DB50 uses uppercase `%08X-%016llX`;25ASCII bytes exclude terminating NUL. This is guest ChipID then guest ECID, distinct from physical host identity. Returned hostkeyhash argumentsx3/x4 are ignored by native set_params; actual host key itself is retained separately.

Linux ECID mapping is source-proven: upstream `scripts/extract-ecid.py` parses vm.json machineId base64plist ECID; omvm `bin/omvm` passes it to `share/libvirt-domain.py`; that sets QEMU machine `uuid={ecid}`; vmapple passes vms->uuid to configuration/device ecid. A direct vm.json ChipID mapping is NOT established. Use actual guest4/3 firstu32 as authoritative for this string, not physical host ADT ChipID. No actual values appear in this document.

## Physical P256 host key and48-byte normalized digest

Native common signer0x10000CD30 was called with operationmode2, signingflags0x4004, fixed host-marker context32, an ephemeral SOFTWARE P256 key retained via native set_params, and public test digest bytes0..47. Native returnedstatus0 andDERsignature. SecKeyVerifySignature DigestX962 validated it against full48bytes AND first32bytes; verification failed for last32bytes and for SHA256(digest48). A32byte digest fixture likewise validated directly and failed when hashed again. `/tmp/omvm-swpka-hostdigest-fixtures.m` and `.txt`; no physical SEP/account/guest key involved.

There are TWO separate truncation stages: SIKA builder normalizes hash to SIGNING FLAGS curve size (SHA384->signflagsP256 means LAST32; SHA256->signflagsP384 means16zero||SHA256). Then actual ECDSA key order truncates any oversized supplied digest on the LEFT/MSB side. With actual certified host keyP256 but signingflags0x4004, builder retains48bytes, native Security signs its FIRST32. Therefore a32byte kernel digest ABI can match native P256 by taking first32bytes of the FINAL normalized48byte digest. Do not prematurely choose first32 ofSHA384 when signingflags call for builder last32 normalization.
