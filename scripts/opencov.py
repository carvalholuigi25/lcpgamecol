import os
import webbrowser

## Mode coverage (0 = default coverage page, 1 = pretty modified coverage page)
modecov=0

if modecov == 0:
    filename="htmlcov/index.html"
else:
    filename="coverage-report.html"

webbrowser.open('file://' + os.path.realpath("mycoverage/"+filename))
