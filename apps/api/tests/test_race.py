from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.messaging import MessageTemplate
from app.services import messaging_service, race
from app.services.message_defaults import DEFAULT_TEMPLATES


def test_losing_a_first_read_race_keeps_the_session_usable(session: Session) -> None:
    key, (name, subject, body) = next(iter(DEFAULT_TEMPLATES.items()))
    session.add(MessageTemplate(key=key, name=name, subject=subject, body=body))
    session.commit()

    # Another request inserted the same default a moment ago; this one must not fail the page.
    duplicate = MessageTemplate(key=key, name=name, subject=subject, body=body)
    assert race.add_if_absent(session, [duplicate]) is False
    assert session.scalar(select(func.count()).select_from(MessageTemplate)) == 1

    messaging_service.ensure_templates(session)
    session.commit()
    assert session.scalar(select(func.count()).select_from(MessageTemplate)) == len(DEFAULT_TEMPLATES)
    assert race.add_if_absent(session, []) is True
