#!/usr/bin/env python3
"""Build the protected PDF for this probe from PROBE-VI.md.

The default source is the parent of harness. Run from any directory, or pass paths explicitly:

    python build_pdf.py                       # source dir = parent of harness
    python build_pdf.py --source DIR --out DIR/name.pdf
    python build_pdf.py --engine-dir /path/to/texbin

Requires XeLaTeX (TeX Live or MiKTeX) with the DejaVu fonts, and pypdf[crypto]. The
engine is located on PATH; --engine-dir overrides that for an installation
that is not on PATH.

The output is encrypted at creation: an empty user password so anyone can read
it, a random owner password, and viewer permission flags allowing printing while
disabling copying and modification. These flags do not establish content
integrity. In a signed publication package, verify content integrity using the
signatures and hash manifest.
The decrypted intermediate exists only in memory.

Build metadata (/Producer, /CreationDate, /ModDate) is deliberately removed:
it names the toolchain and the exact build second, and neither belongs in a
published artefact.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent


def find_engine(name, engine_dir):
    if engine_dir:
        candidate = Path(engine_dir) / (name + (".exe" if os.name == "nt" else ""))
        if candidate.is_file():
            return str(candidate)
        raise SystemExit(f"{name} not found in --engine-dir {engine_dir}")
    found = shutil.which(name)
    if not found:
        raise SystemExit(
            f"{name} not found on PATH. Install TeX Live or MiKTeX, or pass "
            f"--engine-dir pointing at the directory that contains it."
        )
    return found


def esc(s):
    table = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
             "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    return "".join(table.get(c, c) for c in s).replace(chr(34), r"\textquotedbl{}")


def inline(s):
    parts, end = [], 0
    token = re.compile(r"\\\(.*?\\\)|`[^`]+`|\[[^\]]+\]\([^\)]+\)|\*\*[^*]+\*\*|\*[^*]+\*", re.S)
    for m in token.finditer(s):
        parts.append(esc(s[end:m.start()]))
        t = m.group()
        if t.startswith(r"\("):
            parts.append(t)
        elif t.startswith("`"):
            code = t[1:-1]
            if re.fullmatch("[a-f0-9]{64}", code):
                code = r"\allowbreak{}".join(code[i:i + 16] for i in range(0, 64, 16))
                parts.append(r"{\footnotesize\ttfamily " + code + "}")
            else:
                parts.append(r"\texttt{" + esc(code) + "}")
        elif t.startswith("["):
            label, url = re.fullmatch(r"\[([^\]]+)\]\(([^\)]+)\)", t).groups()
            parts.append(r"\href{" + url + "}{" + esc(label) + "}")
        elif t.startswith("**"):
            parts.append(r"\textbf{" + esc(t[2:-2]) + "}")
        else:
            parts.append(r"\emph{" + esc(t[1:-1]) + "}")
        end = m.end()
    parts.append(esc(s[end:]))
    return "".join(parts)


def to_latex_body(src):
    out, lines, i, listenv = [], src.splitlines(), 0, None
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if listenv:
                out.append(r"\end{" + listenv + "}")
                listenv = None
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(r"\begin{quote}\small\begin{verbatim}" + "\n"
                       + "\n".join(block) + "\n" + r"\end{verbatim}\end{quote}")
        elif line.strip() == r"\[":
            if listenv:
                out.append(r"\end{" + listenv + "}")
                listenv = None
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if lines[i].strip() == r"\]":
                    break
                i += 1
            while out and not out[-1].strip():
                out.pop()
            out.append("\n".join(block))
        else:
            lm = re.match(r"^(- |\d+\. )(.*)", line)
            if lm:
                env = "itemize" if lm[1] == "- " else "enumerate"
                if listenv != env:
                    if listenv:
                        out.append(r"\end{" + listenv + "}")
                    listenv = env
                    out.append(r"\begin{" + env + "}")
                out.append(r"\item " + inline(lm[2]))
            else:
                if listenv:
                    out.append(r"\end{" + listenv + "}")
                    listenv = None
                if not line:
                    out.append("")
                elif line == "---":
                    out.append(r"\par\medskip")
                elif line.startswith("# "):
                    out.append(r"{\raggedright\LARGE\bfseries " + inline(line[2:]) + r"\par}\vspace{4pt}")
                elif line.startswith("### "):
                    if i < 10:
                        out.append(r"{\raggedright\large " + inline(line[4:]) + r"\par}\vspace{8pt}")
                    else:
                        out.append(r"\subsection*{" + inline(line[4:]) + "}")
                elif line.startswith("## "):
                    out.append(r"\Needspace{8\baselineskip}\section*{" + inline(line[3:]) + "}")
                else:
                    out.append(inline(line.rstrip()) + (r"\par" if line.endswith("  ") else ""))
        i += 1
    if listenv:
        out.append(r"\end{" + listenv + "}")
    return "\n".join(out)


PREAMBLE = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=23mm,headheight=14pt,footskip=12mm]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}[Ligatures=NoCommon]
\setsansfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}[Scale=0.88]
\usepackage{amsmath,amssymb}
\usepackage{xcolor,graphicx,fancyhdr,needspace}
\usepackage[unicode,colorlinks=true,urlcolor=blue,linkcolor=blue,breaklinks=true]{hyperref}
\hypersetup{pdftitle={Individual Viability Does Not Compose: A Common-Control Counterexample. Probe VI},pdfauthor={Maksim Barziankou (MxBv)},pdfsubject={NC2.5 Empirical Probes - Part VI},pdfkeywords={viability theory, admissible sets, constrained control, common control, NC2.5, DOI:10.17605/OSF.IO/WFBX6},pdfcreator={PETRONUS}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\setlength{\emergencystretch}{3em}
\hyphenpenalty=10000\exhyphenpenalty=10000
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\sffamily\scriptsize NC2.5 EMPIRICAL PROBES / VI}
\fancyfoot[L]{\sffamily\scriptsize PETRONUS / DOI: 10.17605/OSF.IO/WFBX6 / CC BY-NC-ND 4.0}
\fancyfoot[R]{\sffamily\scriptsize Page \thepage}
\renewcommand{\headrulewidth}{0.3pt}
\begin{document}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(HERE.parent),
                    help="directory containing PROBE-VI.md (default: parent of harness)")
    ap.add_argument("--out", default=None,
                    help="output PDF path (default: <source>/Individual Viability Does Not Compose (2026).pdf)")
    ap.add_argument("--engine-dir", default=None,
                    help="directory holding xelatex/xdvipdfmx if they are not on PATH")
    args = ap.parse_args()

    source = Path(args.source).resolve()
    manuscript = source / "PROBE-VI.md"
    if not manuscript.is_file():
        raise SystemExit(f"PROBE-VI.md not found in {source}")
    target = Path(args.out).resolve() if args.out else \
        source / "Individual Viability Does Not Compose (2026).pdf"

    if target.exists():
        raise SystemExit(f"Output already exists: {target}")

    xelatex = find_engine("xelatex", args.engine_dir)
    xdvipdfmx = find_engine("xdvipdfmx", args.engine_dir)

    md = manuscript.read_text(encoding="utf-8")
    owner = secrets.token_hex(24)
    tex = (PREAMBLE
           + "\n" + r"\special{pdf:encrypt userpw () ownerpw (" + owner + ") length 256 perm 2052}"
           + "\n" + to_latex_body(md) + "\n" + r"\end{document}" + "\n")

    with tempfile.TemporaryDirectory(prefix="probe-vi-build-") as tmp:
        build = Path(tmp)
        # newline="" so the .tex keeps the bytes we generated on every platform
        with open(build / "probe-vi.tex", "w", encoding="utf-8", newline="") as fh:
            fh.write(tex)
        for _ in range(2):
            r = subprocess.run([xelatex, "-no-pdf", "-interaction=nonstopmode",
                                "-halt-on-error", "-output-directory", str(build),
                                str(build / "probe-vi.tex")],
                               cwd=build, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
            if r.returncode:
                print((r.stdout + r.stderr)[-4000:])
                raise SystemExit("TeX compilation failed")
        raw = build / "raw.pdf"
        r = subprocess.run([xdvipdfmx, "-V", "7", "-o", str(raw), str(build / "probe-vi.xdv")],
                           input="", cwd=build, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=240)
        if r.returncode:
            print((r.stdout + r.stderr).replace(owner, "[redacted]")[-3000:])
            raise SystemExit("encrypted PDF generation failed")

        # Re-serialise with standard dictionary spacing. The document is decrypted
        # in memory only; every on-disk form stays AES-256 encrypted.
        reader = PdfReader(str(raw))
        reader.decrypt("")
        writer = PdfWriter(clone_from=reader)
        writer.pdf_header = "%PDF-1.7"
        for key in ("/Producer", "/CreationDate", "/ModDate"):
            if writer._info is not None and key in writer._info:
                del writer._info[key]
        writer.encrypt("", owner, algorithm="AES-256", permissions_flag=2052)
        buf = BytesIO()
        writer.write(buf)
        with target.open("xb") as final:
            final.write(buf.getvalue())

    pdf = PdfReader(str(target))
    if not pdf.is_encrypted or not pdf.decrypt(""):
        raise SystemExit("PDF must be protected but readable with an empty user password")
    if int(pdf.trailer["/Encrypt"]["/P"]) & (8 | 16 | 32 | 256 | 1024):
        raise SystemExit("forbidden modification/copy permissions")

    # measured: exempt these are the built file's own properties, each already
    # gated by the two assertions above; the build fails rather than misreports
    print(json.dumps({
        "pdf": str(target),
        "pages": len(pdf.pages),
        "encrypted": pdf.is_encrypted,
        "permissions": int(pdf.trailer["/Encrypt"]["/P"]),
        "encryption_revision": int(pdf.trailer["/Encrypt"]["/R"]),
        "source_sha256": hashlib.sha256(manuscript.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
