"""Core admit card download engine with validation, retries, and resume capability."""

from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Set, Union

import httpx
from rich.console import Console

from .config import Settings

console = Console()


@dataclass
class StudentTarget:
    """Represents an admit card target to download."""

    student_id: str
    name: str = ""
    roll_no: str = ""

    @property
    def clean_id(self) -> str:
        return self.student_id.strip()

    def get_base_filename(self) -> str:
        """Constructs a clean base filename in the format StudentName_id or roll_name_id."""
        safe_id = re.sub(r'[^\w\-.]', '_', self.clean_id)
        if self.name:
            # Clean up extra spaces/special chars in name -> Student_Name
            cleaned_name = re.sub(r'\s+', '_', self.name.strip())
            safe_name = re.sub(r'[^\w\-.]', '_', cleaned_name)
            safe_name = re.sub(r'_+', '_', safe_name).strip('_')
            return f"{safe_name}_{safe_id}"
        elif self.roll_no:
            safe_roll = re.sub(r'[^\w\-.]', '_', self.roll_no.strip())
            return f"{safe_roll}_{safe_id}"
        return f"admit_card_{safe_id}"

    def get_filename(self, ext: str = ".pdf") -> str:
        """Constructs a clean, safe filename with the given extension."""
        if not ext.startswith("."):
            ext = f".{ext}"
        return f"{self.get_base_filename()}{ext}"


@dataclass
class DownloadResult:
    """Result of a single admit card download attempt."""

    target: StudentTarget
    status: str  # "success", "failed", "skipped"
    file_path: Optional[Path] = None
    status_code: Optional[int] = None
    error_message: str = ""
    file_size_bytes: int = 0
    content_type: str = ""


def sanitize_file_path(path_input: Union[str, Path]) -> Path:
    """Cleans up paths pasted from Windows 'Copy as path' (stripping surrounding quotes and ampersands)."""
    if isinstance(path_input, Path):
        return path_input

    cleaned = str(path_input).strip()
    if cleaned.startswith("&"):
        cleaned = cleaned[1:].strip()

    # Repeatedly strip surrounding single or double quotes
    while (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    return Path(cleaned)


def extract_id_from_entrance_no(raw_val: str) -> str:
    """Extracts numeric entrance ID from strings like 'EN-26-41819' -> '41819'."""
    raw_val = raw_val.strip()
    match = re.search(r'(\d+)$', raw_val)
    if match:
        return match.group(1)
    return raw_val


def suggest_url_template(raw_url: str) -> str:
    """Intelligently detects numeric IDs in a URL and converts them to {entranceid} or {student_id} placeholder."""
    raw_url = raw_url.strip()
    if not raw_url:
        return raw_url

    # If it already contains standard placeholders, return as is
    if any(tag in raw_url for tag in ("{student_id}", "{id}", "{roll_no}", "{entranceid}", "{entrance_id}")):
        return raw_url

    # Check for query parameters like entranceid=41626 or id=123 or roll=123
    param_pattern = re.compile(
        r'([?&](?:entranceid|entrance_id|applicantid|applicant_id|studentid|student_id|candidateid|candidate_id|roll_no|rollno|reg_no|regno|symbol_no|symbolno|id|roll)=)(\d+)',
        re.IGNORECASE,
    )
    if param_pattern.search(raw_url):
        return param_pattern.sub(r'\1{student_id}', raw_url)

    # Check for path segment numbers e.g. /admit/1024 or /1024/print or /1024.pdf
    path_pattern = re.compile(r'(/)(\d+)(/|\.pdf|\.php|\.aspx|\?|$)', re.IGNORECASE)
    matches = list(path_pattern.finditer(raw_url))
    if matches:
        last_match = matches[-1]
        start, end = last_match.span()
        prefix = raw_url[:start]
        replaced = f"{last_match.group(1)}{{student_id}}{last_match.group(3)}"
        suffix = raw_url[end:]
        return f"{prefix}{replaced}{suffix}"

    return raw_url


def deduplicate_targets(targets: List[StudentTarget]) -> List[StudentTarget]:
    """Deduplicates targets by student_id while preserving original order."""
    seen: Set[str] = set()
    deduped: List[StudentTarget] = []
    for t in targets:
        cid = t.clean_id
        if cid and cid not in seen:
            seen.add(cid)
            deduped.append(t)
    return deduped


def parse_targets_from_text(text: str) -> List[StudentTarget]:
    """Parses targets from a comma-separated string, space-separated string, range, or multi-line text."""
    text = text.strip()
    if not text:
        return []

    # Check if text is a standalone range like "41600-41650" or "2024001..2024050"
    if re.match(r'^\d+\s*(?:-|to|\.\.)\s*\d+$', text, re.IGNORECASE):
        return parse_targets_from_range(text)

    targets: List[StudentTarget] = []
    tokens = re.split(r'[,;\n\r]+', text)
    for token in tokens:
        token = token.strip()
        if not token or token.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r'\t', token) if p.strip()]
        if len(parts) >= 2:
            targets.append(StudentTarget(
                student_id=extract_id_from_entrance_no(parts[0]),
                name=parts[1],
                roll_no=parts[2] if len(parts) > 2 else ""
            ))
        else:
            range_match = re.match(r'^(\d+)\s*(?:-|to|\.\.)\s*(\d+)$', token, re.IGNORECASE)
            if range_match:
                targets.extend(parse_targets_from_range(token))
            else:
                space_tokens = [s.strip() for s in token.split() if s.strip()]
                if len(space_tokens) > 1 and all(extract_id_from_entrance_no(st).isdigit() for st in space_tokens):
                    for st in space_tokens:
                        targets.append(StudentTarget(student_id=extract_id_from_entrance_no(st)))
                else:
                    targets.append(StudentTarget(student_id=extract_id_from_entrance_no(token)))

    return deduplicate_targets(targets)


