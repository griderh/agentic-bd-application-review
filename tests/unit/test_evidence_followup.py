import pytest

from bd_packet_builder.followup import MinimumAmountCheck, minimum_amount_result

CHECK = MinimumAmountCheck(
    criterion_quote="minimum net capital of $10 million on line 3750",
    field_label="Net capital",
    line_label="3750",
)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("9,999,999.99", False),
        ("10,000,000", True),
        ("12,345,678", True),
    ],
)
def test_minimum_amount_compares_exact_USD_threshold(amount, expected):
    row = f"Net capital $ {amount} [3750]"
    result = minimum_amount_result(CHECK, amount, (row, row.replace("[3750]", "3750")))
    assert result["value"] == amount.replace(",", "")
    assert result["minimum"] == "10000000"
    assert result["meets_minimum"] is expected


@pytest.mark.parametrize(
    "rows",
    [
        (),
        ("Net capital 12,345,678 3750", "Net capital 12,345,678 3760"),
        ("Net capital 12,345,678\n3750", "Net capital 12,345,678 3750"),
        ("Net capital 12,345,678 3750\nNet capital 12,345,678 3750",),
        ("Net capital (12,345,678) 3750",),
        ("Net capital -12,345,678 3750",),
        ("Net capital 12,345,678 13750",),
        ("Net capital \u2212$12,345,678 3750",),
        ("Net capital $12,345,678 3750 (in thousands)",),
        ("Net capital EUR 12,345,678 3750",),
    ],
)
def test_minimum_amount_rejects_absent_conflicting_ambiguous_or_wrong_row(rows):
    with pytest.raises(ValueError):
        minimum_amount_result(CHECK, "12,345,678", rows)
