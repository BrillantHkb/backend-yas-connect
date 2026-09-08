"""Exécute les scheduled_jobs dont next_execution <= now."""

import importlib
from datetime import datetime, timedelta

from croniter import croniter
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.config.models import ScheduledJob


class Command(BaseCommand):
    help = "Exécute les scheduled_jobs dont next_execution <= now."

    def handle(self, *args, **options):
        now = timezone.now()
        due = ScheduledJob.objects.filter(enabled=True, next_execution__lte=now)
        for job in due:
            module_path, func_name = job.handler.rsplit(".", 1)
            try:
                fn = getattr(importlib.import_module(module_path), func_name)
                fn()
                job.last_status = "OK"
                job.last_error = ""
            except Exception as exc:
                job.last_status = "ERROR"  # AD down : pas de coupure de masse (handler lève)
                job.last_error = str(exc)[:2000]
            job.last_execution = now
            if job.cron_expression:
                job.next_execution = croniter(job.cron_expression, now).get_next(datetime)
            elif job.interval_seconds:
                job.next_execution = now + timedelta(seconds=job.interval_seconds)
            job.save(
                update_fields=[
                    "last_status",
                    "last_error",
                    "last_execution",
                    "next_execution",
                    "updated_at",
                ]
            )
            self.stdout.write(f"{job.job_name}: {job.last_status}")
