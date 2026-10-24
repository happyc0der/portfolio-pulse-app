import re
from typing import Any

LINE_PREFIX = re.compile(r"^(?:\s*(?:[-•*]|\d+\.)\s+)?(?:\*\*[^*]+\*\*:?\s*)?")
HEADING_LINE = re.compile(r"^\s*(?:#{1,6}\s+\S.*|(?:[-•*]\s+)?\*\*[^*]+\*\*:?|[A-Z][A-Za-z ,'&/-]{0,60}:)\s*$")
CITATION = re.compile(r"\[(\d+)\]")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?!\[)|(?<=\])\s+(?=[A-Z])")
# A full stop after these is an abbreviation or an initial ("J. Smith"), not the end of a sentence.
# "Series B." and "Class A." still end one, since rounds are named that way far more often than people.
ABBREVIATION_END = re.compile(r"(?:^|[\s(])(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|Inc|Corp|Co|Ltd|LLC|Mrs?|Ms|Dr|St|[Vv]s|[Aa]pprox|[Ee]st|e\.g|i\.e|U\.S|U\.K|(?<!Series )(?<!Class )[A-Z])\.$")
NUMBER_ABBREVIATION = re.compile(r"(?:^|[\s(])No\.$")
GREETING = re.compile(r"^(?:hi|hello|hey|dear)\b", re.IGNORECASE)
CLOSING = re.compile(r"^(?:(?:best|regards|warmly|thanks|sincerely|cheers)\b|[^.?!]*,$)", re.IGNORECASE)
FIGURE = re.compile(r"[\d$€£¥%]")
QUANTITY_WORD = re.compile(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|(?:twen|thir|for|fif|six|seven|eigh|nine)ty|hundreds?|thousands?|millions?|billions?|trillions?|dozens?|half|halved|twice|percent|(?:doubl|tripl|quadrupl)(?:e|ed|es|ing))\b", re.IGNORECASE)
OFFER = re.compile(r"^[*_\"“]*(?:I['’]d|I would|I['’]m happy|Happy to|Glad to|Let me know|Would you|Could we|Can we|If helpful|If it helps|We['’]d love|We would love|Feel free|Looking forward|Congrats|Congratulations)\b", re.IGNORECASE)
WORD = re.compile(r"[A-Za-z][A-Za-z-]*")
# Title case capitalises these in source titles; they open ordinary sentences and are never names on their own.
COMMON_WORDS = {"A", "An", "And", "Are", "As", "At", "But", "By", "For", "From", "How", "If", "In", "Is", "It", "Its", "Of", "On", "Or",
                "Our", "So", "That", "The", "There", "These", "They", "This", "To", "We", "What", "When", "Why", "With", "You", "Your"}


def split_sentences(body: str) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in SENTENCE_BREAK.finditer(body):
        before = body[start:match.start()]
        if ABBREVIATION_END.search(before) or (NUMBER_ABBREVIATION.search(before) and body[match.end():match.end() + 1].isdigit()):
            continue
        pieces.append(before)
        start = match.end()
    pieces.append(body[start:])
    return [piece.strip() for piece in pieces if piece.strip()]


def mid_sentence_capitals(sentence: str) -> set[str]:
    return {word for word in WORD.findall(sentence)[1:] if word[0].isupper() and word != "I"}


def known_names(lines: list[str], sources: list[dict[str, Any]]) -> set[str]:
    # A name can open a sentence ("Arm held early talks"), where it looks like any first word, so collect
    # the names the draft and its sources use elsewhere: mid-sentence, in bold labels, in company fields.
    prefixes = [LINE_PREFIX.match(line).group(0) for line in lines]
    texts = [line[len(prefix):] for line, prefix in zip(lines, prefixes)]
    texts += [str(source.get(field) or "") for source in sources for field in ("title", "ai_summary")]
    names = {word for text in texts for sentence in split_sentences(text) for word in mid_sentence_capitals(sentence)}
    names |= {word for text in prefixes + [str(source.get(field) or "") for source in sources for field in ("company", "publisher")]
              for word in WORD.findall(text) if word[0].isupper()}
    return names - COMMON_WORDS - {"I"}


