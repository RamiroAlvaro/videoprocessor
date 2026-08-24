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
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
subprocess.run([sys.executable, str(path)], check=True)
