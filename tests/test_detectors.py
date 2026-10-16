"""Tests for the rule-based detectors. All values here are made up."""

from sirgal.detectors import HIGH, LOW, MEDIUM, iban_ok, luhn_ok, scan_text, verhoeff_ok, worst_severity


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



def test_verhoeff_matches_published_examples():
    # Wikipedia, "Verhoeff algorithm": 236 -> 3 and 942 -> 7.
    # https://en.wikipedia.org/wiki/Verhoeff_algorithm
    # Rosetta Code, "Verhoeff algorithm": 236 -> 3, 12345 -> 1, 123456789012 -> 0,
    # and each fails with 9 as its last digit. https://rosettacode.org/wiki/Verhoeff_algorithm
    for valid in ("2363", "9427", "123451", "1234567890120"):
        assert verhoeff_ok(valid), valid
    for invalid in ("2369", "9429", "123459", "1234567890129"):
        assert not verhoeff_ok(invalid), invalid


def test_verhoeff_catches_any_single_wrong_digit_and_swapped_neighbours():
    number = "234567890124"
    for i in range(len(number)):
        for d in "0123456789":
            if d != number[i]:
                assert not verhoeff_ok(number[:i] + d + number[i + 1:]), (i, d)
    for i in range(len(number) - 1):
        if number[i] != number[i + 1]:
            assert not verhoeff_ok(number[:i] + number[i + 1] + number[i] + number[i + 2:]), i


def test_verhoeff_ignores_separators_and_rejects_no_digits():
    assert verhoeff_ok("2345 6789 0124")
    assert verhoeff_ok("2345-6789-0124")
    assert not verhoeff_ok("")
    assert not verhoeff_ok("no digits")


def test_aadhaar_found_grouped_or_not():
    # Made up: the first 11 digits were picked, the last is the Verhoeff check digit.
    assert scan_text("Aadhaar: 2345 6789 0124") == {"aadhaar": 1}
    assert scan_text("UID 987654321012") == {"aadhaar": 1}
    assert scan_text("aadhaar=5000-0000-0047") == {"aadhaar": 1}
    assert scan_text("2345 6789 0124, 9876 5432 1012") == {"aadhaar": 2}


def test_aadhaar_with_wrong_check_digit_is_ignored():
    assert scan_text("Aadhaar: 2345 6789 0125") == {}
    assert scan_text("Aadhaar: 987654321013") == {}


def test_aadhaar_never_starts_with_0_or_1():
    # Both pass Verhoeff, but no Aadhaar number starts with 0 or 1.
    assert verhoeff_ok("123456789010") and verhoeff_ok("023456789014")
    assert scan_text("1234 5678 9010") == {}
    assert scan_text("0234 5678 9014") == {}


def test_aadhaar_needs_the_same_separator_throughout():
    assert scan_text("2345 6789-0124") == {}
    assert scan_text("2345 67890124") == {}


def test_aadhaar_inside_a_longer_number_is_ignored():
    # Order and account numbers: a valid-looking 12 digits with more digits around them.
    assert scan_text("Ref 12345678901240") == {}
    assert scan_text("Ref 2345678901241") == {}
    assert scan_text("Ref 3 2345 6789 0124") == {}
    assert scan_text("Ref 2345 6789 0124 5") == {}
    assert scan_text("SKU-234567890124") == {}
    assert scan_text("v234567890124") == {}


def test_card_number_is_not_also_an_aadhaar_number():
    # Passes Luhn, and its first 12 digits also pass Verhoeff.
    assert verhoeff_ok("453201511287")
    assert scan_text("card: 4532 0151 1287 0008") == {"credit_card": 1}
    assert scan_text("card: 4532015112870008") == {"credit_card": 1}


def test_iban_is_not_also_an_aadhaar_number():
    # A valid IBAN ending in 12 digits that pass Verhoeff on their own.
    assert verhoeff_ok("345678901238")
    assert scan_text("IBAN GB67WESTAB345678901238") == {"iban": 1}


def test_aadhaar_is_not_counted_as_phone():
    assert scan_text("Contact: 2345 6789 0124") == {"aadhaar": 1}
    assert scan_text("Contact: 234567890124") == {"aadhaar": 1}


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