def needs_no_citation(sentence: str, names: set[str]) -> bool:
    # A figure is a checkable claim even inside a question or an offer ("your team of 99").
    if FIGURE.search(sentence):
        return False
    if sentence.rstrip("*_)\"'”’ ").endswith("?") or OFFER.match(sentence):
        return True
    # Without a quantity or a name, a statement asserts nothing checkable.
    words = WORD.findall(sentence)
    return not QUANTITY_WORD.search(sentence) and not mid_sentence_capitals(sentence) and not (words and words[0] in names)


def signoff_start(lines: list[str]) -> int | None:
    # The closing ("Best,", "Talk soon,") plus the name, title and firm lines under it, within the last three lines.
    for index in range(max(1, len(lines) - 3), len(lines)):
        closing = lines[index]
        if CLOSING.match(closing) and len(closing) <= 40 and not FIGURE.search(closing) and all(
                len(line) <= 60 and not CITATION.search(line) and not re.search(r"\d|[.?!]$", line) for line in lines[index + 1:]):
            return index
    return None


def label_rank(raw_line: str) -> int:
    # "#" headings outrank bold or "Label:" lines, which outrank bulleted labels; deeper indents rank lower.
    stripped = raw_line.lstrip()
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes:
        return hashes
    return 8 + len(raw_line) - len(stripped) if re.match(r"[-•*]\s", stripped) else 7


def has_body(entries: list[tuple[str, int | None]], index: int) -> bool:
    rank = entries[index][1]
    for _, other in entries[index + 1:]:
        if other is None:
            return True
        if other <= rank:
            return False
    return False


def citation_checked_text(text: str, sources: list[dict[str, Any]], kind: str) -> tuple[str, int, list[int]]:
    valid_numbers = {str(source["number"]) for source in sources}
    # Keep line boundaries so a greeting and a multi-line sign-off are identifiable.
    raw_lines = [line for line in text.strip().splitlines() if line.strip()]
    lines = [line.strip() for line in raw_lines]
    exempt: set[int] = set()
    if kind == "founder_email" and lines:
        if GREETING.match(lines[0]):
            exempt.add(0)
        signoff = signoff_start(lines)
        if signoff is not None:
            exempt.update(range(signoff, len(lines)))

    names = known_names(lines, sources)
    # Each entry is (line, rank): rank None for content, else the line is only a heading or label.
    entries: list[tuple[str, int | None]] = []
    dropped = 0
    cited: set[int] = set()
    # Work line by line so Markdown structure survives the check: a bullet ("- ") and a bold
    # label ("**What happened:**") stay attached to the sentences after them.
    for index, line in enumerate(lines):
        if index in exempt:
            entries.append((line, None))
            continue
        if HEADING_LINE.match(line) and not CITATION.search(line):
            entries.append((line, label_rank(raw_lines[index])))
            continue
        prefix = LINE_PREFIX.match(line).group(0)
        good: list[str] = []
        for sentence in split_sentences(line[len(prefix):]):
            citations = CITATION.findall(sentence)
            if any(number not in valid_numbers for number in citations) or not (citations or needs_no_citation(sentence, names)):
                dropped += 1
                continue
            cited.update(int(number) for number in citations)
            good.append(sentence)
        if good and prefix.strip():
            entries.append((prefix + " ".join(good), None))
        else:
            entries.extend((sentence, None) for sentence in good)
    # A label whose content was all dropped would dangle ("**What happened:**" and nothing under it);
    # "#" headings stay, since they frame the document even when a section is empty.
    kept = [line for index, (line, rank) in enumerate(entries) if rank is None or rank <= 6 or has_body(entries, index)]
    return "\n".join(kept), dropped, sorted(cited)
