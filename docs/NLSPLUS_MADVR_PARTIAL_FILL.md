# NLS+ for madVR and partial-fill presentation

This experiment adds an HLSL implementation of VideoProcessor's NLS+ mapping so the same logical NLS+ profile can run on madVR as well as VP Renderer/libplacebo.

## Project-native partial fill

The physical viewport remains exactly what it is: for a 16:9 display, `screen_aspect` stays `16:9`.

Partial fill is now an NLS-profile property:

`target_fill: 0.82`

This follows VideoProcessor's existing separation between viewport presentation and the NLS geometric target. The runtime keeps the physical viewport target and derives an NLS-only target from it. No fake 2.168:1 screen/viewport is created.

For physical screen aspect `S` and requested active-picture height fraction `F`:

`effective_nls_target_aspect = S / F`

For `S = 16/9` and `F = 0.82`, the effective NLS target is about **2.1680:1**. A 2.39:1 movie therefore needs only about **1.1024x** aspect correction instead of the 1.344x correction required for a complete 16:9 fill.

Omitting `target_fill`, or setting it to `1.0`, preserves the historical NLS target behavior.

## Variable-aspect / IMAX Enhanced content

The NLS+ profile uses `aspect_direction: wider_only`. That is deliberate for movies which change aspect ratio during playback, such as IMAX Enhanced titles.

With the 82% partial-fill target:

- 2.35-2.40:1 scope content is wider than the ~2.168 target, so NLS+ is active.
- ~2.20:1 content is already close to the requested fill and is protected by the configured tolerance/deadband.
- 2.00:1, 1.90:1 IMAX and 1.85:1 content are narrower than the NLS-only target, so VideoProcessor uses linear passthrough rather than reverse stretching them.
- When a movie changes back from 1.90:1 to 2.39:1, NLS+ becomes active again after the existing active-picture geometry stabilisation accepts the scope geometry.

The viewport and Windows/madVR display mode remain 16:9 throughout these transitions.

`tolerance_percent: 2` provides a small deadband around the partial-fill threshold, in addition to VideoProcessor's existing stable active-picture geometry logic.

## Suggested first test

- physical display / viewport: `16:9`
- shader: `NLS+`
- `target_fill: 0.82`
- geometry: protected
- horizontal centre protection: 0.40
- vertical centre protection: 0.30
- axis balance: 0.25
- max centre zoom: 1.08
- curve: 2.0
- tolerance: 2%
- aspect direction: `wider_only`
- source: both a normal 2.35-2.40:1 movie and a variable-aspect 2.39/1.90 IMAX title

Check faces and circles in the centre, slow horizontal pans, objects crossing from centre to the sides, aspect-ratio transitions, madVR rendering time, repeated/dropped frames, and the remaining top/bottom bars.

## Tuning other fill levels

For a physical 16:9 display:

- 80% -> effective NLS target about 2.2222:1
- 82% -> effective NLS target about 2.1680:1 (initial test)
- 83% -> effective NLS target about 2.1422:1
- 85% -> effective NLS target about 2.0915:1

The 82% target is intentionally a moderate first step: more aggressive than the original 80% experiment, while still leaving room to increase fill later if the geometry remains visually transparent.
