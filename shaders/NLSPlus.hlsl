/*
 * VideoProcessor NLS+ Smart Partial Fit for madVR.
 *
 * This is an original, Envy-inspired implementation based only on the public
 * NLS+ behaviour documented by madVR Labs: combine crop with horizontal and
 * vertical nonlinear correction, protect the centre, and use only the amount
 * of correction required by the selected target.  It does not reproduce or
 * reverse-engineer proprietary Envy code.
 *
 * IMPORTANT madVR coordinate contract:
 * VideoProcessor still uses its detected active-picture bounds to decide the
 * source aspect and target geometry.  However, when madVR hard-coded black-bar
 * cropping is enabled, the external pre-resize shader operates in the picture
 * domain presented by madVR.  Re-applying the original full-raster top/bottom
 * bounds inside this shader creates horizontal seams: the middle of the frame
 * receives the NLS+/side-crop X mapping while the rows outside those stale
 * bounds keep the old X mapping.  Therefore this HLSL treats TEXCOORD0 as the
 * complete shader-domain picture (0..1 in both axes) and applies one continuous
 * mapping to every row and column.
 *
 * The current field-test preset caps symmetric side crop at 6.5% per edge when
 * the source is wider than the target.  Crop is automatically reduced when
 * less is needed, so the shader never crops past the target AR.  The remaining
 * aspect correction is then shared between both axes.  For the 16:9 / 89%
 * height / ~2.39:1 test case this leaves only about 4% residual AR correction,
 * split roughly evenly between horizontal and vertical mapping.
 *
 * $MinimumShaderProfile: ps_3_0
 */

sampler s0 : register(s0);

float NlsMapRadius(float radius, float centerScale, float curve,
    int geometry, float centerProtection)
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

float NlsMapCoordinate(float coordinate, float centerScale, float curve,
    int geometry, float centerProtection)
{
    float centered = coordinate * 2.0 - 1.0;
    float mappedRadius = NlsMapRadius(abs(centered), centerScale,
        curve, geometry, centerProtection);
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
    const float strength = saturate({{strength}});
    const float curve = clamp({{curve}}, 1.0, 2.9);
    const float requestedRatio = clamp({{stretch_ratio}}, 1.0, 1.5);
    const bool sourceWider = {{warp_axis}} >= 0.5;
    const int geometry = (int)clamp({{geometry}}, 0.0, 1.0);
    const int quality = (int)clamp({{quality}}, 0.0, 3.0);

    // With madVR black-bar crop enabled, TEXCOORD0 is treated as the complete
    // picture domain.  Do not re-apply VideoProcessor's original raster bounds
    // here; those bounds remain upstream geometry metadata only.
    const float2 pictureMinimum = float2(0.0, 0.0);
    const float2 pictureMaximum = float2(1.0, 1.0);

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

    // Crop first so less nonlinear correction is needed.  The crop is applied
    // continuously to the whole shader domain, avoiding the old top/bottom
    // discontinuity when horizontal crop was applied only inside stale raster
    // active-picture bounds.
    float maximumUsefulSideCrop = 0.0;
    if (sourceWider && requestedRatio > 1.000001)
        maximumUsefulSideCrop = 0.5 * (1.0 - 1.0 / requestedRatio);
    float sideCrop = sourceWider ? min(0.065, maximumUsefulSideCrop) : 0.0;
    float keptWidth = 1.0 - 2.0 * sideCrop;

    // Cropping already supplies part of the aspect correction.  Share only the
    // residual correction between horizontal and vertical nonlinear maps.
    float residualRatio = sourceWider ?
        max(1.0, requestedRatio * keptWidth) : requestedRatio;
    float requestedBalance = clamp({{axis_balance}}, 0.0, 1.0) * strength;
    float maxCenterZoom = clamp({{max_center_zoom}}, 1.0, 1.25);
    float ratioLog = log(max(residualRatio, 1.000001));
    float balanceLimit = residualRatio <= 1.000001 ? 1.0 :
        log(maxCenterZoom) / ratioLog;
    float balance = min(requestedBalance, clamp(balanceLimit, 0.0, 1.0));

    // q is target/effective-source aspect.  The two inverse-map centre slopes
    // retain the exact quotient required to preserve central geometry after
    // madVR applies the presentation aspect.  A balance of 0.5 shares the
    // residual correction evenly in logarithmic aspect space.
    float q = sourceWider ? 1.0 / residualRatio : residualRatio;
    float xExponent = sourceWider ? balance : 1.0 - balance;
    float yExponent = sourceWider ? balance - 1.0 : -balance;
    float xScale = pow(q, xExponent);
    float yScale = pow(q, yExponent);

    float horizontalProtection =
        clamp({{horizontal_center_protection}}, 0.0, 0.45);
    float verticalProtection =
        clamp({{vertical_center_protection}}, 0.0, 0.45);
    float mappedX = NlsMapCoordinate(pictureTex.x, xScale, curve,
        geometry, horizontalProtection);
    float mappedY = NlsMapCoordinate(pictureTex.y, yScale, curve,
        geometry, verticalProtection);

    float croppedLeft = sideCrop;
    float croppedRight = 1.0 - sideCrop;
    float2 sampleMinimum = float2(croppedLeft, 0.0);
    float2 sampleMaximum = float2(croppedRight, 1.0);
    float2 sampleTex = float2(
        lerp(croppedLeft, croppedRight, mappedX), mappedY);

    // The wider-content case has its largest residual minification on the
    // vertical axis; filter along that dominant axis.  Horizontal crop is a
    // magnification, so it does not need an expensive second separable pass.
    float footprint;
    float2 sampleAxis;
    if (sourceWider)
    {
        footprint = max(abs(ddy(sampleTex.y)), abs(ddy(pictureTex.y)));
        sampleAxis = float2(0.0, 1.0);
    }
    else
    {
        footprint = max(abs(ddx(sampleTex.x)), abs(ddx(pictureTex.x)));
        sampleAxis = float2(croppedRight - croppedLeft, 0.0);
    }

    return FilterAlongAxis(sampleTex, sampleAxis, footprint,
        sampleMinimum, sampleMaximum, quality);
}
