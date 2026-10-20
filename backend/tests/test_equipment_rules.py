"""SCRUM-24 equipment rules without I/O (app/modules/equipment/rules.py)."""

import pytest

from app.modules.equipment import rules
from app.modules.events.schemas import ReadinessState


class TestEquipmentReadiness:
    @pytest.mark.parametrize(("statuses", "expected"), [
        ([], ReadinessState.not_required),
        (["released"], ReadinessState.not_required),
        (["reserved", "released"], ReadinessState.ready),
        (["reserved", "reserved"], ReadinessState.ready),
        (["reserved", "pending"], ReadinessState.pending),
        (["reserved", "re_review"], ReadinessState.pending),
        (["reserved", "rejected"], ReadinessState.issue),
        (["pending", "rejected", "re_review"], ReadinessState.issue),
    ])
    def test_readiness_follows_the_live_lines(self, statuses, expected):
        assert rules.equipment_readiness(statuses) is expected


class TestLabels:
    @pytest.mark.parametrize(("status", "label"), [
        ("pending", "Pending"), ("reserved", "Reserved"), ("rejected", "Not available"),
        ("re_review", "Re-review"), ("released", "Released"), ("some_new_status", "Some new status"),
    ])
    def test_status_labels(self, status, label):
        assert rules.line_status_label(status) == label

    def test_line_label(self):
        assert rules.line_label(3, "4K Projector") == "3 × 4K Projector"
        assert rules.line_label(1, None) == "1 × equipment"
        assert rules.line_label(None, "4K Projector") is None
