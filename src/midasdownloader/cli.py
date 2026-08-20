"""Command line interface for the MidasDownloader Admit Card Downloader."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .config import Settings
from .downloader import (
    AdmitCardDownloader,
    DownloadResult,
    StudentTarget,
    deduplicate_targets,
    parse_targets_from_file,
    parse_targets_from_range,
    parse_targets_from_text,
    sanitize_file_path,
    suggest_url_template,
)
from .pdf_merger import (
    combine_all_pages_together,
    combine_page1_only,
    combine_separate_pages,
)

app = typer.Typer(
    name="midasdownloader",
    help="Fast, reliable, batch downloader for university entrance admit cards.",
    add_completion=False,
)
console = Console()


def handle_post_download_combination(output_dir: Path, downloaded_files: List[Path], prompt_user: bool = True) -> None:
    """Prompts user to combine downloaded admit cards and performs combination accordingly."""
    pdf_files = [f for f in downloaded_files if f and f.exists() and f.suffix.lower() == ".pdf" and f.stat().st_size > 0]
    
    # If downloaded_files is empty, look into output_dir
    if not pdf_files and output_dir.exists():
        pdf_files = sorted(
            [f for f in output_dir.glob("*.pdf") if not f.name.startswith("combined_")],
            key=lambda x: x.name,
        )

    if not pdf_files:
        return

    console.print("\n[bold yellow]📄 Post-Download PDF Options[/bold yellow]")

    # Question 1: Do they want the admit card combined?
    if prompt_user:
        combine_choice = Confirm.ask(
            "[bold cyan]1. Do you want to combine the downloaded admit cards into a single PDF?[/bold cyan]",
            default=True,
        )
        if not combine_choice:
            console.print("[dim]Skipping PDF combination. Individual PDFs are saved in the output directory.[/dim]")
            return

    # Question 2: Do they need the second page of the pdf?
    need_second_page = Confirm.ask(
        "[bold cyan]2. Do you need the second page (instructions/rules) of the admit cards?[/bold cyan]",
        default=False,
    )

    if not need_second_page:
        # Case 1: Page 1 only
        combined_file = output_dir / "combined_admit_cards_page1.pdf"
        console.print(f"[cyan]Combining Page 1 of {len(pdf_files)} admit cards...[/cyan]")
        count = combine_page1_only(pdf_files, combined_file)
        console.print(
            Panel(
                f"[bold green]✔ Successfully created combined PDF (Page 1 only)![/bold green]\n\n"
                f"• [bold]Output File:[/bold] {combined_file.resolve()}\n"
                f"• [bold]Total Pages Merged:[/bold] {count}\n"
                f"• [bold]File Size:[/bold] {combined_file.stat().st_size / (1024 * 1024):.2f} MB",
                title="Combined PDF Ready",
                border_style="green",
            )
        )
    else:
        # Question 3: Both pages together or in separate files?
        console.print("\n[bold cyan]3. How would you like both pages saved?[/bold cyan]")
        console.print("  [cyan]1[/cyan]) Both pages together in one combined file ([dim]Student1 P1, Student1 P2, Student2 P1, Student2 P2...[/dim])")
        console.print("  [cyan]2[/cyan]) Separate combined files ([dim]One combined file for all Page 1s, and another for all Page 2s[/dim])")

        page_mode = IntPrompt.ask("Select option", default=1, choices=["1", "2"])

        if page_mode == 1:
            combined_file = output_dir / "combined_admit_cards_all_pages.pdf"
            console.print(f"[cyan]Combining all pages of {len(pdf_files)} admit cards...[/cyan]")
            count = combine_all_pages_together(pdf_files, combined_file)
            console.print(
                Panel(
                    f"[bold green]✔ Successfully created combined PDF (All pages interleaved)![/bold green]\n\n"
                    f"• [bold]Output File:[/bold] {combined_file.resolve()}\n"
                    f"• [bold]Total Pages Merged:[/bold] {count}\n"
                    f"• [bold]File Size:[/bold] {combined_file.stat().st_size / (1024 * 1024):.2f} MB",
                    title="Combined PDF Ready",
                    border_style="green",
                )
            )
        else:
            p1_file = output_dir / "combined_page1_admit_cards.pdf"
            p2_file = output_dir / "combined_page2_instructions.pdf"
            console.print(f"[cyan]Generating separate combined PDFs for Page 1 and Page 2...[/cyan]")
            p1_count, p2_count = combine_separate_pages(pdf_files, p1_file, p2_file)
            console.print(
                Panel(
                    f"[bold green]✔ Successfully created separate combined PDFs![/bold green]\n\n"
                    f"• [bold]Page 1 File (Admit Cards):[/bold] {p1_file.resolve()} ({p1_count} pages, {p1_file.stat().st_size / (1024 * 1024):.2f} MB)\n"
                    f"• [bold]Page 2 File (Instructions):[/bold] {p2_file.resolve()} ({p2_count} pages, {p2_file.stat().st_size / (1024 * 1024):.2f} MB)",
                    title="Combined PDFs Ready",
                    border_style="green",
                )
            )


def run_batch_download(settings: Settings, targets: List[StudentTarget], force: bool = False, prompt_combine: bool = True) -> None:
    """Executes the batch download for the given targets and settings."""
    console.print(
        Panel(
            f"[bold]Target Count:[/bold] {len(targets)}\n"
            f"[bold]Output Directory:[/bold] {settings.output_dir.resolve()}\n"
            f"[bold]URL Template:[/bold] {settings.url_template}\n"
            f"[bold]Cookie:[/bold] {settings.cookie_name}=***{settings.cookie_value[-6:] if len(settings.cookie_value) > 6 else '***'}\n"
            f"[bold]Request Delay:[/bold] {settings.request_delay}s",
            title="Admit Card Batch Download",
            border_style="cyan",
        )
    )

    downloader = AdmitCardDownloader(settings)
    results: List[DownloadResult] = []

    with downloader.create_client() as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Downloading admit cards...", total=len(targets))

            for target in targets:
                label = f"{target.name} ({target.clean_id})" if target.name else target.clean_id
                progress.update(task, description=f"[cyan]Downloading {label}...")
                res = downloader.download_single(client, target, force=force)
                results.append(res)
                progress.advance(task)

                # Courtesy rate-limit delay
                if res.status != "skipped" and settings.request_delay > 0:
                    time.sleep(settings.request_delay)

    # Generate Summary Table
    successes = [r for r in results if r.status == "success"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    table = Table(title="Download Summary", border_style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    table.add_row("[green]Downloaded[/green]", str(len(successes)), f"Saved to {settings.output_dir}")
    if skipped:
        table.add_row("[yellow]Skipped (Existing)[/yellow]", str(len(skipped)), "Already downloaded (use --force to re-download)")
    if failed:
        table.add_row("[red]Failed[/red]", str(len(failed)), "See error breakdown below")

    console.print("\n", table)

    if failed:
        err_table = Table(title="Failed Downloads", border_style="red")
        err_table.add_column("Entrance ID", style="cyan")
        err_table.add_column("Student Name", style="yellow")
        err_table.add_column("Error Message", style="red")

        for f_res in failed:
            err_table.add_row(f_res.target.clean_id, f_res.target.name or "N/A", f_res.error_message)

        console.print("\n", err_table)

    # Post-download combination prompt
    saved_files = [r.file_path for r in results if r.file_path and r.file_path.exists()]
    if saved_files and prompt_combine:
        handle_post_download_combination(settings.output_dir, saved_files, prompt_user=True)


@app.command(name="combine")
def combine(
    folder: Path = typer.Argument(
        ...,
        help="Path to folder containing downloaded admit card PDFs (e.g. out/2026-08-20_12-41-12)",
    ),
) -> None:
    """Combine existing admit card PDFs in a folder with interactive page options."""
    clean_folder = sanitize_file_path(folder)
    if not clean_folder.exists() or not clean_folder.is_dir():
        console.print(f"[bold red]Folder not found:[/bold red] {clean_folder}")
        raise typer.Exit(code=1)

    pdf_files = sorted(
        [f for f in clean_folder.glob("*.pdf") if not f.name.startswith("combined_")],
        key=lambda x: x.name,
    )
    if not pdf_files:
        console.print(f"[yellow]No PDF files found in {clean_folder}[/yellow]")
        raise typer.Exit(code=1)

    console.print(f"[green]Found [bold]{len(pdf_files)}[/bold] PDF files in [cyan]{clean_folder}[/cyan][/green]")
    handle_post_download_combination(clean_folder, pdf_files, prompt_user=False)


@app.command(name="interactive")
def interactive() -> None:
    """Interactive guided wizard to enter URL template, cookie, entrance IDs, and output folder."""
    console.print(
        Panel(
            "[bold cyan]🎓 MidasDownloader - Interactive Session[/bold cyan]\n\n"
            "• [bold green]In-Memory Security:[/bold green] Your session cookie stays strictly in memory for this session.\n"
            "• [bold green]Multi-Batch Support:[/bold green] Keep running batch after batch until you choose to exit.\n"
            "• [bold green]Automatic PDF Merge:[/bold green] Combine Page 1 or all pages after each batch.",
            title="Admit Card Downloader",
            border_style="cyan",
        )
    )

    settings = Settings()

    # -------------------------------------------------------------
    # Initial Session Setup: Authentication Cookie (In-Memory)
    # -------------------------------------------------------------
    console.print("\n[bold yellow]🔑 Authentication Setup[/bold yellow]")
    existing_cookie = settings.cookie_value
    cookie_name = settings.cookie_name or "ci_session"

    if existing_cookie:
        masked = f"***{existing_cookie[-6:]}" if len(existing_cookie) > 6 else "***"
        use_existing = Confirm.ask(
            f"Found existing cookie ([bold cyan]{cookie_name}={masked}[/bold cyan]). Use this session?",
            default=True,
        )
        if not use_existing:
            cookie_name = Prompt.ask("Cookie name", default="ci_session").strip()
            existing_cookie = Prompt.ask("Paste session cookie value", password=True).strip()
            settings.cookie_name = cookie_name
            settings.cookie_value = existing_cookie
    else:
        console.print("[dim]Find your cookie in Chrome: Press F12 -> Application -> Cookies -> copy 'ci_session' value[/dim]")
        cookie_name = Prompt.ask("Cookie name", default="ci_session").strip()
        settings.cookie_name = cookie_name
        settings.cookie_value = Prompt.ask("Paste your session cookie value", password=True).strip()

    if not settings.cookie_value:
        console.print("[bold red]Cookie is required to download admit cards. Exiting.[/bold red]")
        raise typer.Exit(code=1)

    batch_number = 1

    # -------------------------------------------------------------
    # Multi-Batch Loop
    # -------------------------------------------------------------
    while True:
        console.print(f"\n[bold green]═══ Batch #{batch_number} Setup ═══[/bold green]")

        # 1. URL Template
        console.print("\n[bold yellow]Step 1: Admit Card URL Template[/bold yellow]")
        console.print("Paste the admit card URL (e.g. from browser address bar with entranceid=...)")

        user_url = Prompt.ask("[bold]Paste URL[/bold]").strip()
        while not user_url:
            user_url = Prompt.ask("[bold red]URL cannot be empty. Please paste URL[/bold red]").strip()

        suggested = suggest_url_template(user_url)
        if (
            suggested != user_url
            and "{student_id}" not in user_url
            and "{id}" not in user_url
            and "{entranceid}" not in user_url
            and "{entrance_id}" not in user_url
        ):
            console.print(f"\n[cyan]Detected sample entrance ID in URL. Converted to template:[/cyan]\n[bold green]{suggested}[/bold green]")
            if Confirm.ask("Use this converted template?", default=True):
                user_url = suggested

        if (
            "{student_id}" not in user_url
            and "{id}" not in user_url
            and "{roll_no}" not in user_url
            and "{entranceid}" not in user_url
            and "{entrance_id}" not in user_url
        ):
            console.print("[yellow]Notice: URL doesn't have {student_id} placeholder. Appending /{student_id} to URL.[/yellow]")
            user_url = user_url.rstrip("/") + "/{student_id}"

        settings.url_template = user_url
        console.print(f"[green]✔ URL Template set to:[/green] [bold]{settings.url_template}[/bold]")

        # 2. Student Entrance IDs (Supports Windows Copy as path with quotes)
        console.print("\n[bold yellow]Step 2: Student Entrance IDs[/bold yellow]")
        targets: List[StudentTarget] = []

        default_report = Path("report/Report.xls")
        if not default_report.exists():
            default_report = Path("report_sample.xls")

        if default_report.exists():
            try:
                detected_targets = parse_targets_from_file(default_report)
                if detected_targets:
                    if Confirm.ask(
                        f"Found report file [bold cyan]{default_report}[/bold cyan] with [bold green]{len(detected_targets)}[/bold green] students. Load from this file?",
                        default=True,
                    ):
                        targets = detected_targets
            except Exception:
                pass

        while not targets:
            console.print("\nPaste your [bold cyan]comma-separated entrance IDs[/bold cyan] (e.g. 41819, 41829, 41891...) or [bold cyan]file path[/bold cyan]:")
            raw_ids = Prompt.ask("[bold]Entrance IDs or File Path[/bold]").strip()

            if not raw_ids:
                continue

            # Support Windows 'Copy as path' with or without quotes
            potential_path = sanitize_file_path(raw_ids)
            if potential_path.exists() and potential_path.is_file():
                try:
                    targets = parse_targets_from_file(potential_path)
                    console.print(f"[green]✔ Loaded {len(targets)} students from {potential_path}[/green]")
                except Exception as e:
                    console.print(f"[red]Error loading file:[/red] {e}")
                    continue
            else:
                targets = parse_targets_from_text(raw_ids)

            if not targets:
                console.print("[bold red]No valid entrance IDs could be parsed. Please try again.[/bold red]")

        targets = deduplicate_targets(targets)
        console.print(f"\n[green]✔ Total Entrance IDs for Batch #{batch_number}:[/green] [bold]{len(targets)}[/bold]")
        sample_preview = []
        for t in targets[:4]:
            if t.name:
                sample_preview.append(f"{t.name} ({t.clean_id}) -> [dim]{t.get_filename()}[/dim]")
            else:
                sample_preview.append(f"{t.clean_id} -> [dim]{t.get_filename()}[/dim]")
        for sp in sample_preview:
            console.print(f"  • {sp}")
        if len(targets) > 4:
            console.print(f"  [dim]... (+{len(targets) - 4} more students)[/dim]")

        # 3. Output Folder Location
        console.print("\n[bold yellow]Step 3: Output Folder Location[/bold yellow]")
        default_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = Prompt.ask(
            "[bold]Enter folder name inside out/[/bold]",
            default=default_folder,
        ).strip()

        if folder_name.startswith("out/") or folder_name.startswith("out\\"):
            folder_name = folder_name[4:].strip()
        folder_name = folder_name.strip("/\\")
        if not folder_name:
            folder_name = default_folder

        settings.output_dir = Path.cwd() / "out" / folder_name
        console.print(f"[green]✔ Output directory set to:[/green] [bold cyan]{settings.output_dir.resolve()}[/bold cyan]")

        # 4. Optional Pre-flight Verification Check
        console.print("\n[bold yellow]Step 4: Verification & Download[/bold yellow]")
        first_target = targets[0]
        label = f"{first_target.name} ({first_target.clean_id})" if first_target.name else first_target.clean_id
        if Confirm.ask(f"Run a test check on the first student ([bold cyan]{label}[/bold cyan]) to verify login?", default=True):
            downloader = AdmitCardDownloader(settings)
            console.print(f"[cyan]Testing {first_target.clean_id}...[/cyan]")
            with downloader.create_client() as client:
                test_res = downloader.download_single(client, first_target, force=True)

            if test_res.status == "success":
                console.print(
                    Panel(
                        f"[bold green]✔ Test Check Successful![/bold green]\n\n"
                        f"[bold]Downloaded sample:[/bold] {test_res.file_path}\n"
                        f"[bold]File size:[/bold] {test_res.file_size_bytes:,} bytes\n"
                        f"[bold]Status Code:[/bold] {test_res.status_code}",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[bold red]Test Failed![/bold red]\n\n"
                        f"[bold]Error:[/bold] {test_res.error_message}\n"
                        f"[bold]Status Code:[/bold] {test_res.status_code or 'N/A'}\n\n"
                        "Please check if your session cookie expired or if the URL template is correct.",
                        border_style="red",
                    )
                )
                if not Confirm.ask("Do you still want to proceed with the remaining downloads?", default=False):
                    if Confirm.ask("Do you want to re-enter your session cookie?", default=True):
                        settings.cookie_value = Prompt.ask("Paste refreshed session cookie value", password=True).strip()
                    continue

        # 5. Batch Download Execution & Combination
        if Confirm.ask(f"Start downloading all [bold]{len(targets)}[/bold] admit cards into [cyan]{settings.output_dir}[/cyan]?", default=True):
            run_batch_download(settings, targets, force=False, prompt_combine=True)
            console.print(f"\n[bold green]🎉 Batch #{batch_number} Finished! Saved in:[/bold green] [cyan]{settings.output_dir.resolve()}[/cyan]")

        # 6. Ask for Next Batch or Exit
        console.print("\n" + "─" * 60)
        another_batch = Confirm.ask("[bold cyan]Do you want to download another batch of admit cards?[/bold cyan]", default=False)
        if not another_batch:
            console.print("\n[bold green]Thank you for using MidasDownloader! Goodbye 👋[/bold green]\n")
            break

        batch_number += 1


@app.command()
def download(
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to XLS, CSV, or TXT file containing entrance IDs (e.g. report/Report.xls)",
    ),
    student_ids: Optional[List[str]] = typer.Option(
        None,
        "--id",
        "-i",
        help="Single, multiple, or comma-separated entrance IDs (e.g. -i '41819, 41829, 41891')",
    ),
    id_range: Optional[str] = typer.Option(
        None,
        "--range",
        "-r",
        help="Range of numerical IDs (e.g. 41600-41650)",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="URL template with {student_id} placeholder",
    ),
    cookie: Optional[str] = typer.Option(
        None,
        "--cookie",
        "-c",
        help="Session cookie value (overrides .env)",
    ),
    cookie_name: Optional[str] = typer.Option(
        None,
        "--cookie-name",
        help="Cookie key name (default: ci_session)",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory to save downloaded admit cards (default: out/YYYY-MM-DD_HH-MM-SS)",
    ),
    delay: Optional[float] = typer.Option(
        None,
        "--delay",
        "-d",
        help="Delay in seconds between requests (default: 0.4s)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-download and overwrite existing admit cards",
    ),
    no_combine: bool = typer.Option(
        False,
        "--no-combine",
        help="Skip post-download PDF combination prompt",
    ),
    interactive_mode: bool = typer.Option(
        False,
        "--interactive",
        help="Run interactive guided wizard",
    ),
) -> None:
    """Download student admit cards in batch from university portal."""
    if interactive_mode or (not file and not student_ids and not id_range):
        interactive()
        return

    settings = Settings()

    if url:
        settings.url_template = url
    if cookie:
        settings.cookie_value = cookie
    if cookie_name:
        settings.cookie_name = cookie_name
    if output_dir:
        settings.output_dir = sanitize_file_path(output_dir)
    if delay is not None:
        settings.request_delay = delay

    if not settings.url_template:
        console.print(
            Panel(
                "[bold red]URL Template is required![/bold red]\n\n"
                "Please pass [bold]--url[/bold] with the template URL, e.g.:\n"
                '  [cyan]--url "https://portal.university.example.edu/entrance/report/prints?entranceid={student_id}&..."[/cyan]\n\n'
                "Or run interactive mode:\n"
                "  [bold]uv run midasdownloader[/bold]",
                title="URL Required",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    targets: List[StudentTarget] = []

    if file:
        try:
            targets.extend(parse_targets_from_file(file))
            console.print(f"[green]✔[/green] Loaded [bold]{len(targets)}[/bold] targets from [cyan]{file}[/cyan]")
        except Exception as e:
            console.print(f"[bold red]Error reading file:[/bold red] {e}")
            raise typer.Exit(code=1)

    if student_ids:
        for sid in student_ids:
            targets.extend(parse_targets_from_text(sid))

    if id_range:
        try:
            range_targets = parse_targets_from_range(id_range)
            targets.extend(range_targets)
            console.print(f"[green]✔[/green] Generated [bold]{len(range_targets)}[/bold] targets from range [cyan]{id_range}[/cyan]")
        except ValueError as e:
            console.print(f"[bold red]Range error:[/bold red] {e}")
            raise typer.Exit(code=1)

    targets = deduplicate_targets(targets)

    if not targets:
        interactive()
        return

    if not settings.cookie_value:
        console.print(
            Panel(
                "[bold red]Authentication cookie is missing![/bold red]\n\n"
                "Set it in your [cyan].env[/cyan] file:\n"
                "  [bold]ci_session[/bold]=your_cookie_value_here\n\n"
                "Or pass it directly via CLI:\n"
                "  [bold]--cookie[/bold] your_cookie_value_here\n\n"
                "Or run interactive mode:\n"
                "  [bold]uv run midasdownloader[/bold]",
                title="Cookie Required",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    run_batch_download(settings, targets, force=force, prompt_combine=not no_combine)


@app.command()
def check(
    test_id: str = typer.Argument(..., help="Sample entrance ID to test authentication and download"),
    url: str = typer.Option(..., "--url", "-u", help="URL template with {student_id}"),
    cookie: Optional[str] = typer.Option(None, "--cookie", "-c", help="Cookie value (overrides .env)"),
) -> None:
    """Test authentication and verify URL template with a single entrance ID."""
    settings = Settings()
    settings.url_template = url
    if cookie:
        settings.cookie_value = cookie

    if not settings.cookie_value:
        console.print("[bold red]Cookie is required for check. Set in .env or pass --cookie.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Testing admit card download for ID:[/cyan] [bold]{test_id}[/bold]")
    downloader = AdmitCardDownloader(settings)

    with downloader.create_client() as client:
        result = downloader.download_single(client, StudentTarget(student_id=test_id), force=True)

    if result.status == "success":
        console.print(
            Panel(
                f"[bold green]Authentication & Download Successful![/bold green]\n\n"
                f"[bold]Saved to:[/bold] {result.file_path}\n"
                f"[bold]File size:[/bold] {result.file_size_bytes:,} bytes\n"
                f"[bold]Status Code:[/bold] {result.status_code}",
                title="Check Passed",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]Download Failed![/bold red]\n\n"
                f"[bold]Error:[/bold] {result.error_message}\n"
                f"[bold]HTTP Status:[/bold] {result.status_code or 'N/A'}\n\n"
                "Please verify your cookie and URL template.",
                title="Check Failed",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command(name="init-env")
def init_env() -> None:
    """Create a sample .env file in the current directory."""
    env_file = Path(".env")
    if env_file.exists():
        console.print("[yellow].env file already exists! Please edit it directly.[/yellow]")
        return

    content = """# MidasDownloader Authentication Configuration
# 1. Your session cookie name (default: ci_session) and cookie value from Chrome DevTools
COOKIE_NAME="ci_session"
ci_session="PASTE_YOUR_CI_SESSION_COOKIE_VALUE_HERE"

# 2. Courtesy delay between requests in seconds (avoids overwhelming server)
REQUEST_DELAY="0.4"
"""
    env_file.write_text(content, encoding="utf-8")
    console.print("[green]✔ Created .env template! Open it to paste your ci_session cookie.[/green]")
