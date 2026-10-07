"""Generate a fictional company's files for testing Sirgal.

Some files contain sensitive data (salaries, SSNs, card numbers, passwords),
some are harmless. manifest.json records what each file contains and how it
is meant to be shared, so later we can check whether Sirgal flags the right ones.

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

    def record(rel_path, sharing, contains):
        manifest.append({
            "path": rel_path,
            "sharing": sharing,
            "sensitive": bool(contains),
            "contains": contains,
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

    manifest_data = {"company": COMPANY, "seed": args.seed, "files": manifest}
    write_text(root / "manifest.json", json.dumps(manifest_data, indent=2) + "\n")

    risky = sum(1 for m in manifest if m["sensitive"] and m["sharing"] != PRIVATE)
    print(f"Created {len(manifest)} files in {root}/")
    print(f"{risky} are sensitive and overshared. See manifest.json for details.")


if __name__ == "__main__":
    main()