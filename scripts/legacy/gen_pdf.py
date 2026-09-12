import os

from fpdf import FPDF

out = "E:/trae/cede/mcu-rag-qa-v2/data/test_normal_pdf.pdf"
os.makedirs(os.path.dirname(out), exist_ok=True)
pdf = FPDF()
fp = "C:/Windows/Fonts/msyh.ttc"
if os.path.exists(fp):
    pdf.add_font("CJK", "", fp, uni=True)
    pdf.set_font("CJK", size=12)
else:
    pdf.set_font("Helvetica", size=12)
pages = [
    ["Python Programming Guide", "", "Python is a high-level language created by Guido van Rossum in 1991.", "It emphasizes code readability.", "Python is dynamically-typed and garbage-collected.", "It supports multiple programming paradigms.", "Used in web dev, data science, and AI."],
    ["Data Types", "", "Python has several built-in data types.", "Numeric: int, float, complex", "Sequence: list, tuple, range", "Text: str", "Mapping: dict", "Set: set, frozenset", "Boolean: bool", "Variables need no explicit declaration."],
    ["Control Flow", "", "Python supports standard control flow.", "if/elif/else for conditional logic.", "for loops for iterating over sequences.", "while loops for repeated execution.", "List comprehensions for concise list creation.", "range function generates number sequences."],
    ["Functions", "", "Functions are defined with def keyword.", "Default arguments: def power(base, exp=2)", "Lambda: lambda x: x**2", "Functions are first-class objects.", "Modules are files with Python definitions.", "Packages are collections of modules."],
    ["File I/O", "", "File operations use the with statement.", "open for reading, writing, appending.", "Exception handling with try/except.", "Common exceptions: TypeError, ValueError.", "finally block always executes."],
    ["OOP", "", "Python supports OOP with classes.", "class Animal: def __init__(self, name)", "Inheritance, encapsulation, polymorphism.", "Special methods like __str__ and __repr__.", "Properties with @property decorator."],
    ["Data Processing", "", "JSON: json.dumps and json.loads", "Regex: re.findall and re.match", "Dates: datetime and timedelta", "Collections: defaultdict, Counter, deque", "Itertools: chain, cycle, permutations"],
]
for pg in pages:
    pdf.add_page()
    for line in pg:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
pdf.output(out)
print("OK: " + out)
