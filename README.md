# Sirgal

**Find sensitive files your AI assistant can see before your employees do.**

> Sirgal is in early development, and I'm building it in public. Version 0.3.0 scans Google Drive for overshared files that contain sensitive data, in text, PDF, Word and Excel files, including personal details written in documents (optional local model). Microsoft 365 support is planned.

## The problem

Microsoft Copilot and Google Gemini can read every file an employee has access to. In most companies, years of careless sharing means that's far more than it should be: a salary sheet shared with the whole company back in 2019, a customer list in a folder anyone with the link can open, a passwords file someone forgot about.

Before AI assistants, nobody stumbled on these files. Now anyone can ask "what does my manager earn?" and get an answer.

## What Sirgal does

Sirgal connects to your company's cloud storage, checks every file, and looks for two things: sensitive content (salaries, ID numbers, card numbers, passwords) and sharing that's too wide. When both show up in the same file, Sirgal flags it in a report so you can fix it before you switch on an AI assistant.

A real scan of the sample test company that ships with the project:

```
$ sirgal scan --source gdrive --model

RISK    SHARED WITH            FILE                                          FOUND
HIGH    anyone with the link   acme-robotics/HR/salaries_2026.csv            25 bank IBANs, salary data, 25 emails
HIGH    1 person               acme-robotics/HR/employee_records.csv         25 SSNs, dates of birth, 25 emails
HIGH    1 person               acme-robotics/HR/medical_leave_notes.txt      4 health details
HIGH    1 person               acme-robotics/HR/offer_letter.docx            salary data
HIGH    1 person               acme-robotics/HR/payroll_q3.xlsx              25 bank IBANs, salary data
HIGH    1 person               acme-robotics/HR/sick_note.pdf                1 health detail
HIGH    1 person               acme-robotics/IT/passwords.txt                6 passwords
MEDIUM  1 person               acme-robotics/HR/exit_interview_notes.txt     1 home address
UNKNOWN 1 person               acme-robotics/HR/passport_scan.pdf            (not checked: no readable text, maybe a scan or a protected file)
OK      anyone with the link   acme-robotics/Finance/vendor_invoice.pdf      -
OK      anyone with the link   acme-robotics/Marketing/blog_ideas.txt        -
OK      anyone with the link   acme-robotics/Marketing/customer_quote.txt    -
OK      1 person               acme-robotics/General/holiday_calendar.xlsx   -
OK      1 person               acme-robotics/General/office_move.txt         -
OK      1 person               acme-robotics/General/team_lunch.txt          -
OK      1 person               acme-robotics/General/weekly_sync_notes.txt   -
OK      1 person               acme-robotics/HR/leave_policy.txt             -
OK      private                acme-robotics/Sales/customers.csv             40 card numbers, 38 phone numbers, 40 emails

18 files scanned: 7 high risk, 1 medium risk, 1 shared but not checked, 9 ok.
File contents were read in memory and not saved.
```

The salary sheet that anyone with the link can open is a problem. So are the salaries on the second sheet of a payroll workbook, an offer letter, a sick note PDF, and an exit interview with someone's home address. The scanned passport has no text to read, so Sirgal says UNKNOWN instead of guessing. The customer list with card numbers is fine, because only its owner can see it. So are meeting notes full of names, an office address, a supplier invoice, and a leave policy that mentions medical leave.

### What it checks

