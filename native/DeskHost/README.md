# Desk screen broker — preparation, not an activated service

This optional component supplies capture and typed mouse/keyboard input while
an already-authenticated Desk session reaches the Windows lock desktop. It does
not authenticate Windows, store passwords, remove the lock, alter desktop ACLs,
disable UAC/SAC, or provide a shell. The owner types the Windows password in the
normal Windows UI. It is not a pre-login remote host: Desk must already be
running in the owner's console session after that user's first login.

## Trust and installation

The default distribution mode requires valid, chain-trusted **Authenticode**
signatures from the same pinned certificate. A Microsoft Store signature on
an MSIX alone does not sign this standalone EXE installer. Store distribution
of LocalSystem services additionally requires restricted-capability approval.

For a private pilot, an administrator may explicitly select **fixed-version**
mode. The installer verifies the exact service and GUI hashes embedded in the
prepared package before copying files. The protected installation binds that
GUI path, user SID and exact file hash, and also pins the service image hash.
Every new GUI connection is checked against that binding. Updating the GUI
requires a new administrative binding; it is deliberately not a publisher-wide
grant. These are application IPC authorization pins, **not Windows/WDAC allow
rules**. They never make a file that Windows blocks execute. SAC, Defender,
UAC and Windows authentication remain in force. No development certificate,
trusted-root entry, security exclusion or OS policy exception is installed.

The administrative installer uses a protected, fixed `%ProgramFiles%\DeskHost`
directory. It verifies the selected trust mode **before copying service files**. The
native installer derives the authorized user's SID from the installed GUI's
owner; the service image, configuration and registry metadata are writable only
by Administrators and SYSTEM. Installing or enabling it needs the PC owner's
explicit administrative approval. Do not install a preview as a production
service or claim a live lock-screen test passed before it actually does.

The local byte pipe rejects remote connections and admits only SYSTEM and the
configured user. The broker checks the caller's process ID, exact GUI path,
user SID, active console session and either the trusted publisher or exact GUI
hash. The GUI verifies the
server's SYSTEM token, session zero, exact protected path and installed image
hash before sending anything. In publisher mode, signed GUI updates with the
same certificate remain supported. In fixed-version mode, **every GUI update**
requires a new administrative binding. A certificate/service change requires
administrative approval in either mode.

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
Version 0.13.1 adds a read-only input-state probe (operation 6), returning
desktop generation and whether capture has primed input. The GUI prefers the
administrator-bound service for input on Default as well as protected desktops
only after an approved host-control lease and a successful probe. It compares
physical geometry with the viewer's frame and re-primes capture on desktop or
monitor changes. A switch during capture rejects that input; it does not fall
back to another privilege level. Legacy operation 1 remains unchanged.
Coordinates refer to the selected capture's physical monitor and virtual
desktop. Positional and keyboard input requires a capture first. Disconnect or
permission revocation closes the lease; a 30-second watchdog removes abandoned
connections. The client uses cancellable, bounded pipe I/O.

## Build and checks

Build for x64 with the .NET Framework C# compiler and reference
`System.ServiceProcess.dll` and `System.Runtime.Serialization.dll`.
`--self-test` validates framing, bounds and native layouts without accessing
the desktop or SCM. `--preflight-fixed` only compares explicit package hashes;
it does not authorize a service or modify the system. `--service`, `--agent`,
`--install-client` and `--install-fixed` enforce the checks above. A blocked self-test must be
reported, not run through another runtime as a security workaround.

Before production distribution, complete trusted signing. Before activating a
private pilot, obtain explicit administrative approval of the exact components.
Then complete physical tests for lock/unlock, keyboard layouts, multi-monitor/DPI, held
keys during disconnect, permission revocation and service stop. Keep the
previous working Desk installation available until those checks pass.
