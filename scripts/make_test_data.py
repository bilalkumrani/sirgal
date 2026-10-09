"""Generate a fictional company's files for testing Sirgal.

Some files contain sensitive data (salaries, SSNs, card numbers, passwords),
some are harmless. manifest.json records what each file contains, how it is
meant to be shared, and which detection layer should catch it:

    "rules"  structured data that patterns and checksums can find
    "model"  sensitive details in written text, which needs a local model

Some harmless files are full of people's names on purpose. Almost every
document mentions people, so names alone must not make a file risky.

Everything here is fake, made up by Faker.

Usage:
    python scripts/make_test_data.py
    python scripts/make_test_data.py --employees 50 --seed 7
"""

import argparse
import csv
import json
from pathlib import Path

from faker import Faker

COMPANY = "Acme Robotics"
DOMAIN = "acme.example"  # .example is reserved, so it can never be a real domain

# How each file is meant to be shared once uploaded to Google Drive.
PRIVATE = "private"          # only the owner
COMPANY_WIDE = "company"     # everyone in the organization
PUBLIC_LINK = "public_link"  # anyone with the link


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_employees(fake, count):
    people = []
    for _ in range(count):
        first, last = fake.first_name(), fake.last_name()
        people.append({
            "name": f"{first} {last}",
            "email": f"{first}.{last}@{DOMAIN}".lower(),
            "job": fake.job(),
            "ssn": fake.ssn(),
            "dob": fake.date_of_birth(minimum_age=22, maximum_age=64).isoformat(),
            "salary": fake.random_int(45_000, 180_000, step=500),
            "iban": fake.iban(),
        })
    return people


