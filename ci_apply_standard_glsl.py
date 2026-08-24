from pathlib import Path
import re
import urllib.request

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


# ---------------------------------------------------------------------------
# Preserve target shader metadata/parameters for VP Renderer custom GLSL.
# ---------------------------------------------------------------------------
path = "src/VideoProcessor-Lib/microsoft_directshow/MadVRShaderLoader.h"
text = read(path)
text = replace_once(
    text,
    "\tbool nls = false;\n\tbool none = false;\n\tdouble aspectTolerancePercent = 5.0;",
    "\tbool nls = false;\n\tbool none = false;\n\tbool postResize = false;\n\tunsigned int order = 0;\n\tdouble aspectTolerancePercent = 5.0;",
    "ConfiguredShaderRule stage/order fields",
)
write(path, text)

path = "src/VideoProcessor-Lib/microsoft_directshow/MadVRShaderLoader.cpp"
text = read(path)
text = replace_once(
    text,
    "\t\tLoadTypedNlsSettings(config, section, rule);\n\t}\n\tstd::string stage = \"pre_resize\";",
    "\t\tLoadTypedNlsSettings(config, section, rule);\n\t}\n\telse\n\t{\n\t\tLoadShaderParameters(config, section, rule);\n\t}\n\tstd::string stage = \"pre_resize\";",
    "target custom shader parameter loading",
)
text = replace_once(
    text,
    "\tconfigured.nls = rule.nls;\n\tconfigured.none = rule.none;\n\tconfigured.aspectTolerancePercent =",
    "\tconfigured.nls = rule.nls;\n\tconfigured.none = rule.none;\n\tif (!rule.postScale.empty())\n\t{\n\t\tconfigured.postResize = true;\n\t\tconfigured.order = rule.postScale.front().order;\n\t}\n\telse if (!rule.preScale.empty())\n\t{\n\t\tconfigured.postResize = false;\n\t\tconfigured.order = rule.preScale.front().order;\n\t}\n\tconfigured.aspectTolerancePercent =",
    "configured shader stage/order propagation",
)
write(path, text)

# ---------------------------------------------------------------------------
# Generalize VP Renderer from one NLS hook to standard GLSL + optional NLS.
# ---------------------------------------------------------------------------
path = "src/VideoProcessor-Lib/vprenderer/LibplaceboVideoRenderer.cpp"
text = read(path)

text = replace_once(
    text,
    "\tNlsMappingDecision nlsDecision;\n\tconst struct pl_hook* nlsHook = nullptr;\n\tstd::string nlsHookSignature;\n\tstd::string rejectedNlsHookSignature;\n\tstd::string activeNlsShaderPath;",
    "\tNlsMappingDecision nlsDecision;\n\tstd::vector<const struct pl_hook*> standardHooks;\n\tstd::vector<const struct pl_hook*> activeRenderHooks;\n\tstd::vector<std::string> activeStandardShaderPaths;\n\tconst struct pl_hook* nlsHook = nullptr;\n\tstd::string nlsHookSignature;\n\tstd::string rejectedNlsHookSignature;\n\tstd::string activeNlsShaderPath;",
    "VP Renderer standard hook state",
)

