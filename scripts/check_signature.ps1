<# Verify the release binary without changing the machine's certificate trust. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$ExpectedSubject
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ExpectedSubject)) {
    throw 'An exact expected production certificate subject is required'
}
$signature = Get-AuthenticodeSignature -LiteralPath $Executable
if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate) {
    throw "Invalid Authenticode signature: $($signature.Status)"
}
if ($signature.SignerCertificate.Subject -cne $ExpectedSubject) {
    throw 'The certificate subject does not match the configured production publisher'
}
if ($null -eq $signature.TimeStamperCertificate) {
    throw 'A trusted release timestamp is required'
}
Write-Output 'OK: trusted Authenticode signature, expected publisher and timestamp.'
