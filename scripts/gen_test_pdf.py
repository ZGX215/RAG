"""
生成测试用普通 PDF 文档（7 页，涵盖 Python 常见主题）
=====================================================

用法: python scripts/gen_test_pdf.py

生成文件: data/test_normal_pdf.pdf
"""

from pathlib import Path
from fpdf import FPDF

project_root = Path(__file__).resolve().parent.parent
out_path = project_root / "data" / "test_normal_pdf.pdf"
out_path.parent.mkdir(parents=True, exist_ok=True)

pdf = FPDF()
cjk = Path("C:/Windows/Fonts/msyh.ttc")
if cjk.exists():
    pdf.add_font("CJK", "", str(cjk), uni=True)
    pdf.set_font("CJK", size=12)
else:
    pdf.set_font("Helvetica", size=12)

pages = [
    ["Python Programming Guide", "", "Python is a high-level language created by Guido van Rossum in 1991.",
     "It emphasizes code readability with significant indentation.", "",
     "Python is dynamically-typed and garbage-collected.", "It supports multiple programming paradigms.", "",
     "Key features: easy syntax, dynamic typing, and extensive libraries.", "Used in web dev, data science, and AI."],
    ["Data Types", "", "Python has several built-in data types.",
     "Numeric: int, float, complex. Sequence: list, tuple, range.", "",
     "Text: str. Mapping: dict. Set: set, frozenset.", "Boolean: bool with values True and False.", "",
     "Variables need no explicit declaration in Python."],
    ["Control Flow", "", "Python supports standard control flow.", "if/elif/else for conditional logic.", "",
     "for loops for iterating over sequences.", "while loops for repeated execution.", "",
     "List comprehensions for concise list creation.", "range function generates number sequences."],
    ["Functions", "", "Functions are defined with def keyword.", "Default arguments: def power(base, exp=2)", "",
     "Lambda: lambda x: x**2 for anonymous functions.", "Functions are first-class objects in Python.", "",
     "Modules are files with Python definitions.", "Packages are collections of modules organized in directories."],
    ["File I/O", "", "File operations use the with statement.", "open for reading, writing, and appending files.", "",
     "Exception handling with try/except/finally.", "Common exceptions: TypeError, ValueError, KeyError.", "",
     "The finally block always executes regardless of exceptions."],
    ["OOP", "", "Python supports OOP with classes.", "class Animal: def __init__(self, name)", "",
     "Inheritance for code reuse between classes.", "Encapsulation with _protected and __private attributes.", "",
     "Polymorphism through duck typing.", "Special methods like __str__ and __repr__."],
    ["Data Processing", "", "JSON: json.dumps and json.loads for data serialization.",
     "Regex: re.findall and re.match for pattern matching.", "",
     "Dates: datetime and timedelta for time manipulation.", "Collections: defaultdict, Counter, deque for data structures.",
     "", "Itertools: chain, cycle, permutations for iteration tools."],
]

for pg in pages:
    pdf.add_page()
    for line in pg:
        if not line:
            pdf.ln(5)
        else:
            pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")

pdf.output(str(out_path))
print(f"OK: {out_path} ({len(pages)} pages, {out_path.stat().st_size//1024} KB)")