def parse_targets_from_html_table(content: str) -> List[StudentTarget]:
    """Parses targets from an HTML table (standard in Midas/ERP Report.xls exports)."""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.IGNORECASE | re.DOTALL)
    if not rows:
        return []

    header_row = rows[0]
    headers = [re.sub(r'<[^>]+>', '', h).strip().lower() for h in re.findall(r'<th[^>]*>(.*?)</th>', header_row, re.IGNORECASE | re.DOTALL)]
    if not headers:
        headers = [re.sub(r'<[^>]+>', '', h).strip().lower() for h in re.findall(r'<td[^>]*>(.*?)</td>', header_row, re.IGNORECASE | re.DOTALL)]

    id_idx = 1
    name_idx = 2
    roll_idx = None

    for idx, h in enumerate(headers):
        if any(kw in h for kw in ("entrance", "id", "reg", "applicant", "symbol")):
            id_idx = idx
        elif any(kw in h for kw in ("student name", "name", "full name")):
            name_idx = idx
        elif "roll" in h:
            roll_idx = idx

    targets: List[StudentTarget] = []
    for r in rows[1:]:
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', r, re.IGNORECASE | re.DOTALL)]
        if not cells or len(cells) <= max(id_idx, name_idx):
            continue
        raw_id = cells[id_idx]
        raw_name = cells[name_idx] if name_idx < len(cells) else ""
        raw_roll = cells[roll_idx] if roll_idx is not None and roll_idx < len(cells) else ""

        student_id = extract_id_from_entrance_no(raw_id)
        if not student_id:
            continue

        clean_name = " ".join(raw_name.split())
        targets.append(StudentTarget(student_id=student_id, name=clean_name, roll_no=raw_roll))

    return targets


