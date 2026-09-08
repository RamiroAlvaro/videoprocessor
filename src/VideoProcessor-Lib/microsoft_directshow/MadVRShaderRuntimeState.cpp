/*
 * Copyright(C) 2026 Bill Slack
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, version 3.
 */

#include <pch.h>

#include "MadVRShaderRuntimeState.h"

#include <ConfigFile.h>

#include <algorithm>
#include <cmath>
#include <sstream>


namespace
{
	bool TryParseRuntimeDouble(const std::string& raw, double minimum,
		double maximum, double& value)
	{
		try
		{
			size_t consumed = 0;
			const std::string text = ConfigFile::Trim(raw);
			const double parsed = std::stod(text, &consumed);
			if (consumed != text.size() || !std::isfinite(parsed) ||
				parsed < minimum || parsed > maximum)
				return false;
			value = parsed;
			return true;
		}
		catch (...)
		{
			return false;
		}
	}


	bool TryConfiguredNlsTargetFill(const ConfigFile& config,
		const std::string& section, double& fill)
	{
		std::string raw;
		if (!config.TryGetString(section, "target_fill", raw))
			return false;
		return TryParseRuntimeDouble(raw, 0.50, 1.0, fill);
	}


	struct RuntimeNlsPolicy
	{
		double tolerancePercent = 5.0;
		double activeAspectMinimum = 0.0;
		NlsAspectDirection direction = NlsAspectDirection::NARROWER_ONLY;
		double maximumStretchRatio = NLS_DEFAULT_MAXIMUM_STRETCH_RATIO;
	};


	bool TryConfiguredNlsPolicy(const ConfigFile& config,
		const std::string& section, RuntimeNlsPolicy& policy)
	{
		std::string raw;
		if (!config.TryGetString(section, "shader_type", raw) ||
			ConfigFile::NormalizeName(raw) != "nls")
			return false;

		RuntimeNlsPolicy parsed;
		if (config.TryGetString(section, "tolerance_percent", raw) &&
			!TryParseRuntimeDouble(raw, 0.0, 50.0, parsed.tolerancePercent))
			return false;
		if (config.TryGetString(section, "active_aspect_min", raw) &&
			!TryParseRuntimeDouble(raw, 1.0, 4.0, parsed.activeAspectMinimum))
			return false;
		if (config.TryGetString(section, "max_stretch_ratio", raw) &&
			!TryParseRuntimeDouble(raw, NLS_MINIMUM_STRETCH_RATIO,
				NLS_SHADER_MAXIMUM_STRETCH_RATIO,
				parsed.maximumStretchRatio))
			return false;
		if (config.TryGetString(section, "aspect_direction", raw))
		{
			const std::string direction = ConfigFile::NormalizeName(raw);
			if (direction == "narrower_only")
				parsed.direction = NlsAspectDirection::NARROWER_ONLY;
			else if (direction == "wider_only")
				parsed.direction = NlsAspectDirection::WIDER_ONLY;
			else if (direction == "any")
				parsed.direction = NlsAspectDirection::ANY;
			else
				return false;
		}
		policy = parsed;
		return true;
	}


	template <typename Reader>
	bool ResolveConfiguredNlsSection(const std::string& effectiveRule,
		Reader&& reader)
	{
		if (effectiveRule.empty())
			return false;

		ConfigFile config;
		if (!config.Load())
			return false;

		std::istringstream selectors(effectiveRule);
		std::string selector;
		while (std::getline(selectors, selector, ','))
		{
			selector = ConfigFile::NormalizeName(ConfigFile::Trim(selector));
			if (selector.empty())
				continue;

			if (selector.rfind("@shader-key:", 0) != 0)
			{
				if (reader(config, "shader." + selector))
					return true;
				continue;
			}

			// Manual target-mode selection is stored as @shader-key:<key>. Resolve
			// that key back to its shader section so runtime geometry can honor the
			// same target_fill/aspect guards as an automatically selected rule.
			const std::string key = ConfigFile::NormalizeName(ConfigFile::Trim(
				selector.substr(std::string("@shader-key:").size())));
			if (key.empty())
				continue;
			for (const std::string& section : config.GetSectionNames())
			{
				if (section.rfind("shader.", 0) != 0)
					continue;
				std::string shortcut;
				if (!config.TryGetString(section, "shortcut", shortcut))
					continue;
				if (ConfigFile::NormalizeName(ConfigFile::Trim(shortcut)) != key)
					continue;
				if (reader(config, section))
					return true;
			}
		}
		return false;
	}


