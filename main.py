from scraper import COURSES_URL, LOGIN_URL, CourseScraper
from sys import argv


def main() -> None:
    if not (
        (len(argv) == 2 and argv[1] == "--all-courses")
        or (len(argv) == 3 and argv[1] == "--course")
    ):
        print(
            """-> Please use one of the following commands:\n>>> main.py --all-courses\n>>> main.py --course [course link]"""
        )
        return

    scraper = CourseScraper()
    scraper.login(LOGIN_URL)

    try:
        if argv[1] == "--all-courses":
            scraper.download_all_courses(COURSES_URL)
        else:
            scraper.download_course(argv[2])
    finally:
        scraper.go_to_courses_page(COURSES_URL)


if __name__ == "__main__":
    main()