set_start = text.index("\tvoid SetConfiguredShaderSelection(")
set_end = text.index("\n\tstatic std::map<std::string, std::string> FixedNlsParameters", set_start)
new_set = r'''	void SetConfiguredShaderSelection(const std::string& selector,
		const std::vector<ConfiguredShaderRule>& selection,
		uint64_t rendererGeneration)
	{
		requestedShaderSelector =
			MadVRShaderLoader::CanonicalizeRuleSelector(selector);
		nlsRendererGeneration = rendererGeneration;
		nlsRequested = false;
		nlsRule = {};
		ActivePictureTransitionModel::SetRuntimeStableGeometryDeadbandPercent(
			ActivePictureTransitionModel::
				DEFAULT_STABLE_GEOMETRY_DEADBAND_PERCENT);
		// Shader selection changes presentation, not the captured source. Keep
		// generation-current active-picture authority and its transition history
		// so toggling NLS cannot flash through full-raster/pillarbox geometry.
		nlsDecision = {};
		nlsHookSignature.clear();
		rejectedNlsHookSignature.clear();
		{
			std::lock_guard<std::mutex> guard(shaderStatusMutex);
			activeNlsShaderPath.clear();
		}
		lastNlsHookBindingPolicy.clear();
		DestroyStandardHooks();
		pl_mpv_user_shader_destroy(&nlsHook);

		const auto none = std::find_if(selection.begin(), selection.end(),
			[](const ConfiguredShaderRule& rule) { return rule.none; });
		if (none != selection.end())
		{
			SetShaderStatus("Shaders: Off");
			MadVRShaderLoader::SetRuntimeShaderSelection(
				requestedShaderSelector, requestedShaderSelector,
				NlsMappingMode::OFF);
			DebugLog::Log(
				"Alpha shaders: selected \"%s\" (off)",
				requestedShaderSelector.c_str());
			return;
		}

		std::string standardReason;
		if (!LoadStandardHooks(selection, standardReason))
		{
			SetShaderStatus("Rejected: " + standardReason);
			MadVRShaderLoader::SetRuntimeShaderSelection(
				requestedShaderSelector, requestedShaderSelector,
				NlsMappingMode::OFF);
			DebugLog::Log(
				"Alpha shaders: selector \"%s\" rejected: %s",
				requestedShaderSelector.c_str(), standardReason.c_str());
			return;
		}

		const auto nls = std::find_if(selection.begin(), selection.end(),
			[](const ConfiguredShaderRule& rule) { return rule.nls; });
		if (nls == selection.end() || nls->filename.empty())
		{
			BindActiveHooks(false);
			SetShaderStatus(standardHooks.empty() ?
				"Shaders: Off" : "Standard GLSL: Active");
			MadVRShaderLoader::SetRuntimeShaderSelection(
				requestedShaderSelector, requestedShaderSelector,
				NlsMappingMode::OFF);
			DebugLog::Log(
				"Alpha shaders: selected \"%s\" with %u standard GLSL hook(s)",
				requestedShaderSelector.c_str(),
				static_cast<unsigned int>(standardHooks.size()));
			return;
		}

		nlsRule = *nls;
		nlsTransition.SetStableGeometryDeadbandPercent(
			nlsRule.stableGeometryDeadbandPercent);
		ActivePictureTransitionModel::SetRuntimeStableGeometryDeadbandPercent(
			nlsRule.stableGeometryDeadbandPercent);
		nlsRequested = true;
		BindActiveHooks(false);
		SetNlsShaderStatus("Waiting");
		MadVRShaderLoader::SetRuntimeShaderSelection(
			requestedShaderSelector, requestedShaderSelector,
			NlsMappingMode::WAITING);
		DebugLog::Log(
			"Alpha shaders: armed \"%s\" with NLS rule \"%s\" file=%s and %u standard GLSL hook(s) renderer_generation=%llu",
			requestedShaderSelector.c_str(), nlsRule.name.c_str(),
			nlsRule.filename.c_str(),
			static_cast<unsigned int>(standardHooks.size()),
			static_cast<unsigned long long>(nlsRendererGeneration));
	}
'''
text = text[:set_start] + new_set + text[set_end:]

create_start = text.index("\tbool CreateNlsHook(")
create_end = text.index("\n\tstruct NlsHookMappingState", create_start)
new_create = r'''	bool CreateUserHook(const ConfiguredShaderRule& rule,
		const std::map<std::string, std::string>& parameters,
		const struct pl_hook*& hook, std::string& resolvedPath,
		std::string& reason)
	{
		hook = nullptr;
		std::string source;
		if (!ReadUserShader(rule.filename, source, resolvedPath, reason))
			return false;
		if (!ApplyUserShaderParameters(source, parameters, reason))
			return false;
		hook = pl_mpv_user_shader_parse(
			d3d11->gpu, source.data(), source.size());
		if (!hook)
		{
			reason = "libplacebo could not parse shader";
			return false;
		}
		return true;
	}

	bool CreateNlsHook(const ConfiguredShaderRule& rule,
		const struct pl_hook*& hook, std::string& hookKey,
		std::string& resolvedPath, std::string& reason)
	{
		const std::map<std::string, std::string> parameters =
			FixedNlsParameters(rule);
		hookKey = NlsHookKey(rule, parameters);
		return CreateUserHook(rule, parameters, hook, resolvedPath, reason);
	}
'''
text = text[:create_start] + new_create + text[create_end:]