| Found in the file | How |
|---|---|
| Card numbers, bank IBANs | Pattern plus checksum (Luhn, mod-97), so random numbers don't count |
| US Social Security numbers, phone numbers, emails | Pattern |
| Salary data, dates of birth | Keyword plus matching numbers or dates |
| Passwords | Login keywords plus lines like `Stripe: user / secret` |
| Home addresses, health details | Optional local model ([GLiNER-PII](https://huggingface.co/knowledgator/gliner-pii-base-v1.0)), only when tied to a person |

The model layer follows one rule: a detail counts only when it belongs to a person. "Jason's home address" is sensitive; the office address is not. "Jason is having knee surgery" is sensitive; "employees can take medical leave" is not. Names on their own never make a file risky. The model only reads shared files that the rules haven't already rated high. [How it was chosen](https://github.com/bilalkumrani/sirgal/blob/main/scripts/compare_detectors.py): on the test company it caught 9 of 9 sensitive files with no false positives; Microsoft Presidio caught 7 and flagged a harmless invoice.

It reads plain text, CSV, PDF, Word (including tables), Excel (every sheet), Google Docs and Google Sheets (every tab), all in memory. Shared files it can't read, like scanned images, password-protected PDFs or unsupported types, are listed as **UNKNOWN**, never as OK, because Sirgal doesn't call a file safe without looking inside.

## How it fits together

```mermaid
flowchart TB
    admin["IT / Security team"]
    ai["AI assistants<br/>Copilot, Gemini"]

    subgraph company["Your environment"]
        direction LR
        sirgal["Sirgal"] -- "3. checks content<br/>+ sharing" --> report["Risk report"]
    end

    subgraph apps["Your cloud apps"]
        direction LR
        gdrive["Google Drive"]
        m365["Microsoft 365<br/>(planned)"]
        slack["Slack<br/>(planned)"]
    end

    admin -- "1. runs a scan" --> sirgal
    sirgal -- "2. reads files<br/>(read-only)" --> apps
    report -- "4. risky files" --> admin
    ai -. "sees what<br/>employees see" .-> apps
```

## Who it's for

IT and security teams at small and mid-size companies getting ready to turn on Copilot or Gemini, and the IT providers (MSPs) who look after those companies.

## Security promises

Sirgal reads your files, so you should know exactly what it does with them.

- **Runs on your own machine or servers.** Your data never goes to me or any third party.
- **Read-only.** It asks Google for read-only access, so it can't change, delete or re-share anything. (A future opt-in "fix sharing" feature will ask for separate permission.)
- **Doesn't keep file contents.** Files are read in memory during a scan and discarded right after. Sirgal keeps only the file name, link, sharing settings, and the types of sensitive data found.
- **No outside AI services.** Everything runs on your machine, including the optional model. Nothing is sent to OpenAI, Google's AI, or anyone else.
- **Open source.** Every line of code is here for you to check.

## Roadmap

- [x] 0.0.1: package and command
- [x] Test company data generator for safe demos
- [x] Google Drive connector
- [x] Sensitive data detection, layer 1: rules and checksums
- [x] Sensitive data detection, layer 2: home addresses and health details with a local model (optional)
- [x] PDF, Word and Excel files
- [ ] Scanned documents (text recognition)
- [ ] HTML report
- [ ] Microsoft 365 (OneDrive and SharePoint) connector
- [ ] Fix risky sharing (opt-in)
- [ ] Slack connector

## Quick start

Requires Python 3.10 or newer.

```
pip install sirgal
```

Sirgal talks to Google Drive with your own Google Cloud credentials, so no third-party app ever gets access. One-time setup, about 10 minutes:

1. In [Google Cloud Console](https://console.cloud.google.com), create a project (for example `sirgal`).
2. **APIs & Services → Library**, find **Google Drive API**, and click **Enable**.
3. **Google Auth Platform** (OAuth consent screen): fill in an app name and your email, then pick an audience.
   - Google Workspace: choose **Internal**.
   - Personal Gmail: choose **External**, then add your own address under **Audience → Test users**. Google asks you to log in again every 7 days in this mode.
4. **Clients → Create client → Desktop app**, then download the JSON file.
5. Save it as `~/.config/sirgal/credentials.json` and lock it down:

   ```
   mkdir -p ~/.config/sirgal
   mv ~/Downloads/client_secret_*.json ~/.config/sirgal/credentials.json
   chmod 600 ~/.config/sirgal/credentials.json
   ```

Then run a scan:

```
sirgal scan --source gdrive
```

The first time, your browser opens so you can approve read-only access. Sirgal saves the login token next to `credentials.json`, readable only by your user. To log out, delete `~/.config/sirgal/gdrive-token.json`.

Sirgal currently scans files owned by the account you log in with.

### Optional: check notes and documents too

Rules can't spot a home address or a health condition written in a sentence. A small model that runs on your machine can:

```
pip install "sirgal[ner]"
sirgal scan --source gdrive --model
```

The first run downloads the model from Hugging Face (about 700 MB) and caches it. It takes roughly a quarter of a second per shared document on a laptop. If you've already downloaded the model, point to its folder instead: `--model path/to/gliner-pii-base-v1.0`.

## Development

```
git clone https://github.com/bilalkumrani/sirgal.git
cd sirgal
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`python3 scripts/make_test_data.py` creates the sample Acme Robotics files in `test-data/`, with an answer key in `manifest.json`. Upload them to a test Google account to try a real scan without touching real data.

`python3 scripts/compare_detectors.py` reruns the model comparison against that answer key (needs `pip install presidio-analyzer gliner` and a spaCy model; see the script for setup).

## Follow along

I post progress, design decisions, and the problems I run into on LinkedIn. [Follow me there](https://linkedin.com/in/bilalkumrani/).

## License

Apache 2.0. See [LICENSE](LICENSE).