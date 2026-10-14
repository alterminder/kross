# Roadmap

Planned work, not yet built. Ideas and offers to help are welcome in
[issues](https://github.com/alterminder/kross/issues).

## Training content

- **Trainer-confirmed numbers.** Every dial value, move effect and threshold in `content/behaviour_rules.yaml` and the
  curated scenarios is still a draft. The direction of each effect is grounded in its source; the sizes need review by
  experienced humanitarian negotiation trainers.

## Facilitated training

- **Cohorts and assignments:** a trainer assigns scenarios to a group and follows their progress.
- **A facilitator role** between org admin and member.
- **Live push** for the trainer view (it polls today).

## Voice

- **Spoken counterpart and dictation**, as an optional module switched on per deployment. Scenarios already carry
  `avatar` settings for it.

## Sign-in

- **Email-link sign-in** alongside Google and OIDC: a one-time link sent by email, no passwords. Needs a transactional
  email provider with SPF/DKIM/DMARC on the domain, hashed single-use tokens (15–30 min), a confirm-button page
  (email scanners prefetch links), per-address and per-IP rate limits, and revoking an old address's email login
  when an account's email changes.
