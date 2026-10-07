<#
Optional local Authenticode signing. Never creates/imports certificates or replaces an artifact.
The default is no timestamp request; verification uses only cached Windows trust material.
#>
[CmdletBinding(DefaultParameterSetName='Sign')]
param(
    [Parameter(Mandatory=$true, ParameterSetName='Sign')]
    [Parameter(Mandatory=$true, ParameterSetName='Verify')][string]$InputFile,
    [Parameter(Mandatory=$true, ParameterSetName='Sign')][string]$OutputFile,
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [ValidateSet('CurrentUser','LocalMachine')][string]$CertificateStore = 'CurrentUser',
    [Parameter(Mandatory=$true, ParameterSetName='Preflight')][switch]$Preflight,
    [Parameter(Mandatory=$true, ParameterSetName='Verify')][switch]$VerifyOnly,
    [Parameter(ParameterSetName='Sign')][string]$TimestampServer = '',
    [Parameter(ParameterSetName='Sign')][switch]$AllowTimestampNetwork
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$thumbprint = $CertificateThumbprint.Replace(' ', '').ToUpperInvariant()
if ($thumbprint -notmatch '^[A-F0-9]{40}$') { throw 'CertificateThumbprint must be the exact 40-character certificate thumbprint.' }
if ($TimestampServer -and -not $AllowTimestampNetwork) { throw 'Timestamp server requires -AllowTimestampNetwork and prior approval of that exact URL.' }
if ($AllowTimestampNetwork -and -not $TimestampServer) { throw '-AllowTimestampNetwork requires an explicit timestamp URL.' }
if ($TimestampServer) {
    $timestampUri = $null
    if (-not [Uri]::TryCreate($TimestampServer, [UriKind]::Absolute, [ref]$timestampUri) -or
        $timestampUri.Scheme -notin @('http','https') -or $timestampUri.UserInfo -or $timestampUri.Fragment) {
        throw 'TimestampServer must be an approved HTTP/HTTPS URL without credentials or a fragment.'
    }
}

function Assert-PlainPath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse-point input/output paths are not supported.' }
        if ($item -is [IO.FileInfo]) { $item = $item.Directory } else { $item = $item.Parent }
    }
}

function Get-SigningCertificate {
    $certificatePath = 'Cert:\' + $CertificateStore + '\My\' + $thumbprint
    if (-not (Test-Path -LiteralPath $certificatePath)) { throw 'No matching certificate in the selected My store. A PG-owned trusted code-signing identity is required; nothing was signed.' }
    $certificate = Get-Item -LiteralPath $certificatePath
    if (-not $certificate.HasPrivateKey) { throw 'The selected certificate has no accessible private key.' }
    $now = [DateTime]::Now
    if ($now -lt $certificate.NotBefore -or $now -ge $certificate.NotAfter) { throw 'The selected certificate is not currently valid.' }
    $codeSigning = $false
    foreach ($extension in $certificate.Extensions) {
        if ($extension -is [Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]) {
            foreach ($usage in $extension.EnhancedKeyUsages) {
                if ($usage.Value -eq '1.3.6.1.5.5.7.3.3') { $codeSigning = $true }
            }
        }
    }
    if (-not $codeSigning) { throw 'The certificate must explicitly permit the Code Signing EKU.' }
    # Keep this desktop workflow bounded to RSA SHA256 identities. Hardware-backed keys may prompt.
    if ($certificate.PublicKey.Oid.Value -ne '1.2.840.113549.1.1.1' -or $certificate.PublicKey.Key.KeySize -lt 2048) {
        throw 'This workflow requires an RSA code-signing identity with a key of at least 2048 bits.'
    }
    return $certificate
}

function Initialize-OfflineVerifier {
    if ('KoshReleaseTrust' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KoshReleaseTrust {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct FileInfo {
        public uint Size; [MarshalAs(UnmanagedType.LPWStr)] public string Path;
        public IntPtr Handle; public IntPtr Subject;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct TrustData {
        public uint Size; public IntPtr Policy; public IntPtr Sip;
        public uint Ui; public uint Revocation; public uint Choice; public IntPtr File;
        public uint StateAction; public IntPtr State; public IntPtr Url;
        public uint Flags; public uint Context;
    }
    [DllImport("wintrust.dll", ExactSpelling = true, CharSet = CharSet.Unicode)]
    private static extern int WinVerifyTrust(IntPtr window, [In] ref Guid action, [In] ref TrustData data);
    public static int Verify(string path) {
        var file = new FileInfo { Size = (uint)Marshal.SizeOf(typeof(FileInfo)), Path = path };
        IntPtr pointer = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(FileInfo)));
        Marshal.StructureToPtr(file, pointer, false);
        // No UI, Authenticode file choice, state kept for explicit close.
        // 0x1000: cache-only URL retrieval; 0x10: no revocation checks; 0x2000: disable MD2/MD4.
        var data = new TrustData { Size = (uint)Marshal.SizeOf(typeof(TrustData)), Ui = 2,
            Choice = 1, File = pointer, StateAction = 1, Flags = 0x1000 | 0x10 | 0x2000 };
        Guid action = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
        try { return WinVerifyTrust(new IntPtr(-1), ref action, ref data); }
        finally {
            data.StateAction = 2;
            WinVerifyTrust(new IntPtr(-1), ref action, ref data);
            Marshal.DestroyStructure(pointer, typeof(FileInfo));
            Marshal.FreeHGlobal(pointer);
        }
    }
}
'@
}