# Existing NLS/reset sites must leave selected standard hooks attached.
clear_pair = "\t\trenderParams.hooks = nullptr;\n\t\trenderParams.num_hooks = 0;"
clear_count = text.count(clear_pair)
if clear_count != 7:
    raise RuntimeError(f"per-frame hook clear sites: expected 7 after selection rewrite, found {clear_count}")
text = text.replace(clear_pair, "\t\tBindActiveHooks(false);")

text = replace_once(
    text,
    "\t\t\t\t\trenderParams.hooks = &nlsHook;\n\t\t\t\t\trenderParams.num_hooks = 1;",
    "\t\t\t\t\tBindActiveHooks(true);",
    "active NLS hook composition",
)

helper_anchor = r'''	void SetShaderStatus(const std::string& status)
	{
		std::lock_guard<std::mutex> guard(shaderStatusMutex);
		if (activeShaderStatus == status)
			return;
		activeShaderStatus = status;
		++activeShaderStatusSerial;
	}
'''
helpers = helper_anchor + r'''
	void DestroyStandardHooks()
	{
		renderParams.hooks = nullptr;
		renderParams.num_hooks = 0;
		activeRenderHooks.clear();
		for (const struct pl_hook*& hook : standardHooks)
			pl_mpv_user_shader_destroy(&hook);
		standardHooks.clear();
		std::lock_guard<std::mutex> guard(shaderStatusMutex);
		activeStandardShaderPaths.clear();
	}

	void BindActiveHooks(bool nlsActive)
	{
		activeRenderHooks.clear();
		activeRenderHooks.insert(activeRenderHooks.end(),
			standardHooks.begin(), standardHooks.end());
		if (nlsActive && nlsHook)
			activeRenderHooks.push_back(nlsHook);
		renderParams.hooks = activeRenderHooks.empty() ?
			nullptr : activeRenderHooks.data();
		renderParams.num_hooks =
			static_cast<int>(activeRenderHooks.size());
	}

	void SetNlsShaderStatus(const char* nlsStatus)
	{
		if (standardHooks.empty())
			SetShaderStatus(std::string("NLS: ") + nlsStatus);
		else
			SetShaderStatus(std::string("Standard GLSL: Active / NLS: ") +
				nlsStatus);
	}

	bool LoadStandardHooks(
		const std::vector<ConfiguredShaderRule>& selection,
		std::string& reason)
	{
		struct OrderedRule
		{
			const ConfiguredShaderRule* rule = nullptr;
			bool postResize = false;
			unsigned int order = 0;
		};

		std::vector<OrderedRule> rules;
		unsigned int preOrdinal = 0;
		unsigned int postOrdinal = 0;
		for (const ConfiguredShaderRule& rule : selection)
		{
			if (rule.none || rule.nls || rule.filename.empty())
				continue;
			unsigned int& ordinal = rule.postResize ? postOrdinal : preOrdinal;
			++ordinal;
			rules.push_back({ &rule, rule.postResize,
				rule.order == 0 ? ordinal : rule.order });
		}
		std::stable_sort(rules.begin(), rules.end(),
			[](const OrderedRule& left, const OrderedRule& right)
			{
				if (left.postResize != right.postResize)
					return !left.postResize;
				return left.order < right.order;
			});

		std::vector<std::string> resolvedPaths;
		for (const OrderedRule& ordered : rules)
		{
			const ConfiguredShaderRule& rule = *ordered.rule;
			const struct pl_hook* hook = nullptr;
			std::string resolvedPath;
			if (!CreateUserHook(rule, rule.parameters, hook,
				resolvedPath, reason))
			{
				DebugLog::Log(
					"Alpha shaders: rejected custom GLSL \"%s\": %s",
					rule.filename.c_str(), reason.c_str());
				DestroyStandardHooks();
				return false;
			}
			standardHooks.push_back(hook);
			resolvedPaths.push_back(resolvedPath);
			DebugLog::Log(
				"Alpha shaders: loaded custom GLSL \"%s\" stage=%s order=%u",
				rule.filename.c_str(),
				rule.postResize ? "post_resize" : "pre_resize",
				ordered.order);
		}
		{
			std::lock_guard<std::mutex> guard(shaderStatusMutex);
			activeStandardShaderPaths = std::move(resolvedPaths);
		}
		return true;
	}
'''
text = replace_once(text, helper_anchor, helpers, "standard GLSL helper insertion")

