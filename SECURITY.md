# Security policy

Sirgal reads company files, so security problems in Sirgal itself are taken seriously.

## Reporting a vulnerability

**Please don't report security problems in public issues, pull requests or discussions.**

Report privately, in either of these ways:

1. **GitHub private reporting (preferred):** [open a private security advisory](https://github.com/bilalkumrani/sirgal/security/advisories/new).
2. **Email:** security@bilalumrani.com

Please include:

- what the problem is and what an attacker could do with it
- steps to reproduce, ideally using the sample test company from `scripts/make_test_data.py`
- the Sirgal version (`sirgal --version`), Python version and operating system

Never include real company data, file contents, file names or login tokens in a report.

## What to expect

- You'll get an acknowledgement within 3 working days.
- You'll get an assessment and a plan within 10 working days.
- Once a fix is released, the advisory is published. You'll be credited, unless you'd rather not be.

Please give us a reasonable chance to release a fix before telling anyone else.

## Supported versions

Sirgal is pre-1.0. Security fixes go into the latest release only, so please upgrade before reporting:

```
pip install --upgrade sirgal
```

## What counts as a vulnerability

Breaking any of Sirgal's security promises counts as a security bug. For example:

- Sirgal changing, deleting or re-sharing anything, when it should be read-only
- file contents being written to disk, kept, logged, or included in a report
- data being sent anywhere other than the cloud service being scanned (and the one-time model download from Hugging Face, when you choose to use the model)
- login tokens or credentials being exposed, or stored with loose file permissions
- a report that can run code or formulas through a crafted file name
- a sensitive shared file being rated OK when it couldn't actually be read

Out of scope: problems in Google's or Microsoft's own services, in third-party models, or attacks that need someone to already control the machine running Sirgal.
