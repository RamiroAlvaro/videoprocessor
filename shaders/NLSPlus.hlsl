/*
 * VideoProcessor NLS+ Smart 90 for madVR.
 *
 * Fixed geometry profile for a 16:9 display with a 90% Scope target.
 * VideoProcessor supplies source/target aspect through {{stretch_ratio}}.
 * The shader derives the symmetric lateral crop needed to cap the residual
 * nonlinear correction at 1.08x, then shares that residual 25% horizontally
 * and 75% vertically in logarithmic aspect space.
 *
 * This implementation is original and does not reproduce proprietary Envy
 * code. Its design is informed only by publicly documented NLS behaviour.
 *
 * IMPORTANT PERFORMANCE / QUALITY NOTE
 * ------------------------------------
 * Earlier Smart 90 test builds applied an additional multi-tap prefilter to
 * parts of the pre-resize warp. That looked conservative when the warp was
 * considered in isolation, but it is mathematically unnecessary in the actual
 * madVR pipeline used here.
 *
 * For the supported Scope -> 90% transform the COMPLETE mapping is a
 * magnification in both axes after crop + nonlinear warp + madVR presentation:
 *
 *   2.39:1 example
 *     presentation vertical scale ~= 1.20896x
 *     largest inverse-map Y slope ~= 1.05942
 *     source pixels / displayed pixel <= 1.05942 / 1.20896 ~= 0.876
 *
 *     kept source width ~= 0.8926
 *     largest inverse-map X slope ~= 1.01906
 *     source pixels / displayed pixel <= 0.8926 * 1.01906 ~= 0.910
 *
 * Both maxima are below 1.0, so there is no net local minification and no
 * aliasing condition that requires an anti-minification prefilter. Filtering
 * before madVR's final high-quality resize only spends texture bandwidth and
 * can soften detail. The correct fast path is therefore one native bilinear
 * texture lookup at the warped coordinate, leaving final reconstruction to
 * madVR. Geometry is unchanged from the previous Smart 90 build.
 *
 * IMPORTANT madVR coordinate contract:
 * With madVR hard-coded black-bar crop enabled, the external pre-resize shader
 * operates over the complete active-picture domain. Do not re-apply the
 * original full-raster active-picture bounds here; doing so caused the old
 * horizontal seams at stale top/bottom bar coordinates.
 *
 * $MinimumShaderProfile: ps_3_0
 */

sampler s0 : register(s0);

float NlsSmoothIntegral(float radius)
{
    float r = saturate(radius);
    float r2 = r * r;
    float r3 = r2 * r;
    float r4 = r2 * r2;
    float r5 = r4 * r;
    float r6 = r3 * r3;
    return r - 5.0 * r4 + 6.0 * r5 - 2.0 * r6;
}

float NlsWarpCoordinate(float coordinate, float centerSlope)
{
    float centered = coordinate * 2.0 - 1.0;
    float radius = abs(centered);
    float delta = centerSlope - 1.0;
    float mappedRadius = radius + delta * NlsSmoothIntegral(radius);
    mappedRadius = saturate(mappedRadius);
    return (centered < 0.0 ? -mappedRadius : mappedRadius) * 0.5 + 0.5;
}

float4 main(float2 tex : TEXCOORD0) : COLOR
{
    const float requestedRatio = clamp({{stretch_ratio}}, 1.0, 1.5);
    const bool sourceWider = {{warp_axis}} >= 0.5;

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
        return tex2D(s0, saturate(fittedTex));
    }

    float2 pictureTex = saturate(tex);

    // Smart 90 is intentionally a wider-content profile. The runtime rule
    // normally keeps narrower/equal material out; this guard is fail-safe.
    if (!sourceWider || requestedRatio <= 1.000001)
        return tex2D(s0, pictureTex);

    // Geometry-derived crop. Keep exactly enough width to cap the residual
    // nonlinear correction at 1.08x; easier aspect ratios automatically crop
    // less.
    const float residualLimit = 1.08;
    float residualRatio = min(requestedRatio, residualLimit);
    float keptWidth = clamp(residualRatio / requestedRatio, 0.01, 1.0);
    float sideCrop = 0.5 * (1.0 - keptWidth);

    // Preserve the exact Smart 90 geometry from the preceding build.
    // 25% of logarithmic residual correction goes to X, 75% to Y. The central
    // slope quotient remains exactly residualRatio, preserving centre aspect
    // after madVR applies the presentation aspect.
    const float horizontalShare = 0.25;
    float centerSlopeX = pow(residualRatio, -horizontalShare);
    float centerSlopeY = residualRatio * centerSlopeX;

    float mappedX = NlsWarpCoordinate(pictureTex.x, centerSlopeX);
    float mappedY = NlsWarpCoordinate(pictureTex.y, centerSlopeY);

    float croppedLeft = sideCrop;
    float croppedRight = 1.0 - sideCrop;
    float2 sampleTex = float2(
        lerp(croppedLeft, croppedRight, mappedX), mappedY);

    // No extra prefilter: the complete Smart 90 transform is net magnification
    // everywhere. madVR remains responsible for final high-quality scaling.
    return tex2D(s0, saturate(sampleTex));
}
