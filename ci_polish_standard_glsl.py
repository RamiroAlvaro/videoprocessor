from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_article(text, article_id, replacement):
    pattern = re.compile(
        rf'<article id="{re.escape(article_id)}"[^>]*>.*?</article>',
        re.DOTALL,
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"{article_id}: expected exactly one article, found {count}")
    return text


# Documentation: stage/order are physical for HLSL and logical ordering metadata
# for VP Renderer GLSL. The mpv user shader's //!HOOK directive remains the
# authority for the actual libplacebo execution point.
path = "CONFIGURATION.html"
text = read(path)
text = replace_article(
    text,
    "shader-member-stage",
    '<article id="shader-member-stage" data-fields="shader.&lt;group&gt;.&lt;member&gt;.stage"><h3><code>[shader.&lt;group&gt;.&lt;member&gt;] stage</code></h3><p class="meta"><strong>Purpose:</strong> declares the logical pre/post-resize stage used to order a selected effect across renderer backends. <strong>Syntax:</strong> <code>pre_resize</code> or <code>post_resize</code>. <strong>Omitted:</strong> <code>pre_resize</code>.</p><table class="values"><thead><tr><th>Value</th><th>Meaning</th></tr></thead><tbody><tr><td><code>pre_resize</code></td><td>DirectShow/HLSL inserts the shader before resizing. VP Renderer/GLSL places the file in the pre-resize logical ordering group, while the shader\'s own <code>//!HOOK</code> directive chooses its actual libplacebo execution point.</td></tr><tr><td><code>post_resize</code></td><td>DirectShow/HLSL inserts the shader after resizing. VP Renderer/GLSL places the file in the post-resize logical ordering group, while the shader\'s own <code>//!HOOK</code> directive chooses its actual libplacebo execution point.</td></tr></tbody></table><p><strong>Effect and verification:</strong> For HLSL, changing <code>stage</code> changes the physical insertion point. For GLSL, changing <code>stage</code> never rewrites the user shader: inspect its <code>//!HOOK</code> directive and the VP Renderer load log to verify the real libplacebo hook stage before tuning an effect.</p></article>',
)
text = replace_article(
    text,
    "shader-member-order",
    '<article id="shader-member-order" data-fields="shader.&lt;group&gt;.&lt;member&gt;.order"><h3><code>[shader.&lt;group&gt;.&lt;member&gt;] order</code></h3><p class="meta"><strong>Purpose:</strong> orders selected shader files within the same declared logical stage. <strong>Syntax:</strong> non-negative integer. <strong>Omitted:</strong> <code>0</code>.</p><table class="values"><thead><tr><th>Value</th><th>Meaning</th></tr></thead><tbody><tr><td><code>0</code> or omitted</td><td>Assign an automatic ordinal as selected entries are collected. Use this for a lone effect or when no relative placement is required.</td></tr><tr><td><code>1</code> or higher</td><td>Sort that entry in ascending numeric order against every other selected entry in the same logical stage.</td></tr><tr><td>Equal positive values</td><td>Allowed; the effective selected-entry order breaks the tie deterministically.</td></tr></tbody></table><p><strong>Effect and verification:</strong> It has no visible effect when only one shader is active in a logical stage. DirectShow uses the resulting order inside its physical pre/post-resize chains. VP Renderer supplies GLSL hooks to libplacebo in this deterministic order, but libplacebo still schedules each hook at the stage declared by that shader\'s own <code>//!HOOK</code> directive.</p></article>',
)
write(path, text)


# Checked-in example: make the backend-specific strength behavior explicit.
path = "VideoProcessor.cfg"
text = read(path)
text = replace_once(
    text,
    "glsl_file: Adaptive sharpen.glsl\nparam_strength: 0.5",
    "glsl_file: Adaptive sharpen.glsl\n"
    "# param_strength is substituted into the GLSL template only; the legacy\n"
    "# HLSL implementation keeps its historical internal tuning.\n"
    "param_strength: 0.5",
    "Adaptive Sharpen backend-specific strength comment",
)
write(path, text)


