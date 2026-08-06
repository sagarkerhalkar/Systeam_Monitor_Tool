# Commercial CI

The commercial branch uses normal Git source and pull-request validation. Patch injection, Base64 transfer payloads and CI workflows that rewrite source files are not permitted.

Run the commercial tests locally from the repository root:

```bash
PYTHONPATH=commercial python -m unittest discover -s commercial/tests -v
python commercial/tools/verify_release_foundation.py
python -m py_compile server.py
python -m compileall -q commercial
```

The GitHub workflow additionally validates the dashboard JavaScript and the required Windows and Ubuntu agent scripts on native hosted runners.
