"""The background job runner behind the site's long-running analysis."""

import time

import pytest

from tradingbot.web.jobs import Cancelled, JobRunner, JobState


def wait_for(runner, job_id, states, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = runner.get(job_id)
        if job and job.state in states:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {states}")


def test_a_job_runs_and_returns_its_result():
    runner = JobRunner()
    job = runner.submit("test", lambda ctx: {"answer": 42})
    finished = wait_for(runner, job.id, {JobState.DONE})
    assert finished.result == {"answer": 42}
    assert finished.progress == 1.0


def test_progress_is_reported_as_the_job_advances():
    runner = JobRunner()
    seen = []

    def work(ctx):
        for i in range(4):
            ctx.progress(i / 4, f"step {i}")
            seen.append(i)
            time.sleep(0.01)
        return {}

    job = runner.submit("test", work)
    wait_for(runner, job.id, {JobState.DONE})
    assert seen == [0, 1, 2, 3]
    assert runner.get(job.id).message.startswith("step")


def test_a_failing_job_records_the_error_and_does_not_raise():
    """One bad job must never take the server down."""
    runner = JobRunner()
    job = runner.submit("test", lambda ctx: (_ for _ in ()).throw(ValueError("boom")))
    finished = wait_for(runner, job.id, {JobState.FAILED})
    assert finished.error == "boom"
    assert finished.result is None


def test_an_error_with_no_message_still_reports_something():
    runner = JobRunner()
    job = runner.submit("test", lambda ctx: (_ for _ in ()).throw(RuntimeError()))
    assert wait_for(runner, job.id, {JobState.FAILED}).error == "RuntimeError"


def test_a_job_can_be_cancelled_at_a_progress_checkpoint():
    runner = JobRunner()

    def slow(ctx):
        for i in range(500):
            ctx.progress(i / 500)
            time.sleep(0.005)
        return {"finished": True}

    job = runner.submit("test", slow)
    wait_for(runner, job.id, {JobState.RUNNING})
    assert runner.cancel(job.id)
    finished = wait_for(runner, job.id, {JobState.CANCELLED})
    assert finished.result is None


def test_cancelling_a_finished_job_reports_that_it_is_too_late():
    runner = JobRunner()
    job = runner.submit("test", lambda ctx: {})
    wait_for(runner, job.id, {JobState.DONE})
    assert not runner.cancel(job.id)


def test_cancelling_an_unknown_job_is_false_not_an_error():
    assert not JobRunner().cancel("nope")


def test_a_job_that_ignores_cancellation_still_finishes():
    """Cancellation is cooperative; a job with no checkpoints simply completes."""
    runner = JobRunner()
    job = runner.submit("test", lambda ctx: {"done": True})
    wait_for(runner, job.id, {JobState.DONE})
    assert runner.get(job.id).result == {"done": True}


def test_jobs_are_listed_newest_first():
    runner = JobRunner()
    ids = []
    for _ in range(3):
        ids.append(runner.submit("test", lambda ctx: {}).id)
        time.sleep(0.01)
    for job_id in ids:
        wait_for(runner, job_id, {JobState.DONE})
    assert [j.id for j in runner.list_jobs()][:3] == list(reversed(ids))


def test_finished_jobs_are_evicted_once_stale():
    runner = JobRunner(retention_seconds=0)
    first = runner.submit("test", lambda ctx: {})
    wait_for(runner, first.id, {JobState.DONE})
    time.sleep(0.01)
    runner.submit("test", lambda ctx: {})  # triggers eviction
    assert runner.get(first.id) is None


def test_running_jobs_are_never_evicted():
    runner = JobRunner(retention_seconds=0, max_jobs=1)

    def slow(ctx):
        time.sleep(0.4)
        return {}

    running = runner.submit("test", slow)
    wait_for(runner, running.id, {JobState.RUNNING})
    for _ in range(4):
        runner.submit("test", lambda ctx: {})
    assert runner.get(running.id) is not None


def test_shutdown_signals_every_running_job():
    runner = JobRunner()

    def slow(ctx):
        for i in range(500):
            ctx.progress(i / 500)
            time.sleep(0.005)
        return {}

    job = runner.submit("test", slow)
    wait_for(runner, job.id, {JobState.RUNNING})
    runner.shutdown()
    assert wait_for(runner, job.id, {JobState.CANCELLED}).state is JobState.CANCELLED


def test_a_job_serialises_for_the_api():
    runner = JobRunner()
    job = runner.submit("validate", lambda ctx: {"ok": True})
    payload = wait_for(runner, job.id, {JobState.DONE}).as_dict()
    assert {"id", "kind", "state", "progress", "result", "elapsed_seconds"} <= set(payload)
    assert payload["kind"] == "validate"


def test_finished_states_are_marked_as_such():
    assert JobState.DONE.finished and JobState.FAILED.finished and JobState.CANCELLED.finished
    assert not JobState.RUNNING.finished and not JobState.QUEUED.finished
