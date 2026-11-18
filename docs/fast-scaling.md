# Screen scaling latency

The live 0.14.2 session used DXGI at 1920 x 1080, requested 30 FPS and
received about 11 FPS. The measured capture stage was 78 ms: desktop query
0 ms, acquisition 16 ms, scaling 62 ms. Encoding was 21.9 ms and frame
delivery 115.3 ms. The network remained direct, with about 14 ms RTT.
Dedicated input application time was 4.1 ms. These are measurements of that
session, not guarantees for other machines.

0.14.3 retains Lanczos resizing and output dimensions. For compatible sizes,
up to four workers resize horizontal strips and combine them. Strip bounds
are integer source rows. The implementation also preserves the horizontal/
vertical pass order selected by the pinned Pillow 13 implementation, since
its 8-bit intermediate rounding differs between pass orders. Unsafe strip
layouts, small images, one-worker systems and worker errors use the original
whole-image Lanczos path. Jobs never accumulate across frames; capture waits
for this bounded batch. Capture context teardown closes the worker pool.

Only a capture-provider-confirmed unchanged frame with the same PIL image
identity, source/monitor geometry, mode and target size may reuse a previous
scaled image. A changed provider flag, image, source, monitor or target forces
recalculation. Mouse coordinates continue to map onto the original native
monitor geometry. No Windows display resolution is changed.

The motion classifier's 80 x 45 thumbnail uses Pillow's reducing_gap=3.0
optimization. This affects codec activity detection, not the displayed image.
The lossless tile encoder avoids copying already-RGB input before reading its
immutable byte snapshot. Inputs of other modes retain the RGB conversion.

Synthetic full-quality strip prototypes measured 2560 x 1440 -> 1920 x 1080
at 41.67 ms serial vs 18.24 ms parallel, and 3840 x 2160 -> 1920 x 1080
at 71.69 ms vs 28.67 ms. Tests compare complete output pixel buffers, including
random patterns across strip boundaries and portrait/odd geometries. These
local results do not prove an improvement on the remote PC.

The optional native service remains excluded; no replacement service is
built or used to evade its previous Windows error 4551. Fixed-version service
bindings remain incompatible with the updated GUI until properly validated
and rebound by the owner. Publishing the application is not Authenticode.

References: [Pillow resize documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize)
and [the pinned resampling implementation](https://github.com/python-pillow/Pillow/blob/13.0.0/src/libImaging/Resample.c).
