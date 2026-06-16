from datetime import datetime, timezone

from app.models import ManualReview, ManualReviewStatus, ReviewResult, ReviewStatus, RiskLevel
from app.services.wecom_notifications import enqueue_review_notification, run_wecom_notification_worker


class FakeNotificationRepository:
    def __init__(self):
        self.items = []
        self.sent = []
        self.retried = []
        self.failed = []

    def enqueue_wecom_notification(self, **kwargs):
        item = {"id": len(self.items) + 1, "status": "queued", "attempts": 0, **kwargs}
        self.items.append(item)
        return item

    def list_due_wecom_notifications(self, now):
        return list(self.items)

    def mark_wecom_notification_sent(self, **kwargs):
        self.sent.append(kwargs)

    def mark_wecom_notification_retry(self, **kwargs):
        self.retried.append(kwargs)

    def mark_wecom_notification_failed(self, **kwargs):
        self.failed.append(kwargs)


class FakeWecomClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent = []

    def send_text_message(self, to_user_ids, content):
        if self.should_fail:
            raise RuntimeError("send failed")
        self.sent.append((to_user_ids, content))


def test_enqueue_review_notification_for_pending_manual_review(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "wecom_reviewer_user_ids", "u1,u2")
    monkeypatch.setattr(settings, "wecom_notification_base_url", "https://review.example.com")
    repository = FakeNotificationRepository()

    item = enqueue_review_notification(repository, _review_result(needs_manual=True))

    assert item is not None
    assert repository.items[0]["to_user_ids"] == ["u1", "u2"]
    assert "营业执照审核提醒" in repository.items[0]["message"]
    assert repository.items[0]["detail_url"] == "https://review.example.com/reviews/task-1"


def test_enqueue_review_notification_defaults_to_all_visible_wecom_users(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "wecom_reviewer_user_ids", "")
    monkeypatch.setattr(settings, "wecom_notification_base_url", "")
    repository = FakeNotificationRepository()

    enqueue_review_notification(repository, _review_result(needs_manual=True))

    assert repository.items[0]["to_user_ids"] == ["@all"]


def test_worker_sends_due_notifications():
    repository = FakeNotificationRepository()
    repository.items.append(
        {
            "id": 1,
            "to_user_ids": ["u1"],
            "message": "hello",
            "attempts": 0,
        }
    )
    client = FakeWecomClient()

    result = run_wecom_notification_worker(repository, client=client)

    assert result.processed == 1
    assert result.sent == 1
    assert client.sent == [(["u1"], "hello")]
    assert repository.sent[0]["notification_id"] == 1


def test_worker_retries_failed_notifications():
    repository = FakeNotificationRepository()
    repository.items.append(
        {
            "id": 1,
            "to_user_ids": ["u1"],
            "message": "hello",
            "attempts": 0,
        }
    )

    result = run_wecom_notification_worker(repository, client=FakeWecomClient(should_fail=True))

    assert result.retried == 1
    assert repository.retried[0]["attempts"] == 1
    assert repository.retried[0]["error"] == "send failed"


def _review_result(needs_manual: bool) -> ReviewResult:
    now = datetime.now(timezone.utc)
    return ReviewResult(
        task_id="task-1",
        use_case_name="business_license",
        use_case_version="v1",
        skill_name="business_license",
        skill_version="v1",
        ruleset_version="rules",
        capability_names=["business_license"],
        document_type="business_license",
        status=ReviewStatus.PENDING_MANUAL_REVIEW if needs_manual else ReviewStatus.REVIEWED,
        risk_level=RiskLevel.HIGH if needs_manual else RiskLevel.NONE,
        needs_manual_review=needs_manual,
        rule_results=[],
        summary="待人工复核",
        manual_review=ManualReview(
            status=ManualReviewStatus.PENDING if needs_manual else ManualReviewStatus.NOT_REQUIRED
        ),
        audit_events=[],
        created_at=now,
        updated_at=now,
        skill_result={},
    )