# Preserve upstream BSD text, record provenance, and remove trailing whitespace.
path = "shaders/Adaptive sharpen.glsl"
text = read(path)
text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
version_marker = "// Adaptive sharpen - version 2021-10-17\n"
if "gist.github.com/igv/8a77e4eb8276753b54bb94c1c50c317e" not in text:
    text = replace_once(
        text,
        version_marker,
        version_marker
        + "// Original mpv/libplacebo user-shader source: "
        + "https://gist.github.com/igv/8a77e4eb8276753b54bb94c1c50c317e\n",
        "Adaptive Sharpen provenance",
    )
write(path, text)


# Make hook-array lifetime and logical/physical stage diagnostics explicit.
path = "src/VideoProcessor-Lib/vprenderer/LibplaceboVideoRenderer.cpp"
text = read(path)
text = replace_once(
    text,
    "\tvoid BindActiveHooks(bool nlsActive)\n\t{\n\t\tactiveRenderHooks.clear();",
    "\tvoid BindActiveHooks(bool nlsActive)\n\t{\n"
    "\t\t// pl_render_params borrows this pointer array during pl_render_image.\n"
    "\t\t// Keep the backing storage as renderer-owned state so neither standard\n"
    "\t\t// hooks nor the optional NLS hook can outlive the array that exposes them.\n"
    "\t\tactiveRenderHooks.clear();",
    "active hook lifetime comment",
)
text = replace_once(
    text,
    "\t\t\tDebugLog::Log(\n"
    "\t\t\t\t\"Alpha shaders: loaded custom GLSL \\\"%s\\\" stage=%s order=%u\",\n"
    "\t\t\t\trule.filename.c_str(),\n"
    "\t\t\t\trule.postResize ? \"post_resize\" : \"pre_resize\",\n"
    "\t\t\t\tordered.order);",
    "\t\t\tDebugLog::Log(\n"
    "\t\t\t\t\"Alpha shaders: loaded custom GLSL \\\"%s\\\" logical_stage=%s order=%u hook_stages=0x%X\",\n"
    "\t\t\t\trule.filename.c_str(),\n"
    "\t\t\t\trule.postResize ? \"post_resize\" : \"pre_resize\",\n"
    "\t\t\t\tordered.order, static_cast<unsigned int>(hook->stages));",
    "standard GLSL stage diagnostics",
)
text = text.replace(
    "\n\n\nbool LibplaceboVideoRenderer::GetActiveShaderSections(",
    "\n\nbool LibplaceboVideoRenderer::GetActiveShaderSections(",
)
write(path, text)


# GPU tests: exercise the shipped Adaptive Sharpen file and a real two-hook
# standard+NLS chain through D3D11 WARP and libplacebo.
path = "src/VideoProcessor-Test/LibplaceboLutParserTests.cpp"
text = read(path)

