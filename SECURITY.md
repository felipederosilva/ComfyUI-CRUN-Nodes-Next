# Security and scope

This alpha is designed for a trusted, single-user, loopback ComfyUI installation.
It is not a hardened multi-user service. Do not expose its Comfy server publicly.

The local bridge checks peer and Host loopback addresses, same-origin requests,
and a process-local nonce for actions. Keys are never returned by status routes.
Provider requests use a fixed HTTPS CRUN host; redirects are not followed with
credentials. HTTP exceptions are sanitized. Never paste your key into an issue.

DPAPI protects saved keys on Windows at rest. Unix permissions do not encrypt
keys. Other processes running as your user, browser extensions with access to
Comfy, or compromised custom nodes may still read/request secrets or spend credits.
Use a dedicated CRUN key with provider-side usage caps if available.

Catalogs are untrusted data. Labels are rendered as text. External preview URLs
must be HTTPS, are not fetched through the Comfy backend, and load only on user
action. A preview request exposes the browser's IP to that media host.

Paid generation and uploads are deliberately not implemented in 0.1.0. Cost
estimation is not a reservation and cannot guarantee the final bill. The optional
installer refuses existing destinations and never changes KIE Next.

For a suspected secret leak, revoke the key in CRUN first, then open a sanitized
issue or use GitHub private vulnerability reporting if enabled. Do not attach
credential files, raw request headers or unredacted Comfy configurations.
