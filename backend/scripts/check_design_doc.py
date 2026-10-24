"""设计文档一致性检查：确认文档描述与代码/配置没有漂移。"""

import pathlib
import re

ROOT = pathlib.Path(r"C:\Users\yr200\Documents\trae_projects\YR")
CSS = ROOT / "kg-vue3" / "src" / "styles" / "main.css"
IDENT = ROOT / "kg-vue3" / "src" / "styles" / "identity.css"
DOC = ROOT / "docs" / "设计系统.md"

css_text = CSS.read_text(encoding="utf-8") + IDENT.read_text(encoding="utf-8")
doc_text = DOC.read_text(encoding="utf-8")

# 只取 :root（亮色）里的第一条定义
defs = {}
for m in re.finditer(r"^\s*(--[\w-]+):\s*([^;]+);", css_text, re.M):
    name, val = m.group(1), m.group(2).strip()
    if name not in defs:
        defs[name] = val

CHECK = [
    "--accent", "--accent-light", "--accent-strong", "--accent-fill",
    "--text-primary", "--text-secondary", "--text-muted", "--text-faint",
    "--bg-deep", "--bg-primary", "--bg-secondary", "--bg-tertiary",
    "--bg-hover", "--bg-active", "--border", "--border-light",
    "--radius-sm", "--radius", "--radius-lg", "--ctrl-h",
    "--fs-xs", "--fs-sm", "--fs-md", "--fs-base", "--fs-lg", "--fs-xl",
    "--panel-width", "--toolbar-height",
    "--violet-text", "--amber", "--magenta", "--seal",
    "--success-fill", "--danger-fill", "--warning-fill",
]

ok, missing, mismatch = [], [], []
for name in CHECK:
    val = defs.get(name)
    if val is None:
        missing.append(name)
        continue
    # 只核对简单字面值（hex / px / 数字），复杂的 color-mix 跳过
    if not re.fullmatch(r"#[0-9A-Fa-f]{3,8}|\d+(\.\d+)?px|\d+", val):
        ok.append((name, val, "跳过（复合值）"))
        continue
    if val in doc_text:
        ok.append((name, val, "一致"))
    else:
        mismatch.append((name, val))

print("=== 设计系统.md 的 token 与 CSS 实际定义核对 ===\n")
for name, val, note in ok:
    if note == "一致":
        print(f"  OK   {name:18} {val}")
print()
if mismatch:
    print("!! 文档里没出现这些值（可能写错或漏记）：")
    for name, val in mismatch:
        print(f"  XX   {name:18} CSS 实际 = {val}")
else:
    print("没有不一致的字面值。")
if missing:
    print("\nCSS 里没找到定义的 token：", ", ".join(missing))
print(f"\n合计核对 {len(CHECK)} 个，一致 {sum(1 for _, _, n in ok if n == '一致')}，"
      f"不一致 {len(mismatch)}，跳过 {sum(1 for _, _, n in ok if n != '一致')}。")
