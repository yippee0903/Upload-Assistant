# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from typing import Any, Optional, cast

import cli_ui
from typing_extensions import TypeAlias

from cogs.redaction import Redaction
from src.cleanup import cleanup_manager
from src.get_desc import DescriptionBuilder
from src.manualpackage import ManualPackageManager
from src.trackersetup import TRACKER_SETUP

Meta: TypeAlias = dict[str, Any]
StatusDict: TypeAlias = dict[str, Any]


async def check_mod_q_and_draft(
    tracker_class: Any,
    meta: Meta,
) -> tuple[Optional[str], Optional[str], dict[str, Any]]:
    tracker_capabilities = {
        "AITHER": {"mod_q": True, "draft": False},
        "BHD": {"draft_live": True},
        "BLU": {"mod_q": True, "draft": False},
        "LST": {"mod_q": True, "draft": True},
        "LT": {"mod_q": True, "draft": False},
        "LUME": {"mod_q": True, "draft": False},
    }

    modq, draft = None, None
    tracker_caps = tracker_capabilities.get(tracker_class.tracker, {})
    if tracker_class.tracker == "BHD" and tracker_caps.get("draft_live"):
        draft_int = await tracker_class.get_live(meta)
        draft = "Draft" if draft_int == 0 else "Live"

    else:
        if tracker_caps.get("mod_q"):
            modq_flag = await tracker_class.get_flag(meta, "modq")
            modq_enabled = str(modq_flag).lower() in ["1", "true", "yes"]
            modq = "Yes" if modq_enabled else "No"
        if tracker_caps.get("draft"):
            draft_flag = await tracker_class.get_flag(meta, "draft")
            draft_enabled = str(draft_flag).lower() in ["1", "true", "yes"]
            draft = "Yes" if draft_enabled else "No"

    return modq, draft, tracker_caps


