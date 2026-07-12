import sys

import pages
import parse
import scrape
import tag
import write


def main(only: set[str] | None = None) -> None:
    scrape.main(only)
    tag.main()
    parse.main()
    write.main()
    pages.main()


if __name__ == '__main__':
    main(set(sys.argv[1:]) or None)
