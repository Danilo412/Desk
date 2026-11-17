# Service identity check in 0.13.2

An approved session on 0.13.1 reached the notebook video, but the ordinary
GUI could not use the administrator-installed broker. Its server check tried
to open the LocalSystem process and then query its token. A read-only local
probe confirmed that opening an existing system-service process with
PROCESS_QUERY_LIMITED_INFORMATION was denied while querying its SCM status
and configuration succeeded. This reproduces an incompatible prerequisite;
it does not establish the exact failure stage on every remote host.

Microsoft documents the cross-account privilege requirements of
[OpenProcessToken](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocesstoken).
The GUI must remain unelevated and must not enable debugging privileges.

The replacement check uses only read access to the local Service Control
Manager. Before exchanging any application request it verifies all of:

- The pipe's kernel-reported server PID matches DeskScreenBroker's running PID.
- The pipe server's kernel-reported session is zero.
- SCM configuration and status both identify an own-process service.
- The service account is LocalSystem.
- The configured command exactly matches the pinned DeskHost image and --service.
- The installed image hash equals the administrator's protected ServiceHash.
- A second SCM snapshot matches the first, rejecting a restart or change.

No process/token handles are requested from the GUI. The server still
independently enforces the administrator-approved owner, GUI image path,
exact version or trusted publisher, active console, and typed bounded RPCs.
No policy exception, root certificate, service ACL expansion, or implicit
control authorization is introduced.

Connection-constructor errors now enter the normal bounded numeric diagnostic
path and close a failed connection. Reauthorization during connection setup
rejects the old connection before sending a request. The status button always
shows a numbered, timestamped result even when the service state is unchanged.

Automated tests exercise identity mismatch, changed binaries, service restart,
connection failures/retries, lease cancellation, and read-only visible UI
feedback. These tests do not certify live mouse, keyboard, or lock-screen
behavior. Those still require an authorized two-computer test and the owner's
manual Windows authentication. The preview is not a stable-channel release.
