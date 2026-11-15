# Desk screen broker — preparation, not an activated service

This optional component supplies capture and typed mouse/keyboard input while
an already-authenticated Desk session reaches the Windows lock desktop. It does
not authenticate Windows, store passwords, remove the lock, alter desktop ACLs,
disable UAC/SAC, or provide a shell. The owner types the Windows password in the
normal Windows UI. It is not a pre-login remote host: Desk must already be
running in the owner's console session after that user's first login.

## Trust and installation

The broker and the GUI must have valid, chain-trusted **Authenticode** signatures
from the same pinned signing certificate. A Microsoft Store signature on an
MSIX alone does not satisfy this standalone EXE installer. Store distribution
of LocalSystem packaged services additionally requires approval of restricted
capabilities. Production installation and service modes reject missing trust.
No development certificate or trust-store exception is installed by this code.

The administrative installer uses a protected, fixed `%ProgramFiles%\DeskHost`
directory. It verifies both signatures **before copying service files**. The
native installer derives the authorized user's SID from the installed GUI's
owner; the service image, configuration and registry metadata are writable only
by Administrators and SYSTEM. Installing or enabling it needs the PC owner's
explicit administrative approval. Do not install a preview as a production
service or claim a live lock-screen test passed before it actually does.

The local byte pipe rejects remote connections and admits only SYSTEM and the
configured user. The broker checks the caller's process ID, exact GUI path,
user SID, active console session and trusted publisher. The GUI verifies the
server's SYSTEM token, session zero, exact protected path and installed image
hash before sending anything. Signed GUI updates at the pinned path and with
the same certificate remain supported; a certificate change requires a new
administrative service binding.

## Privileged worker

The LocalSystem service has no network listener. For a verified client lease it
starts a separate headless worker in the active console session using an
explicit inherited-handle list. Only the two anonymous RPC pipes are inherited.
A job object kills the worker when its broker lease ends. The worker disables
token privileges not needed for ordinary desktop access and attaches only to
the known Default, Winlogon or screen-saver desktop. It releases pressed input
on desktop changes and shutdown. There are no persistent GUI windows, file
commands, process-launch RPC, password APIs or keystroke logs.

Requests are bounded to 512 bytes and restricted to state, monitors, capture,
typed input and release. Responses are capped at 32 MiB; images at 3840×2160.
Coordinates refer to the selected capture's physical monitor and virtual
desktop. Positional and keyboard input requires a capture first. Disconnect or
permission revocation closes the lease; a 30-second watchdog removes abandoned
connections. The client uses cancellable, bounded pipe I/O.

## Build and checks

Build for x64 with the .NET Framework C# compiler and reference
`System.ServiceProcess.dll` and `System.Runtime.Serialization.dll`.
`--self-test` validates framing, bounds and native layouts without accessing
the desktop or SCM. `--service`, `--agent` and `--install-client` are production
modes with the trust and identity checks above. A blocked self-test must be
reported, not run through another runtime as a security workaround.

Before public activation, complete trusted signing, an administrative install
and physical tests for lock/unlock, keyboard layouts, multi-monitor/DPI, held
keys during disconnect, permission revocation and service stop. Keep the
previous working Desk installation available until those checks pass.