def parse_targets_from_file(file_path: Union[str, Path]) -> List[StudentTarget]:
    """Parses student targets from an XLS (HTML table), CSV, or text file with sanitized path handling."""
    clean_path = sanitize_file_path(file_path)
    if not clean_path.exists():
        raise FileNotFoundError(f"Input file not found: {clean_path}")

    suffix = clean_path.suffix.lower()

    # Check for HTML table in .xls or .html files
    if suffix in (".xls", ".html", ".htm"):
        content = clean_path.read_text(encoding="utf-8", errors="ignore")
        if "<table" in content.lower() or "<tr" in content.lower():
            return deduplicate_targets(parse_targets_from_html_table(content))

    if suffix == ".csv":
        targets: List[StudentTarget] = []
        with open(clean_path, "r", encoding="utf-8-sig") as f:
            sample = f.read(2048)
            f.seek(0)
            has_header = csv.Sniffer().has_header(sample) if sample.strip() else False

            reader = csv.reader(f)
            headers = []
            if has_header:
                headers = [h.strip().lower() for h in next(reader, [])]

            id_idx = 0
            name_idx = None
            roll_idx = None

            if headers:
                for idx, h in enumerate(headers):
                    if any(kw in h for kw in ("entrance", "id", "applicant", "reg", "symbol")):
                        id_idx = idx
                    elif "name" in h:
                        name_idx = idx
                    elif "roll" in h:
                        roll_idx = idx

            for row in reader:
                if not row or not any(row):
                    continue
                if id_idx < len(row) and row[id_idx].strip():
                    raw_id = row[id_idx].strip()
                    student_id = extract_id_from_entrance_no(raw_id)
                    name = " ".join(row[name_idx].strip().split()) if name_idx is not None and name_idx < len(row) else ""
                    roll = row[roll_idx].strip() if roll_idx is not None and roll_idx < len(row) else ""
                    targets.append(StudentTarget(student_id=student_id, name=name, roll_no=roll))

        return deduplicate_targets(targets)

    # Plain text file
    with open(clean_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
        return deduplicate_targets(parse_targets_from_text(content))


def parse_targets_from_range(id_range: str) -> List[StudentTarget]:
    """Parses a numerical range like '41600-41650' or '2024001..2024050'."""
    match = re.match(r'^(\d+)\s*(?:-|to|\.\.)\s*(\d+)$', id_range.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid range format '{id_range}'. Expected format: '41600-41650' or '2024001..2024050'")

    start_str, end_str = match.groups()
    start, end = int(start_str), int(end_str)
    pad_len = max(len(start_str), len(end_str))

    if start > end:
        start, end = end, start

    return [
        StudentTarget(student_id=str(num).zfill(pad_len))
        for num in range(start, end + 1)
    ]


class AdmitCardDownloader:
    """Manages session lifecycle and downloads admit cards."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)

    def download_single(
        self,
        client: httpx.Client,
        target: StudentTarget,
        force: bool = False,
    ) -> DownloadResult:
        """Downloads a single admit card with validation and file integrity checks."""
        # Build target URL with all supported placeholder aliases
        url = self.settings.url_template.format(
            student_id=target.clean_id,
            id=target.clean_id,
            entranceid=target.clean_id,
            entrance_id=target.clean_id,
            roll_no=target.roll_no or target.clean_id,
            roll=target.roll_no or target.clean_id,
            applicant_id=target.clean_id,
            applicantid=target.clean_id,
        )

        max_retries = 3
        last_error = ""

        for attempt in range(1, max_retries + 1):
            try:
                response = client.get(url, follow_redirects=True)
                
                # Check HTTP status code
                if response.status_code != 200:
                    return DownloadResult(
                        target=target,
                        status="failed",
                        status_code=response.status_code,
                        error_message=f"HTTP {response.status_code}",
                    )

                content = response.content
                content_type = response.headers.get("content-type", "").lower()
                final_url = str(response.url).lower()

                # Clean leading whitespace often prepended by PHP output
                cleaned_content = content.lstrip(b" \t\r\n")

                # Determine file type
                is_pdf = cleaned_content.startswith(b"%PDF") or "application/pdf" in content_type
                is_html = cleaned_content.startswith(b"<!DOCTYPE") or b"<html" in cleaned_content[:300].lower() or "text/html" in content_type

                # Validation 1: Check for session expiration or login redirection
                if is_html:
                    html_snippet = cleaned_content[:2000].decode("utf-8", errors="ignore").lower()
                    if (
                        "login" in final_url
                        or "auth" in final_url
                        or 'type="password"' in html_snippet
                        or 'name="password"' in html_snippet
                        or "please log in" in html_snippet
                        or "session expired" in html_snippet
                        or "invalid session" in html_snippet
                    ):
                        return DownloadResult(
                            target=target,
                            status="failed",
                            status_code=response.status_code,
                            error_message="Authentication failed: Session expired or invalid cookie (redirected to login)",
                        )

                    # Validation 2: Check for 'no record found' / invalid ID errors
                    if "no record found" in html_snippet or "invalid entrance id" in html_snippet or "data not found" in html_snippet:
                        return DownloadResult(
                            target=target,
                            status="failed",
                            status_code=response.status_code,
                            error_message=f"No record found for entrance ID {target.clean_id}",
                        )

                # Save sanitized binary data
                save_data = cleaned_content if is_pdf else content

                # Determine file extension (.pdf or .html)
                ext = ".pdf" if is_pdf else ".html"
                filename = target.get_filename(ext=ext)
                output_file = self.settings.output_dir / filename

                # Check if already downloaded and valid
                if not force and output_file.exists() and output_file.stat().st_size > 300:
                    return DownloadResult(
                        target=target,
                        status="skipped",
                        file_path=output_file,
                        file_size_bytes=output_file.stat().st_size,
                        content_type=content_type,
                    )

                # Save file
                with open(output_file, "wb") as f:
                    f.write(save_data)

                return DownloadResult(
                    target=target,
                    status="success",
                    file_path=output_file,
                    status_code=response.status_code,
                    file_size_bytes=len(save_data),
                    content_type=content_type,
                )

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
            except Exception as e:
                return DownloadResult(
                    target=target,
                    status="failed",
                    error_message=f"Unexpected error: {e}",
                )

        return DownloadResult(
            target=target,
            status="failed",
            error_message=f"Network error after {max_retries} retries: {last_error}",
        )

    def create_client(self) -> httpx.Client:
        """Initializes and returns an authenticated HTTPX client with raw headers."""
        return httpx.Client(
            headers=self.settings.get_headers(),
            timeout=self.settings.timeout,
            follow_redirects=True,
        )
