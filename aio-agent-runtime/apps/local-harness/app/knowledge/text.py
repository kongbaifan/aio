"""Bounded deterministic keyword terms. Original citation text is never NFKC-rewritten."""

import re
import unicodedata


def terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    values = set()
    for word in re.findall(r"[a-z0-9_]{2,64}|[\u3400-\u9fff]{1,256}", normalized):
        if "\u3400" <= word[0] <= "\u9fff":
            values.update(word)
            values.update(word[i : i + 2] for i in range(len(word) - 1))
        else:
            values.add(word)
        if len(values) >= 512:
            break
    return sorted(values)[:512]
