# Probe VI: Individual Viability Does Not Compose

Maksim Barziankou (MxBv), The Urgrund Laboratheory.

Paper: https://doi.org/10.17605/OSF.IO/WFBX6

This companion checks a three-state, one-input linear counterexample to the
composition of individual admissible sets. The certificate and its tests require
Python 3.10 or newer and use only the standard library. No network connection
or account is needed to run them.

Run from this directory:

```text
python -B probe_vi.py
python -B -m unittest discover -p "test_*.py" -v
```

The first command prints a deterministic JSON certificate with six named checks
and result PASS. The second runs seven tests, including seventeen model mutations
that must fail at their intended first check, and three models with a shared
control that distinguish a local rate calculation from joint viability.
It also exercises two faulty set helpers and two changes to the third-coordinate
dynamics. The latter are rejected by the trajectory check first in the full
certificate; the constancy guard is additionally tested directly.

certificate.json records the unmodified certificate. To regenerate it, write
output to a new file, for example `python -B probe_vi.py > certificate.new.json`.
Check that the command exited successfully and the new file is complete JSON
with result PASS before replacing certificate.json. Keep the previous receipt
until these checks succeed.

Together, the checks cover the explicitly checked standing conditions,
individual witnesses, the absence of a common witness, exact-set identities,
tangency and boundary hulls, and two negative controls. The sum-rate check
alone is local; the common-control conclusion also requires the exact-model
check. They do not reproduce the source paper's numerical examples or its
complete sampling implementation, and do not implement a general viability
solver. The limits and proof are stated in the paper.

The full publication package also contains build_pdf.py. From its publication
directory, rebuild to a new file with:

```text
python harness/build_pdf.py --out rebuilt-probe-vi.pdf
```

PDF generation additionally requires pypdf[crypto] and XeLaTeX/xdvipdfmx (TeX Live or
MiKTeX) with the DejaVu fonts. Use --engine-dir if the TeX executables are not
on PATH. The default source directory is the parent of harness; --source can
override it. Existing output files are refused. A rebuilt PDF needs its own
signature and timestamp; random encryption parameters prevent byte-identical
PDF builds.

The code is licensed under MIT; see LICENSE. The paper has its own CC BY-NC-ND
4.0 licence.
