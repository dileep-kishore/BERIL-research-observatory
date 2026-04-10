"""Static alias table for biological entity normalization.

Provides a canonical-name -> aliases mapping for organisms, methods, and
concepts commonly encountered in the BERIL observatory.  The table can be
loaded from and saved to JSON so it grows over time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Repo-relative default location for the persisted alias table.
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "graph" / "aliases.json"

# ---------------------------------------------------------------------------
# Built-in alias table
# ---------------------------------------------------------------------------

BUILTIN_ALIASES: dict[str, list[str]] = {
    # -- Organisms ----------------------------------------------------------
    "Pseudomonas putida": [
        "P. putida",
        "p. putida",
        "pseudomonas putida",
        "Pseudomonas putida KT2440",
        "P. putida KT2440",
    ],
    "Escherichia coli": [
        "E. coli",
        "e. coli",
        "escherichia coli",
        "Escherichia coli K-12",
        "E. coli K-12",
        "Escherichia coli BW25113",
        "E. coli BW25113",
    ],
    "Cupriavidus metallidurans": [
        "C. metallidurans",
        "c. metallidurans",
        "cupriavidus metallidurans",
        "Cupriavidus metallidurans CH34",
        "C. metallidurans CH34",
        "Ralstonia metallidurans",
    ],
    "Shewanella oneidensis": [
        "S. oneidensis",
        "s. oneidensis",
        "shewanella oneidensis",
        "Shewanella oneidensis MR-1",
        "S. oneidensis MR-1",
    ],
    "Pseudomonas fluorescens": [
        "P. fluorescens",
        "p. fluorescens",
        "pseudomonas fluorescens",
        "Pseudomonas fluorescens FW300-N2E3",
        "P. fluorescens FW300-N2E3",
    ],
    "Pseudomonas simiae": [
        "P. simiae",
        "p. simiae",
        "pseudomonas simiae",
        "Pseudomonas simiae WCS417",
        "P. simiae WCS417",
    ],
    "Pseudomonas stutzeri": [
        "P. stutzeri",
        "p. stutzeri",
        "pseudomonas stutzeri",
        "Pseudomonas stutzeri RCH2",
    ],
    "Bacillus subtilis": [
        "B. subtilis",
        "b. subtilis",
        "bacillus subtilis",
    ],
    "Sinorhizobium meliloti": [
        "S. meliloti",
        "s. meliloti",
        "sinorhizobium meliloti",
    ],
    "Dinoroseobacter shibae": [
        "D. shibae",
        "d. shibae",
        "dinoroseobacter shibae",
    ],

    # -- Concepts -----------------------------------------------------------
    "core genome": [
        "core genes",
        "core gene",
        "core-genome",
        "core_genome",
        "core gene set",
    ],
    "accessory genome": [
        "accessory genes",
        "accessory gene",
        "accessory-genome",
        "accessory_genome",
        "shell genome",
        "shell genes",
    ],
    "dark genes": [
        "functional dark matter",
        "hypothetical proteins",
        "uncharacterized genes",
        "genes of unknown function",
        "functionally unannotated genes",
    ],
    "pangenome": [
        "pan-genome",
        "pan genome",
        "pan_genome",
    ],
    "horizontal gene transfer": [
        "HGT",
        "lateral gene transfer",
        "LGT",
        "horizontal transfer",
    ],
    "metal resistance": [
        "metal tolerance",
        "heavy metal resistance",
        "metal homeostasis",
    ],
    "biofilm": [
        "biofilm formation",
        "biofilm development",
    ],
    "fitness": [
        "gene fitness",
        "fitness score",
        "fitness value",
    ],

    # -- Methods ------------------------------------------------------------
    "RB-TnSeq": [
        "randomly barcoded transposon sequencing",
        "RB-Tnseq",
        "rb-tnseq",
        "RBTnSeq",
        "randomly barcoded TnSeq",
        "barcode sequencing",
        "BarSeq",
    ],
    "Fitness Browser": [
        "fitness-browser",
        "fitness browser",
        "Fitness_Browser",
        "fit.genomics.lbl.gov",
    ],
    "comparative genomics": [
        "genome comparison",
        "comparative genome analysis",
    ],
    "transposon mutagenesis": [
        "Tn mutagenesis",
        "transposon insertion",
        "Tn-seq",
        "TnSeq",
    ],
}

# ---------------------------------------------------------------------------
# Genus abbreviation table (derived from BUILTIN_ALIASES organism keys)
# ---------------------------------------------------------------------------

GENUS_ABBREVIATIONS: dict[str, str] = {
    "P.": "Pseudomonas",
    "E.": "Escherichia",
    "C.": "Cupriavidus",
    "S.": "Shewanella",
    "B.": "Bacillus",
    "D.": "Dinoroseobacter",
}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_aliases(path: str | Path | None = None) -> dict[str, list[str]]:
    """Load the alias table from a JSON file, falling back to built-ins.

    Parameters
    ----------
    path
        Path to JSON file.  Defaults to ``data/graph/aliases.json``
        relative to the repository root.

    Returns
    -------
    dict[str, list[str]]
        Canonical name -> list of known aliases.
    """
    target = Path(path) if path else _DEFAULT_PATH
    if target.exists():
        with target.open() as fh:
            data: dict[str, Any] = json.load(fh)
        # Merge built-ins that may have been added since the file was saved
        merged = {**BUILTIN_ALIASES}
        for canon, aliases in data.items():
            existing = set(merged.get(canon, []))
            existing.update(aliases)
            merged[canon] = sorted(existing)
        return merged
    return {k: list(v) for k, v in BUILTIN_ALIASES.items()}


def save_aliases(aliases: dict[str, list[str]], path: str | Path | None = None) -> Path:
    """Persist the alias table to JSON.

    Parameters
    ----------
    aliases
        Canonical name -> list of known aliases.
    path
        Destination file.  Parent directories are created if needed.

    Returns
    -------
    Path
        The written file path.
    """
    target = Path(path) if path else _DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as fh:
        json.dump(aliases, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return target