parse_anchor = """\tconst pl_hook* ParseBundledNlsShader(pl_gpu gpu, const char* fileName,
\t\tdouble axisBalance, double strength = 1.0)
\t{
"""
helpers = """\tconst pl_hook* ParseBundledAdaptiveSharpen(pl_gpu gpu,
\t\tdouble strength = 0.5)
\t{
\t\tstd::string source = LoadBundledShader("Adaptive sharpen.glsl");
\t\tAssert::IsFalse(source.empty(),
\t\t\tL"Bundled Adaptive Sharpen shader was not found");
\t\tReplaceShaderToken(source, "strength", std::to_string(strength));
\t\tAssert::IsTrue(source.find("{{") == std::string::npos,
\t\t\tL"Bundled Adaptive Sharpen still contains an unsubstituted token");
\t\tconst pl_hook* hook = pl_mpv_user_shader_parse(
\t\t\tgpu, source.data(), source.size());
\t\tAssert::IsNotNull(hook,
\t\t\tL"libplacebo rejected bundled Adaptive Sharpen GLSL");
\t\treturn hook;
\t}

\tconst pl_hook* ParseDeterministicStandardOutputShader(pl_gpu gpu)
\t{
\t\tstatic const char source[] =
\t\t\t"//!HOOK OUTPUT\\n"
\t\t\t"//!BIND HOOKED\\n"
\t\t\t"//!DESC VP standard hook composition test\\n"
\t\t\t"vec4 hook() {\\n"
\t\t\t"    vec4 color = HOOKED_texOff(0);\\n"
\t\t\t"    return vec4(color.r * 0.5, color.g, color.b, color.a);\\n"
\t\t\t"}\\n";
\t\tconst pl_hook* hook = pl_mpv_user_shader_parse(
\t\t\tgpu, source, sizeof(source) - 1);
\t\tAssert::IsNotNull(hook,
\t\t\tL"libplacebo rejected deterministic standard OUTPUT test hook");
\t\treturn hook;
\t}

"""
text = replace_once(text, parse_anchor, helpers + parse_anchor,
    "GPU shader parser helpers")

text = replace_once(
    text,
    "\t\tstd::vector<RgbaPixel> RenderCoordinateField(\n"
    "\t\t\tconst pl_hook* hook, int width = 64, int height = 64)\n",
    "\t\tstd::vector<RgbaPixel> RenderCoordinateField(\n"
    "\t\t\tconst std::vector<const pl_hook*>& hooks,\n"
    "\t\t\tint width = 64, int height = 64)\n",
    "multi-hook GPU fixture signature",
)
text = replace_once(
    text,
    "\t\t\tif (hook)\n"
    "\t\t\t{\n"
    "\t\t\t\tparams.hooks = &hook;\n"
    "\t\t\t\tparams.num_hooks = 1;\n"
    "\t\t\t}",
    "\t\t\tif (!hooks.empty())\n"
    "\t\t\t{\n"
    "\t\t\t\tparams.hooks = hooks.data();\n"
    "\t\t\t\tparams.num_hooks = static_cast<int>(hooks.size());\n"
    "\t\t\t}",
    "multi-hook render parameters",
)
fixture_tail = """\t\t\tpl_tex_destroy(gpu, &sourceTexture);
\t\t\treturn result;
\t\t}

\tprivate:
"""
fixture_additions = """\t\t\tpl_tex_destroy(gpu, &sourceTexture);
\t\t\treturn result;
\t\t}

\t\tstd::vector<RgbaPixel> RenderCoordinateField(
\t\t\tconst pl_hook* hook, int width = 64, int height = 64)
\t\t{
\t\t\tstd::vector<const pl_hook*> hooks;
\t\t\tif (hook)
\t\t\t\thooks.push_back(hook);
\t\t\treturn RenderCoordinateField(hooks, width, height);
\t\t}

\t\tbool HasHookErrors() const
\t\t{
\t\t\treturn m_renderer &&
\t\t\t\t(pl_renderer_get_errors(m_renderer).errors & PL_RENDER_ERR_HOOKS) != 0;
\t\t}

\tprivate:
"""
text = replace_once(text, fixture_tail, fixture_additions,
    "GPU fixture single-hook compatibility overload")

