"""Generate FS25 fruit-type XML files from a CropConfig."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .utils import CropConfig, ensure_dir

# ---------------------------------------------------------------------------
# Jinja2 environment – templates live next to this package's parent dir
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_fruit_type_xml(crop: CropConfig, output_dir: str | Path) -> Path:
    """Render the fruit-type XML for *crop* and write it to *output_dir*.

    Returns the path to the written file.
    """
    env = _get_env()
    template = env.get_template("fruit_type.xml.j2")
    content = template.render(crop=crop)

    out = ensure_dir(output_dir)
    dest = out / f"{crop.name}.xml"
    dest.write_text(content, encoding="utf-8")
    return dest


def generate_mod_desc_entry(crop: CropConfig, output_dir: str | Path) -> Path:
    """Render the modDesc snippet for *crop* and write it to *output_dir*.

    Returns the path to the written file.
    """
    env = _get_env()
    template = env.get_template("mod_desc_entry.xml.j2")
    content = template.render(crop=crop)

    out = ensure_dir(output_dir)
    dest = out / f"{crop.name}_modDesc_entry.xml"
    dest.write_text(content, encoding="utf-8")
    return dest
