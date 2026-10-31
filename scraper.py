from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from bs4 import BeautifulSoup
import re
from datetime import datetime

import time
import json
import os
import shutil
from typing import Literal
from urllib.parse import urlparse

import questionary

LOGIN_URL = "https://padrepauloricardo.org/entrar"
COURSES_URL = "https://padrepauloricardo.org/cursos"
PROFILE_URL_PART = "quem-esta-assistindo"

# Written inside a course folder when all of its classes were processed
COMPLETE_MARKER = ".complete"

CourseStatus = Literal["new", "partial", "complete"]
ExistingPolicy = Literal["resume", "replace_all", "ask"]


class CourseScraper:
    def __init__(self) -> None:
        self.MAX_WAIT_TIME: int = 10
        self.MIN_WAIT_TIME: int = 3
        self.DEBUG_MODE: bool = True
        self.email: str = ""
        self.password: str = ""

        self.base_download_dir: str = os.path.abspath("downloads")
        self.current_download_dir: str = (
            self.base_download_dir
        )  # Track current download directory
        self.log_file: str = os.path.join(self.base_download_dir, "log.txt")

        # Create downloads directory if it doesn't exist
        os.makedirs(self.base_download_dir, exist_ok=True)

        # Initialize log file
        self._init_log_file()

        chrome_options = Options()
        chrome_options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": self.base_download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
        # Keep the browser open (on the courses page) when the script finishes
        chrome_options.add_experimental_option("detach", True)

        self.driver: webdriver.Chrome = webdriver.Chrome(options=chrome_options)
        self.cookies_file: str = "cookies.json"

        self.log("=" * 40)
        self.log("System started")
        self.log("=" * 40)

    def _init_log_file(self) -> None:
        """Initialize log file with session header"""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'='*40}\n")
            f.write(f"NEW SESSION - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"{'='*40}\n\n")

    def log(
        self,
        message: str,
        exception: Exception | None = None,
        level: str = "INFO",
    ) -> None:
        """
        Log messages with timestamp

        Args:
            message: Message to log
            exception: Exception object (optional)
            level: Log level (INFO, WARNING, ERROR, SUCCESS)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Define prefix based on level
        prefix_map = {"INFO": "->", "WARNING": "! ", "ERROR": "X ", "SUCCESS": "✓ "}
        prefix = prefix_map.get(level, "->")

        # Format message
        if exception:
            log_message = (
                f"[{timestamp}] {prefix} {message} | Exception: {str(exception)}"
            )
        else:
            log_message = f"[{timestamp}] {prefix} {message}"

        # Display in console if DEBUG_MODE is active
        if self.DEBUG_MODE:
            print(log_message)

        # Save to file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"Error saving log: {e}")

    def ask_credentials(self) -> None:
        """Ask for email and password in the terminal (password is hidden)."""
        email: str | None = questionary.text("Email:").ask()
        password: str | None = questionary.password("Senha:").ask()
        if not email or not password:  # None means the prompt was cancelled
            raise SystemExit("Login cancelado.")
        self.email = email
        self.password = password

    def save_cookies(self) -> None:
        """Store cookies to JSON file"""
        with open(self.cookies_file, "w", encoding="utf-8") as file:
            json.dump(self.driver.get_cookies(), file)
        self.log("Cookies saved successfully", level="SUCCESS")

    def load_cookies(self) -> bool:
        """Load cookies from file and add them to driver"""
        if not os.path.exists(self.cookies_file):
            self.log("Cookies file not found", level="WARNING")
            return False

        with open(self.cookies_file, "r") as file:
            cookies = json.load(file)

        for cookie in cookies:
            self.driver.add_cookie(cookie)

        self.log("Cookies loaded successfully", level="SUCCESS")
        return True

    def select_first_profile(self) -> None:
        """Se o site mostrar a tela de perfis, clica sempre no primeiro."""
        if PROFILE_URL_PART not in self.driver.current_url:
            return
        self.log("Profile selection screen detected. Choosing first profile")
        first_profile = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.profile-gate__tile"))
        )
        first_profile.click()
        WebDriverWait(self.driver, 10).until(
            lambda d: PROFILE_URL_PART not in d.current_url
        )
        self.log("Profile selected", level="SUCCESS")

    def is_logged_in(self) -> bool:
        url = self.driver.current_url.lower()
        return "entrar" not in url and PROFILE_URL_PART not in url

    def login(self, login_url: str) -> None:
        """Perform login using cookies or manual credentials"""
        self.log(f"Starting login process at: {login_url}")

        self.driver.get(login_url)
        self.driver.maximize_window()

        # Try login using cookies (if valid)
        if self.load_cookies():
            self.driver.get(login_url)
            time.sleep(3)
            self.select_first_profile()
            if self.is_logged_in():
                self.save_cookies()  # guarda também o perfil escolhido
                self.log("Logged in using saved cookies", level="SUCCESS")
                return
            else:
                self.log("Cookies invalid. Performing manual login", level="WARNING")

        # Manual login
        self.ask_credentials()
        self.log("Filling login credentials")
        email_input = WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
            EC.presence_of_element_located((By.ID, "inputEmail"))
        )
        email_input.send_keys(self.email)

        password_input = WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
            EC.presence_of_element_located((By.ID, "inputPassword"))
        )
        password_input.send_keys(self.password + Keys.ENTER)

        time.sleep(5)
        self.select_first_profile()

        if not self.is_logged_in():
            raise RuntimeError("Login failed: still on login/profile page")

        self.save_cookies()
        self.log("Manual login completed successfully", level="SUCCESS")

    def download_class_audio(self) -> None:
        """Download audio file from class"""
        try:
            self.log("Searching for audio button")
            WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Áudio d')]")
                )
            )
            audio_button = self.driver.find_element(
                By.XPATH, "//*[contains(text(), 'Áudio d')]"
            )
            audio_button.click()
            self.log("Audio download started", level="SUCCESS")
        except Exception as e:
            self.log("Could not find audio button", e, level="ERROR")

    def download_class_downloadables(self) -> None:
        """Download files from class"""
        try:
            self.log("Searching for download links")

            # Espera os elementos dentro do id 'download-content' estarem presentes
            WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
                EC.presence_of_all_elements_located((By.ID, "download-content"))
            )

            # Encontra todos os links de download dentro do 'download-content'
            download_section = self.driver.find_element(By.ID, "download-content")
            all_download_links = download_section.find_elements(By.TAG_NAME, "a")

            # Filtra apenas os links que contêm '(pdf)' no texto
            pdf_links = [link for link in all_download_links if "(pdf)" in link.text]

            for pdf in pdf_links:
                pdf.click()
                self.log(
                    f"Pdf download started for: {pdf.get_attribute('download')}",
                    level="SUCCESS",
                )

        except Exception as e:
            self.log(f"Could not find or click on pdf links: {str(e)}", level="ERROR")

    def sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename"""
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)
        filename = filename.strip()
        return filename[:200]  # Limit filename length

    def class_text_filename(self, class_name: str) -> str:
        """Name of the .txt file saved for a class."""
        filename = self.sanitize_filename(f"{class_name}.txt")
        filename = (
            ("00." + filename)
            if not filename[0].isdigit()
            else filename.replace(". ", ".")
        )
        return filename.replace(" ", "_")

    def download_class_summary(self, class_num: int, class_name: str) -> None:
        """Extract and save class text content to .txt file"""
        try:
            self.log("Starting class text extraction")

            # Wait for lesson-content__text div to load
            WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
                EC.presence_of_element_located((By.CLASS_NAME, "lesson-content__text"))
            )

            self.log("Class content loaded, processing HTML")

            # Get page HTML
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            # Find lesson-content__text div
            lesson_content = soup.find("div", class_="lesson-content__text")

            if not lesson_content:
                self.log("Could not find lesson-content__text div", level="ERROR")
                return

            # Extract lesson title
            title_element = lesson_content.find("h2", class_="lesson-text__title")
            title = (
                title_element.get_text(strip=True)
                if title_element
                else "untitled_lesson"
            )
            self.log(f"Extracted title: {title}")

            # Extract theme
            theme_element = lesson_content.find("span", class_="lesson-text__theme")
            theme = theme_element.get_text(strip=True) if theme_element else ""

            # Extract description
            description_element = lesson_content.find(
                "div", class_="lesson-text__description"
            )
            description = (
                description_element.get_text(strip=True) if description_element else ""
            )

            # Extract article content
            article = lesson_content.find("article", class_="editor")

            if not article:
                self.log("Could not find article content", level="ERROR")
                return

            # Remove scripts and styles
            for script in article(["script", "style"]):
                script.decompose()

            # Get all text formatted
            paragraphs = article.find_all("p")
            content_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs])

            self.log(
                f"Text extracted: {len(content_text)} characters, {len(paragraphs)} paragraphs"
            )

            # Build final text
            full_text = f"{theme}\n\n"
            full_text += f"{title}\n"
            full_text += "=" * len(title) + "\n\n"

            if description:
                full_text += f"{description}\n\n"
                full_text += "-" * 80 + "\n\n"

            full_text += content_text

            # Create filename
            filename = self.class_text_filename(class_name)
            filepath = os.path.join(self.current_download_dir, filename)

            # Save file
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_text)

            self.log(f"Text saved successfully to: {filename}", level="SUCCESS")

        except Exception as e:
            self.log("Error downloading class summary", e, level="ERROR")

    def get_class_material(
        self,
        class_info: tuple[str, str],
        class_num: int,
        first_time: bool = False,
    ) -> None:
        """Navigate to class URL and download materials"""
        class_name = class_info[0]
        class_url = class_info[1]

        self.log(f"Accessing class {class_num} URL: {class_url}")
        self.driver.get(class_url)

        if first_time:
            try:
                review_button = WebDriverWait(self.driver, self.MIN_WAIT_TIME).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, ".course-review__ask-later")
                    )
                )
                review_button.click()
                self.log("Review popup closed")
            except:
                pass

        self.download_class_audio()
        self.download_class_summary(class_num, class_name)
        # self.download_class_downloadables()

    def get_all_classes_links(self, course_url: str) -> list[tuple[str, str]]:
        """Get all class URLs from a course"""
        self.log(f"Getting class list from course: {course_url}")
        self.driver.get(course_url)

        # Wait until lessons load
        WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
            EC.presence_of_all_elements_located((By.ID, "course-classes"))
        )
        all_classes = self.driver.find_elements(By.CSS_SELECTOR, "a.class")

        classes_list: list[tuple[str, str]] = []
        for class_info in all_classes:
            href = class_info.get_attribute("href")
            if not href:
                self.log("Skipping class without link", level="WARNING")
                continue
            name = class_info.find_element(
                By.CSS_SELECTOR, ".class__title"
            ).text.strip()

            classes_list.append((name, href))

        self.log(f"Found {len(classes_list)} classes in course", level="SUCCESS")
        return classes_list

    @staticmethod
    def course_name_from_url(course_url: str) -> str:
        """Last segment of the course URL path (used as the folder name)."""
        name = urlparse(course_url).path.rstrip("/").split("/")[-1]
        if name in ("", ".", ".."):
            raise ValueError(f"Could not get the course name from: {course_url}")
        return name

    def course_dir_for(self, course_name: str) -> str:
        return os.path.join(self.base_download_dir, course_name)

    def get_course_status(self, course_name: str) -> CourseStatus:
        """
        new      -> no folder (or an empty one)
        partial  -> folder with files but no completion marker
        complete -> folder with the completion marker
        """
        course_dir = self.course_dir_for(course_name)
        if not os.path.isdir(course_dir) or not os.listdir(course_dir):
            return "new"
        if os.path.exists(os.path.join(course_dir, COMPLETE_MARKER)):
            return "complete"
        return "partial"

    def confirm_replace_course(self, course_name: str, status: CourseStatus) -> bool:
        """Ask whether an already existing course should be replaced."""
        if status == "complete":
            message = f'O curso "{course_name}" já foi baixado. Deseja substituí-lo?'
        else:
            message = (
                f'O curso "{course_name}" foi baixado parcialmente. '
                "Deseja baixá-lo novamente (substituindo a pasta)?"
            )
        return bool(questionary.confirm(message, default=False).unsafe_ask())

    def ask_existing_policy(self, existing_count: int) -> ExistingPolicy:
        """Ask what to do with courses that already exist in the downloads folder."""
        answer: ExistingPolicy = questionary.select(
            f"{existing_count} curso(s) já existem na pasta de downloads. "
            "O que deseja fazer?",
            choices=[
                questionary.Choice(
                    "Terminar de baixar (cursos que faltam e aulas ausentes nos existentes)",
                    value="resume",
                ),
                questionary.Choice(
                    "Baixar tudo e substituir os existentes", value="replace_all"
                ),
                questionary.Choice(
                    "Perguntar individualmente para cada curso existente",
                    value="ask",
                ),
            ],
        ).unsafe_ask()
        return answer

    def should_skip_existing(
        self, policy: ExistingPolicy, course_name: str, status: CourseStatus
    ) -> bool:
        """Decide whether an already existing course is skipped."""
        if policy == "ask":
            return not self.confirm_replace_course(course_name, status)
        return False  # resume and replace_all never skip

    def _download_course(self, course_url: str, resume: bool = False) -> None:
        """
        Download a course.

        resume=False: an existing folder is deleted and the course is downloaded
        from scratch.
        resume=True: an existing folder is kept and only the classes whose text
        file is missing are downloaded.
        """
        course_name = self.course_name_from_url(course_url)
        course_dir = self.course_dir_for(course_name)

        if os.path.isdir(course_dir) and not resume:
            self.log(f"Removing existing folder: {course_dir}", level="WARNING")
            shutil.rmtree(course_dir)
        os.makedirs(course_dir, exist_ok=True)

        # The course is only complete again after this run finishes
        marker_path = os.path.join(course_dir, COMPLETE_MARKER)
        if os.path.exists(marker_path):
            os.remove(marker_path)

        # Update current download directory for this course
        self.current_download_dir = course_dir

        self.log(f"Starting course download: {course_name}")
        self.log(f"Destination directory: {course_dir}")

        # Change Chrome download folder at runtime
        self.driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": course_dir},
        )

        classes_info = self.get_all_classes_links(course_url)

        # (position in the course, class info) of the classes still to download
        pending = list(enumerate(classes_info, start=1))
        if resume:
            pending = [
                (index, info)
                for index, info in pending
                if not os.path.exists(
                    os.path.join(course_dir, self.class_text_filename(info[0]))
                )
            ]
            self.log(
                f"{len(classes_info) - len(pending)} of {len(classes_info)} "
                f"classes already downloaded, {len(pending)} missing"
            )

        for position, (index, class_info) in enumerate(pending, start=1):
            self.log(f"Processing class {index}/{len(classes_info)}")
            self.get_class_material(class_info, index, first_time=(position == 1))
            time.sleep(1)

        # Only reached if the loop was not interrupted by an error
        with open(marker_path, "w", encoding="utf-8"):
            pass

        self.log(f"Course download completed: {course_name}", level="SUCCESS")

    def download_course(self, course_url: str) -> None:
        """Download a single course, asking before replacing an existing one."""
        course_name = self.course_name_from_url(course_url)
        status = self.get_course_status(course_name)

        if status != "new" and not self.confirm_replace_course(course_name, status):
            self.log(f"Kept existing course: {course_name}", level="WARNING")
            return

        self._download_course(course_url)

    def get_all_courses_links(self, courses_url: str) -> list[str | None]:
        """Get all course URLs from courses page"""
        self.log(f"Getting courses list from: {courses_url}")
        self.driver.get(courses_url)

        # Wait until courses load
        WebDriverWait(self.driver, self.MAX_WAIT_TIME).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "course-card"))
        )

        links = self.driver.find_elements(By.CLASS_NAME, "course-card")
        urls: list[str | None] = [link.get_attribute("href") for link in links]
        self.log(f"Found {len(urls)} courses", level="SUCCESS")
        return urls

    def download_all_courses(self, courses_url: str = COURSES_URL) -> None:
        """Download all courses from platform"""
        self.log("Starting download of all courses")
        raw_urls = self.get_all_courses_links(courses_url)

        try:
            enable_cookies_button = WebDriverWait(
                self.driver, self.MIN_WAIT_TIME
            ).until(EC.element_to_be_clickable((By.ID, "c-p-bn")))
            enable_cookies_button.click()
            self.log("Cookies banner accepted")
        except:
            pass

        courses: list[tuple[str, str]] = []
        for index, url in enumerate(raw_urls, start=1):
            if not url:
                self.log(f"Skipping empty URL for course {index}", level="WARNING")
                continue
            courses.append((self.course_name_from_url(url), url))

        existing = [
            name for name, _ in courses if self.get_course_status(name) != "new"
        ]
        policy: ExistingPolicy = "replace_all"
        if existing:
            policy = self.ask_existing_policy(len(existing))

        for index, (course_name, url) in enumerate(courses, start=1):
            status = self.get_course_status(course_name)
            if status != "new" and self.should_skip_existing(
                policy, course_name, status
            ):
                self.log(
                    f"Course {index}/{len(courses)} skipped: {course_name}",
                    level="WARNING",
                )
                continue

            self.log(f"Course {index}/{len(courses)}: {course_name}")
            # "resume" keeps existing folders and only fetches what is missing
            self._download_course(url, resume=(policy == "resume" and status != "new"))
            time.sleep(1)

        self.log("All courses download completed!", level="SUCCESS")

    def go_to_courses_page(self, courses_url: str = COURSES_URL) -> None:
        """Leave the browser on the courses page."""
        try:
            self.driver.get(courses_url)
            self.log("Browser left on the courses page")
        except Exception as e:
            self.log("Could not go back to the courses page", e, level="WARNING")