	double ConfiguredNlsTargetFill(const std::string& effectiveRule)
	{
		double fill = 1.0;
		ResolveConfiguredNlsSection(effectiveRule,
			[&fill](const ConfigFile& config, const std::string& section)
			{
				return TryConfiguredNlsTargetFill(config, section, fill);
			});
		return fill;
	}


	bool ConfiguredRuntimeNlsPolicy(const std::string& effectiveRule,
		RuntimeNlsPolicy& policy)
	{
		return ResolveConfiguredNlsSection(effectiveRule,
			[&policy](const ConfigFile& config, const std::string& section)
			{
				return TryConfiguredNlsPolicy(config, section, policy);
			});
	}


	void RecalculateRuntimeNlsDecision(MadVRShaderRuntimeSnapshot& state)
	{
		if (state.nlsMode == MadVRNlsMappingMode::OFF)
			return;
		if (!state.activeGeometry.stable ||
			!std::isfinite(state.activeGeometry.aspectRatio) ||
			state.activeGeometry.aspectRatio <= 0.0 ||
			!std::isfinite(state.nlsTargetAspect) || state.nlsTargetAspect <= 0.0)
		{
			state.nlsMode = MadVRNlsMappingMode::WAITING;
			return;
		}

		RuntimeNlsPolicy policy;
		if (!ConfiguredRuntimeNlsPolicy(state.effectiveRule, policy))
			return;

		// A stable picture below active_aspect_min is not "waiting" for geometry;
		// it is an intentionally ineligible picture. Keep the NLS mode armed but
		// present the source natively. This is critical for Smart 90: 16:9, 1.85,
		// 1.90 and 2.00 must remain untouched while the same N selection stays on.
		if (policy.activeAspectMinimum > 0.0 &&
			state.activeGeometry.aspectRatio < policy.activeAspectMinimum)
		{
			MadVRNlsMappingDecision decision;
			decision.mode = MadVRNlsMappingMode::LINEAR_PASSTHROUGH;
			decision.sourceAspect = state.activeGeometry.aspectRatio;
			decision.targetAspect = state.nlsTargetAspect;
			decision.maximumRatio = policy.maximumStretchRatio;
			decision.requestedRatio = std::max(
				state.nlsTargetAspect / state.activeGeometry.aspectRatio,
				state.activeGeometry.aspectRatio / state.nlsTargetAspect);
			decision.reason =
				"active picture is below the configured NLS minimum; preserving source geometry";
			state.nlsDecision = decision;
			state.nlsMode = decision.mode;
			state.lastSafeNlsMode = decision.mode;
			return;
		}

		MadVRNlsMappingDecision decision = EvaluateNlsMapping(true,
			state.activeGeometry.aspectRatio, state.nlsTargetAspect,
			policy.tolerancePercent, policy.activeAspectMinimum,
			policy.direction, policy.maximumStretchRatio);
		decision = ConstrainMadVRNlsMappingToGeometry(
			decision, state.activeGeometry);
		state.nlsDecision = decision;
		state.nlsMode = decision.mode;
		if (decision.mode == MadVRNlsMappingMode::ACTIVE ||
			decision.mode == MadVRNlsMappingMode::LINEAR_PASSTHROUGH ||
			decision.mode == MadVRNlsMappingMode::SAFE_FIT)
			state.lastSafeNlsMode = decision.mode;
	}
}


bool ResolveMadVRNlsOutputAspect(double targetAspect,
	unsigned long& aspectX, unsigned long& aspectY)
{
	aspectX = 0;
	aspectY = 0;
	if (!std::isfinite(targetAspect) || targetAspect <= 0.0)
		return false;
	double bestError = (std::numeric_limits<double>::max)();
	for (unsigned long denominator = 1; denominator <= 10000; ++denominator)
	{
		const unsigned long numerator = static_cast<unsigned long>(
			std::llround(targetAspect * denominator));
		if (numerator == 0)
			continue;
		const double error = std::abs(
			static_cast<double>(numerator) / denominator - targetAspect);
		if (error < bestError)
		{
			bestError = error;
			aspectX = numerator;
			aspectY = denominator;
			if (error < 1e-12)
				break;
		}
	}
	return aspectX != 0 && aspectY != 0;
}


