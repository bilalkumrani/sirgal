# Sirgal

**Find sensitive files your AI assistant can see before your employees do.**

> Sirgal is in early development, and I'm building it in public. Version 0.0.1 only installs the command. Scanning comes next.

## The problem

Microsoft Copilot and Google Gemini can read every file an employee has access to. In most companies, years of careless sharing means that's far more than it should be: a salary sheet shared with the whole company back in 2019, a customer list in a folder anyone with the link can open, a passwords file someone forgot about.

Before AI assistants, nobody stumbled on these files. Now anyone can ask "what does my manager earn?" and get an answer.

## What Sirgal does

Sirgal connects to your company's cloud storage, checks every file, and looks for two things: sensitive content (salaries, ID numbers, card numbers, passwords) and sharing that's too wide. When both show up in the same file, Sirgal flags it in a report so you can fix it before you switch on an AI assistant.

What a scan will look like (planned):

```
$ sirgal scan --source gdrive

Scanned 4,812 files in 3m 12s

HIGH    Salaries_2024.xlsx     salary data     shared: anyone with the link
HIGH    staff_passports.pdf    ID numbers      shared: whole company
MEDIUM  customer_export.csv    phone numbers   shared: 14 people outside the team

3 high-risk files, 11 medium. Full report: sirgal-report.html
```

## How it fits together

```mermaid
flowchart TB
    admin["IT / Security team"]
    ai["AI assistants<br/>Copilot, Gemini"]

    subgraph company["Your environment"]
        direction LR
        sirgal["Sirgal"] --> report["Risk report"]
    end

    subgraph apps["Your cloud apps"]
        direction LR
        gdrive["Google Drive"]
        m365["Microsoft 365<br/>(planned)"]
        slack["Slack<br/>(planned)"]
    end

    admin -- "1. runs a scan" --> sirgal
    sirgal -- "2. read-only scan" --> apps
    report -- "3. risky files" --> admin
    ai -. "sees what<br/>employees see" .-> apps
`````

## Who it's for

IT and security teams at small and mid-size companies getting ready to turn on Copilot or Gemini, and the IT providers (MSPs) who look after those companies.

## Security promises

Sirgal reads your files, so you should know exactly what it does with them.

- **Runs on your own machine or servers.** Your data never goes to me or any third party.
- **Read-only by default.** It changes sharing settings only if you explicitly turn that on.
- **Doesn't store file contents.** It keeps only the file name, location, sharing level, and the type of sensitive data found.
- **Open source.** Every line of code is here for you to check.

## Roadmap

- [x] 0.0.1: package and command
- [ ] Fake company data generator for safe demos
- [ ] Google Drive connector
- [ ] Sensitive data detection
- [ ] HTML report
- [ ] Microsoft 365 (OneDrive and SharePoint) connector
- [ ] Fix risky sharing (opt-in)
- [ ] Slack connector

## Install

```
pip install sirgal
sirgal --version
```

Requires Python 3.10 or newer.

## Follow along

I post progress, design decisions, and the problems I run into on LinkedIn. [Follow me there](https://linkedin.com/in/bilalkumrani/).

## License

Apache 2.0. See [LICENSE](LICENSE).