text = replace_once(
    text,
    "\t\t\tcaptureWorkers.clear();\n\t\t\tpl_mpv_user_shader_destroy(&nlsHook);",
    "\t\t\tcaptureWorkers.clear();\n\t\t\tDestroyStandardHooks();\n\t\t\tpl_mpv_user_shader_destroy(&nlsHook);",
    "standard hook retirement",
)

text = replace_once(
    text,
    "\t\t\t\tSetShaderStatus(\"NLS: unavailable (analysis input)\");",
    "\t\t\t\tSetNlsShaderStatus(\"unavailable (analysis input)\");",
    "analysis unavailable status",
)
for old, new, label in [
    ("SetShaderStatus(\"NLS: Active\");", "SetNlsShaderStatus(\"Active\");", "NLS active status"),
    ("SetShaderStatus(\"NLS: Passthrough\");", "SetNlsShaderStatus(\"Passthrough\");", "NLS passthrough status"),
    ("SetShaderStatus(\"NLS: Safe fit\");", "SetNlsShaderStatus(\"Safe fit\");", "NLS safe-fit status"),
    ("SetShaderStatus(\"NLS: Waiting\");", "SetNlsShaderStatus(\"Waiting\");", "NLS waiting status"),
]:
    text = replace_once(text, old, new, label)

text = replace_once(
    text,
    "\t\tactiveRule = TEXT(\"NLS: Pending\");",
    "\t\tactiveRule = TEXT(\"Shaders: Pending\");",
    "generic pending shader status",
)

active_start = text.index("std::vector<CString> LibplaceboVideoRenderer::ActiveShaders() const")
active_end = text.index("\n\n\nbool LibplaceboVideoRenderer::GetActiveShaderSections", active_start)
new_active = r'''std::vector<CString> LibplaceboVideoRenderer::ActiveShaders() const
{
	std::vector<CString> shaders;
	if (!m_impl)
		return shaders;
	std::lock_guard<std::mutex> guard(m_impl->shaderStatusMutex);
	for (const std::string& path : m_impl->activeStandardShaderPaths)
	{
		CString label;
		label.Format(TEXT("GLSL: %S"), FileNameFromPath(path).c_str());
		shaders.push_back(label);
	}
	if (!m_impl->activeNlsShaderPath.empty())
	{
		CString label;
		label.Format(TEXT("GLSL: %S"),
			FileNameFromPath(
				m_impl->activeNlsShaderPath).c_str());
		shaders.push_back(label);
	}
	return shaders;
}
'''
text = text[:active_start] + new_active + text[active_end:]

text = replace_once(
    text,
    "\t\t\t// This is the sole per-frame NLS authority. Derive every mapping input\n\t\t\t// from the exact source rectangle selected above, then publish crop,\n\t\t\t// hook, runtime geometry, status, and destination layout as one decision.\n\t\t\tBindActiveHooks(false);",
    "\t\t\t// This is the sole per-frame NLS authority. Standard user shaders stay\n\t\t\t// selected independently; derive NLS from the exact source rectangle and\n\t\t\t// compose its hook only on frames where the mapping is authoritative.\n\t\t\tBindActiveHooks(false);",
    "per-frame hook authority comment",
)

write(path, text)