MadVRNlsPresentationPlan ResolveMadVRNlsPresentationPlan(
	const MadVRNlsMappingDecision& decision,
	const MadVRActivePictureGeometry& geometry)
{
	MadVRNlsPresentationPlan plan;
	plan.shaderGeometry = geometry;
	if (decision.mode != MadVRNlsMappingMode::ACTIVE || !geometry.stable)
		return plan;

	const bool validBounds =
		std::isfinite(geometry.aspectRatio) && geometry.aspectRatio > 0.0 &&
		std::isfinite(geometry.left) && std::isfinite(geometry.top) &&
		std::isfinite(geometry.right) && std::isfinite(geometry.bottom) &&
		geometry.left >= 0.0 && geometry.top >= 0.0 &&
		geometry.right <= 1.0 && geometry.bottom <= 1.0 &&
		geometry.right > geometry.left && geometry.bottom > geometry.top;
	if (!validBounds || !std::isfinite(decision.targetAspect) ||
		decision.targetAspect <= 0.0)
		return plan;

	const double activeWidth = geometry.right - geometry.left;
	const double activeHeight = geometry.bottom - geometry.top;
	const double rasterAspect =
		decision.targetAspect * activeHeight / activeWidth;
	if (!std::isfinite(rasterAspect) || rasterAspect < 0.25 ||
		rasterAspect > 4.0 ||
		!ResolveMadVRNlsOutputAspect(rasterAspect, plan.aspectX, plan.aspectY))
		return MadVRNlsPresentationPlan{};

	plan.customShader = true;
	plan.rasterAspect = rasterAspect;
	return plan;
}


MadVRNlsMappingDecision ConstrainMadVRNlsMappingToGeometry(
	const MadVRNlsMappingDecision& decision,
	const MadVRActivePictureGeometry& geometry)
{
	MadVRNlsMappingDecision constrained = decision;
	const MadVRNlsPresentationPlan plan =
		ResolveMadVRNlsPresentationPlan(decision, geometry);
	if (decision.mode != MadVRNlsMappingMode::ACTIVE || plan.customShader)
		return constrained;

	constrained.mode = MadVRNlsMappingMode::SAFE_FIT;
	constrained.safeFitVertical =
		decision.sourceAspect > decision.targetAspect;
	constrained.safeFitFraction = std::max(0.01, std::min(1.0,
		std::min(decision.sourceAspect, decision.targetAspect) /
		std::max(decision.sourceAspect, decision.targetAspect)));
	constrained.reason +=
		"; geometry cannot establish a safe madVR mapping; using native safe fit";
	return constrained;
}


bool MadVROutputAspectRequiresRestart(unsigned long currentAspectX,
	unsigned long currentAspectY, unsigned long desiredAspectX,
	unsigned long desiredAspectY, double nativeAspect)
{
	if (!std::isfinite(nativeAspect) || nativeAspect <= 0.0)
		return desiredAspectX != currentAspectX || desiredAspectY != currentAspectY;
	const auto effectiveAspect = [nativeAspect](
		unsigned long aspectX, unsigned long aspectY)
	{
		return aspectX > 0 && aspectY > 0 ?
			static_cast<double>(aspectX) / aspectY : nativeAspect;
	};
	return std::abs(effectiveAspect(desiredAspectX, desiredAspectY) -
		effectiveAspect(currentAspectX, currentAspectY)) > 0.0001;
}


bool MadVRNlsOutputContractIsPrepared(
	const MadVRShaderRuntimeSnapshot& snapshot)
{
	return snapshot.nlsMode != MadVRNlsMappingMode::OFF &&
		snapshot.nlsMode != MadVRNlsMappingMode::WAITING &&
		snapshot.activeGeometry.stable &&
		snapshot.activeGeometry.rendererGeneration == snapshot.rendererGeneration;
}


MadVRShaderChainUpdatePlan ResolveMadVRShaderChainUpdatePlan(
	bool previousPreKnown, uint64_t previousPreFingerprint,
	uint64_t desiredPreFingerprint, bool desiredPreEmpty,
	bool previousPostKnown, uint64_t previousPostFingerprint,
	uint64_t desiredPostFingerprint, bool desiredPostEmpty)
{
	MadVRShaderChainUpdatePlan plan;
	plan.preScale = previousPreKnown ?
		previousPreFingerprint != desiredPreFingerprint : !desiredPreEmpty;
	plan.postScale = previousPostKnown ?
		previousPostFingerprint != desiredPostFingerprint : !desiredPostEmpty;
	return plan;
}


MadVRShaderRuntimeSnapshot MadVRShaderRuntimeState::GetSnapshot() const
{
	std::lock_guard<std::mutex> lock(m_mutex);
	return m_state;
}