def main():
    parser = argparse.ArgumentParser(description="Generate fake company files for testing Sirgal.")
    parser.add_argument("--out", default="test-data", help="output folder (default: test-data)")
    parser.add_argument("--employees", type=int, default=25, help="number of employees (default: 25)")
    parser.add_argument("--customers", type=int, default=40, help="number of customers (default: 40)")
    parser.add_argument("--seed", type=int, default=42, help="same seed gives the same files every time")
    args = parser.parse_args()

    Faker.seed(args.seed)
    fake = Faker("en_US")
    root = Path(args.out) / "acme-robotics"
    manifest = []

    def record(rel_path, sharing, contains, sensitive=None, layer=None):
        if sensitive is None:
            sensitive = bool(contains)
        manifest.append({
            "path": rel_path,
            "sharing": sharing,
            "sensitive": sensitive,
            "contains": contains,
            "layer": layer if layer else ("rules" if sensitive else None),
        })

    staff = make_employees(fake, args.employees)

    # 1. Salary sheet shared with anyone who has the link. The worst case.
    write_csv(
        root / "HR/salaries_2026.csv",
        ["name", "email", "job_title", "annual_salary_usd", "bank_iban"],
        [[p["name"], p["email"], p["job"], p["salary"], p["iban"]] for p in staff],
    )
    record("HR/salaries_2026.csv", PUBLIC_LINK, ["person_name", "email", "salary", "iban"])

    # 2. Employee records visible to the whole company. Classic Copilot risk.
    write_csv(
        root / "HR/employee_records.csv",
        ["name", "email", "ssn", "date_of_birth"],
        [[p["name"], p["email"], p["ssn"], p["dob"]] for p in staff],
    )
    record("HR/employee_records.csv", COMPANY_WIDE, ["person_name", "email", "ssn", "date_of_birth"])

    # 3. Customer list with card numbers, correctly kept private.
    write_csv(
        root / "Sales/customers.csv",
        ["company", "contact", "email", "phone", "card_number"],
        [
            [fake.company(), fake.name(), fake.email(), fake.phone_number(), fake.credit_card_number()]
            for _ in range(args.customers)
        ],
    )
    record("Sales/customers.csv", PRIVATE, ["person_name", "email", "phone", "credit_card"])

    # 4. Shared passwords file, visible to the whole company.
    services = ["AWS root", "Stripe", "Office Wi-Fi", "QuickBooks", "GitHub admin", "Payroll portal"]
    lines = [f"{s}: {fake.user_name()} / {fake.password(length=14)}" for s in services]
    write_text(root / "IT/passwords.txt", "Shared logins, do not forward\n\n" + "\n".join(lines) + "\n")
    record("IT/passwords.txt", COMPANY_WIDE, ["password"])

    # 5. Harmless file shared publicly. Sirgal should NOT flag this.
    ideas = "\n".join(f"- {fake.catch_phrase()}" for _ in range(10))
    write_text(root / "Marketing/blog_ideas.txt", f"{COMPANY} blog ideas\n\n{ideas}\n")
    record("Marketing/blog_ideas.txt", PUBLIC_LINK, [])

    # 6. Harmless file shared company-wide. Also should NOT be flagged.
    write_text(
        root / "General/team_lunch.txt",
        f"Team lunch on Friday at 1pm.\nPlace: {fake.city()} Grill\n{fake.paragraph(nb_sentences=3)}\n",
    )
    record("General/team_lunch.txt", COMPANY_WIDE, [])

    # ---- Written documents. Rules can't catch these; a local model should. ----

    # 7. Exit interview with a home address, visible to the whole company.
    leaver = fake.random_element(staff)
    leaver_first = leaver["name"].split()[0]
    reason = fake.random_element([
        "a long commute and no option to work remotely",
        "wanting to move into a management role",
        "moving closer to family",
    ])
    address = f"{fake.street_address()}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}"
    write_text(
        root / "HR/exit_interview_notes.txt",
        f"Exit interview notes\n\n"
        f"Employee: {leaver['name']}, {leaver['job']}\n\n"
        f"{leaver_first} said the main reason for leaving was {reason}. "
        f"{leaver_first} was positive about the team but felt the role had stopped growing.\n\n"
        f"Send the final documents to {leaver_first}'s home address: {address}.\n",
    )
    record("HR/exit_interview_notes.txt", COMPANY_WIDE, ["person_name", "home_address"], layer="model")

    # 8. Medical leave notes, visible to the whole company.
    conditions = [
        "recovery after knee surgery",
        "treatment for anxiety",
        "complications during pregnancy",
        "ongoing chemotherapy",
        "a back injury",
    ]
    leave_lines = []
    for person in fake.random_elements(staff, length=4, unique=True):
        first = person["name"].split()[0]
        leave_lines.append(
            f"{person['name']} is on medical leave for {fake.random_element(conditions)}. "
            f"{first} expects to return in {fake.random_int(2, 10)} weeks."
        )
    write_text(root / "HR/medical_leave_notes.txt", "Leave tracker\n\n" + "\n".join(leave_lines) + "\n")
    record("HR/medical_leave_notes.txt", COMPANY_WIDE, ["person_name", "health_info"], layer="model")

    # 9. Meeting notes full of names but nothing sensitive. Must stay OK.
    attendees = [p["name"] for p in fake.random_elements(staff, length=4, unique=True)]
    firsts = [n.split()[0] for n in attendees]
    write_text(
        root / "General/weekly_sync_notes.txt",
        f"Weekly product sync\n\nAttendees: {', '.join(attendees)}\n\n"
        f"{firsts[0]} walked through the roadmap for next quarter. "
        f"{firsts[1]} will follow up with the design team about the new onboarding screens. "
        f"{firsts[2]} and {firsts[3]} are pairing on the reporting bug.\n\n"
        f"Next sync is on Thursday.\n",
    )
    record("General/weekly_sync_notes.txt", COMPANY_WIDE, ["person_name"], sensitive=False)

    # 10. Public customer quote with a name and a city. Public on purpose, must stay OK.
    write_text(
        root / "Marketing/customer_quote.txt",
        f"Customer quote for the website\n\n"
        f"\"{fake.catch_phrase()} is exactly what our warehouse needed.\" "
        f"said {fake.name()}, operations lead at {fake.company()} in {fake.city()}.\n",
    )
    record("Marketing/customer_quote.txt", PUBLIC_LINK, ["person_name", "city"], sensitive=False)

    manifest_data = {"company": COMPANY, "seed": args.seed, "files": manifest}
    write_text(root / "manifest.json", json.dumps(manifest_data, indent=2) + "\n")

    risky = sum(1 for m in manifest if m["sensitive"] and m["sharing"] != PRIVATE)
    print(f"Created {len(manifest)} files in {root}/")
    model_only = sum(1 for m in manifest if m["layer"] == "model")
    print(f"{risky} are sensitive and overshared ({model_only} need the model layer). See manifest.json for details.")


if __name__ == "__main__":
    main()