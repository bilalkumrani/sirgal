"""Tests for the rule-based detectors. All values here are made up."""

from sirgal.detectors import HIGH, LOW, MEDIUM, iban_ok, luhn_ok, scan_text, worst_severity


def test_valid_card_number_is_found():
    # 4111 1111 1111 1111 is a well-known test card number that passes Luhn.
    assert scan_text("card: 4111 1111 1111 1111") == {"credit_card": 1}


def test_long_number_failing_luhn_is_ignored():
    assert scan_text("Order 1234567812345678 shipped") == {}


def test_luhn_and_iban_checksums():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
    assert iban_ok("GB82WEST12345698765432")
    assert not iban_ok("GB82WEST12345698765433")


def test_ssn_found_but_never_issued_ones_ignored():
    assert scan_text("SSN 251-29-2287")["ssn"] == 1
    assert "ssn" not in scan_text("000-12-3456 666-12-3456 900-12-3456")


def test_ssn_is_not_counted_as_phone():
    assert "phone" not in scan_text("SSN 251-29-2287")


def test_salary_needs_numbers_not_just_the_word():
    assert "salary" not in scan_text("We will discuss salary bands next week.")
    assert scan_text("name,annual_salary_usd\nAli,67000")["salary"] == 1


def test_date_of_birth_needs_dates():
    assert "date_of_birth" not in scan_text("Please add your date of birth to the form.")
    assert scan_text("name,dob\nAli,1993-06-09")["date_of_birth"] == 1


def test_password_lines_found():
    text = "Shared logins\nStripe: vlopez / 9xK!pQ2\nAWS root: admin / s3cret"
    assert scan_text(text)["password"] == 2


def test_password_word_alone_is_not_enough():
    assert "password" not in scan_text("Remember to reset your password every 90 days.")


def test_filename_counts_as_a_credential_hint():
    assert scan_text("Wi-Fi: office / hunter22", filename="passwords.txt")["password"] == 1


def test_ordinary_text_finds_nothing():
    assert scan_text("Team lunch on Friday at 1pm. Meeting moved to 2026-10-08, room 4.") == {}


def test_results_are_counts_never_values():
    found = scan_text("SSN 251-29-2287, email ali@acme.example")
    assert all(isinstance(v, int) for v in found.values())
    assert "251-29-2287" not in str(found)


def test_worst_severity():
    assert worst_severity({"email": 3, "ssn": 1}) == HIGH
    assert worst_severity({"email": 3, "phone": 1}) == MEDIUM
    assert worst_severity({"email": 3}) == LOW
    assert worst_severity({}) is None
