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


# Key-shaped test values are built at runtime so GitHub secret scanning never sees one.
FAKE_KEYS = {
    "private key": "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow" + "A" * 60 + "\n-----END RSA " + "PRIVATE KEY-----",
    "openssh key": "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + "b3Bl" * 20,
    "aws access key": "AKIA" + "X" * 16,
    "aws session key": "ASIA" + "Y7" * 8,
    "github token": "ghp" + "_" + "x" * 36,
    "github app token": "ghs" + "_" + "Z9" * 18,
    "github fine-grained token": "github" + "_pat_" + "x" * 82,
    "google api key": "AIza" + "x" * 35,
    "slack bot token": "xoxb" + "-" + "1" * 12 + "-" + "x" * 24,
    "slack user token": "xoxp" + "-" + "x" * 30,
}


def test_each_key_format_is_found():
    for name, key in FAKE_KEYS.items():
        assert scan_text(f"config:\n{key}\n") == {"secret_key": 1}, name


def test_private_key_block_counts_once_and_its_body_is_not_numbers():
    block = "-----BEGIN " + "PRIVATE KEY-----\n" + "4111111111111111 2125550123\n" + "-----END " + "PRIVATE KEY-----"
    assert scan_text(block) == {"secret_key": 1}


def test_lookalikes_are_not_keys():
    text = (
        "Our AWS keys start with AKIA. Never share a public key.\n"
        "-----BEGIN PUBLIC KEY-----\n"
        "AKIA" + "X" * 15 + " is too short, " + "AKIA" + "X" * 17 + " too long.\n"
        "ghp" + "_short and xoxb" + "- alone are not tokens."
    )
    assert "secret_key" not in scan_text(text)


def test_keys_are_counted_never_returned():
    key = "AKIA" + "Q" * 16
    found = scan_text(f"aws_access_key_id = {key}")
    assert found["secret_key"] == 1
    assert key not in str(found)


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