function Assert-SignedFile([string]$Path) {
    Initialize-OfflineVerifier
    $verifiedStream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $status = [KoshReleaseTrust]::Verify($Path)
        if ($status -ne 0) { throw ('Signature verification failed against cached Windows trust; HRESULT 0x{0:X8}. Online revocation was not checked.' -f $status) }
        $signer = New-Object Security.Cryptography.X509Certificates.X509Certificate2([Security.Cryptography.X509Certificates.X509Certificate]::CreateFromSignedFile($Path))
        try {
            if ($signer.Thumbprint.ToUpperInvariant() -ne $thumbprint) { throw 'Signature signer does not match the requested certificate thumbprint.' }
        } finally { $signer.Dispose() }
        $hash = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hash.ComputeHash($verifiedStream)).Replace('-','').ToLowerInvariant() } finally { $hash.Dispose() }
    } finally { $verifiedStream.Dispose() }
}

if ($Preflight) {
    $certificate = Get-SigningCertificate
    [ordered]@{mode='preflight'; thumbprint=$thumbprint; certificate_store=$CertificateStore;
        private_key_present=$true; code_signing_eku=$true; currently_valid=$true;
        trust='not_checked_until_signed_file_verification'; signed=$false; timestamp_requested=$false} | ConvertTo-Json
    return
}

$inputPath = [IO.Path]::GetFullPath($InputFile)
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) { throw 'The explicitly selected input file does not exist.' }
Assert-PlainPath $inputPath
if ([IO.Path]::GetExtension($inputPath) -ne '.exe') { throw 'This release workflow accepts only an explicitly selected EXE.' }
if ($VerifyOnly) {
    $digest = Assert-SignedFile $inputPath
    [ordered]@{mode='verify'; sha256=$digest; signer_thumbprint=$thumbprint;
        signature='valid_against_cached_windows_trust'; revocation='not_checked'; smartscreen_reputation='unknown'} | ConvertTo-Json
    return
}

$outputPath = [IO.Path]::GetFullPath($OutputFile)
if ($outputPath.Equals($inputPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be different from the input; in-place signing is refused.' }
if ([IO.Path]::GetExtension($outputPath) -ne '.exe') { throw 'OutputFile must use the .exe extension.' }
$receiptPath = $outputPath + '.signing.json'
if ((Test-Path -LiteralPath $outputPath) -or (Test-Path -LiteralPath $receiptPath)) { throw 'Output already exists. Choose a new output filename; nothing was overwritten.' }
$outputParent = [IO.Path]::GetDirectoryName($outputPath)
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) { throw 'The output parent directory must already exist.' }
Assert-PlainPath $outputParent
$certificate = Get-SigningCertificate
$candidatePath = Join-Path $outputParent ('.kosh-signing-' + [Guid]::NewGuid().ToString('N') + '.exe')
$inputStream = [IO.File]::Open($inputPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $inputDigest = [BitConverter]::ToString($hash.ComputeHash($inputStream)).Replace('-','').ToLowerInvariant() } finally { $hash.Dispose() }
    $inputStream.Position = 0
    $candidateStream = [IO.File]::Open($candidatePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $inputStream.CopyTo($candidateStream) } finally { $candidateStream.Dispose() }
    # Signer-only chain inclusion avoids asking the signing cmdlet to build/fetch an intermediate chain.
    $signArguments = @{LiteralPath=$candidatePath; Certificate=$certificate; HashAlgorithm='SHA256'; IncludeChain='Signer'; ErrorAction='Stop'}
    if ($TimestampServer) { $signArguments.TimestampServer = $TimestampServer }
    $signed = Set-AuthenticodeSignature @signArguments
    if ($TimestampServer -and $null -eq $signed.TimeStamperCertificate) { throw 'Requested timestamp was not returned. Candidate retained; no signed release published.' }
    $signedDigest = Assert-SignedFile $candidatePath
    # File.Move refuses an existing destination, including one created after preflight.
    [IO.File]::Move($candidatePath, $outputPath)
    $publishedDigest = Assert-SignedFile $outputPath
    if ($publishedDigest -ne $signedDigest) { throw 'Published file changed after verification; no signing receipt issued.' }
    $receipt = [ordered]@{format=1; mode='sign'; generated_utc=[DateTime]::UtcNow.ToString('o');
        input_sha256=$inputDigest; output_sha256=$publishedDigest; signer_thumbprint=$thumbprint;
        certificate_store=$CertificateStore; hash_algorithm='SHA256'; signature='valid_against_cached_windows_trust';
        timestamp_requested=[bool]$TimestampServer; timestamp_present=($null -ne $signed.TimeStamperCertificate);
        revocation='not_checked'; smartscreen_reputation='unknown'} | ConvertTo-Json
    $receiptStream = [IO.File]::Open($receiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $writer = New-Object IO.StreamWriter($receiptStream, (New-Object Text.UTF8Encoding($false)))
    try { $writer.Write($receipt) } finally { $writer.Dispose() }
    Write-Output $receipt
} finally { $inputStream.Dispose() }
