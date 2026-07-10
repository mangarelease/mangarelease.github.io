import importlib
import os
import sys
import warnings
from collections import defaultdict
from concurrent.futures import Future, as_completed
from faulthandler import dump_traceback
from pathlib import Path
from threading import Thread
from time import time

from session import CF_ACCOUNT, REQUEST_STATS
from utils import SOURCES, Info, Series, Table

MODULES = {s.stem: importlib.import_module(f'source.{s.stem}') for s in Path('lnrelease/source').glob('*.py')}

SERIES = Path('series.csv')
INFO = Path('info.csv')

# first full runs need far longer than the incremental daily refresh;
# CI can set SCRAPE_TIMEOUT to stay within the actions job limit
TIMEOUT = int(os.environ.get('SCRAPE_TIMEOUT', 60 * 60 * 12))


def merge_series(table: Table, new: set[Series]) -> None:
    # set union keeps the existing element, which would drop
    # origin/category tags picked up by this scrape
    existing = {s.key: s for s in table}
    for s in new:
        if old := existing.get(s.key):
            old.origin = old.origin or s.origin
            old.category = old.category or s.category
        else:
            table.add(s)


def worker(future: Future, fn, *args) -> None:
    try:
        result = fn(*args)
    except BaseException as exc:
        future.set_exception(exc)
    else:
        future.set_result(result)


def main(only: set[str] | None = None) -> None:
    if not CF_ACCOUNT and os.environ.get('GITHUB_EVENT_NAME') == 'schedule':
        return

    if unknown := (only or set()) - set(MODULES):
        warnings.warn(f'Unknown sources: {sorted(unknown)}; '
                      f'available: {sorted(MODULES)}', RuntimeWarning)
    modules = [m for stem, m in MODULES.items() if not only or stem in only]

    series = Table(SERIES, Series)
    info = Table(INFO, Info)
    sources: defaultdict[str, set[Info]] = defaultdict(set)
    for inf in info:
        sources[inf.source].add(inf)

    start = time()
    futures: dict[Future[tuple[set[Series], set[Info]]], str] = {}
    for module in modules:
        future = Future()
        name: str = module.NAME
        futures[future] = name
        Thread(target=worker,
               name=f'Thread-{name.replace(" ", "-")}',
               args=(future,
                     module.scrape_full,
                     series.copy(),
                     sources[name].copy()),
               daemon=True,
               ).start()

    try:
        for future in as_completed(futures, timeout=TIMEOUT):
            try:
                serie, inf = future.result()
                merge_series(series, serie)
                series.save()
                info -= sources[futures[future]]
                info |= inf
                info.save()
                sources[futures[future]] = inf
            except Exception as e:
                warnings.warn(f'Error scraping {futures[future]}: {e}', RuntimeWarning)
            else:
                print(f'{futures[future]} done ({time() - start:.2f}s): '
                      f'{len(serie)} series, {len(inf)} info rows', flush=True)
    except TimeoutError:
        dump_traceback()

    print('\nStats:')
    for netloc, stats in REQUEST_STATS.items():
        print(f'{netloc:>50s}: {stats}')

    series -= series - {Series(i.serieskey, '') for i in info}
    series.save()
    info.clear()
    for _, inf in sorted(sources.items(), key=lambda x: SOURCES[x[0]]):
        info.update(inf - info)
    info.save()


if __name__ == '__main__':
    main(set(sys.argv[1:]) or None)
