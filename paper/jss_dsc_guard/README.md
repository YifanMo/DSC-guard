# JSS manuscript draft

This directory contains a Journal of Systems and Software style draft based on the rejected DSC-Guard paper and the latest local evaluation artifacts.

Files:

- `main.tex`: new JSS/Elsevier manuscript draft.
- `references.bib`: BibTeX entries cited by the draft.
- `elsarticle-num.bst`: Elsevier numeric bibliography style copied from the official `elsarticle` template.
- `elsarticle.dtx` and `elsarticle.ins`: official Elsevier class source files.
- `elsarticle.cls`: generated Elsevier class file.
- `build_pdf.sh`: local build script that uses the project-local BasicTeX extraction under `tools/basictex_pkg/`.

Current local build command:

```bash
cd paper/jss_dsc_guard
./build_pdf.sh
```

The build uses a no-sudo BasicTeX extraction inside the project:

```text
tools/basictex_pkg/expanded/BasicTeX-2026-Start.pkg/Payload/usr/local/texlive/2026basic
```

TeX-generated font and cache files are redirected to:

```text
tools/texlive-local/
```

This avoids writing to the system TeX tree or `~/Library/texlive`.
