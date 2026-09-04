/*
 * VideoProcessor NLS+ for madVR.
 *
 * The first madVR implementation intentionally reuses the proven one-axis
 * protected NLS mapping and sampling structure from NLS.hlsl.  Partial-fill
 * reduces the required correction before it reaches this shader, so the
 * established madVR path is preferred over introducing a second, more complex
 * HLSL program during initial validation.
 *
 * $MinimumShaderProfile: ps_3_0
 */

sampler s0 : register(s0);

float4 main(float2 tex : TEXCOORD0) : COLOR
{
    const float strength = saturate({{strength}});
    const float curve = clamp({{curve}}, 1.0, 2.9);
    const float stretchRatio = clamp({{stretch_ratio}}, 1.0, 1.5);
    const bool verticalWarp = {{warp_axis}} >= 0.5;
    const float activeLeft = saturate({{active_left}});
    const float activeTop = saturate({{active_top}});
    const float activeRight = clamp({{active_right}}, activeLeft + 0.01, 1.0);
    const float activeBottom = clamp({{active_bottom}}, activeTop + 0.01, 1.0);
    const float activeWidthFraction = activeRight - activeLeft;
    const float activeHeightFraction = activeBottom - activeTop;
    const int geometry = (int)clamp({{geometry}}, 0.0, 1.0);
    const int quality = (int)clamp({{quality}}, 0.0, 3.0);
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
        fittedCoordinate = (fittedCoordinate - safeFitStart) / safeFitFraction;
        if (safeFitVertical)
            fittedTex.y = fittedCoordinate;
        else
            fittedTex.x = fittedCoordinate;
        return tex2D(s0, float2(
            lerp(activeLeft, activeRight, fittedTex.x),
            lerp(activeTop, activeBottom, fittedTex.y)));
    }

    const float2 activeMinimum = float2(activeLeft, activeTop);
    const float2 activeMaximum = float2(activeRight, activeBottom);
    const float2 activeSize = activeMaximum - activeMinimum;
    const bool insideActivePicture =
        tex.x >= activeLeft && tex.x <= activeRight &&
        tex.y >= activeTop && tex.y <= activeBottom;
    float2 activeTex = saturate((tex - activeMinimum) / activeSize);
    float centeredCoordinate =
        (verticalWarp ? activeTex.y : activeTex.x) * 2.0 - 1.0;
    float radius = abs(centeredCoordinate);

    float mappedRadius;
    const float effectiveRatio = lerp(1.0, stretchRatio, strength);
    const float centerProtection = clamp({{center_protection}}, 0.0, 0.45);
    if (geometry == 0 || centerProtection <= 0.0)
    {
        mappedRadius = effectiveRatio * radius -
            (effectiveRatio - 1.0) * pow(radius, curve);
    }
    else if (radius <= centerProtection)
    {
        mappedRadius = radius * effectiveRatio;
    }
    else
    {
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

        float startPosition = centerProtection * effectiveRatio;
        float startSlope = effectiveRatio;
        float edgeSlope = max(0.20,
            1.0 - 0.5 * (effectiveRatio - 1.0) * curve);
        mappedRadius = h00 * startPosition + h10 * span * startSlope +
            h01 + h11 * span * edgeSlope;
    }

    centeredCoordinate =
        (centeredCoordinate < 0.0 ? -mappedRadius : mappedRadius);
    float warpedCoordinate = centeredCoordinate * 0.5 + 0.5;

    float footprint = verticalWarp ?
        max(abs(ddy(warpedCoordinate)), abs(ddy(activeTex.y))) :
        max(abs(ddx(warpedCoordinate)), abs(ddx(activeTex.x)));
    if (!insideActivePicture)
        return tex2D(s0, tex);
    float2 sampleTex = tex;
    if (verticalWarp)
        sampleTex.y = lerp(activeTop, activeBottom, warpedCoordinate);
    else
        sampleTex.x = lerp(activeLeft, activeRight, warpedCoordinate);
    float2 sampleAxis = verticalWarp ?
        float2(0.0, activeHeightFraction) : float2(activeWidthFraction, 0.0);
    if (quality == 0)
        return tex2D(s0, sampleTex);

    if (quality == 1)
    {
        float4 color = 0.0;
        color += tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.125, activeMinimum, activeMaximum)) * 0.125;
        color += tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.375, activeMinimum, activeMaximum)) * 0.375;
        color += tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.375, activeMinimum, activeMaximum)) * 0.375;
        color += tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.125, activeMinimum, activeMaximum)) * 0.125;
        return color;
    }

    if (quality == 2)
    {
        float4 c0 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 2.5, activeMinimum, activeMaximum));
        float4 c1 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.5, activeMinimum, activeMaximum));
        float4 c2 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.5, activeMinimum, activeMaximum));
        float4 c3 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.5, activeMinimum, activeMaximum));
        float4 c4 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.5, activeMinimum, activeMaximum));
        float4 c5 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 2.5, activeMinimum, activeMaximum));
        float4 color =
            (c2 + c3) * 0.6114130435 +
            (c1 + c4) * -0.1358695652 +
            (c0 + c5) * 0.0244565217;
        float4 neighborhoodMin = min(min(c0, c1), min(min(c2, c3), min(c4, c5)));
        float4 neighborhoodMax = max(max(c0, c1), max(max(c2, c3), max(c4, c5)));
        return clamp(color, neighborhoodMin, neighborhoodMax);
    }

    float4 c0 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 3.5, activeMinimum, activeMaximum));
    float4 c1 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 2.5, activeMinimum, activeMaximum));
    float4 c2 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.5, activeMinimum, activeMaximum));
    float4 c3 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.5, activeMinimum, activeMaximum));
    float4 c4 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.5, activeMinimum, activeMaximum));
    float4 c5 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.5, activeMinimum, activeMaximum));
    float4 c6 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 2.5, activeMinimum, activeMaximum));
    float4 c7 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 3.5, activeMinimum, activeMaximum));
    float4 color =
        (c3 + c4) * 0.6188774241 +
        (c2 + c5) * -0.1660113634 +
        (c1 + c6) * 0.0597640908 +
        (c0 + c7) * -0.0126301515;
    float4 neighborhoodMin = min(min(min(c0, c1), min(c2, c3)),
        min(min(c4, c5), min(c6, c7)));
    float4 neighborhoodMax = max(max(max(c0, c1), max(c2, c3)),
        max(max(c4, c5), max(c6, c7)));
    return clamp(color, neighborhoodMin, neighborhoodMax);
}
