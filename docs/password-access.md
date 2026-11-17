# Password access preview

Desk 0.14.0 adds optional owner-configured password authentication to the
existing signed numeric-address lookup and certificate-pinned TLS 1.3 path.
It is disabled by default. Setting a password stores only a random salt and
scrypt verifier in the existing DPAPI-protected IdentityStore, and leaves the
feature disabled. A separate local confirmation enables access without a new
consent dialog for clients that know the password. Client passwords are not
saved in favorites, profiles, settings, diagnostics, or connection events.

The client advertises password support in its encrypted hello. If enabled,
the host sends a fresh nonce, receives one bounded password response inside
the already-pinned encrypted transport, verifies it, and only then establishes
the ordinary session with the owner's existing control/clipboard/audio
permissions. No password is sent to a signaling directory or relay as an
application credential. The relay only carries the encrypted transport.
The password is not a Windows logon credential and does not itself elevate
the GUI or install a service.

The verifier uses hashlib.scrypt with n=32768, r=8, p=1, a 16-byte random salt,
32-byte output, and a 64 MiB memory cap. See Python's primary
[hashlib documentation](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt).
Configuration requires 12–128 characters and at most 512 UTF-8 bytes.
Parameters are fixed locally, not supplied by a connecting peer. Five failed
attempts within five minutes block further password attempts until the window
expires. The limiter is shared across invitations in this app execution;
restarting the application resets its in-memory attempt history.

Disabling, changing, or removing the password changes its revision. Existing
password sessions are closed by the local UI and a bounded session watcher;
host input also checks the revision before injection. Separately trusted
devices keep their existing key-based authorization and revocation mechanism.
Old clients retain the existing local-consent flow and cannot use passwords.

The computer must be on, with the GUI running after the owner's first login.
The existing administrator-approved, path/user/version-bound service remains
required for protected desktops. This feature does not add a scheduled-task
elevation, bypass UAC, remove a Windows password, create a firewall exception,
or start access before the first logon. The entire GUI stays unelevated.

Tests use synthetic credentials and loopback TLS. They cover successful access
without prior device trust/owner consent, wrong passwords, cancellation,
fingerprint mismatch before the password prompt, nonce mismatch, rate limits,
revocation and input denial, persistence, salt uniqueness, and UI confirmation.
They never type into the live desktop or Windows authentication screen.
Actual public-relay password sessions and protected-desktop input still need
owner-assisted validation before promotion to the stable update channel.
