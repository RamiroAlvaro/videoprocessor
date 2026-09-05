/*
 * VideoProcessor NLS+ Smart 90 for madVR.
 *
 * Original implementation informed by public NLS literature and behaviour:
 * - use a small, geometry-derived crop first;
 * - share the remaining correction across both axes;
 * - keep central geometry exact;
 * - move distortion gradually toward the frame edges;
 * - keep the mapping monotonic and endpoint preserving.
 *
 * This does not reproduce or reverse-engineer proprietary madVR Envy code.
 * It is an independently derived fixed profile for a 16:9 display with a
 * 90% Scope target.  VideoProcessor supplies the source/target aspect ratio as
 * {{stretch_ratio}}; the shader then automatically chooses the minimum crop
 * required to keep the nonlinear residual at or below 1.08x.
 *
 * For target_fill=0.90 on a 16:9 display, representative side crops are:
 *   2.35:1 -> ~4.61% per side
 *   2.39:1 -> ~5.37% per side
 *   2.40:1 -> ~5.56% per side
 * The remaining correction is capped at 1.08x.
 *
 * The residual correction is deliberately vertical-dominant: 25% of the
 * logarithmic correction is assigned to horizontal compression and 75% to
 * vertical expansion.  This still uses both axes, but keeps horizontal local
 * scale changes small to reduce the classic side-warp effect during camera
 * pans.  At the 1.08x cap the inverse-map centre slopes are approximately
 * 0.98094 (X) and 1.05942 (Y), whose quotient exactly preserves centre aspect.
 *
 * The spatial ramp is the integral of a quintic smootherstep-derived profile:
 *   phi(r) = 1 - 20r^3 + 30r^4 - 12r^5
 *   F(r)   = r - 5r^4 + 6r^5 - 2r^6,  F'(r)=phi(r)
 * F(0)=F(1)=0, so the centre and frame edges remain anchored.  phi has zero
 * first/second derivative at both ends, avoiding the hard transition of the
 * previous protected-centre Hermite map.  At the 1.08x residual cap every
 * local inverse-map slope remains comfortably positive, so fold-over cannot
 * occur.
 *
 * IMPORTANT madVR coordinate contract:
 * With madVR hard-coded black-bar crop enabled, the external pre-resize shader
 * operates over the complete active-picture domain.  Do not re-apply the
 * original full-raster active-picture bounds here; doing so caused the old
 * horizontal seams at the stale top/bottom bar boundaries.
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

float4 FilterAlongAxis(float2 sampleTex, float2 sampleAxis, float footprint,
    float2 sampleMinimum, float2 sampleMaximum, int quality)
{
    if (quality == 0)
        return tex2D(s0, sampleTex);

    if (quality == 1)
    {
        float4 color = 0.0;
        color += tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.125,
            sampleMinimum, sampleMaximum)) * 0.125;
        color += tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.375,
            sampleMinimum, sampleMaximum)) * 0.375;
        color += tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.375,
            sampleMinimum, sampleMaximum)) * 0.375;
        color += tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.125,
            sampleMinimum, sampleMaximum)) * 0.125;
        return color;
    }

    if (quality == 2)
    {
        float4 c0 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 2.5,
            sampleMinimum, sampleMaximum));
        float4 c1 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.5,
            sampleMinimum, sampleMaximum));
        float4 c2 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.5,
            sampleMinimum, sampleMaximum));
        float4 c3 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.5,
            sampleMinimum, sampleMaximum));
        float4 c4 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.5,
            sampleMinimum, sampleMaximum));
        float4 c5 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 2.5,
            sampleMinimum, sampleMaximum));
        float4 color =
            (c2 + c3) * 0.6114130435 +
            (c1 + c4) * -0.1358695652 +
            (c0 + c5) * 0.0244565217;
        float4 neighborhoodMin = min(min(c0, c1),
            min(min(c2, c3), min(c4, c5)));
        float4 neighborhoodMax = max(max(c0, c1),
            max(max(c2, c3), max(c4, c5)));
        return clamp(color, neighborhoodMin, neighborhoodMax);
    }

    float4 c0 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 3.5,
        sampleMinimum, sampleMaximum));
    float4 c1 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 2.5,
        sampleMinimum, sampleMaximum));
    float4 c2 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 1.5,
        sampleMinimum, sampleMaximum));
    float4 c3 = tex2D(s0, clamp(sampleTex - sampleAxis * footprint * 0.5,
        sampleMinimum, sampleMaximum));
    float4 c4 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 0.5,
        sampleMinimum, sampleMaximum));
    float4 c5 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 1.5,
        sampleMinimum, sampleMaximum));
    float4 c6 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 2.5,
        sampleMinimum, sampleMaximum));
    float4 c7 = tex2D(s0, clamp(sampleTex + sampleAxis * footprint * 3.5,
        sampleMinimum, sampleMaximum));
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

float4 main(float2 tex : TEXCOORD0) : COLOR
{
    const float requestedRatio = clamp({{stretch_ratio}}, 1.0, 1.5);
    const bool sourceWider = {{warp_axis}} >= 0.5;
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
        return tex2D(s0, saturate(fittedTex));
    }

    float2 pictureTex = saturate(tex);

    // Smart 90 is intentionally a wider-content profile.  The rule's
    // aspect_direction=wider_only normally keeps narrower/equal content out of
    // this shader; this guard makes the shader fail-safe if configuration ever
    // routes such content here.
    if (!sourceWider || requestedRatio <= 1.000001)
        return tex2D(s0, pictureTex);

    // Distortion-budget crop.  Rather than using a fixed crop percentage, keep
    // exactly enough source width to limit the nonlinear correction to 1.08x.
    // For easier cases no crop is required at all.
    const float residualLimit = 1.08;
    float residualRatio = min(requestedRatio, residualLimit);
    float keptWidth = clamp(residualRatio / requestedRatio, 0.01, 1.0);
    float sideCrop = 0.5 * (1.0 - keptWidth);

    // Use both axes, but bias the correction vertically for Scope -> taller
    // presentation.  p=0.25 means 25% of the logarithmic residual is handled
    // by X and 75% by Y.  The centre slopes satisfy
    //     slopeY / (residualRatio * slopeX) == 1
    // exactly, so a small central circle remains a circle after presentation.
    const float horizontalShare = 0.25;
    float centerSlopeX = pow(residualRatio, -horizontalShare);
    float centerSlopeY = residualRatio * centerSlopeX;

    float mappedX = NlsWarpCoordinate(pictureTex.x, centerSlopeX);
    float mappedY = NlsWarpCoordinate(pictureTex.y, centerSlopeY);

    float croppedLeft = sideCrop;
    float croppedRight = 1.0 - sideCrop;
    float2 sampleMinimum = float2(croppedLeft, 0.0);
    float2 sampleMaximum = float2(croppedRight, 1.0);
    float2 sampleTex = float2(
        lerp(croppedLeft, croppedRight, mappedX), mappedY);

    // Scope -> taller has its only potentially minifying nonlinear component
    // on Y.  X is crop/magnification plus a small horizontal correction, so
    // retain the proven single-axis prefilter and avoid an unnecessary second
    // separable pass.
    float footprint = max(abs(ddy(sampleTex.y)), abs(ddy(pictureTex.y)));
    float2 sampleAxis = float2(0.0, 1.0);

    return FilterAlongAxis(sampleTex, sampleAxis, footprint,
        sampleMinimum, sampleMaximum, quality);
}
