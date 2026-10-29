import pytest

from bd_packet_builder.scan import ScanTranscript, ScanVerificationError, check_agreement


@pytest.mark.parametrize(
    ("vision", "subject", "quote", "expected"),
    [
        ("Firm: Example LLC\nCRD: 001234", "Example LLC", "CRD: 001234", None),
        ("Firm: Example LLC\nCRD: 1234", "Example LLC", "CRD: 001234", "scan_quote_disagrees"),
        (
            "Firm: Clearing LLC\nCRD: 001234",
            "Clearing LLC",
            "CRD: 001234",
            "scan_subject_disagrees",
        ),
        ("Firm: Example LLC\nCRD: 001234", "Example LLC", "CRD: 009999", "scan_quote_disagrees"),
    ],
)
def test_independent_image_reading_must_agree_with_quote_and_subject(
    vision: str,
    subject: str,
    quote: str,
    expected: str | None,
) -> None:
    transcript = ScanTranscript(
        readable=True,
        subject=subject,
        text=vision,
        reporting_period=None,
    )
    if expected is None:
        check_agreement(transcript, "Example LLC", quote)
    else:
        with pytest.raises(ScanVerificationError, match=expected):
            check_agreement(transcript, "Example LLC", quote)


def test_unreadable_or_unknown_subject_never_passes() -> None:
    transcript = ScanTranscript(
        readable=False,
        subject=None,
        text="CRD: 001234",
        reporting_period=None,
    )
    with pytest.raises(ScanVerificationError, match="scan_page_unreadable"):
        check_agreement(transcript, "Example LLC", "CRD: 001234")
