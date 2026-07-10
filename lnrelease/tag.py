import csv
import re
import warnings
from collections import defaultdict
from pathlib import Path

from scrape import INFO, SERIES
from utils import CATEGORIES, ORIGINS, Info, Series, Table

# manual overrides: key,origin,category (either may be blank); wins over heuristics
OVERRIDES = Path('origins.csv')

# publishers whose entire manga catalogue is licensed from Japan
JP_PUBLISHERS = {
    'Denpa',
    'J-Novel Club',
    'Kodansha',
    'One Peace Books',
    'Square Enix',
    'Udon Entertainment',
    'VIZ Media',
}
# publisher-level origin/category signals
PUB_TAGS = {
    'Ize Press': ('KR', 'manhwa'),
    'WEBTOON Unscrolled': ('other', 'webtoon'),
}
ARTBOOK = re.compile(r'\bart ?(?:book|works)\b|\bthe art of\b|\billustrations?\b|\bsketchbook\b',
                     flags=re.IGNORECASE)


def load_overrides() -> dict[str, tuple[str, str]]:
    overrides = {}
    if OVERRIDES.is_file():
        with open(OVERRIDES, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                key, origin, category = row
                if origin and origin not in ORIGINS:
                    warnings.warn(f'Unknown origin override: {row}', RuntimeWarning)
                elif category and category not in CATEGORIES:
                    warnings.warn(f'Unknown category override: {row}', RuntimeWarning)
                else:
                    overrides[key] = (origin, category)
    return overrides


def tag(series: Table, info: Table, overrides: dict[str, tuple[str, str]]) -> None:
    publishers: defaultdict[str, set[str]] = defaultdict(set)
    for i in info:
        publishers[i.serieskey].add(i.publisher)

    flagged = 0
    for s in series:
        for publisher in publishers.get(s.key, ()):
            if signal := PUB_TAGS.get(publisher):
                s.origin = s.origin or signal[0]
                s.category = s.category or signal[1]

        # default: JP manga is the overwhelming base rate; flag guesses for review
        flag = ''
        if not s.origin:
            s.origin = 'JP'
            pubs = publishers.get(s.key, set())
            if not (pubs and pubs <= JP_PUBLISHERS):
                flag = 'review'
        if not s.category:
            s.category = 'artbook' if ARTBOOK.search(s.title) else 'manga'
        s.flag = flag

        if override := overrides.get(s.key):
            origin, category = override
            s.origin = origin or s.origin
            s.category = category or s.category
            s.flag = ''
        flagged += bool(s.flag)

    print(f'tag: {len(series)} series tagged, {flagged} flagged for review, '
          f'{len(overrides)} overrides', flush=True)


def main() -> None:
    series = Table(SERIES, Series)
    info = Table(INFO, Info)
    tag(series, info, load_overrides())
    series.save()


if __name__ == '__main__':
    main()
