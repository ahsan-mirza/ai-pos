"""AxizPOS transactional email layout.

Colors match the landing page: orange #F26A21, ink #2B2B2B, light page background.
HTML is table-based with inline styles. Callers pass the real code, expiry, and support address.
Sample previews are returned by `sample_previews` and are never handed to the mailer.
"""

from __future__ import annotations

import html
from urllib.parse import urlparse

ACCENT = "#F26A21"
INK = "#2B2B2B"
MUTED = "#5C6570"
PAGE = "#F4F5F7"
LINE = "#E7E5E4"
CODE_WASH = "#FFF7F2"
NOTICE_WASH = "#FFF7ED"
FONT = "Arial, Helvetica, sans-serif"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def spaced_code(code: str) -> str:
    """Groups a 6-digit code for display. Any other value is returned unchanged."""
    digits = "".join(character for character in code if character.isdigit())
    if len(digits) == 6 and digits == code.strip():
        return f"{digits[:3]} {digits[3:]}"
    return code.strip()


def safe_http_url(url: str | None) -> str | None:
    """Accepts an http(s) URL with no embedded credentials. Anything else is dropped."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    return url.strip()


def verification_parts(*, code: str, minutes: int, support_email: str) -> tuple[str, str]:
    shown = spaced_code(code)
    plain = (
        f"Your AxizPOS verification code is {code.strip()}. It expires in {minutes} minutes.\n\n"
        "You're one step closer to getting started with AxizPOS. "
        "Enter the verification code to confirm your email address.\n\n"
        "Do not share this code. If you did not request it, you can ignore this email.\n\n"
        f"AxizPOS\n{support_email}"
    )
    html_body = _layout(
        eyebrow="AXIZPOS ACCOUNT SECURITY",
        heading="Verify your email address",
        paragraphs=[
            "You're one step closer to getting started with AxizPOS. "
            "Enter the verification code below to confirm your email address.",
        ],
        code=shown,
        notice=(
            f"This code expires in {minutes} minutes. Do not share it. "
            "If you did not request it, you can ignore this email."
        ),
        support_email=support_email,
    )
    return plain, html_body


def password_reset_parts(*, code: str, minutes: int, name: str, support_email: str) -> tuple[str, str]:
    greeting = f"Hi {name.strip()}," if name.strip() else "Hello,"
    plain = (
        f"{greeting}\n\n"
        f"Your AxizPOS password reset code is {code.strip()}. It expires in {minutes} minutes.\n\n"
        "Enter this code on the AxizPOS sign-in page to choose a new password. Do not share it.\n"
        "If you did not request a reset, you can ignore this email.\n\n"
        f"AxizPOS\n{support_email}"
    )
    html_body = _layout(
        eyebrow="AXIZPOS ACCOUNT SECURITY",
        heading="Reset your password",
        paragraphs=[
            greeting,
            "A password reset was requested for your AxizPOS account. "
            "Enter the code below on the sign-in page to choose a new password.",
        ],
        code=spaced_code(code),
        notice=(
            f"This code expires in {minutes} minutes. Do not share it. "
            "If you did not request a reset, you can ignore this email."
        ),
        support_email=support_email,
    )
    return plain, html_body


def notice_html(*, heading: str, body: str, support_email: str) -> str:
    """Branded HTML for an existing plain-text customer notice. The stored text stays the plain part."""
    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()] or [body.strip()]
    return _layout(
        eyebrow="AXIZPOS",
        heading=heading.strip() or "AxizPOS",
        paragraphs=paragraphs,
        support_email=support_email,
    )


def store_code_parts(*, code: str, minutes: int, support_email: str) -> tuple[str, str]:
    plain = (
        f"Your AxizPOS store-code verification is {code.strip()}. It expires in {minutes} minutes.\n\n"
        "Enter this code on the AxizPOS sign-in page. The store codes are shown only after the code is accepted.\n"
        "Do not share it. If you did not request this, you can ignore this email.\n\n"
        f"AxizPOS\n{support_email}"
    )
    html_body = _layout(
        eyebrow="AXIZPOS ACCOUNT SECURITY",
        heading="Confirm your email",
        paragraphs=[
            "Enter this code on the AxizPOS sign-in page to see the store codes registered to this email.",
        ],
        code=spaced_code(code),
        notice=(
            f"This code expires in {minutes} minutes. Do not share it. "
            "If you did not request this, you can ignore this email."
        ),
        support_email=support_email,
    )
    return plain, html_body


def store_code_result_parts(*, stores: list[tuple[str, str]], support_email: str) -> tuple[str, str]:
    """`stores` is (sign-in code, label). The label is the store name, with a branch when one is assigned."""
    lines = [f"{label}: {code}" for code, label in stores]
    listed = "\n".join(lines) if lines else "No store code is linked to this email."
    plain = (
        "These are the AxizPOS store codes registered to this email.\n\n"
        f"{listed}\n\n"
        "Use a store code on the sign-in page with your email and password. "
        "If you did not request this, contact support.\n\n"
        f"AxizPOS\n{support_email}"
    )
    html_body = _layout(
        eyebrow="AXIZPOS ACCOUNT SECURITY",
        heading="Your store codes",
        paragraphs=[
            "These store codes are registered to this email. Use one on the sign-in page.",
            listed,
        ],
        notice="If you did not request this, contact support. Do not forward this email.",
        support_email=support_email,
    )
    return plain, html_body


def password_changed_parts(*, support_email: str) -> tuple[str, str]:
    plain = (
        "The password for your AxizPOS portal account was changed.\n\n"
        "If you made this change, sign in with the new password. "
        "If you did not, contact support so the account can be locked.\n\n"
        f"AxizPOS\n{support_email}"
    )
    html_body = _layout(
        eyebrow="AXIZPOS ACCOUNT SECURITY",
        heading="Your password was changed",
        paragraphs=[
            "The password for your AxizPOS portal account was changed.",
            "If you made this change, sign in with the new password. "
            "If you did not, contact support so the account can be locked.",
        ],
        support_email=support_email,
    )
    return plain, html_body


def sample_previews(support_email: str = "support@axizpos.com") -> dict[str, tuple[str, str]]:
    """Sample renders. The code is 000000 and these values are not passed to a mailer."""
    return {
        "verification": verification_parts(code="000000", minutes=3, support_email=support_email),
        "password_reset": password_reset_parts(
            code="000000", minutes=10, name="Sample User", support_email=support_email
        ),
        "store_code": store_code_parts(code="000000", minutes=10, support_email=support_email),
        "store_code_result": store_code_result_parts(
            stores=[("sample", "Sample Store")], support_email=support_email
        ),
        "password_changed": password_changed_parts(support_email=support_email),
    }


def _layout(
    *,
    eyebrow: str,
    heading: str,
    paragraphs: list[str],
    support_email: str,
    code: str | None = None,
    notice: str | None = None,
    button_label: str | None = None,
    button_url: str | None = None,
) -> str:
    blocks = [
        f'<p style="margin:0 0 16px;font-family:{FONT};font-size:16px;line-height:24px;color:{INK};">{esc(part)}</p>'
        for part in paragraphs
    ]
    if code:
        blocks.append(
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            f'style="margin:0 0 20px;background:{CODE_WASH};border:1px solid #F6D3BF;border-radius:12px;">'
            "<tr><td align=\"center\" style=\"padding:22px 16px;\">"
            f'<p style="margin:0;font-family:Consolas,Courier New,monospace;font-size:32px;line-height:40px;'
            f'font-weight:700;letter-spacing:2px;color:{INK};">{esc(code)}</p>'
            "</td></tr></table>"
        )
    safe = safe_http_url(button_url)
    if button_label and safe:
        blocks.append(
            "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 0 20px;\">"
            "<tr><td align=\"center\" bgcolor=\""
            f'{ACCENT}" style="border-radius:12px;background:{ACCENT};">'
            f'<a href="{esc(safe)}" style="display:inline-block;padding:14px 28px;font-family:{FONT};'
            f'font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;">{esc(button_label)}</a>'
            "</td></tr></table>"
        )
    if notice:
        blocks.append(
            f'<p style="margin:0;padding:14px 16px;background:{NOTICE_WASH};border-radius:12px;'
            f'font-family:{FONT};font-size:14px;line-height:22px;color:{INK};">{esc(notice)}</p>'
        )
    support = esc(support_email)
    wordmark = (
        f'<p style="margin:0;font-family:{FONT};font-size:22px;font-weight:700;color:{INK};">'
        f'Axiz<span style="color:{ACCENT};">POS</span></p>'
    )
    eyebrow_html = (
        f'<p style="margin:0;font-family:{FONT};font-size:11px;font-weight:700;'
        f'letter-spacing:1px;color:{ACCENT};">{esc(eyebrow)}</p>'
    )
    heading_html = (
        f'<h1 style="margin:8px 0 16px;font-family:{FONT};font-size:24px;line-height:32px;'
        f'font-weight:700;color:{INK};">{esc(heading)}</h1>'
    )
    card = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:#ffffff;border:1px solid {LINE};border-radius:16px;">'
    )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'</head><body style="margin:0;padding:0;background:{PAGE};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};">'
        '<tr><td align="center" style="padding:32px 16px;">'
        f"{card}<tr><td style=\"padding:28px 32px 8px;\">{wordmark}</td></tr>"
        f'<tr><td style="padding:8px 32px 0;">{eyebrow_html}{heading_html}{"".join(blocks)}</td></tr>'
        '<tr><td style="padding:8px 32px 28px;">'
        f'<p style="margin:20px 0 0;font-family:{FONT};font-size:12px;line-height:18px;color:{MUTED};">'
        f'AxizPOS<br><a href="mailto:{support}" style="color:{MUTED};">{support}</a></p>'
        "</td></tr></table></td></tr></table></body></html>"
    )
