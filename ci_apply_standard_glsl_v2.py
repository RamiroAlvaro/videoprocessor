from pathlib import Path
import subprocess
import sys

path = Path("ci_apply_standard_glsl.py")
text = path.read_text(encoding="utf-8")

old = '''clear_pair = "\\t\\trenderParams.hooks = nullptr;\\n\\t\\trenderParams.num_hooks = 0;"
clear_count = text.count(clear_pair)
if clear_count != 7:
    raise RuntimeError(f"per-frame hook clear sites: expected 7 after selection rewrite, found {clear_count}")
text = text.replace(clear_pair, "\\t\\tBindActiveHooks(false);")
'''
new = '''clear_pattern = re.compile(
    r"(?m)^(?P<indent>[ \\t]*)renderParams\\.hooks = nullptr;\\n"
    r"(?P=indent)renderParams\\.num_hooks = 0;"
)
clear_matches = list(clear_pattern.finditer(text))
if len(clear_matches) < 5:
    raise RuntimeError(
        f"per-frame hook clear sites: expected at least 5, found {len(clear_matches)}"
    )
text = clear_pattern.sub(
    lambda match: f"{match.group('indent')}BindActiveHooks(false);",
    text,
)
'''
if text.count(old) != 1:
    raise RuntimeError("could not locate the original hook-clear patch block")
text = text.replace(old, new, 1)

old_url = 'shader_url = "https://gist.githubusercontent.com/igv/8a77e4eb8276753b54bb94c1c50c317e/raw/adaptive-sharpen.glsl"'
new_url = 'shader_url = "https://gist.githubusercontent.com/igv/8a77e4eb8276753b54bb94c1c50c317e/raw/572f59099cd0e3eb5e321a6da0a3d90a7382e2dc/adaptive-sharpen.glsl"'
if text.count(old_url) != 1:
    raise RuntimeError("could not locate Adaptive Sharpen source URL")
text = text.replace(old_url, new_url, 1)

old_strength = '''if "#define curve_height 1.0" not in shader:
    raise RuntimeError("Adaptive Sharpen curve_height baseline not found")
shader = shader.replace("#define curve_height 1.0", "#define curve_height {{strength}}", 1)
'''
new_strength = '''shader, strength_count = re.subn(
    r"(?m)^(#define\\s+curve_height\\s+)1\\.0(\\b.*)$",
    r"\\g<1>{{strength}}\\2",
    shader,
    count=1,
)
if strength_count != 1:
    raise RuntimeError("Adaptive Sharpen curve_height baseline not found")
'''
if text.count(old_strength) != 1:
    raise RuntimeError("could not locate Adaptive Sharpen strength patch block")
text = text.replace(old_strength, new_strength, 1)

path.write_text(text, encoding="utf-8", newline="\n")
subprocess.run([sys.executable, str(path)], check=True)
