# Capture during remote control

Observed in the real 0.14.1 connection after both machines were updated:
direct WebRTC, TLS 1.3, 1920 x 1080 requested at 30 FPS, 6.5–6.6 received FPS,
141 ms capture, 18.5 ms encoding, 179.5 ms frame delivery and one outstanding
frame of about 0.4 KiB. The input channel was dedicated; 0.0 ms application
time is not proof of a successful click/keystroke. The local automation click
was rejected with error 87, so manual input verification was requested.

The previous CaptureSource condition excluded DXGI whenever separate_cursor
was true. Peer._capture sets this true for sessions with control permission,
forcing them onto MSS even on supported single-monitor desktops. Version
0.14.2 removes that exclusion. DXcam's DXGI path is a desktop-surface capture
and does not compose the separate hardware cursor. This matches the MSS
with_cursor=False policy; cursor shapes still travel separately. Software
cursors drawn by applications can be part of either captured surface.

Single-monitor selection, output dimension validation, explicit MSS override,
fallback on initialization/access loss, frame-cache behavior and COM cleanup
are preserved. Multiple-monitor/ambiguous layouts retain the exact MSS monitor.
Protected desktop capture and service authorization are unchanged.

Capture duration included the Windows desktop probe, surface grab and optional
resize. New numeric stage metrics distinguish these without weakening any
desktop checks. A local read-only WTS query timing was below 1 ms, but does
not establish the remote PC's query cost. The remote 141 ms measurement alone
does not prove that all of that time was inside GDI.

References: the installed, pinned DXcam 0.3.0 DXGI implementation and
[DXcam's capture backend guidance](https://github.com/ra1nty/DXcam#capture-backend).
No real capture is executed from shell or tests. GPU and MSS regression
tests use synthetic arrays and stub providers. End-to-end improvement still
requires measuring the updated host during a real authorized session.
