"""Markdown (a GitHub README, a docs/*.md file, a .md link), reStructuredText (README.rst) and plain text as blocks.

Not a full CommonMark parser: the parts a lesson needs. Fenced code is kept verbatim with its info string's language;
ATX and setext headings carry GitHub's anchor slug; list items keep their number and depth; images, badges, HTML
comments, link reference definitions and raw HTML tags are dropped (their text kept); [text](url) keeps the text.
"""

from __future__ import annotations

import re

from .html import norm_lang
from .model import Block, slug

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^`\s{]*)?[^`]*$")  # any indent: fences inside list items
_ATX = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|(\d{1,9})[.)])\s+(.*)$")
_REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S+")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]")
_BADGE_LINK = re.compile(r"\[\s*(?:!\[[^\]]*\]\([^)]*\)\s*)+\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def inline(text: str) -> str:
    t = _BADGE_LINK.sub("", text)
    t = _IMG.sub("", t)
    t = re.sub(r"<img\b[^>]*>", "", t, flags=re.IGNORECASE)
    t = _LINK.sub(r"\1", t)
    t = _REF_LINK.sub(r"\1", t)
    t = _AUTOLINK.sub(r"\1", t)
    t = _TAG.sub("", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(t.split())


def parse_markdown(md: str, *, url: str | None = None) -> list[Block]:
    md = _COMMENT.sub("", md.replace("\r\n", "\n").replace("\t", "    "))
    lines = md.split("\n")
    blocks: list[Block] = []
    para: list[str] = []
    item_numbers: dict[int, int] = {}
    in_list = False

    def flush() -> None:
        nonlocal para
        t = inline(" ".join(para))
        para = []
        if t:
            blocks.append(Block("text", t, url=url))

    i = 0
    while i < len(lines):
        line = lines[i]
        fm = _FENCE.match(line)
        if fm:
            flush()
            indent, fence, info = len(fm.group(1)), fm.group(2), fm.group(3) or ""
            body: list[str] = []
            i += 1
            while i < len(lines):
                l = lines[i]
                if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", l):
                    break
                body.append(l[indent:] if l[:indent].strip() == "" else l)
                i += 1
            i += 1
            code = "\n".join(body).strip("\n")
            if code.strip():
                blocks.append(Block("code", code, lang=norm_lang(info.split(",")[0]), url=url))
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        if _REF_DEF.match(line) or _TABLE_SEP.match(line) and "|" in line or _HR.match(line) and not para:
            flush()
            i += 1
            continue
        hm = _ATX.match(line)
        if hm:
            flush()
            in_list = False
            t = inline(hm.group(2))
            if t:
                blocks.append(Block("heading", t, level=len(hm.group(1)), anchor=slug(t), url=url))
            i += 1
            continue
        if para and _SETEXT.match(line) and not in_list:
            t = inline(" ".join(para))
            para = []
            if t:
                blocks.append(Block("heading", t, level=1 if line.strip()[0] == "=" else 2, anchor=slug(t), url=url))
            i += 1
            continue
        im = _ITEM.match(line)
        if im:
            flush()
            in_list = True
            depth = len(im.group(1)) // 2
            depth = min(depth, 6)
            ordered = im.group(3) is not None
            for d in [d for d in item_numbers if d > depth]:
                del item_numbers[d]
            num = int(im.group(3)) if ordered else 0
            item_numbers[depth] = num
            text = [im.group(4)]
            i += 1
            while i < len(lines) and lines[i].strip() and not _ITEM.match(lines[i]) and not _FENCE.match(lines[i]) \
                    and not _ATX.match(lines[i]):
                text.append(lines[i].strip())
                i += 1
            t = inline(" ".join(text))
            if t:
                blocks.append(Block("item", t, level=depth, ordered=ordered, number=num, url=url))
            continue
        if line.startswith("    ") and not para and not in_list:
            flush()
            body = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                body.append(lines[i][4:])
                i += 1
            code = "\n".join(body).strip("\n")
            if code.strip():
                blocks.append(Block("code", code, url=url))
            continue
        if not line.startswith(" ") and in_list and not para:
            in_list = False
        stripped = re.sub(r"^\s{0,3}>\s?", "", line)
        if "|" in stripped and stripped.strip().startswith("|"):
            flush()
            cells = [inline(c) for c in stripped.strip().strip("|").split("|")]
            t = " | ".join(c for c in cells if c)
            if t:
                blocks.append(Block("text", t, url=url))
            i += 1
            continue
        para.append(stripped)
        i += 1
    flush()
    return blocks


# ------------------------------------------------------------------------------------------------ reStructuredText

_RST_UNDER = re.compile(r"^([=\-~^\"'`#*+<>:.])\1{2,}\s*$")
_RST_CODE = re.compile(r"^\.\.\s+(?:code-block|code|sourcecode|highlight)::\s*(\S*)\s*$")
_RST_DIRECTIVE = re.compile(r"^\.\.\s+[\w:-]+::")
_RST_ROLE = re.compile(r":[\w:-]+:`([^`<]*?)(?:\s*<[^>]*>)?`")


def _rst_inline(t: str) -> str:
    t = _RST_ROLE.sub(r"\1", t)
    t = re.sub(r"`([^`<]+?)\s*<[^>]+>`_{1,2}", r"\1", t)
    t = re.sub(r"``([^`]+)``", r"`\1`", t)
    t = re.sub(r"\|[^|\s][^|]*\|", "", t)  # substitutions (badges)
    return " ".join(t.split())


def parse_rst(text: str, *, url: str | None = None) -> list[Block]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    para: list[str] = []
    levels: list[str] = []

    def flush() -> None:
        nonlocal para
        t = _rst_inline(" ".join(para))
        para = []
        if t:
            blocks.append(Block("text", t, url=url))

    def literal(start: int, lang: str | None) -> int:
        j = start
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or not lines[j].startswith((" ", "\t")):
            return start
        ind = len(lines[j]) - len(lines[j].lstrip())
        body: list[str] = []
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) >= ind):
            if lines[j].strip().startswith(":") and not body:  # directive options (:linenos:)
                j += 1
                continue
            body.append(lines[j][ind:])
            j += 1
        code = "\n".join(body).strip("\n")
        if code.strip():
            blocks.append(Block("code", code, lang=lang, url=url))
        return j

    i = 0
    while i < len(lines):
        line = lines[i]
        cm = _RST_CODE.match(line)
        if cm:
            flush()
            i = literal(i + 1, norm_lang(cm.group(1)))
            continue
        if _RST_DIRECTIVE.match(line) or line.startswith((".. |", ".. _")):
            flush()
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                i += 1
            continue
        if i + 1 < len(lines) and line.strip() and _RST_UNDER.match(lines[i + 1]) and \
                len(lines[i + 1].strip()) >= len(line.strip()) - 1 and not para:
            if _RST_UNDER.match(line):  # an overline: the title is the next line
                i += 1
                continue
            ch = lines[i + 1].strip()[0]
            if ch not in levels:
                levels.append(ch)
            t = _rst_inline(line)
            blocks.append(Block("heading", t, level=min(6, levels.index(ch) + 1), anchor=slug(t), url=url))
            i += 2
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        if _RST_UNDER.match(line):
            i += 1
            continue
        im = _ITEM.match(line)
        if im and not para:
            ordered = im.group(3) is not None
            blocks.append(Block("item", _rst_inline(im.group(4)), level=len(im.group(1)) // 2, ordered=ordered,
                                number=int(im.group(3)) if ordered else 0, url=url))
            i += 1
            continue
        if line.rstrip().endswith("::"):
            para.append(line.rstrip()[:-1] if not line.rstrip().endswith(" ::") else line.rstrip()[:-3])
            flush()
            i = literal(i + 1, None)
            continue
        para.append(line.strip())
        i += 1
    flush()
    return blocks


def parse_plain(text: str, *, url: str | None = None) -> list[Block]:
    """Plain text: paragraphs split on blank lines; an indented paragraph is a code block."""
    out: list[Block] = []
    for chunk in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        if all(l.startswith(("    ", "\t")) for l in lines if l.strip()):
            out.append(Block("code", "\n".join(l[4:] if l.startswith("    ") else l.lstrip("\t") for l in lines).strip("\n"),
                             url=url))
        else:
            out.append(Block("text", " ".join(chunk.split()), url=url))
    return out
