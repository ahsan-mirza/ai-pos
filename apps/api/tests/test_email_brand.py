"""Branded AxizPOS mail: layout, escaping, and the multipart message. Samples are not sent."""

from email.message import EmailMessage

from app.services.email_brand import (
    notice_html,
    password_reset_parts,
    safe_http_url,
    sample_previews,
    spaced_code,
    verification_parts,
)
from app.services.messaging_providers import Outgoing, build_email


def test_verification_uses_the_real_code_and_expiry():
    plain, html_body = verification_parts(code="482916", minutes=3, support_email="support@axizpos.com")
    assert "is 482916" in plain
    assert "3 minutes" in plain and "3 minutes" in html_body
    assert "482 916" in html_body
    assert "#F26A21" in html_body
    assert "Axiz" in html_body and "Verify your email address" in html_body
    assert "000000" not in plain and "000000" not in html_body


def test_password_reset_greets_a_name_and_keeps_a_contiguous_code():
    plain, html_body = password_reset_parts(
        code="120034", minutes=10, name="Sara", support_email="support@axizpos.com"
    )
    assert "Hi Sara," in plain and "Hi Sara," in html_body
    assert "is 120034" in plain
    assert "120 034" in html_body
    assert "10 minutes" in html_body
    unnamed, _ = password_reset_parts(code="120034", minutes=10, name="  ", support_email="support@axizpos.com")
    assert unnamed.startswith("Hello,")


def test_user_content_is_escaped_and_unsafe_links_are_dropped():
    html_body = notice_html(
        heading="<script>",
        body='Hello <b>there</b>\n\nSee javascript:alert(1)',
        support_email="support@axizpos.com",
    )
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
    assert "&lt;b&gt;" in html_body
    assert safe_http_url("javascript:alert(1)") is None
    assert safe_http_url("https://user:secret@axizpos.com/reset") is None
    assert safe_http_url("https://portal.axizpos.com/login") == "https://portal.axizpos.com/login"


def test_sample_previews_are_marked_sample_data():
    samples = sample_previews()
    assert set(samples) == {
        "verification",
        "password_reset",
        "store_code",
        "store_code_result",
        "password_changed",
    }
    for key in ("verification", "password_reset", "store_code"):
        plain, html_body = samples[key]
        assert "000000" in plain
        assert "000 000" in html_body
        assert "support@axizpos.com" in html_body
    assert "Sample Store" in samples["store_code_result"][0]
    assert "account was changed" in samples["password_changed"][0].lower()


def test_one_render_does_not_include_another_recipients_name():
    sara, _ = password_reset_parts(code="111111", minutes=10, name="Sara", support_email="support@axizpos.com")
    omar, _ = password_reset_parts(code="222222", minutes=10, name="Omar", support_email="support@axizpos.com")
    assert "Omar" not in sara
    assert "Sara" not in omar
    assert "111111" not in omar


def test_html_alternative_stays_with_the_plain_part_and_a_pdf():
    message = build_email(
        Outgoing(
            to="owner@example.com",
            subject="Verify your AxizPOS email",
            body="Your AxizPOS verification code is 482916.",
            html=verification_parts(code="482916", minutes=3, support_email="support@axizpos.com")[1],
            attachment=("invoice.pdf", b"%PDF"),
        ),
        "AxizPOS <pos@example.com>",
    )
    assert isinstance(message, EmailMessage)
    assert message.get_body(preferencelist=("plain",)).get_content().strip().endswith("482916.")
    assert "482 916" in message.get_body(preferencelist=("html",)).get_content()
    attachments = list(message.iter_attachments())
    assert attachments and attachments[0].get_filename() == "invoice.pdf"


def test_code_spacing_leaves_non_codes_alone():
    assert spaced_code("482916") == "482 916"
    assert spaced_code("12") == "12"
