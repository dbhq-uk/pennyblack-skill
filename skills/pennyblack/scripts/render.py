"""Turn a markdown letter into HTML the print API can set.

This is deliberately a small subset, not a markdown engine. A letter needs
paragraphs, line breaks, emphasis, headings, lists and rules. It does not need
tables, footnotes or embedded HTML, and supporting them would mean either a
dependency or a lot of code that can go wrong silently on something being
posted to a real person.

Anything it does not understand is passed through as plain text rather than
mangled, so the worst case is a letter that looks plainer than intended, never
one that loses a sentence.
"""

import html
import re

# A4 with sensible margins, a serif face, and sizes that survive print.
# Intelliprint applies letterheads server-side as a background, so this
# stylesheet deliberately leaves the top of the page alone.
STYLESHEET = """
@page { size: A4; margin: 25mm 20mm 20mm 20mm; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 11.5pt;
  line-height: 1.45;
  color: #111;
}
h1 { font-size: 15pt; margin: 0 0 12pt; }
h2 { font-size: 13pt; margin: 16pt 0 8pt; }
h3 { font-size: 11.5pt; margin: 14pt 0 6pt; }
p { margin: 0 0 10pt; }
ul, ol { margin: 0 0 10pt 18pt; padding: 0; }
li { margin: 0 0 4pt; }
hr { border: 0; border-top: 1px solid #ccc; margin: 14pt 0; }
.address { margin: 0 0 18pt; }
.date { margin: 0 0 18pt; }
"""

_INLINE = (
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", re.S), r"<em>\1</em>"),
    (re.compile(r"`(.+?)`", re.S), r"<code>\1</code>"),
    (re.compile(r"\[(.+?)\]\((.+?)\)"), r"\1 (\2)"),  # a printed link needs its URL visible
)


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for pattern, repl in _INLINE:
        out = pattern.sub(repl, out)
    return out


def markdown_to_html(text: str, *, title: str = "Letter") -> str:
    """Convert a markdown letter to a standalone HTML document."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body: list[str] = []
    para: list[str] = []
    list_type: str | None = None

    def flush_para():
        nonlocal para
        if para:
            body.append("<p>" + "<br>\n".join(_inline(l) for l in para) + "</p>")
            para = []

    def close_list():
        nonlocal list_type
        if list_type:
            body.append(f"</{list_type}>")
            list_type = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_para()
            close_list()
            continue

        if re.fullmatch(r"(-\s*){3,}|(\*\s*){3,}|(_\s*){3,}", stripped):
            flush_para()
            close_list()
            body.append("<hr>")
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            body.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue

        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if bullet or numbered:
            flush_para()
            wanted = "ul" if bullet else "ol"
            if list_type != wanted:
                close_list()
                body.append(f"<{wanted}>")
                list_type = wanted
            item = (bullet or numbered).group(1)
            body.append(f"<li>{_inline(item)}</li>")
            continue

        close_list()
        para.append(stripped)

    flush_para()
    close_list()

    return (
        "<!DOCTYPE html>\n<html lang=\"en-GB\"><head>"
        "<meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{STYLESHEET}</style>"
        "</head><body>\n" + "\n".join(body) + "\n</body></html>"
    )


def looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


def prepare(text: str, *, title: str = "Letter") -> str:
    """Pass HTML through untouched; convert anything else from markdown."""
    return text if looks_like_html(text) else markdown_to_html(text, title=title)
