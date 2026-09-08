# NLS+ for madVR and partial-fill presentation

This experiment adds an HLSL implementation of VideoProcessor's NLS+ mapping so the same logical NLS+ profile can run on madVR as well as VP Renderer/libplacebo.

The implementation is original VideoProcessor code. It is inspired by publicly documented madVR Envy NLS+ behaviour (crop/zoom plus nonlinear correction, protected central geometry, and bounded stretch), but does not contain or reverse-engineer proprietary Envy code.

## Project-native partial fill

The physical viewport remains exactly what it is: for a 16:9 display, `screen_aspect` stays `16:9`.

Partial fill is an NLS-profile property. For physical screen aspect `S` and requested active-picture height fraction `F`:

`effective_nls_target_aspect = S / F`

The first field test used `target_fill: 0.82`. With a 16:9 screen that produced a target of about 2.1680:1 and correctly reduced the bars, but the required ~10% one-axis vertical nonlinear correction was visibly objectionable on faces. The user described the result as a funhouse-mirror effect.

## Smart Partial Fit: crop first, then small two-axis correction

The next madVR field-test preset follows the public NLS+ design principle that a modest crop can substantially reduce the nonlinear stretch required to reach a desired presentation size.

The preset uses:

- physical viewport: 16:9
- `target_fill: 0.86`
- maximum symmetric side crop in the madVR HLSL path: 5% per edge
- `axis_balance: 0.50`
- `max_center_zoom: 1.04`
- horizontal centre protection: 0.35
- vertical centre protection: 0.35
- protected geometry
- medium reconstruction quality for the first field validation

For a measured ~2.388:1 scope source:

- the 86% height target is about 2.0672:1;
- without crop the requested aspect correction would be about 1.155x;
- 5% crop per side retains 90% of the source width and supplies most of that correction geometrically;
- the remaining correction is only about 1.040x;
- with `axis_balance: 0.50`, that residual is shared between horizontal and vertical nonlinear maps instead of being applied as a ~10-15% vertical warp.

At 2160 lines, 86% active-picture height intentionally leaves about 151 black pixels above and below the image. The objective is not to fill the 16:9 screen; it is to make scope content visibly larger while retaining bars and minimizing visible geometry distortion.

The side crop is automatically reduced if less crop is needed for a source closer to the target aspect. It must never crop past the requested target geometry.

## Why this is closer to Envy NLS+ behaviour

Public Envy documentation and user guidance describe NLS+ as a compromise among zoom/crop, center protection, horizontal and vertical nonlinear areas/strength, and maximum stretch. The important design lesson for this experiment is that crop and stretch are complementary: accepting a small amount of symmetric edge loss lets the nonlinear component become much gentler.

VideoProcessor therefore treats the following as separate responsibilities:

1. active-picture detection decides where the real image begins and the encoded black bars end;
2. `target_fill` decides how much of the physical 16:9 screen height should be used;
3. bounded symmetric side crop reduces the residual aspect correction;
4. a protected two-axis nonlinear map handles only the remaining correction;
5. madVR owns final presentation and black-bar crop/fit.

## DirectShow / madVR prerequisites found in field testing

For the tested DeckLink capture path, `V210_TO_P010` is required for reliable madVR hard-coded black-bar detection. With P010 active, VideoProcessor consistently detected the 3840x1608 active picture inside the 3840x2160 HDMI raster (~2.388:1).

External madVR pixel shaders also require the legacy DirectX compiler runtime on the test machine. Before `D3DCompiler_43.dll` was installed, madVR returned `0x80004005` from `AddPixelShader`. After installing the Microsoft DirectX June 2010 runtime, the same NLS+ shader installed with `HRESULT=0x00000000` and the pre-resize stage became active.

## Variable-aspect / IMAX Enhanced content

The NLS+ profile remains `aspect_direction: wider_only`.

With the 86% partial-fill target:

- normal 2.35-2.40:1 scope content is wider than the ~2.067 target, so Smart Partial NLS+ is active;
- ~2.00:1, 1.90:1 IMAX and 1.85:1 content are narrower than the target and therefore use passthrough rather than reverse stretching;
- when content changes back to scope, NLS+ re-engages only after the existing active-picture geometry stabilization accepts the new scope geometry.

The physical viewport and Windows/madVR display mode remain 16:9 throughout.

## Field validation checklist

For the Smart Partial 86% build, verify:

- the image still has visible top/bottom bars;
- side crop is small and symmetric;
- faces near the center retain believable proportions;
- circles, doors and subtitles do not visibly bend;
- objects crossing the protected center into the outer region do not show a sudden rubber-band transition;
- slow horizontal and vertical pans do not expose a moving funhouse-mirror boundary;
- 2.39 -> 1.90 -> 2.39 material transitions between NLS+ / passthrough / NLS+ cleanly;
- madVR rendering time remains below the 41.67 ms budget at 24 fps and dropped/repeated frames stay stable after transitions settle.

If the 86% / 5% preset is still visibly deforming faces, the next tuning step should prefer slightly more crop or slightly less fill before increasing nonlinear strength. If it is visually transparent, the crop/fill balance can then be tuned toward the user's preferred screen utilization.
