import importlib
import warnings
from collections import defaultdict
from itertools import groupby
from operator import attrgetter
from pathlib import Path

import publisher
from scrape import INFO, SERIES
from utils import FORMATS, PRIMARY, SECONDARY, SOURCES, Book, Info, Series, Table

PUBLISHERS = {}
for file in Path('lnrelease/publisher').glob('*.py'):
    module = importlib.import_module(f'publisher.{file.stem}')
    PUBLISHERS[module.NAME] = module

BOOKS = Path('books.csv')
ARTBOOKS = Path('artbooks.csv')


def main() -> None:
    series = {row.key: row for row in Table(SERIES, Series)}
    info = Table(INFO, Info)
    links: defaultdict[str, list[Info]] = defaultdict(list)
    lst: list[Info] = []
    for i in info:
        links[i.link].append(i)
        if i.source not in SECONDARY or i.publisher not in PRIMARY:
            lst.append(i)
    lst.sort()
    # sort by source then title
    links = dict(sorted(links.items(), key=lambda x: (SOURCES[x[1][0].source], x[1][0].title)))
    BOOKS.unlink(missing_ok=True)
    ARTBOOKS.unlink(missing_ok=True)
    books = Table(BOOKS, Book)

    for key, group in groupby(lst, attrgetter('serieskey', 'publisher')):
        serieskey = key[0]
        serie = series[serieskey]
        pub = key[1]
        if pub in PUBLISHERS:
            module = PUBLISHERS[pub]
        else:
            module = publisher
            warnings.warn(f'Unknown publisher: {pub}; {serieskey}', RuntimeWarning)
        inf: defaultdict[str, list[Info]] = defaultdict(list)
        for i in group:
            inf[i.format].append(i)
        inf = dict(sorted(inf.items(), key=lambda x: FORMATS.get(x[0], 0)))
        for x in module.parse(serie, inf, links).values():
            books.update(x)

    for book in books:
        if serie := series.get(book.serieskey):
            # unresolved series default to the JP manga base rate
            book.origin = serie.origin or 'JP'
            book.category = serie.category or 'manga'

    # art books go to their own file, same schema; the main dataset and the
    # release calendar (built downstream from books.csv) stay manga/comics only
    artbooks = Table(ARTBOOKS, Book)
    for book in list(books):
        if book.category == 'artbook':
            books.discard(book)
            artbooks.add(book)
    books.save()
    artbooks.save()


if __name__ == '__main__':
    main()
