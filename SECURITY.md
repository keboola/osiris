# Security Policy

## Supported Versions

Currently supporting security updates for:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take the security of Osiris Pipeline seriously. If you have discovered a security vulnerability, please follow these steps:

### How to Report

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email your findings to `petr@keboola.com` with:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Initial Assessment**: Within 5 business days, we'll provide an initial assessment
- **Resolution Timeline**: We aim to resolve critical issues within 30 days
- **Credit**: We'll credit you in the security advisory (unless you prefer to remain anonymous)

## Security Best Practices

When using Osiris Pipeline:

### Database Credentials
- Store credentials in `.env` files (never commit these)
- Use read-only database users when possible
- Rotate credentials regularly

### LLM API Keys
- Never share API keys in issues or discussions
- Use environment variables for all API keys
- Set appropriate usage limits on your LLM accounts

### Pipeline Security
- Review generated SQL before execution
- Use the human validation step (never bypass it)
- Run Osiris in isolated environments for testing
- Avoid running pipelines with production write access until thoroughly tested

### Data Protection
- Be mindful of sensitive data in your databases
- Consider data masking for development/testing
- Review pipeline outputs before sharing

## Known Security Considerations

### SQL Injection Protection
Osiris includes built-in SQL injection prevention (see `docs/sql-safety.md`):
- Parameterized queries
- Schema validation
- Query sanitization
- Human approval required before execution

### LLM Security
- LLM responses are treated as untrusted input
- All generated SQL requires human validation
- No automatic execution without explicit approval

## Dependencies

We regularly update dependencies to patch known vulnerabilities:
- Run `pip list --outdated` to check for updates
- Use `pip-audit` to scan for known vulnerabilities
- Monitor security advisories for critical dependencies

## Security Tools

The project includes security scanning in the development workflow:
```bash
make secrets-check  # Scan for exposed secrets
make security       # Run Bandit security analysis
```

## Contact

Security Team: `petr@keboola.com`
Project Maintainers: See [CHANGELOG.md](CHANGELOG.md) for current maintainers

## Commitment

We are committed to:
- Responding quickly to security reports
- Providing transparent communication about vulnerabilities
- Releasing timely security patches
- Maintaining this security policy

Thank you for helping keep Osiris Pipeline and its users safe!
