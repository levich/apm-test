"""Offline, packaged user guide; only known sections can be opened."""

import re
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).with_name("documentation")


def section_names():
    names = sorted(path.stem for path in (ROOT / "en").glob("*.md"))
    return ["index", *[name for name in names if name != "index"]] if "index" in names else names


def guide(section, language):
    if section not in section_names():
        raise KeyError(section)
    language = "ru" if language == "ru" else "en"
    source = (ROOT / language / (section + ".md")).read_text()
    source = re.sub(
        r"^<!-- (?:setting|environment|credential|command|option|label):[^\n]*-->\n?",
        "",
        source,
        flags=re.MULTILINE,
    )
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = parser.parse(source)
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            title = tokens[index + 1].content
            anchor = re.sub(r"[^\w-]+", "-", title.replace("`", "").lower()).strip("-")
            token.attrSet("id", anchor)
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "link_open":
                    href = child.attrGet("href") or ""
                    if re.fullmatch(r"[a-z-]+\.md(?:#[\w.-]+)?", href):
                        child.attrSet("href", "/ui/documentation/" + href.replace(".md", "", 1))
    return parser.renderer.render(tokens, parser.options, {}), source.splitlines()[0].removeprefix("# ")


def navigation(language):
    language = "ru" if language == "ru" else "en"
    return [
        {
            "id": name,
            "title": (ROOT / language / (name + ".md")).read_text().splitlines()[0].removeprefix("# "),
        }
        for name in section_names()
    ]
