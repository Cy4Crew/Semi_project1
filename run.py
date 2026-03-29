from __future__ import annotations

import argparse
import asyncio
import uvicorn

from app.api.main import app
from app.core.config import settings
from app.core.db import close_pool, open_pool, get_conn
from app.core.logging import setup_logging
from app.crawler.scheduler import scheduler
from app.init_db import init_db
from app.notifier.worker import alert_worker
from app.repository.targets import reset_queued_targets
# [추가] 텔레그램 수집기 브릿지 병합
from app.telegram.telegram_bridge import run_bridge as run_tg_bridge


def run_api() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


async def run_crawler() -> None:
    await scheduler.run()


async def run_alert_worker() -> None:
    await alert_worker.run()


# 텔레그램 브릿지의 예외 처리를 위한 래퍼 함수 병합
async def _safe_tg_bridge():
    try:
        await run_tg_bridge()
    except Exception as e:
        print(f"[TELEGRAM-BRIDGE] 치명적 오류: {e}")
        import traceback
        traceback.print_exc()


async def run_all() -> None:
    api_config = uvicorn.Config(app, host=settings.api_host, port=settings.api_port, log_level="info")
    api_server = uvicorn.Server(api_config)
    
    # 모든 서비스(API, Crawler, Alert, Telegram)를 태스크 리스트에 포함
    tasks = [
        asyncio.create_task(api_server.serve()),
        asyncio.create_task(run_crawler()),
        asyncio.create_task(run_alert_worker()),
        asyncio.create_task(_safe_tg_bridge()),  # 텔레그램 브릿지 태스크 추가
    ]
    
    try:
        await asyncio.gather(*tasks)
    finally:
        # 종료 시 모든 태스크 취소
        for task in tasks:
            task.cancel()


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=["all", "api", "crawler", "alert_worker", "init_db"],
    )
    args = parser.parse_args()

    open_pool()

    if args.mode == "init_db":
        init_db(load_seed_data=True)
        close_pool()
        return

    if args.mode in {"all", "api", "crawler", "alert_worker"}:
        init_db(load_seed_data=True)

    # 대기 중인 타겟 상태 초기화
    with get_conn() as conn:
        reset_queued_targets(conn)
        conn.commit()

    try:
        if args.mode == "api":
            run_api()
        elif args.mode == "crawler":
            asyncio.run(run_crawler())
        elif args.mode == "alert_worker":
            asyncio.run(run_alert_worker())
        else:
            # 기본값 'all'일 때 모든 비동기 서비스 실행
            asyncio.run(run_all())
    finally:
        close_pool()


if __name__ == "__main__":
    main()