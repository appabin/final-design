from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from datetime import datetime, time, timedelta
from typing import Any

from ..config import Settings
from ..db import SQLiteStore


class ReminderService:
    def __init__(self, *, settings: Settings, db: SQLiteStore):
        self.settings = settings
        self.db = db
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def create_from_email_skill(
        self,
        *,
        input_text: str,
        metadata: dict[str, Any],
        title: str | None = None,
    ) -> dict[str, Any]:
        text = input_text.strip()
        if not text:
            raise ValueError("input_text is empty")

        remind_at = self._resolve_remind_at(text=text, metadata=metadata)
        now = datetime.now().astimezone()
        if remind_at <= now:
            raise ValueError("reminder_at must be in the future")

        reminder_title = (
            str(metadata.get("reminder_title") or metadata.get("title") or title or "").strip()
            or self._infer_title(text)
        )
        body = str(metadata.get("body") or self._infer_body(text)).strip()
        if not body:
            body = text[:280]

        calendar_event_id: str | None = None
        calendar_error: str | None = None
        if self._macos_calendar_requested(metadata):
            if sys.platform != "darwin":
                calendar_error = "macOS Calendar integration is only available on macOS"
            else:
                calendar_event_id, calendar_error = self._create_macos_calendar_event(
                    title=reminder_title[:120],
                    body=body[:500],
                    remind_at=remind_at,
                    calendar_name=str(
                        metadata.get("macos_calendar_name")
                        or self.settings.hachi_macos_calendar_name
                        or "Hachi"
                    ).strip()
                    or "Hachi",
                )

        return self.db.create_reminder(
            title=reminder_title[:120],
            body=body[:500],
            remind_at=remind_at.isoformat(),
            remind_at_epoch=remind_at.timestamp(),
            source_text=text[:4000],
            calendar_event_id=calendar_event_id,
            calendar_error=calendar_error,
        )

    def list_reminders(self, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        clean_status = status if status in {"pending", "fired"} else None
        return self.db.list_reminders(limit=limit, status=clean_status)

    async def _run_loop(self) -> None:
        interval = max(2.0, float(self.settings.reminder_poll_interval_seconds))
        while not self._stopped.is_set():
            try:
                await self._fire_due_reminders()
            except Exception:
                # Reminder delivery must not terminate the application service.
                pass
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _fire_due_reminders(self) -> None:
        due = self.db.get_due_reminders(datetime.now().astimezone().timestamp())
        for reminder in due:
            await asyncio.to_thread(self._notify, reminder)
            self.db.mark_reminder_fired(str(reminder["id"]))

    def _notify(self, reminder: dict[str, Any]) -> None:
        if not self.settings.hachi_enable_desktop_notifications:
            return

        title = str(reminder.get("title") or "Hachi 邮件提醒")
        body = str(reminder.get("body") or "")
        if sys.platform == "darwin":
            script = (
                f"display notification {self._osa_quote(body)} "
                f"with title {self._osa_quote(title)}"
            )
            subprocess.run(["osascript", "-e", script], check=False, timeout=8)
            return

        if sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, body], check=False, timeout=8)
            return

    def _macos_calendar_requested(self, metadata: dict[str, Any]) -> bool:
        if "macos_calendar" in metadata:
            return self._truthy(metadata.get("macos_calendar"))
        return bool(self.settings.hachi_enable_macos_calendar_reminders)

    def _create_macos_calendar_event(
        self,
        *,
        title: str,
        body: str,
        remind_at: datetime,
        calendar_name: str,
    ) -> tuple[str | None, str | None]:
        script = """
on run argv
  set calendarName to item 1 of argv
  set eventTitle to item 2 of argv
  set eventBody to item 3 of argv
  set eventYear to item 4 of argv as integer
  set eventMonthIndex to item 5 of argv as integer
  set eventDay to item 6 of argv as integer
  set eventHour to item 7 of argv as integer
  set eventMinute to item 8 of argv as integer
  set durationMinutes to item 9 of argv as integer
  set monthValues to {January, February, March, April, May, June, July, August, September, October, November, December}

  tell application "Calendar"
    set targetCalendar to missing value
    repeat with oneCalendar in calendars
      if name of oneCalendar is calendarName then
        set targetCalendar to oneCalendar
        exit repeat
      end if
    end repeat

    if targetCalendar is missing value then
      set targetCalendar to make new calendar with properties {name:calendarName}
    end if

    set startDate to current date
    set year of startDate to eventYear
    set month of startDate to item eventMonthIndex of monthValues
    set day of startDate to eventDay
    set time of startDate to (eventHour * 3600 + eventMinute * 60)
    set endDate to startDate + (durationMinutes * 60)

    set newEvent to make new event at end of events of targetCalendar with properties {summary:eventTitle, description:eventBody, start date:startDate, end date:endDate}
    make new display alarm at end of display alarms of newEvent with properties {trigger interval:0}
    return uid of newEvent
  end tell
end run
"""
        local_time = remind_at.astimezone()
        duration = max(1, int(self.settings.hachi_macos_calendar_event_duration_minutes))
        args = [
            "osascript",
            "-e",
            script,
            calendar_name,
            title,
            body,
            str(local_time.year),
            str(local_time.month),
            str(local_time.day),
            str(local_time.hour),
            str(local_time.minute),
            str(duration),
        ]
        try:
            completed = subprocess.run(
                args,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            return None, "osascript is not available"
        except subprocess.TimeoutExpired:
            return None, "Timed out while creating macOS Calendar event"

        if completed.returncode != 0:
            return None, (completed.stderr or completed.stdout or "Calendar event creation failed").strip()
        return (completed.stdout or "").strip() or None, None

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}

    def _resolve_remind_at(self, *, text: str, metadata: dict[str, Any]) -> datetime:
        raw = str(metadata.get("reminder_at") or metadata.get("remind_at") or "").strip()
        if raw:
            return self._parse_datetime(raw)

        inferred = self._extract_datetime_from_text(text)
        if inferred is None:
            raise ValueError("reminder_at is required for email_reminder skill")
        return inferred

    def _parse_datetime(self, raw: str) -> datetime:
        value = raw.strip()
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"

        normalized = value.replace("/", "-")
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{2}", normalized):
            normalized = normalized.replace(" ", "T")

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            match = re.search(
                r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{2})",
                value,
            )
            if not match:
                raise ValueError("Unable to parse reminder_at")
            parsed = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
            )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed.astimezone()

    def _extract_datetime_from_text(self, text: str) -> datetime | None:
        patterns = [
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}",
            r"\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._parse_datetime(match.group(0))

        now = datetime.now().astimezone()
        rel = re.search(r"(今天|明天|后天)\s*(\d{1,2})[:：点](\d{2})?", text)
        if rel:
            days = {"今天": 0, "明天": 1, "后天": 2}[rel.group(1)]
            hour = int(rel.group(2))
            minute = int(rel.group(3) or 0)
            target_date = (now + timedelta(days=days)).date()
            return datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=now.tzinfo)
        return None

    def _infer_title(self, text: str) -> str:
        for pattern in [
            r"(?:邮件主题|主题|Subject)[:：]\s*(.+)",
            r"(?:标题|事项)[:：]\s*(.+)",
        ]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return f"邮件提醒：{match.group(1).strip()[:80]}"
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "邮件提醒")
        return f"邮件提醒：{first_line[:80]}"

    def _infer_body(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for label in ("截止", "回复", "会议", "时间", "地点", "发件人", "From"):
            for line in lines:
                if label.lower() in line.lower():
                    return line[:500]
        return "；".join(lines[:3])[:500]

    def _osa_quote(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
