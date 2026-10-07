from app.money import format_inr, prorate, rupees_to_paise


def test_format_inr():
    assert format_inr(2638844) == "₹26,388.44"
    assert format_inr(20000000) == "₹2,00,000.00"
    assert format_inr(5) == "₹0.05"


def test_rupees_to_paise_no_float_drift():
    assert rupees_to_paise(1415.02) == 141502
    assert rupees_to_paise("1254.40") == 125440


def test_prorate():
    assert prorate(1, 3, 100) == 33
