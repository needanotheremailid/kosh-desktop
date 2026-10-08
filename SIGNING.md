# Optional Windows release signing

The installer builder creates an **unsigned development artifact**. Building it does not establish publisher identity. `scripts/sign-release.ps1` is a separate, optional local Authenticode workflow. A signing-capable, trusted identity owned or controlled by the release publisher must already be provisioned. This repository does not create a certificate, import one, change Windows trust, store a password, download tooling, or silently switch to a self-signed identity.

No installer has become signed merely because this workflow exists. Signatures and receipts apply only to the exact output bytes checked by a successful run. Existing released or installed copies retain their previous signature state.

For **1.0.0-rc.5**, signing remains pending. The release-candidate label does not imply a verified publisher, final 1.0 acceptance or a published package. Build and release checks must describe their exact unsigned or separately verified signed bytes; never infer signature state from a version number or a matching release checksum.

## Local identity preflight

The script accepts an exact certificate thumbprint from `CurrentUser\My` or, when explicitly selected, `LocalMachine\My`. It checks current validity, private-key presence, an explicit Code Signing EKU, and an RSA key of at least 2048 bits. Hardware-backed private keys can require their normal provider interaction during signing. Private-key presence alone does not prove the provider will permit signing.

Run a read-only preflight after separately provisioning the chosen identity through its approved provider:

```powershell
powershell.exe -NoProfile -File .\scripts\sign-release.ps1 -Preflight -CertificateThumbprint '<exact certificate thumbprint>'
```

Add `-CertificateStore LocalMachine` only if that is the intended store. Preflight prints no person name or private-key material. It does not claim chain trust before a signed file is verified. A missing, expired, unsuitable, or inaccessible identity stops the operation.

## Sign a separate release copy

Build and inspect the installer and matching source package first. Select an existing output directory and a new output filename:

```powershell
powershell.exe -NoProfile -File .\scripts\sign-release.ps1 -InputFile 'C:\existing\outputs\Kosh unsigned Setup.exe' -OutputFile 'C:\existing\outputs\Kosh signed Setup.exe' -CertificateThumbprint '<exact certificate thumbprint>'
```

The script locks the source against changes, hashes and copies it into a new candidate, then uses Windows PowerShell's installed Authenticode cmdlet with **SHA256** and the selected certificate. It uses signer-only chain inclusion. Intermediate/root certificates needed for verification must already be available in Windows' cached trust material; the workflow does not fetch them. It verifies the candidate before publishing, publishes with a no-clobber move, and verifies the exact published file again. Its sidecar `Kosh signed Setup.exe.signing.json` records input/output SHA256, signer thumbprint, SHA256 content digest, timestamp presence, and verification limits. It does not change the original installer.

Any pre-existing output or receipt is refused. A failure after copying can leave a `.kosh-signing-<random>.exe` candidate, or a published output without a receipt if a later check failed. Those files are **unverified failure evidence** until separately checked; do not distribute them as a signed release. Nothing overwrites or deletes a retained artifact. Use a new output name after resolving the failure.

## Optional approved timestamp

No timestamp server is contacted by default. A timestamp request requires prior approval of the exact server URL and both `-TimestampServer '<approved URL>'` and `-AllowTimestampNetwork`. Supplying a URL without the switch is refused. Credential-bearing and non-HTTP/HTTPS URLs are refused. Never put credentials in a timestamp URL.

The signing cmdlet must return a timestamp certificate when a timestamp was requested; otherwise publication fails. The SHA256 claim applies to the executable content digest. This workflow does not assert a particular timestamp protocol or timestamp digest algorithm. Providers requiring RFC3161 or a specific timestamp digest should use their approved signing tool and then run the independent file verification below. A signature without a trusted timestamp can stop validating after its signing certificate expires.

## Recheck the exact release file

```powershell
powershell.exe -NoProfile -File .\scripts\sign-release.ps1 -VerifyOnly -InputFile 'C:\existing\outputs\Kosh signed Setup.exe' -CertificateThumbprint '<expected signer thumbprint>'
```

The verifier checks an embedded Authenticode signature using Windows policy through `WinVerifyTrust`, with cache-only URL retrieval, no UI, and no online revocation checks. It checks Windows' cached trust result, the actual file's signer thumbprint, and its SHA256 while holding a file lock. An unsigned, invalid, tampered, untrusted, or differently signed file fails. Verification does not require a private key in the local My store. Windows catalogue signatures are a separate mechanism and are not this release workflow's target.

Successful output is specifically `valid_against_cached_windows_trust`; **revocation is not checked** and **SmartScreen reputation is unknown**. Current online revocation checking, another clean Windows computer, publisher provisioning, and production signing remain separate verification layers. A trusted Authenticode signature proves the checked publisher identity and signed-file integrity under the verification policy; it does not promise that Windows SmartScreen will stop showing a warning.

Publishing the signed copy, replacing uploaded assets, installing it, changing shortcuts, or creating a signing account are separate authorized actions. This workflow performs none of them.

## Provider options checked on 6 October 2026

These are dated reference notes, not refreshed provider eligibility, pricing or approval for this RC. Provider rules can change; verify the linked current terms before choosing or applying. No new provider account, submission or identity validation follows from editing this guide.

The local workflow above is prepared; it is not a cloud-provider integration or a completed identity-validation process.

- **Microsoft Artifact Signing:** Eligibility depends on publisher identity, supported region and successful validation. Provider eligibility for this publisher is unconfirmed. Check the [Artifact Signing quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart) before choosing this route; no provider account or validation is claimed.
- **Microsoft Store:** Microsoft's [Windows signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) describe free Store signing after certification for MSIX packages. The current standalone EXE installer is not a Store-certified MSIX package; conversion, submission and certification would be separate work. Microsoft also distinguishes signing from SmartScreen reputation, so a certificate does not guarantee the disappearance of every warning.
- **SignPath Foundation:** Its [eligibility terms](https://signpath.org/terms.html) require an active, released, documented open-source project, qualifying licensing for the project and its components without commercial dual licensing, verifiable builds, maintainer control, manual approval and security controls. Acceptance is discretionary and signatures use the Foundation publisher identity. The included PyMuPDF component's dual-licensing model makes eligibility an unresolved point to clarify. Kosh now has a public source repository and beta release; that alone does not establish the public reputation or eligibility the programme evaluates. No eligibility approval or application is claimed.

For the current EXE release, the next material decision is an acceptable signing provider and verified publisher identity. Until that identity is available, keep development installers explicitly unsigned. Creating a locally trusted self-signed certificate would not establish a trusted publisher on other computers.

## Local checks

```powershell
python.exe -m unittest discover -s tests -p test_sign_release.py -v
```

Tests use isolated synthetic files and an unavailable certificate thumbprint. They exercise refusal, source/output preservation, timestamp authorization/URL checks, and unsigned-file verification. They create no signing identity or trust entry. Passing them proves those local boundaries; it does not prove that a real publisher identity has been provisioned or that an installer has been signed.

The offline verifier was also exercised read-only on the existing .NET Framework `Framework64\v4.0.30319\csc.exe` on 6 October 2026. Its embedded signature passed the cache-only policy with its actual certificate thumbprint; a different requested thumbprint was refused. That is a signed reference-file verification check, not Kosh installer signing or clean-machine proof. Windows PowerShell itself was unsuitable as this reference because its signature is catalogue-based.
