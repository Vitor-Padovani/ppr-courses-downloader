"""
Course Database Manager
A CLI application to manage and search educational course materials
including text transcripts and audio files.
"""

import sqlite3
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional
import argparse


class CourseDatabase:
    """Manages the SQLite database for course materials."""

    def __init__(self, db_path: str = "courses.db") -> None:
        """Initialize database connection and create tables if needed."""
        self.db_path: str = db_path
        self.conn: sqlite3.Connection = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database schema."""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                total_lessons INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                lesson_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                transcript_path TEXT,
                audio_path TEXT,
                transcript_content TEXT,
                word_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id),
                UNIQUE(course_id, lesson_number)
            );

            CREATE INDEX IF NOT EXISTS idx_course_slug ON courses(slug);
            CREATE INDEX IF NOT EXISTS idx_lesson_course ON lessons(course_id);
            CREATE INDEX IF NOT EXISTS idx_lesson_title ON lessons(title);

            CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(
                title, transcript_content, content='lessons', content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS lessons_ai AFTER INSERT ON lessons BEGIN
                INSERT INTO lessons_fts(rowid, title, transcript_content)
                VALUES (new.id, new.title, new.transcript_content);
            END;

            CREATE TRIGGER IF NOT EXISTS lessons_ad AFTER DELETE ON lessons BEGIN
                DELETE FROM lessons_fts WHERE rowid = old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS lessons_au AFTER UPDATE ON lessons BEGIN
                UPDATE lessons_fts SET title = new.title, transcript_content = new.transcript_content
                WHERE rowid = new.id;
            END;
        """)
        self.conn.commit()

    def _last_row_id(self) -> int:
        """Return the last inserted row id (sqlite3 types it as int | None)."""
        row_id = self.cursor.lastrowid
        if row_id is None:
            raise RuntimeError("INSERT did not produce a row id")
        return row_id

    def add_course(self, name: str, slug: str) -> int:
        """Add a new course to the database."""
        try:
            self.cursor.execute(
                "INSERT INTO courses (name, slug) VALUES (?, ?)", (name, slug)
            )
            self.conn.commit()
            return self._last_row_id()
        except sqlite3.IntegrityError:
            # Course already exists, return existing ID
            self.cursor.execute("SELECT id FROM courses WHERE slug = ?", (slug,))
            return self.cursor.fetchone()[0]

    def add_lesson(
        self,
        course_id: int,
        lesson_number: int,
        title: str,
        transcript_path: Optional[str],
        audio_path: Optional[str],
        transcript_content: Optional[str],
    ) -> int:
        """Add a lesson to the database."""
        word_count = len(transcript_content.split()) if transcript_content else 0

        try:
            self.cursor.execute(
                """
                INSERT INTO lessons
                (course_id, lesson_number, title, transcript_path, audio_path,
                 transcript_content, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    course_id,
                    lesson_number,
                    title,
                    transcript_path,
                    audio_path,
                    transcript_content,
                    word_count,
                ),
            )
            self.conn.commit()

            # Update course lesson count
            self.cursor.execute(
                """
                UPDATE courses SET total_lessons = (
                    SELECT COUNT(*) FROM lessons WHERE course_id = ?
                ) WHERE id = ?
            """,
                (course_id, course_id),
            )
            self.conn.commit()

            return self._last_row_id()
        except sqlite3.IntegrityError:
            print(f"Lesson {lesson_number} already exists for course {course_id}")
            return -1

    def search_courses(self, keyword: Optional[str] = None) -> List[sqlite3.Row]:
        """Search courses by keyword."""
        if keyword:
            self.cursor.execute(
                """
                SELECT * FROM courses
                WHERE name LIKE ? OR slug LIKE ?
                ORDER BY name
            """,
                (f"%{keyword}%", f"%{keyword}%"),
            )
        else:
            self.cursor.execute("SELECT * FROM courses ORDER BY name")
        return self.cursor.fetchall()

    def search_lessons(
        self, keyword: str, course_id: Optional[int] = None
    ) -> List[sqlite3.Row]:
        """Full-text search in lesson titles and transcripts."""
        if course_id:
            self.cursor.execute(
                """
                SELECT l.*, c.name as course_name, c.slug as course_slug,
                       (LENGTH(l.transcript_content) - LENGTH(REPLACE(LOWER(l.transcript_content), LOWER(?), ''))) / LENGTH(?) as match_count
                FROM lessons_fts
                JOIN lessons l ON lessons_fts.rowid = l.id
                JOIN courses c ON l.course_id = c.id
                WHERE lessons_fts MATCH ? AND l.course_id = ?
                ORDER BY match_count DESC, rank
            """,
                (keyword, keyword, keyword, course_id),
            )
        else:
            self.cursor.execute(
                """
                SELECT l.*, c.name as course_name, c.slug as course_slug,
                       (LENGTH(l.transcript_content) - LENGTH(REPLACE(LOWER(l.transcript_content), LOWER(?), ''))) / LENGTH(?) as match_count
                FROM lessons_fts
                JOIN lessons l ON lessons_fts.rowid = l.id
                JOIN courses c ON l.course_id = c.id
                WHERE lessons_fts MATCH ?
                ORDER BY match_count DESC, rank
            """,
                (keyword, keyword, keyword),
            )
        return self.cursor.fetchall()

    def search_courses_by_keyword(self, keyword: str) -> List[sqlite3.Row]:
        """Search and rank courses by keyword frequency in their lessons."""
        self.cursor.execute(
            """
            SELECT c.*,
                   COUNT(DISTINCT l.id) as matching_lessons,
                   SUM((LENGTH(l.transcript_content) - LENGTH(REPLACE(LOWER(l.transcript_content), LOWER(?), ''))) / LENGTH(?)) as total_matches
            FROM courses c
            JOIN lessons l ON c.id = l.course_id
            JOIN lessons_fts ON l.id = lessons_fts.rowid
            WHERE lessons_fts MATCH ?
            GROUP BY c.id
            ORDER BY total_matches DESC, matching_lessons DESC
        """,
            (keyword, keyword, keyword),
        )
        return self.cursor.fetchall()

    def get_course_lessons(self, course_id: int) -> List[sqlite3.Row]:
        """Get all lessons for a specific course."""
        self.cursor.execute(
            """
            SELECT * FROM lessons
            WHERE course_id = ?
            ORDER BY lesson_number
        """,
            (course_id,),
        )
        return self.cursor.fetchall()

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        self.cursor.execute("SELECT COUNT(*) as total FROM courses")
        total_courses = self.cursor.fetchone()["total"]

        self.cursor.execute("SELECT COUNT(*) as total FROM lessons")
        total_lessons = self.cursor.fetchone()["total"]

        self.cursor.execute("SELECT SUM(word_count) as total FROM lessons")
        total_words = self.cursor.fetchone()["total"] or 0

        self.cursor.execute("""
            SELECT c.name, COUNT(l.id) as lesson_count
            FROM courses c
            LEFT JOIN lessons l ON c.id = l.course_id
            GROUP BY c.id
            ORDER BY lesson_count DESC
            LIMIT 5
        """)
        top_courses = self.cursor.fetchall()

        return {
            "total_courses": total_courses,
            "total_lessons": total_lessons,
            "total_words": total_words,
            "top_courses": top_courses,
        }

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


class CourseImporter:
    """Handles importing course files into the database."""

    def __init__(self, db: CourseDatabase) -> None:
        self.db: CourseDatabase = db

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to slug format."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", "-", text)
        return text

    @staticmethod
    def _parse_filename(filename: str) -> Tuple[Optional[int], str]:
        """Extract lesson number and title from filename."""
        # Remove extension
        name = os.path.splitext(filename)[0]

        # Try to extract lesson number (e.g., "01.Title" or "01-Title")
        match = re.match(r"^(\d+)[.\-_](.+)$", name)
        if match:
            lesson_num = int(match.group(1))
            title = match.group(2).replace("_", " ").strip()
            return lesson_num, title

        return None, name.replace("_", " ").strip()

    def import_directory(self, root_path: str, verbose: bool = True) -> None:
        """Import all courses from a root directory."""
        root = Path(root_path)

        if not root.exists():
            print(f"Directory not found: {root_path}")
            return

        # Find all course directories
        course_dirs = [d for d in root.iterdir() if d.is_dir()]

        print(f"Found {len(course_dirs)} course directories")
        print("=" * 60)

        for course_dir in sorted(course_dirs):
            self._import_course(course_dir, verbose)

        print("\nImport completed!")

    def _import_course(self, course_path: Path, verbose: bool) -> None:
        """Import a single course directory."""
        course_name = course_path.name.replace("-", " ").replace("_", " ").title()
        course_slug = self._slugify(course_path.name)

        if verbose:
            print(f"\nImporting: {course_name}")

        course_id = self.db.add_course(course_name, course_slug)

        # Find all text and audio files
        txt_files = list(course_path.glob("*.txt"))
        mp3_files = list(course_path.glob("*.mp3"))

        # Create a mapping of lesson numbers to files
        lessons_map: Dict[Optional[int], Dict[str, Any]] = {}

        # Process text files
        for txt_file in txt_files:
            lesson_num, title = self._parse_filename(txt_file.name)
            if lesson_num not in lessons_map:
                lessons_map[lesson_num] = {"title": title}
            lessons_map[lesson_num]["txt"] = txt_file

        # Process audio files
        for mp3_file in mp3_files:
            lesson_num, _ = self._parse_filename(mp3_file.name)
            if lesson_num not in lessons_map:
                lessons_map[lesson_num] = {"title": ""}
            lessons_map[lesson_num]["mp3"] = mp3_file

        # Import lessons
        imported_count = 0
        for lesson_num in sorted(
            lessons_map.keys(), key=lambda x: x if x is not None else -1
        ):
            lesson_data = lessons_map[lesson_num]

            # Read transcript content if available
            transcript_content: Optional[str] = None
            if "txt" in lesson_data:
                try:
                    with open(lesson_data["txt"], "r") as f:
                        transcript_content = f.read()
                except Exception as e:
                    print(f"  Error reading {lesson_data['txt'].name}: {e}")

            txt_path = str(lesson_data.get("txt", ""))
            mp3_path = str(lesson_data.get("mp3", ""))

            lesson_id = self.db.add_lesson(
                course_id=course_id,
                lesson_number=lesson_num if lesson_num is not None else 0,
                title=lesson_data.get("title", "Untitled"),
                transcript_path=txt_path if txt_path else None,
                audio_path=mp3_path if mp3_path else None,
                transcript_content=transcript_content,
            )

            if lesson_id > 0:
                imported_count += 1

        if verbose:
            print(f"  ✓ Imported {imported_count} lessons")


def display_courses(courses: List[sqlite3.Row], show_matches: bool = False) -> None:
    """Display course list."""
    if not courses:
        print("No courses found.")
        return

    if show_matches:
        print("\n" + "=" * 100)
        print(
            f"{'ID':<5} {'Course Name':<45} {'Lessons':<10} {'Matches':<12} {'Occurrences':<12}"
        )
        print("=" * 100)

        for course in courses:
            matches = (
                course["matching_lessons"] if "matching_lessons" in course.keys() else 0
            )
            total = (
                int(course["total_matches"]) if "total_matches" in course.keys() else 0
            )
            print(
                f"{course['id']:<5} {course['name']:<45} {course['total_lessons']:<10} "
                f"{matches:<12} {total:<12}"
            )
    else:
        print("\n" + "=" * 80)
        print(f"{'ID':<5} {'Course Name':<40} {'Lessons':<10} {'Slug':<25}")
        print("=" * 80)

        for course in courses:
            print(
                f"{course['id']:<5} {course['name']:<40} {course['total_lessons']:<10} {course['slug']:<25}"
            )

    print("=" * (100 if show_matches else 80))


def display_lessons(
    lessons: List[sqlite3.Row], show_course: bool = True, show_matches: bool = False
) -> None:
    """Display lesson list."""
    if not lessons:
        print("No lessons found.")
        return

    if show_course:
        if show_matches:
            print("\n" + "=" * 110)
            print(
                f"{'#':<4} {'Course':<30} {'Lesson Title':<50} {'Words':<10} {'Matches':<8}"
            )
            print("=" * 110)

            for lesson in lessons:
                course_name = (
                    lesson["course_name"] if "course_name" in lesson.keys() else "N/A"
                )
                matches = (
                    int(lesson["match_count"]) if "match_count" in lesson.keys() else 0
                )
                print(
                    f"{lesson['lesson_number']:<4} {course_name[:29]:<30} "
                    f"{lesson['title'][:49]:<50} {lesson['word_count']:<10} {matches:<8}"
                )
        else:
            print("\n" + "=" * 100)
            print(f"{'#':<4} {'Course':<30} {'Lesson Title':<50} {'Words':<10}")
            print("=" * 100)

            for lesson in lessons:
                course_name = (
                    lesson["course_name"] if "course_name" in lesson.keys() else "N/A"
                )
                print(
                    f"{lesson['lesson_number']:<4} {course_name[:29]:<30} "
                    f"{lesson['title'][:49]:<50} {lesson['word_count']:<10}"
                )

        print("=" * (110 if show_matches else 100))
    else:
        # Without course column
        print("\n" + "=" * 80)
        print(f"{'#':<4} {'Lesson Title':<60} {'Words':<10}")
        print("=" * 80)

        for lesson in lessons:
            print(
                f"{lesson['lesson_number']:<4} {lesson['title'][:59]:<60} {lesson['word_count']:<10}"
            )

        print("=" * 80)


def display_statistics(stats: Dict[str, Any]) -> None:
    """Display database statistics."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)
    print(f"Total Courses:  {stats['total_courses']}")
    print(f"Total Lessons:  {stats['total_lessons']}")
    print(f"Total Words:    {stats['total_words']:,}")

    if stats["top_courses"]:
        print("\nTop 5 Courses by Lesson Count:")
        for i, course in enumerate(stats["top_courses"], 1):
            print(f"  {i}. {course['name']}: {course['lesson_count']} lessons")

    print("=" * 60)


def main() -> None:
    """Main CLI application."""
    parser = argparse.ArgumentParser(
        description="Course Database Manager - Manage and search educational materials"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Import command
    import_parser = subparsers.add_parser(
        "import", help="Import courses from directory"
    )
    import_parser.add_argument("path", help="Root directory containing course folders")
    import_parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")

    # List courses command
    list_parser = subparsers.add_parser("list", help="List all courses")
    list_parser.add_argument("-s", "--search", help="Search courses by keyword")

    # Show course command
    show_parser = subparsers.add_parser("show", help="Show lessons in a course")
    show_parser.add_argument("course_id", type=int, help="Course ID")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search lesson content")
    search_parser.add_argument("keyword", help="Search keyword")
    search_parser.add_argument(
        "-c", "--course", type=int, help="Limit to specific course ID"
    )
    search_parser.add_argument(
        "--courses",
        action="store_true",
        help="Show courses ranked by keyword frequency",
    )

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()

    # Initialize database
    db = CourseDatabase()

    try:
        if args.command == "import":
            importer = CourseImporter(db)
            importer.import_directory(args.path, verbose=not args.quiet)

        elif args.command == "list":
            courses = db.search_courses(args.search)
            display_courses(courses)

        elif args.command == "show":
            lessons = db.get_course_lessons(args.course_id)
            display_lessons(lessons, show_course=False)

        elif args.command == "search":
            if args.courses:
                # Show courses ranked by keyword frequency
                courses = db.search_courses_by_keyword(args.keyword)
                display_courses(courses, show_matches=True)
                print(f"\nFound {len(courses)} courses with '{args.keyword}'")
            else:
                # Show lessons with matches
                lessons = db.search_lessons(args.keyword, args.course)
                display_lessons(lessons, show_course=True, show_matches=True)
                print(f"\nFound {len(lessons)} lessons with '{args.keyword}'")

        elif args.command == "stats":
            stats = db.get_statistics()
            display_statistics(stats)

        else:
            parser.print_help()

    finally:
        db.close()


if __name__ == "__main__":
    main()