nls_test_anchor = "\t\tTEST_METHOD(BundledNlsGlSlHooksMovePixelsOnTheRealGpuPath)\n"
new_tests = """\t\tTEST_METHOD(BundledAdaptiveSharpenGlSlRendersOnTheRealGpuPath)
\t\t{
\t\t\tTargetLutGpuFixture fixture;
\t\t\tAssert::IsTrue(fixture.Create(),
\t\t\t\tL"Could not create the libplacebo WARP test device");
\t\t\tconst pl_hook* adaptive = ParseBundledAdaptiveSharpen(
\t\t\t\tfixture.Gpu(), 0.5);
\t\t\tconst std::vector<RgbaPixel> pixels =
\t\t\t\tfixture.RenderCoordinateField(adaptive);
\t\t\tAssert::IsTrue(pixels.size() == static_cast<size_t>(64 * 64));
\t\t\tAssert::IsFalse(fixture.HasHookErrors(),
\t\t\t\tL"Bundled Adaptive Sharpen raised a libplacebo hook error");
\t\t\tpl_mpv_user_shader_destroy(&adaptive);
\t\t}

\t\tTEST_METHOD(StandardGlSlAndNlsHooksComposeOnTheRealGpuPath)
\t\t{
\t\t\tTargetLutGpuFixture fixture;
\t\t\tAssert::IsTrue(fixture.Create(),
\t\t\t\tL"Could not create the libplacebo WARP test device");
\t\t\tconst std::vector<RgbaPixel> baseline =
\t\t\t\tfixture.RenderCoordinateField(nullptr);

\t\t\tconst pl_hook* standard =
\t\t\t\tParseDeterministicStandardOutputShader(fixture.Gpu());
\t\t\tconst pl_hook* nls = ParseBundledNlsShader(
\t\t\t\tfixture.Gpu(), "NLS.glsl", 0.0, 1.0);
\t\t\tBindNlsShader(nls, 1.32f, 0.0f);

\t\t\tconst std::vector<RgbaPixel> standardOnly =
\t\t\t\tfixture.RenderCoordinateField(
\t\t\t\t\tstd::vector<const pl_hook*>{ standard });
\t\t\tconst std::vector<RgbaPixel> nlsOnly =
\t\t\t\tfixture.RenderCoordinateField(
\t\t\t\t\tstd::vector<const pl_hook*>{ nls });
\t\t\tconst std::vector<RgbaPixel> combined =
\t\t\t\tfixture.RenderCoordinateField(
\t\t\t\t\tstd::vector<const pl_hook*>{ standard, nls });

\t\t\tsize_t standardEvidence = 0;
\t\t\tsize_t nlsEvidence = 0;
\t\t\tsize_t composedEvidence = 0;
\t\t\tfor (size_t index = 0; index < baseline.size(); ++index)
\t\t\t{
\t\t\t\tconst int baseRed = static_cast<int>(baseline[index].r);
\t\t\t\tconst int standardRed = static_cast<int>(standardOnly[index].r);
\t\t\t\tconst int nlsRed = static_cast<int>(nlsOnly[index].r);
\t\t\t\tconst int combinedRed = static_cast<int>(combined[index].r);
\t\t\t\tif (baseRed >= 16 &&
\t\t\t\t\tstd::abs(standardRed * 2 - baseRed) <= 4)
\t\t\t\t\t++standardEvidence;
\t\t\t\tif (std::abs(nlsRed - baseRed) >= 8)
\t\t\t\t\t++nlsEvidence;
\t\t\t\tif (nlsRed >= 16 &&
\t\t\t\t\tstd::abs(combinedRed * 2 - nlsRed) <= 4)
\t\t\t\t\t++composedEvidence;
\t\t\t}

\t\t\tAssert::IsTrue(standardEvidence > 3000,
\t\t\t\tL"The deterministic standard OUTPUT hook did not affect the GPU output");
\t\t\tAssert::IsTrue(nlsEvidence > 100,
\t\t\t\tL"The NLS hook did not retain measurable coordinate-warp evidence");
\t\t\tAssert::IsTrue(composedEvidence > 3000,
\t\t\t\tL"The standard OUTPUT hook and NLS hook did not compose in one hook array");
\t\t\tAssert::IsFalse(fixture.HasHookErrors(),
\t\t\t\tL"The composed standard+NLS chain raised a libplacebo hook error");

\t\t\tpl_mpv_user_shader_destroy(&standard);
\t\t\tpl_mpv_user_shader_destroy(&nls);
\t\t}

"""
text = replace_once(text, nls_test_anchor, new_tests + nls_test_anchor,
    "standard plus NLS GPU tests")
write(path, text)

print("Standard GLSL polish patch applied successfully")
