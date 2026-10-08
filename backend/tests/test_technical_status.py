"""SCRUM-82: technical-status contract for SCRUM-24."""
import pytest
from app.modules.events import service
from app.modules.events.schemas import ReadinessState

@pytest.mark.parametrize("value", list(ReadinessState))
def test_technical_status_reads_the_existing_column(value):
    assert service.technical_status({"technical_readiness": value.value}) == value