bool MadVRShaderRuntimeState::PrepareNlsOutputContractRendererReplacement()
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_preserveGeometryOnNextRenderer =
		MadVRNlsOutputContractIsPrepared(m_state);
	return m_preserveGeometryOnNextRenderer;
}


uint64_t MadVRShaderRuntimeState::BeginRendererGeneration()
{
	std::lock_guard<std::mutex> lock(m_mutex);
	++m_state.rendererGeneration;
	if (m_preserveGeometryOnNextRenderer &&
		m_state.activeGeometry.stable &&
		(m_state.nlsMode == MadVRNlsMappingMode::ACTIVE ||
			m_state.nlsMode == MadVRNlsMappingMode::LINEAR_PASSTHROUGH ||
			m_state.nlsMode == MadVRNlsMappingMode::SAFE_FIT))
	{
		m_state.activeGeometry.rendererGeneration = m_state.rendererGeneration;
	}
	else
	{
		m_state.activeGeometry = {};
		if (m_state.nlsMode != MadVRNlsMappingMode::OFF)
			m_state.nlsMode = MadVRNlsMappingMode::WAITING;
	}
	m_preserveGeometryOnNextRenderer = false;
	return m_state.rendererGeneration;
}


void MadVRShaderRuntimeState::RecalculateNlsTargetAspectLocked()
{
	if (!std::isfinite(m_physicalNlsTargetAspect) ||
		m_physicalNlsTargetAspect < 1.0 || m_physicalNlsTargetAspect > 4.0)
	{
		m_state.nlsTargetAspect = 0.0;
		return;
	}

	const double fill = ConfiguredNlsTargetFill(m_state.effectiveRule);
	const double target = m_physicalNlsTargetAspect / fill;
	m_state.nlsTargetAspect = std::isfinite(target) &&
		target >= 1.0 && target <= 4.0 ? target : m_physicalNlsTargetAspect;
}


void MadVRShaderRuntimeState::SetRuleSelection(
	const std::string& requestedRule, const std::string& effectiveRule,
	MadVRNlsMappingMode nlsMode)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_state.requestedRule = requestedRule;
	m_state.effectiveRule = effectiveRule;
	RecalculateNlsTargetAspectLocked();
	m_state.nlsMode = nlsMode;
	if (nlsMode == MadVRNlsMappingMode::ACTIVE ||
		nlsMode == MadVRNlsMappingMode::LINEAR_PASSTHROUGH ||
		nlsMode == MadVRNlsMappingMode::SAFE_FIT)
		m_state.lastSafeNlsMode = nlsMode;
	else if (nlsMode == MadVRNlsMappingMode::OFF)
	{
		m_state.lastSafeNlsMode = MadVRNlsMappingMode::OFF;
		m_state.activeGeometry = {};
	}
	else
		m_state.activeGeometry = {};
	RecalculateRuntimeNlsDecision(m_state);
}


void MadVRShaderRuntimeState::SetRequestedRule(
	const std::string& requestedRule)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_state.requestedRule = requestedRule;
}


void MadVRShaderRuntimeState::SetEffectiveRule(
	const std::string& effectiveRule)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_state.effectiveRule = effectiveRule;
	RecalculateNlsTargetAspectLocked();
	RecalculateRuntimeNlsDecision(m_state);
}


void MadVRShaderRuntimeState::SetNlsTargetAspect(double targetAspect)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_physicalNlsTargetAspect = std::isfinite(targetAspect) &&
		targetAspect >= 1.0 && targetAspect <= 4.0 ? targetAspect : 0.0;
	RecalculateNlsTargetAspectLocked();
	RecalculateRuntimeNlsDecision(m_state);
}


void MadVRShaderRuntimeState::SetNlsDecision(
	const MadVRNlsMappingDecision& decision)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_state.nlsDecision = decision;
}


bool MadVRShaderRuntimeState::SetActiveGeometry(
	const MadVRActivePictureGeometry& geometry)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	const bool valid = geometry.stable &&
		geometry.rendererGeneration == m_state.rendererGeneration &&
		std::isfinite(geometry.aspectRatio) && geometry.aspectRatio > 0.0 &&
		geometry.left >= 0.0 && geometry.top >= 0.0 &&
		geometry.right <= 1.0 && geometry.bottom <= 1.0 &&
		geometry.right > geometry.left && geometry.bottom > geometry.top;
	if (!valid)
		return false;
	m_state.activeGeometry = geometry;
	RecalculateRuntimeNlsDecision(m_state);
	return true;
}
