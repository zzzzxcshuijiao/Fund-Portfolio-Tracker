"""APScheduler job definitions for periodic tasks."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.database import SessionLocal
from backend.services.nav_service import NavService
from backend.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def job_refresh_nav():
    """Fetch latest NAV for all held funds (workday 20:00)."""
    logger.info("Scheduled job: refreshing NAV for all funds")
    db = SessionLocal()
    try:
        result = await NavService(db).refresh_all_nav()
        logger.info(f"NAV refresh result: {result}")
    except Exception as e:
        logger.error(f"NAV refresh failed: {e}")
    finally:
        db.close()


async def job_retry_nav():
    """Retry NAV fetch for funds still missing (workday 22:00)."""
    logger.info("Scheduled job: retrying NAV for missing funds")
    db = SessionLocal()
    try:
        result = await NavService(db).refresh_all_nav()
        logger.info(f"NAV retry result: {result}")
    except Exception as e:
        logger.error(f"NAV retry failed: {e}")
    finally:
        db.close()


async def job_daily_snapshot():
    """Create daily portfolio snapshot (workday 22:30)."""
    logger.info("Scheduled job: creating daily snapshot")
    db = SessionLocal()
    try:
        snapshot = SnapshotService(db).create_daily_snapshot()
        logger.info(f"Snapshot created: {snapshot.snapshot_date}, MV={snapshot.total_market_value}")
    except Exception as e:
        logger.error(f"Snapshot creation failed: {e}")
    finally:
        db.close()


async def job_startup_backfill():
    """Check and backfill missed NAV data on startup."""
    logger.info("Startup job: checking for missed NAV data")
    db = SessionLocal()
    try:
        svc = NavService(db)
        status = svc.get_nav_status()
        if status["funds_missing_nav"] > 0:
            logger.info(f"Backfilling NAV for {status['funds_missing_nav']} funds")
            result = await svc.refresh_all_nav()
            logger.info(f"Startup backfill result: {result}")
        else:
            logger.info("All funds have NAV data, no backfill needed")
    except Exception as e:
        logger.error(f"Startup backfill failed: {e}")
    finally:
        db.close()


def setup_scheduler():
    """Configure and return the scheduler with all jobs."""
    # Weekday NAV refresh at 20:00
    scheduler.add_job(
        job_refresh_nav,
        CronTrigger(day_of_week="mon-fri", hour=20, minute=0),
        id="refresh_nav",
        replace_existing=True,
    )

    # Weekday NAV retry at 22:00
    scheduler.add_job(
        job_retry_nav,
        CronTrigger(day_of_week="mon-fri", hour=22, minute=0),
        id="retry_nav",
        replace_existing=True,
    )

    # Weekday snapshot at 22:30
    scheduler.add_job(
        job_daily_snapshot,
        CronTrigger(day_of_week="mon-fri", hour=22, minute=30),
        id="daily_snapshot",
        replace_existing=True,
    )

    return scheduler
