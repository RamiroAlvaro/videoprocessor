# NLS+ for madVR and partial-fill presentation

This experiment adds an HLSL implementation of VideoProcessor's NLS+ mapping so the same logical NLS+ profile can run on madVR as well as VP Renderer/libplacebo.

## Partial-fill target

The physical display remains 16:9. Partial fill is expressed as a less aggressive presentation target, while NLS+ receives the resulting bounded `stretch_ratio` through VideoProcessor's existing geometry contract.

For a 16:9 screen and requested active-picture height fraction `F`:

`target_aspect = (16 / 9) / F`

The initial test target is now **82%**. This corresponds to an effective aspect of about **2.1680:1** (`800:369`). A 2.39:1 movie therefore needs only about **1.1024x** aspect correction instead of the 1.344x correction required for a complete 16:9 fill.

The sample configuration adds `vprenderer.viewport.partial_82` with `screen_aspect: 800:369`. Select that viewport and then select `NLS+`.

## Variable-aspect / IMAX Enhanced content

The NLS+ test profile uses `aspect_direction: wider_only`. That is deliberate for movies which change aspect ratio during playback, such as Disney+ IMAX Enhanced titles.

With the 82% partial-fill target:

- 2.35-2.40:1 scope content is wider than the 2.1680 target, so NLS+ is active.
- 2.20:1 content is already very close to the requested fill and falls into the configured tolerance/deadband.
- 2.00:1, 1.90:1 IMAX and 1.85:1 content are narrower than the partial-fill target, so VideoProcessor uses linear passthrough instead of stretching them in the opposite direction.
- When a movie changes back from 1.90:1 to 2.39:1, NLS+ becomes active again after the active-picture geometry is stable.

This prevents a 2.39 -> 1.90 -> 2.39 movie from being forced toward 2.1680 in its IMAX scenes. The taller IMAX image is preserved naturally.

`tolerance_percent: 2` provides a small deadband around the partial-fill threshold, in addition to VideoProcessor's existing stable active-picture geometry logic.

## Suggested first test

- physical display: 16:9
- viewport: `Partial Fill 82%`
- shader: `NLS+`
- geometry: protected
- horizontal centre protection: 0.40
- vertical centre protection: 0.30
- axis balance: 0.25
- max centre zoom: 1.08
- curve: 2.0
- tolerance: 2%
- aspect direction: `wider_only`
- source: both a normal 2.35-2.40:1 movie and a variable-aspect 2.39/1.90 IMAX title

Check faces and circles in the centre, slow horizontal pans, objects crossing from centre to the sides, the aspect-ratio transitions, madVR rendering time, repeated/dropped frames, and the remaining top/bottom bars.

## Tuning other fill levels

For a physical 16:9 display:

- 80% -> target aspect about 2.2222:1
- 82% -> target aspect about 2.1680:1 (initial test)
- 83% -> target aspect about 2.1422:1
- 85% -> target aspect about 2.0915:1

The 82% target is intentionally a moderate first step: more aggressive than the original 80% experiment, while still leaving room to increase fill later if the geometry remains visually transparent.