# ---------------------------------------------------------------------------
# Bundle one conservative, opt-in mpv/libplacebo user shader example.
# ---------------------------------------------------------------------------
shader_url = "https://gist.githubusercontent.com/igv/8a77e4eb8276753b54bb94c1c50c317e/raw/adaptive-sharpen.glsl"
with urllib.request.urlopen(shader_url, timeout=30) as response:
    shader = response.read().decode("utf-8")
if "Copyright (c) 2015-2021, bacondither" not in shader:
    raise RuntimeError("Adaptive Sharpen license/copyright header not found")
if "//!HOOK OUTPUT" not in shader:
    raise RuntimeError("Adaptive Sharpen OUTPUT hook not found")
if "#define curve_height 1.0" not in shader:
    raise RuntimeError("Adaptive Sharpen curve_height baseline not found")
shader = shader.replace("#define curve_height 1.0", "#define curve_height {{strength}}", 1)
write("shaders/Adaptive sharpen.glsl", shader)

path = "VideoProcessor.cfg"
text = read(path)
text = replace_once(
    text,
    "[shader.standard.adaptive_sharpen]\nshader_type: custom\nlabel: Adaptive Sharpen\nstage: post_resize\norder: 10\nhlsl_file: Adaptive sharpen.hlsl",
    "[shader.standard.adaptive_sharpen]\nshader_type: custom\nlabel: Adaptive Sharpen\nstage: post_resize\norder: 10\nhlsl_file: Adaptive sharpen.hlsl\nglsl_file: Adaptive sharpen.glsl\nparam_strength: 0.5",
    "Adaptive Sharpen VP Renderer sample configuration",
)
write(path, text)

path = "packaging/release-manifest.json"
text = read(path)
needle = '    { "sourceRoot": "repository", "source": "shaders/Adaptive sharpen.hlsl", "destination": "shaders/Adaptive sharpen.hlsl", "owner": "bacondither", "sourceVersion": "Adaptive Sharpen 2021-10-17", "consumer": "madVR", "loadMechanism": "IMadVRExternalPixelShaders", "reason": "Bundled legacy configurable shader." },'
replacement = needle + '\n    { "sourceRoot": "repository", "source": "shaders/Adaptive sharpen.glsl", "destination": "shaders/Adaptive sharpen.glsl", "owner": "bacondither", "sourceVersion": "Adaptive Sharpen 2021-10-17", "consumer": "VideoProcessorVPRenderer.dll", "loadMechanism": "Executable-relative mpv/libplacebo user-shader lookup", "reason": "Bundled optional Adaptive Sharpen implementation for VP Renderer." },'
text = replace_once(text, needle, replacement, "release manifest Adaptive Sharpen GLSL entry")
write(path, text)

path = "tools/package_release.ps1"
text = read(path)
text = replace_once(text, "$shaderDestinations.Count -ne 7", "$shaderDestinations.Count -ne 8", "packaged shader count")
text = replace_once(text, "exactly one seven-file shader tree", "exactly one eight-file shader tree", "packaged shader count message")
write(path, text)

# ---------------------------------------------------------------------------
# Clarify that mpv/libplacebo's own //!HOOK remains the execution authority.
# ---------------------------------------------------------------------------
path = "CONFIGURATION.html"
text = read(path)
old = '<p><strong>Effect and verification:</strong> Keep HLSL and GLSL entries together only when they represent the same intended effect. VP Renderer logs shader loading/compilation failures.</p></article>'
new = '<p><strong>Effect and verification:</strong> Keep HLSL and GLSL entries together only when they represent the same intended effect. VP Renderer parses GLSL implementations as mpv/libplacebo user shaders, so the shader\'s own <code>//!HOOK</code> directive remains authoritative for its libplacebo execution point; <code>stage</code> and <code>order</code> provide deterministic logical ordering between selected files. VP Renderer logs shader loading/compilation failures.</p></article>'
text = replace_once(text, old, new, "GLSL user-shader documentation")
write(path, text)

