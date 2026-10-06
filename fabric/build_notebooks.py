"""Build the Fabric notebook from the pipeline scripts in src/, so the code that runs in
Fabric is exactly the code that runs locally.

  python fabric/build_notebooks.py  ->  fabric/NBA_Game_Predictor.ipynb
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FABRIC = ROOT / "fabric"

STEPS = [("00_download.py", "download"), ("01_parse_pbp.py", "parse_pbp"), ("02_features.py", "features"),
         ("03_pregame_model.py", "pregame_model"), ("04_live_model.py", "live_model"), ("05_export.py", "export")]
RESULT = {"pregame_model": "pregame = ", "live_model": "live = "}


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def step_cells(filename, name):
    source = (SRC / filename).read_text()
    tree = ast.parse(source)
    doc = ast.get_docstring(tree)
    body_start = tree.body[1].lineno - 1 if isinstance(tree.body[0], ast.Expr) else 0
    lines = source.splitlines()[body_start:]
    text = "\n".join(lines)
    text = re.sub(r"^import config as C\n", "", text, flags=re.M)
    text = re.sub(r"\n\nif __name__ == \"__main__\":\n(    .*\n?)+", "\n", text)
    text = text.replace("def main(", f"def run_{name}(")
    text = text.rstrip() + f"\n\n\n{RESULT.get(name, '')}run_{name}()\n"
    title = doc.splitlines()[0]
    rest = "\n".join(doc.splitlines()[1:]).strip()
    return [md(f"## {title}\n\n{rest}" if rest else f"## {title}"), code(text)]


def main() -> None:
    cfg_source = (SRC / "config.py").read_text()
    cfg_source = cfg_source.split('"""', 2)[2].strip()
    cfg_source = cfg_source.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path("/tmp/nba")')
    cfg_source = cfg_source.replace('CHECKSUMS = Path(__file__).resolve().parent / "checksums.json"',
                                    'CHECKSUMS = ROOT / "checksums.json"')
    checks = json.loads((SRC / "checksums.json").read_text())
    config = (
        "import json\nimport types\n" + cfg_source + "\n\n"
        "# Expected SHA-256 of every raw file (the download step refuses files that differ)\n"
        f"EXPECTED_FILES = {json.dumps(checks, indent=1)}\n\n"
        "for _d in (ROOT, RAW, PROCESSED, TABLES, FIGURES, FABRIC):\n"
        "    _d.mkdir(parents=True, exist_ok=True)\n"
        "CHECKSUMS.write_text(json.dumps(EXPECTED_FILES))\n"
        "C = types.SimpleNamespace(**{k: v for k, v in dict(globals()).items() if k.isupper() or k == 'season_label'})\n"
        "print('Working folder:', ROOT)\n\n"
        "import mlflow\n"
        "mlflow.autolog(disable=True)   # Fabric logs every model fit by default; only the two final models are logged, at the end\n"
    )
    cells = [
        md((FABRIC / "notebook_intro.md").read_text()),
        code('%%configure -f\n{\n    "defaultLakehouse": {"name": "NBA_Lakehouse"}\n}'),
        md("## Settings\nPaths, seasons and the pinned data sources (the same `config.py` the repository uses)."),
        code(config),
    ]
    for filename, name in STEPS:
        cells += step_cells(filename, name)
    for part in sorted((FABRIC / "cells").glob("*.py")):
        text = part.read_text()
        title, _, body = text.partition("\n")
        cells += [md("## " + title.lstrip("# ").strip()), code(body)]

    nb = {"cells": cells, "metadata": {
        "kernel_info": {"name": "synapse_pyspark"},
        "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
        "language_info": {"name": "python"},
        "microsoft": {"language": "python", "language_group": "synapse_pyspark"},
    }, "nbformat": 4, "nbformat_minor": 5}
    write(nb, "NBA_Game_Predictor.ipynb")

    # Second notebook: semantic model and report (needs the tables the first one saves)
    rj = (FABRIC / "report" / "report_json.py").read_text()
    rj = rj.split('"""', 2)[2].strip()
    rj = re.sub(r"\n\nif __name__ == \"__main__\":\n(    .*\n?)+", "\n", rj)
    sm = (FABRIC / "report" / "semantic_model.py").read_text().partition("\n")
    cr = (FABRIC / "report" / "create_report.py").read_text().partition("\n")
    cells = [
        md("# NBA Game Predictor: semantic model and report\n\nBuilds the Direct Lake semantic model "
           "and the four-page Power BI report from the tables that **NBA_Game_Predictor** and "
           "**NBA_Upcoming_Picks** save to "
           "`NBA_Lakehouse`. Run that notebook first. The report is defined in Python below, so the "
           "whole report is code."),
        code("%pip install -q semantic-link-labs"),
        md("## " + sm[0].lstrip("# ").strip()), code(sm[2]),
        md("## Report definition\nFour pages: 2026-27 picks, pre-game picks, live win probability, games and teams."),
        code(rj),
        md("## " + cr[0].lstrip("# ").strip()), code(cr[2]),
    ]
    write(dict(nb, cells=cells), "NBA_Report_Builder.ipynb")

    # Third notebook: the daily 2026-27 picks (scheduled in Fabric)
    src = (SRC / "07_upcoming.py").read_text()
    doc = ast.get_docstring(ast.parse(src))
    body = src.split('"""', 2)[2].strip()
    body = body.replace("import config as C\n",
                        "import types\n\nC = types.SimpleNamespace(season_label=lambda s: f\"{s}-{(s + 1) % 100:02d}\")\n")
    body = re.sub(r"\n\n\ndef main\(\).*", "\n", body, flags=re.S)        # main() is the local runner
    run = (FABRIC / "upcoming" / "run_picks.py").read_text().partition("\n")
    cells = [
        md((FABRIC / "upcoming" / "intro.md").read_text()),
        code('%%configure -f\n{\n    "defaultLakehouse": {"name": "NBA_Lakehouse"}\n}'),
        md("## " + doc.splitlines()[0].split(" - ", 1)[1].rstrip(".")),
        code(body),
        md("## " + run[0].lstrip("# ").strip()), code(run[2]),
    ]
    write(dict(nb, cells=cells), "NBA_Upcoming_Picks.ipynb")


def write(nb, name):
    out = FABRIC / name
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
    print(f"{out.name}: {len(nb['cells'])} cells, {out.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
