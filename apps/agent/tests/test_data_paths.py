from pathlib import Path
import subprocess
import sys
import textwrap


def test_canonical_app_data_paths():
    from app.paths import APP_DATA_DIR, DIGITAL_HUMAN_IMAGE_DIR, DIGITAL_HUMAN_METADATA_DIR, RAG_DATA_DIR

    agent_root = Path(__file__).resolve().parents[1]

    assert APP_DATA_DIR == agent_root / "app" / "data"
    assert RAG_DATA_DIR == APP_DATA_DIR / "rag"
    assert DIGITAL_HUMAN_IMAGE_DIR == APP_DATA_DIR / "digital-human" / "images" / "realistic"
    assert DIGITAL_HUMAN_METADATA_DIR == APP_DATA_DIR / "digital-human" / "metadata"


def test_main_static_mount_uses_canonical_app_data_dir():
    # main constructs a process-owned assembly on import. Isolate that import
    # and close its owners instead of leaking its database lock/registries into
    # every later Runtime fixture in this pytest process.
    subprocess.run([sys.executable, '-c', textwrap.dedent('''
        import asyncio
        import app.main as main
        from app.paths import APP_DATA_DIR
        from app.lifespan import run_cleanups
        from app.execution.wiring import aclose_runtime
        try:
            assert main._data_dir == APP_DATA_DIR
        finally:
            async def close():
                failures = await run_cleanups([
                    ('coordinator', main.coordinator.shutdown),
                    ('model_setup', main.model_setup.close),
                    ('runtime', lambda: aclose_runtime(main.runtime)),
                ])
                assert not failures, failures
            asyncio.run(close())
    ''')], check=True, timeout=120)


def test_digital_human_service_uses_canonical_paths():
    from app.paths import DIGITAL_HUMAN_IMAGE_DIR, DIGITAL_HUMAN_METADATA_DIR
    from app.services.digitalhumanservice import digital_human_service

    assert digital_human_service.generator.avatar_image_dir == DIGITAL_HUMAN_IMAGE_DIR
    assert digital_human_service.avatar_metadata_dir == DIGITAL_HUMAN_METADATA_DIR