# ---------------------------------------------------------------------------
# Add resolver coverage for custom GLSL params + stage/order propagation and
# assert that the shipped Adaptive Sharpen entry exposes a VP implementation.
# ---------------------------------------------------------------------------
path = "src/VideoProcessor-Test/ConfigFileTests.cpp"
text = read(path)
marker = "\t\tTEST_METHOD(CheckedInVp0079ConfigurationPassesStartupSchemas)\n"
new_test = r'''		TEST_METHOD(Vp0079CustomGlslParametersResolveForAlpha)
		{
			char temporaryDirectory[MAX_PATH] = {};
			Assert::IsTrue(GetTempPathA(
				ARRAYSIZE(temporaryDirectory), temporaryDirectory) > 0);
			const std::string path = std::string(temporaryDirectory) +
				"VideoProcessor-vp0079-custom-glsl.cfg";
			{
				std::ofstream file(path, std::ios::out | std::ios::trunc);
				file
					<< "[shader.standard]\n"
					<< "type: multi\n"
					<< "[shader.standard.adaptive]\n"
					<< "shortcut: Ctrl+Shift+S\n"
					<< "shader_type: custom\n"
					<< "stage: post_resize\n"
					<< "order: 10\n"
					<< "glsl_file: NLS.glsl\n"
					<< "param_strength: 0.5\n";
			}

			ConfigFile config;
			Assert::IsTrue(config.Load(path));
			std::vector<ConfiguredShaderRule> selection;
			std::string error;
			Assert::IsTrue(MadVRShaderLoader::ResolveConfiguredRuleSelection(
				config, "@shader-key:Ctrl+Shift+S",
				ShaderRendererBackend::LIBPLACEBO, selection, error),
				std::wstring(error.begin(), error.end()).c_str());
			Assert::AreEqual(static_cast<size_t>(1), selection.size());
			Assert::IsFalse(selection.front().nls);
			Assert::AreEqual("NLS.glsl", selection.front().filename.c_str());
			Assert::IsTrue(selection.front().postResize);
			Assert::AreEqual(static_cast<unsigned int>(10),
				selection.front().order);
			Assert::AreEqual(0.5,
				std::stod(selection.front().parameters.at("strength")),
				0.000001);
			DeleteFileA(path.c_str());
		}

'''
text = replace_once(text, marker, new_test + marker, "custom GLSL resolver test")

sample_anchor = "\t\t\tAssert::AreEqual(\"multi\", value.c_str());\n\t\t\tconst std::pair<const char*, const char*> standardShaders[] = {"
sample_replace = "\t\t\tAssert::AreEqual(\"multi\", value.c_str());\n\t\t\tAssert::IsTrue(config.TryGetString(\n\t\t\t\t\"shader.standard.adaptive_sharpen\", \"glsl_file\", value));\n\t\t\tAssert::AreEqual(\"Adaptive sharpen.glsl\", value.c_str());\n\t\t\tAssert::IsTrue(config.TryGetString(\n\t\t\t\t\"shader.standard.adaptive_sharpen\", \"param_strength\", value));\n\t\t\tAssert::AreEqual(\"0.5\", value.c_str());\n\t\t\tconst std::pair<const char*, const char*> standardShaders[] = {"
text = replace_once(text, sample_anchor, sample_replace, "checked-in Adaptive Sharpen GLSL assertions")
write(path, text)

# ---------------------------------------------------------------------------
# Static guardrails before invoking the Windows compiler/test runner.
# ---------------------------------------------------------------------------
renderer = read("src/VideoProcessor-Lib/vprenderer/LibplaceboVideoRenderer.cpp")
if "Rejected: Alpha NLS rule required" in renderer:
    raise RuntimeError("legacy NLS-only rejection remains")
if "renderParams.hooks = &nlsHook" in renderer:
    raise RuntimeError("legacy single-hook binding remains")
if renderer.count("BindActiveHooks(false);") < 8:
    raise RuntimeError("not all standard-hook preservation sites were updated")
if renderer.count("BindActiveHooks(true);") != 1:
    raise RuntimeError("expected one active NLS composition site")
if "activeStandardShaderPaths" not in renderer:
    raise RuntimeError("standard shader diagnostics are missing")

print("Standard GLSL patch applied successfully")
