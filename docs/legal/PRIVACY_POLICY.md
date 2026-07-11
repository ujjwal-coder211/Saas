> ⚠️ **TEMPLATE — NOT LEGAL ADVICE.** A qualified lawyer must review this before
> you publish it, especially for GDPR (EU), India DPDP Act, or CCPA (California)
> compliance. Replace every **[BRACKETED]** placeholder.

# Privacy Policy — [PRODUCT NAME] by Aitotech

**Last updated:** [DATE]

## 1. Who we are
Aitotech ("we") operates [PRODUCT NAME]. Data controller: [COMPANY LEGAL NAME,
once registered], [ADDRESS]. Contact / Data requests: [PRIVACY EMAIL].

## 2. What we collect
- **Account data:** email, plan, API keys, authentication identifiers.
- **Your Content:** prompts, code, files, and context you send to the Service.
- **Usage data:** requests, models used, tokens, latency, costs, timestamps
  (see `saas/billing/` and the audit trail).
- **Technical data:** IP address, device/browser info, logs.
- **Payment data:** handled by **Stripe** — we do **not** store full card numbers.

## 3. How we use it
- To provide, operate, secure, and bill the Service.
- To route requests to third-party AI models on your instruction.
- To enforce quotas, rate limits, and prevent abuse.
- **[State clearly]** whether Your Content is used to train/improve models, and
  how to opt out (the Service supports a `training_opt_in` flag). If you never
  train on customer content, say so — it's a strong trust signal.

## 4. Third parties (sub-processors)
We share data with processors only as needed to run the Service:
- **AI model routing:** OpenRouter and the underlying model providers (your
  prompt content is sent to fulfil your request).
- **Payments:** Stripe.
- **Hosting/infrastructure:** [YOUR HOST — e.g. Railway/Render/AWS].
- **[Analytics/error monitoring, if any — e.g. Sentry].**
Maintain a current sub-processor list; update it as vendors change.

## 5. Legal basis (GDPR, if serving EU users)
We process data to perform our contract with you, for legitimate interests
(security, improvement), for legal compliance, and with consent where required.

## 6. Data retention
- Account data: for the life of your account + [PERIOD] after closure.
- Content/usage/logs: [PERIOD] — state it. The audit trail is append-only.
- You can request deletion (see rights below).

## 7. Security
We use OS-level credential vaulting, an in-loop permission gate, an injection
firewall, and an append-only audit trail. No system is perfectly secure; we
cannot guarantee absolute security.

## 8. Your rights
Depending on your jurisdiction, you may have rights to access, correct, delete,
export, or restrict processing of your data, and to withdraw consent. To exercise
them, contact [PRIVACY EMAIL]. (Reflect GDPR / India DPDP / CCPA specifics as your
lawyer advises.)

## 9. International transfers
Your data may be processed in countries other than yours (e.g. by model/hosting
providers). We take steps to protect it consistent with applicable law.

## 10. Children
The Service is not directed to children under [AGE]; we do not knowingly collect
their data.

## 11. Changes
We may update this policy; material changes will be notified.

**Contact / Data Protection:** [PRIVACY EMAIL]
