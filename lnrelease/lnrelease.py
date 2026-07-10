import parse
import scrape
import tag
import write


def main() -> None:
    scrape.main()
    tag.main()
    parse.main()
    write.main()


if __name__ == '__main__':
    main()
