"""
Template rendering for the CV generation system.

Wraps Jinja2 to render a transformed CV data dict into a self-contained
HTML document (CSS inlined via {% include %}, photo embedded as a base64
data URI) so the output needs no external assets — ideal for PDF export
and for sharing a single HTML file.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from models import VariantType


class TemplateRenderer:
    """Renders transformed CV data into HTML using Jinja2 templates."""

    def __init__(self, project_root: Optional[Path] = None):
        """
        Args:
            project_root: repository root. Defaults to the parent of src/.
        """
        self.project_root = project_root or Path(__file__).parent.parent
        self.template_dir = self.project_root / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml", "jinja2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # "2022-01" -> "2022"; "present" -> "present"
        self.env.filters["year"] = lambda d: str(d).split("-")[0]

    def render(self, variant: VariantType, data: Dict[str, Any]) -> str:
        """
        Render a single variant to an HTML string.

        Args:
            variant: employment | contracting | freelance
            data: output of CVTransformer.transform(variant)

        Returns:
            Complete HTML document as a string.
        """
        context = dict(data)
        context["photo_data_uri"] = self._photo_data_uri(
            data.get("personal_info", {}).get("photo")
        )
        template = self.env.get_template(f"variants/{variant}.html.jinja2")
        return template.render(**context)

    def _photo_data_uri(self, photo_path: Optional[str]) -> Optional[str]:
        """Encode the profile photo as a base64 data URI, or None if absent."""
        if not photo_path:
            return None
        resolved = (self.project_root / photo_path).resolve()
        if not resolved.is_file():
            return None
        mime, _ = mimetypes.guess_type(str(resolved))
        mime = mime or "image/jpeg"
        encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
