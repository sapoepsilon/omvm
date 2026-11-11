# Native software PKA wire contract

Source: build26B123 native AppleVirtualPlatform identity plugin, `/tmp/issuance-hostkey.dis`. No keys created, no calls to cryptographic operation handlers. Descriptors below are `(messageLen,buffersOffset,numBuffers)`; every integer little-endian, packed unaligned fields. Wire header is eight u32: version,subsystem,type,transportLen,messageLen,bufferLen,numBuffers,buffersOffset. Serialized iovec = u64zero pointer + u64length; payloads inline in iovec order after fixed body. Never transmit real process pointers.

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

This confirms keyType, requestbool, secondary, and even P384curveflag do not constrain the special host public getter. Fixed marker full-length equality and flagsbit4 do. Selector generic flagsbit2 guard refers bit1/0x2; getpublic operation mode2 permits it. The internal want-private flag is separate from the requestbool; native public wrapper always initializes internal want-private=false at0xCB04. No ordinary-context native getter calls were made; no private bytes or user identities printed.

## Ordinary deterministic software key derivation

Native0x10000A278 sets up NIST HMAC-DRBG factory using SHA256 (`ccsha256_di`, `ccdrbg_factory_nisthmac`). Per-context initializer0x10000A39C requires nonnull context and output, context length<256 (otherwise abort), allocates DRBG state, and calls ccdrbg_init with ENTROPY=raw context bytes/length, NONCE=null/0, PERSONALIZATION=10bytes `drbg seed\0` (literal at0x1000108CC). It exposes DRBG through ccrng wrapper0x10000D9EC. Ordinary public getter0xCC60–CC68 sends request context directly to this initializer. Public generator0x100009FB4 selects P256/P384 by flagsbit14, calls `ccec_generate_key_legacy` at0xA060 using that RNG, then exports public bytes via ccec_export_pub at0xA0BC. Ordinary sign separately recreates the same deterministic key at0xCE74 then ccec_sign. Exact legacy ECC scalar sampling must be reproduced; SHA256(context) modulo n is NOT established and would not match this algorithm.
