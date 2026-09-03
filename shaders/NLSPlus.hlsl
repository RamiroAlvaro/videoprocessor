/*
 * VideoProcessor NLS+ balanced nonlinear stretch for madVR.
 *
 * HLSL/D3D9 counterpart of NLSPlus.glsl. VideoProcessor owns the target
 * aspect ratio, active-picture geometry, and safe-fit decision. The shader
 * receives only bounded runtime parameters and applies a two-axis nonlinear
 * inverse map. A protected central region keeps faces and central objects
 * geometrically natural while progressively moving the remaining correction
 * toward the edges.
 *
 * $MinimumShaderProfile: ps_3_0
 */

sampler s0 : register(s0);

float NlsPlusMapRadius(float radius, float centerScale,
                       float curve, int geometry,
                       float centerProtection)
{
    if (geometry == 0 || centerProtection <= 0.0)
    {
        return centerScale * radius -
            (centerScale - 1.0) * pow(radius, curve);
    }

    if (radius <= centerProtection)
        return radius * centerScale;

    float span = 1.0 - centerProtection;
    float t = saturate((radius - centerProtection) / span);
    float t2 = t * t;
    float t3 = t2 * t;
    float t4 = t3 * t;
    float t5 = t4 * t;

    float h00 = 1.0 - 10.0 * t3 + 15.0 * t4 - 6.0 * t5;
    float h10 = t - 6.0 * t3 + 8.0 * t4 - 3.0 * t5;
    float h01 = 10.0 * t3 - 15.0 * t4 + 6.0 * t5;
    float h11 = -4.0 * t3 + 7.0 * t4 - 3.0 * t5;

    float startPosition = centerProtection * centerScale;
    float startSlope = centerScale;
    float edgeSlope = max(0.20,
        1.0 - 0.5 * (centerScale - 1.0) * curve);

    return h00 * startPosition + h10 * span * startSlope +
        h01 + h11 * span * edgeSlope;
}

float NlsPlusMapCoordinate(float coordinate, float centerScale,
                           float curve, int geometry,
                           float centerProtection)
{
    float centered = coordinate * 2.0 - 1.0;
    float mappedRadius = NlsPlusMapRadius(abs(centered), centerScale,
        curve, geometry, centerProtection);
    return (centered < 0.0 ? -mappedRadius : mappedRadius) * 0.5 + 0.5;
}

float4 main(float2 tex : TEXCOORD0) : COLOR
{
    const float strength = saturate({{strength}});
    const float curve = clamp({{curve}}, 1.0, 2.9);
    const float ratio = clamp({{stretch_ratio}}, 1.0, 1.5);
    const float requestedBalance = saturate({{axis_balance}}) * strength;
    const float maxCenterZoom = clamp({{max_center_zoom}}, 1.0, 1.25);
    const bool sourceWider = {{warp_axis}} >= 0.5;
    const int geometry = (int)clamp({{geometry}}, 0.0, 1.0);
    const float horizontalCenterProtection =
        clamp({{horizontal_center_protection}}, 0.0, 0.45);
    const float verticalCenterProtection =
        clamp({{vertical_center_protection}}, 0.0, 0.45);

    const float activeLeft = saturate({{active_left}});
    const float activeTop = saturate({{active_top}});
    const float activeRight = clamp({{active_right}}, activeLeft + 0.01, 1.0);
    const float activeBottom = clamp({{active_bottom}}, activeTop + 0.01, 1.0);
    const float2 activeMinimum = float2(activeLeft, activeTop);
    const float2 activeMaximum = float2(activeRight, activeBottom);
    const float2 activeSize = activeMaximum - activeMinimum;

    const bool safeFit = {{safe_fit}} >= 0.5;
    const bool safeFitVertical = {{safe_fit_axis}} >= 0.5;
    const float safeFitFraction = clamp({{safe_fit_fraction}}, 0.01, 1.0);

    if (safeFit)
    {
        float2 fittedTex = tex;
        float safeFitStart = (1.0 - safeFitFraction) * 0.5;
        float safeFitEnd = 1.0 - safeFitStart;
        float fittedCoordinate = safeFitVertical ? tex.y : tex.x;
        if (fittedCoordinate < safeFitStart || fittedCoordinate > safeFitEnd)
            return float4(0.0, 0.0, 0.0, 1.0);

        fittedCoordinate =
            (fittedCoordinate - safeFitStart) / safeFitFraction;
        if (safeFitVertical)
            fittedTex.y = fittedCoordinate;
        else
            fittedTex.x = fittedCoordinate;

        return tex2D(s0, float2(
            lerp(activeLeft, activeRight, fittedTex.x),
            lerp(activeTop, activeBottom, fittedTex.y)));
    }

    const bool insideActivePicture =
        tex.x >= activeLeft && tex.x <= activeRight &&
        tex.y >= activeTop && tex.y <= activeBottom;
    if (!insideActivePicture)
        return tex2D(s0, tex);

    float2 activeTex = saturate((tex - activeMinimum) / activeSize);

    // Share the aspect correction between both axes. The quotient of the two
    // centre slopes always equals the required target/source correction, so the
    // presentation layer sees the correct DAR while the centre can use a nearly
    // isotropic zoom instead of a conspicuous one-axis stretch.
    float ratioLog = log(max(ratio, 1.000001));
    float balanceLimit = ratio <= 1.000001 ? 1.0 :
        log(maxCenterZoom) / ratioLog;
    float balance = min(requestedBalance, saturate(balanceLimit));

    float q = sourceWider ? 1.0 / ratio : ratio;
    float xExponent = sourceWider ? balance : 1.0 - balance;
    float yExponent = sourceWider ? balance - 1.0 : -balance;
    float xScale = pow(q, xExponent);
    float yScale = pow(q, yExponent);

    float2 mapped = activeTex;
    mapped.x = NlsPlusMapCoordinate(mapped.x, xScale, curve, geometry,
        horizontalCenterProtection);
    mapped.y = NlsPlusMapCoordinate(mapped.y, yScale, curve, geometry,
        verticalCenterProtection);

    float2 sampleTex = lerp(activeMinimum, activeMaximum,
        clamp(mapped, 0.0, 1.0));

    // NLS+ is intentionally pre-resize. madVR performs the final scaling after
    // this pass, so a single filtered source lookup keeps the warp inexpensive
    // and avoids the 4K post-resize multi-tap cost that can exhaust the queue.
    return tex2D(s0, sampleTex);
}
