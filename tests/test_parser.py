from bot.utils import parse_amount_note


def test_parse_basic():
    assert parse_amount_note("120 餐饮 午餐") == (120.0, "餐饮", "午餐")
    assert parse_amount_note("+5000 工资") == (5000.0, "工资", "")
    assert parse_amount_note("-50 打车") == (-50.0, "打车", "")


def test_parse_only_amount():
    assert parse_amount_note("99.99") == (99.99, "其他", "")


def test_parse_invalid():
    assert parse_amount_note("hello") == (None, "", "")
    assert parse_amount_note("") == (None, "", "")
