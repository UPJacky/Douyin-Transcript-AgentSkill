param(
    [string]$RequestPath = 'C:\sandbox-results\chromium-desktop-acl-grant-request.json',
    [string]$AckPath = 'C:\sandbox-results\chromium-desktop-acl-grant-ack.json',
    [guid]$RunToken = [guid]::Empty
)
throw 'Interactive desktop ACL grant is disabled until a trusted Sandbox guest attestation is implemented.'