async def process_trackers(
    meta: Meta,
    config: dict[str, Any],
    client: Any,
    console: Any,
    api_trackers: Sequence[str],
    tracker_class_map: Mapping[str, Any],
) -> None:
    tracker_setup = TRACKER_SETUP(config=config)
    tracker_setup_any = cast(Any, tracker_setup)
    enabled_trackers = list(cast(Sequence[str], tracker_setup_any.trackers_enabled(meta)))
    manual_packager = ManualPackageManager(config)

    def print_tracker_result(
        tracker: str,
        tracker_class: Any,
        status: Mapping[str, Any],
        is_success: bool,
    ) -> None:
        """Print tracker upload result immediately after upload completes."""
        try:
            # Check config settings for what to print
            print_links = meta.get("print_tracker_links", True)
            print_messages = meta.get("print_tracker_messages", False)

            # If neither option is enabled, don't print anything
            if not print_links and not print_messages:
                return

            message = None
            if is_success:
                if tracker == "MTV" and "status_message" in status and "data error" not in str(status["status_message"]):
                    if print_links:
                        message = f"[green]{str(status['status_message'])}[/green]"
                elif "torrent_id" in status and print_links:
                    torrent_url = str(getattr(tracker_class, "torrent_url", ""))
                    message = f"[green]{torrent_url}{status['torrent_id']}[/green]"
                elif "status_message" in status and "data error" not in str(status["status_message"]) and (print_messages or (print_links and "torrent_id" not in status)):
                    message = f"{tracker}: {Redaction.redact_private_info(status['status_message'])}"
            else:
                if "status_message" in status and "data error" in str(status["status_message"]):
                    console.print(f"[red]{tracker}: {str(status['status_message'])}[/red]")
                    return

            if message is not None:
                if config["DEFAULT"].get("show_upload_duration", True) or meta.get("upload_timer", True):
                    duration = meta.get(f"{tracker}_upload_duration")
                    if duration and isinstance(duration, (int, float)):
                        color = "#21ff00" if duration < 5 else "#9fd600" if duration < 10 else "#cfaa00" if duration < 15 else "#f17100" if duration < 20 else "#ff0000"
                        message += f" [[{color}]{duration:.2f}s[/{color}]]"
                console.print(message)
        except Exception as e:
            console.print(f"[red]Error printing {tracker} result: {e}[/red]")

    async def process_single_tracker(tracker: str) -> None:
        if str(meta.get("name", "")).endswith("DUPE?"):
            meta["name"] = str(meta.get("name", "")).replace(" DUPE?", "")

        disctype = cast(Optional[str], meta.get("disctype"))
        disctype_value = str(disctype) if disctype is not None else ""
        tracker = tracker.replace(" ", "").upper().strip()

        if tracker == "MANUAL":
            if meta["unattended"]:
                do_manual = True
            else:
                try:
                    do_manual = cli_ui.ask_yes_no("Get files for manual upload?", default=True)
                except EOFError:
                    console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                    await cleanup_manager.cleanup()
                    cleanup_manager.reset_terminal()
                    sys.exit(1)
            if do_manual:
                for manual_tracker in enabled_trackers:
                    if manual_tracker != "MANUAL":
                        manual_tracker = manual_tracker.replace(" ", "").upper().strip()
                        tracker_class = tracker_class_map[manual_tracker](config=config)
                        if manual_tracker in api_trackers:
                            await DescriptionBuilder(manual_tracker, config).unit3d_edit_desc(meta, manual_tracker)
                        else:
                            await tracker_class.edit_desc(meta)
                url = await manual_packager.package(meta)
                if url is False:
                    console.print(f"[yellow]Unable to upload prep files, they can be found at `tmp/{meta['uuid']}")
                else:
                    console.print(f"[green]{meta['name']}")
                    console.print(f"[green]Files can be found at: [yellow]{url}[/yellow]")

            return

        tracker_status = cast(StatusDict, meta.get("tracker_status") or {})
        if not cast(Mapping[str, Any], tracker_status.get(tracker, {})).get("upload", False):
            return

        tracker_class: Any = tracker_class_map[tracker](config=config)
        is_uploaded: Optional[bool] = False
        try:
            if tracker in api_trackers:
                modq, draft, tracker_caps = await check_mod_q_and_draft(tracker_class, meta)
                if tracker_caps.get("mod_q") and modq == "Yes":
                    console.print(f"{tracker} (modq: {modq})")
                if (tracker_caps.get("draft") or tracker_caps.get("draft_live")) and draft in ["Yes", "Draft"]:
                    console.print(f"{tracker} (draft: {draft})")
            try:
                upload_start_time = time.time()
                is_uploaded = await tracker_class.upload(meta, disctype_value)
                meta[f"{tracker}_upload_duration"] = time.time() - upload_start_time
            except Exception as e:
                console.print(f"[red]Upload failed: {e}")
                console.print(traceback.format_exc())
                return
            post_upload_delay = getattr(tracker_class, "post_upload_delay", 0)
            if post_upload_delay:
                await asyncio.sleep(post_upload_delay)
        except Exception:
            console.print(traceback.format_exc())
            return

        if is_uploaded is None:
            console.print(f"[yellow]Warning: {tracker_class.tracker} upload method returned None instead of boolean. Treating as failed upload.[/yellow]")
            is_uploaded = False

        status = cast(StatusDict, meta.get("tracker_status") or {}).get(tracker_class.tracker, {})
        if is_uploaded and "status_message" in status and "data error" not in str(status["status_message"]):
            await client.add_to_client(meta, tracker_class.tracker)
            print_tracker_result(tracker, tracker_class, status, True)
        else:
            print_tracker_result(tracker, tracker_class, status, False)
            console.print(f"[red]{tracker} upload failed or returned data error.[/red]")

    multi_screens = int(config["DEFAULT"].get("multiScreens", 2))
    discs = cast(list[Any], meta.get("discs") or [])
    one_disc = True
    if discs and len(discs) == 1:
        one_disc = True
    elif discs and len(discs) > 1:
        one_disc = False

    filelist = cast(list[str], meta.get("filelist") or [])
    # Use sequential processing when there are multiple video files (pack), regardless
    # of whether tv_pack was correctly set — belt-and-suspenders guard.
    has_multiple_files = len(filelist) > 1 or bool(meta.get("tv_pack"))

    if (not has_multiple_files and one_disc) or multi_screens == 0:
        # Run all tracker tasks concurrently with individual error handling
        tasks: list[tuple[str, asyncio.Task[None]]] = []
        for tracker in enabled_trackers:
            task = asyncio.create_task(process_single_tracker(tracker))
            tasks.append((tracker, task))

        # Wait for all tasks to complete, but don't let one tracker's failure stop others
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

        # Log any exceptions that occurred
        for (tracker, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                console.print(f"[red]{tracker} encountered an error: {result}[/red]")
                if meta.get("debug"):
                    console.print(traceback.format_exception(type(result), result, result.__traceback__))
    else:
        # Process each tracker sequentially
        for tracker in enabled_trackers:
            await process_single_tracker(tracker)

    console.print("[green]All tracker uploads processed.[/green]")
