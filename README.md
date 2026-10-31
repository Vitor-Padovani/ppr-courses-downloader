# Padre Paulo Ricardo Courses Downloader & Manager

This project is a complete toolset to **download, organize, and search** course
materials from [padrepauloricardo.org](https://padrepauloricardo.org) with a Web
Scraper and a Database Manager.

It consists of the following components:

1. **Downloader CLI (`main.py`):** Entry point for downloading courses. It uses
   the scraper class to log in and fetch the content.
2. **Scraper (`scraper.py`):** The `CourseScraper` class. It automates the
   download of audio and text summaries using Selenium.
3. **Database Manager (`database.py`):** Indexes downloaded content into a
   SQLite database, allowing full-text search across all lessons.

## Features

- ✔ Login with an interactive prompt (email and password are never saved to disk)
- ✔ Session reuse through saved cookies
- ✔ Automatic profile selection (always picks the first profile)
- ✔ Download content:
  + *Single course*
  + *All platform courses*
- ✔ Extract and format lesson text into `.txt` files
- ✔ Download class audio files
- ✔ Detects courses that were already downloaded and asks before replacing them
- ✔ Leaves the browser on the courses page when it finishes
- ✔ Local SQLite Database creation
- ✔ Full-text search through all transcripts
- ✔ Rank courses by keyword frequency

## Requirements

### Python libraries

- `selenium`
- `beautifulsoup4`
- `questionary`
- `black` [dev dependency]

Install with:

```bash
uv sync
```

*Note: `database.py` uses only standard Python libraries (sqlite3, argparse,
pathlib).*

You also need Google Chrome installed, since the scraper drives it through
Selenium.

## Login

There is no credentials file. On the first run (or whenever the saved session
expires), the program asks for your email and password in the terminal. The
password is hidden while you type.

After a successful login, the session cookies are saved to `cookies.json` and
reused automatically on the next runs, so you are only prompted again when the
session expires.

If the site shows the "Who is watching?" profile screen after login, the first
profile is selected automatically.

> [!WARNING]
> `cookies.json` gives access to your account without a password. Keep it
> private and never commit it (it should be listed in `.gitignore`).

## Usage: 1. Downloading Content

Use `main.py` to download the courses to your local drive (default folder is
`downloads/`).

### Download ALL courses

```bash
uv run main.py --all-courses
```

### Download a SINGLE course

```bash
uv run main.py --course https://padrepauloricardo.org/cursos/course-link-here
```

If the course was already downloaded (or only partially), the program tells you
and asks whether you want to replace it. Answering "no" keeps the existing
files.

### Courses that already exist

When you use `--all-courses` and some courses are already in `downloads/`, you
choose what to do with them:

- **Finish downloading:** skips the completed courses and downloads only the
  missing or incomplete ones.
- **Download everything and replace:** replaces all existing courses.
- **Ask for each existing course:** asks individually whether to replace each
  one.

> ⚠ Replacing a course **deletes its folder** and downloads it again.

A course is considered *complete* when its folder contains a `.complete` file,
created at the end of the download. Folders without it (an interrupted
download, or courses downloaded with an older version) are treated as
*incomplete*.

When the download ends, the browser stays open on the courses page.

---

## Usage: 2. Database & Search

Once you have downloaded the courses, use `database.py` to index the content
and perform searches.

### Step 1: Import downloaded courses

Scan the download directory and index all text and audio metadata into
`courses.db`.

```bash
# Assuming 'downloads' is your output folder
uv run database.py import downloads
```

### Step 2: Search for keywords

Search for a specific word or phrase across **all** downloaded lessons.

```bash
uv run database.py search "virtude"
```

*Output lists the matching lessons with their course, title, word count and
number of matches.*

To limit the search to a single course, pass its ID (see `list`):

```bash
uv run database.py search "virtude" --course 3
```

### Search and rank courses

Find which courses discuss a topic the most (ranked by frequency).

```bash
uv run database.py search "tomismo" --courses
```

### List all indexed courses

```bash
uv run database.py list
```

### Show the lessons of a course

```bash
uv run database.py show 3
```

### View Database Statistics

See total words, lessons, and top courses.

```bash
uv run database.py stats
```

---

## Logging

All download operations, timestamps, warnings, and errors are stored in:
`downloads/log.txt`. The script prints logs to console when `DEBUG_MODE` is
enabled.

## How It Works

1. **Scraper (`main.py` + `scraper.py`)**:
   + Logs in (using saved cookies when possible), selects the first profile,
     and retrieves course URLs.
   + Iterates through lessons, downloading `.mp3` files and extracting text to
     `.txt` files.
   + Saves files in one folder per course, named after the course URL (e.g.,
     `downloads/course-link-here/01.Lesson_Title.txt`).
   + Creates a `.complete` file in the course folder when the course finishes.

2. **Database Manager (`database.py`)**:
   + **Import**: Reads each course folder inside the chosen directory.
   + **Indexing**: Reads `.txt` files and stores content in a SQLite Virtual
     Table (FTS5) for fast searching.
   + **Querying**: Allows you to find exactly which lessons a specific topic
     was mentioned in (based on the text summary).

## Disclaimer

This tool is for **personal use only**.
Only download content you already have rights to access.
Respect platform Terms of Service and copyright.

## LICENSE

This project is under the *MIT* license.
For more informations, view [this file](LICENSE).