# NLS+ for madVR and partial-fill presentation

This experiment adds an HLSL implementation of VideoProcessor's NLS+ mapping so the same logical NLS+ profile can run on madVR as well as VP Renderer/libplacebo.

## Why partial fill uses a virtual target aspect

The physical display remains 16:9. For partial fill, VideoProcessor should not pretend that the NLS shader alone owns presentation geometry. Instead the viewport supplies a less aggressive geometric target and NLS+ receives the resulting bounded `stretch_ratio` through the existing runtime contract.

For a 16:9 screen and a requested active-picture height fraction `F`, the equivalent virtual target aspect is:

`target_aspect = (16 / 9) / F`

For `F = 0.80`, the result is `20:9` (2.2222:1). A 2.39:1 movie therefore needs only about 1.0755x aspect correction instead of the 1.344x correction required to force a complete 16:9 fill.

The sample configuration adds `vprenderer.viewport.partial_80` with `screen_aspect: 20:9`. Select that viewport and then select `NLS+`.

## Suggested first test

- physical display: 16:9
- viewport: `Partial Fill 80%`
- shader: `NLS+`
- geometry: protected
- horizontal centre protection: 0.35
- vertical centre protection: 0.25
- axis balance: 0.25
- max centre zoom: 1.08
- curve: 2.0
- source: 2.35-2.40:1 movie at 23.976/24 Hz

Check faces and circles in the centre, slow horizontal pans, objects crossing from centre to the sides, madVR rendering time, repeated/dropped frames, and the remaining top/bottom bars.

## Tuning other fill levels

For a physical 16:9 display:

- 78% -> target aspect about 2.2792:1
- 80% -> 2.2222:1 (20:9)
- 82% -> about 2.1680:1
- 85% -> about 2.0915:1

Using a virtual target aspect keeps target geometry in VideoProcessor's presentation layer and avoids introducing a second, shader-private target calculation that could disagree with madVR's output contract.
