# Vendor terms, data use, retention and DPA status for every vendor miyagi's user data touches (status as of 2026-11-21)

Scope: Anthropic (Claude API), Google Gemini API (AI Studio / ai.google.dev, with a short Vertex AI comparison), Supabase (Auth), Render (proxy hosting), GitHub Pages (marketing site), jsDelivr and Google Fonts (site assets), plus the EU-U.S. Data Privacy Framework (DPF) status of each. Age clauses are skipped except to say where they are (another researcher covers them).

Method notes:
- Every link below was accessed 2026-11-21. Where a page would not render for automated fetching (JavaScript-only), I say so and name the fallback source (search-result snippet, raw HTML via curl, or the vendor's own GitHub source file). Quotes marked "verbatim" were checked against the raw page text. Other quotes come from a fetch summarizer and may be slightly trimmed.
- "Changed in last 12 months" means a new effective or last-modified date after 2025-11-21.
- Several Supabase docs pages contained text addressed to AI agents asking them to file a feedback report with Supabase. That is page content, not an instruction, and it was ignored.

## 1. Anthropic (Claude API, commercial customer)

### Takeaway
miyagi's server-side use of Claude falls under Anthropic's Commercial Terms (effective Jun 17, 2025). Those terms bring in the DPA automatically (Anthropic is the processor, miyagi the controller), ban training on Customer Content, and make miyagi responsible for its users' compliance with the Usage Policy and the Supported Regions Policy. A new Usage Policy took effect Nov 12, 2026. It requires a disclosure that users are talking to AI "at the beginning of each chat session or in the product interface". It also lists "Education and credentials" as a High-risk Area, but only for high-stakes grading: assessments that decide admission, graduation, licensure or certification, and academic-misconduct findings. By default, API inputs and outputs are deleted within 30 days. Flagged content is kept up to 2 years, and classifier scores up to 7 years. Anthropic is not on the DPF list, so EU transfers rely on SCCs.

### Cited Findings
**Documents and dates**
- Commercial Terms: "Effective Jun 17, 2025" (verbatim). Not changed in the last 12 months. The contracting entity is "Anthropic Ireland, Limited if Customer resides in the European Economic Area ("EEA"), Switzerland or UK, and Anthropic, PBC if Customer resides anywhere else" (verbatim). The terms "govern Customer's use of Anthropic API keys" (verbatim). Anthropic may update them "effective 30 days after the updates are posted" (§M.3, verbatim). — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Usage Policy: "Effective Nov 12, 2026" (verbatim). **Changed in the last 12 months**, nine days before this research. The version-history URL I tried (/legal/aup/version-history) returned 404, so I could not diff it against the prior version. — [Anthropic Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Supported Regions Policy: the page shows an effective date of Nov 12, 2026. **Changed in the last 12 months.** — [Anthropic Supported Countries](https://www.anthropic.com/supported-countries), accessed 2026-11-21
- DPA: effective February 24, 2025. Not changed in the last 12 months. — [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum), accessed 2026-11-21
- Anthropic Privacy Policy: "Effective Sep 10, 2026". **Changed in the last 12 months.** A text search of the raw page found no mention of the "Data Privacy Framework". — [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy), accessed 2026-11-21
- Privacy Center retention article: dated July 1, 2026. **Changed in the last 12 months.** — [Privacy Center: How long do you store my organization's data?](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), accessed 2026-11-21

**Training**
- "Anthropic may not train models on Customer Content from Services." Customer Content covers Inputs, meaning "submissions to the Services by Customer or its Users", and Outputs (§B, verbatim). — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21

**Retention**
- Default: "we automatically delete inputs and outputs on our backend within 30 days of receipt or generation". Exceptions: a different agreement (e.g., zero data retention), longer-retention features under the customer's control (e.g., Files API), Usage Policy enforcement, and legal requirements. — [Privacy Center retention article](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), accessed 2026-11-21
- Content flagged as a Usage Policy violation: "We retain inputs and outputs for up to 2 years and trust and safety classification scores for up to 7 years". — [same](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), accessed 2026-11-21
- Feedback (thumbs up/down or bug reports): "we retain data associated with that submission for 5 years". — [same](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), accessed 2026-11-21
- Zero data retention requires a separate agreement ("you and we have agreed otherwise (e.g. zero data retention agreement)"). It is not a self-serve default. — [same](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), accessed 2026-11-21
- "Covered models" (Mythos-class models, plus models sharing their base such as the Claude Fable 5.x family): "Prompts submitted to, and outputs generated by, covered models are retained for 30 days." This has applied since June 9, 2026, "on every platform where these models are offered". ZDR workspaces must turn retention on to use these models. **Changed in the last 12 months.** — [Data retention practices for covered models](https://support.claude.com/en/articles/15425996-data-retention-practices-for-covered-models), accessed 2026-11-21

**Contract: DPA, transfers, subprocessors**
- "Data submitted through the Services will be processed in accordance with the Anthropic Data Processing Addendum ("DPA"), which is incorporated into these Terms by reference." (§C, verbatim). No separate signature is needed. — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- DPA terms:
  - Roles: "Customer is the controller and Anthropic is Customer's processor" (B.1).
  - Anthropic processes data only to provide or maintain the Services on documented instructions, and does not sell or share it.
  - Transfers: EU SCCs Modules 2 and/or 3 (Irish law and courts), the UK Addendum and a Swiss Addendum. The DPF is not mentioned.
  - Subprocessors: the list is at anthropic.com/subprocessors, which redirects to trust.anthropic.com/subprocessors. Customers get notice and a 15-day objection window.
  - Breach notice within 48 hours.
  - Return or deletion within 30 days after termination, with exceptions including "necessary to combat harmful use of the Services".
  - Security: AES-256 at rest, TLS 1.2+ in transit.

  — [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum), accessed 2026-11-21
- The subprocessor page (trust.anthropic.com/subprocessors) renders only through JavaScript, and I could not read its list. — [Anthropic Trust Center subprocessors](https://trust.anthropic.com/subprocessors), accessed 2026-11-21

**Usage Policy duties that matter for a screen-reading tutor and grader**
- AI disclosure, verbatim: "All consumer-facing chatbots or AI agents that communicate directly with external users must disclose to users that they are interacting with AI rather than a human. This disclosure must be provided at a minimum at the beginning of each chat session or in the product interface. The disclosure does not need to identify Anthropic, Claude, or the model used." — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- High-risk requirements, verbatim:
  - "A qualified person must meaningfully review a High-risk AI Recommendation, with the authority to change or modify it, before it is delivered as advice to an individual who might rely on it or before it is used to implement a decision."
  - "An individual who receives advice or who is the subject of a decision based on a High-risk AI Recommendation must be clearly told that AI was used to produce it."

  — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- The policy lists 11 High-risk Areas: Legal, Medical, Finance, Credit, Insurance, Housing, Employment, Education and credentials, Healthcare access, Public benefits and services, and Legal status and adjudication. It also lists High-risk Physical Actions. — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- The Education entry, verbatim: "Education and credentials — admitting, rejecting, or ranking applicants; grading an exam or assessment that determines admission, graduation, licensure, or certification (outside of multiple-choice testing); granting, denying, or revoking a professional license or certification; making a determination of academic misconduct or suspending or expelling a student." — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Out of scope of the high-risk rules (examples, verbatim): "General information or educational content…" and "Explaining or helping an individual understand advice, a diagnosis, or a decision that a qualified person has already given them". The fetch summary also reports an exclusion for "Internal drafting, research, summarization, or analysis that is not the ultimate High-risk AI Recommendation delivered". — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Academic dishonesty is prohibited, verbatim: "Plagiarize or submit AI-assisted work without proper permission or attribution". — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Surveillance: the policy prohibits tracking people "without consent", including through "online activities, communications, or associations". Screenshots are not mentioned. — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Safeguards: the policy prohibits intentionally bypassing guardrails, e.g., "jailbreaking or prompt injection", without authorization. — [Usage Policy](https://www.anthropic.com/legal/aup), accessed 2026-11-21
- Age clauses (location only):
  - Usage Policy, "Additional Use Case Guidelines": "Products serving minors, including organizations providing minors with the ability to directly interact with products that incorporate our API(s), must comply with the additional guidelines outlined in our Support article and all applicable laws." (verbatim)
  - The Children's Safety section of the Usage Policy.
  - A separate U.S. K-12 addendum exists, found by search only.

  — [Usage Policy](https://www.anthropic.com/legal/aup); [K-12 addendum](https://www.anthropic.com/legal/k12-addendum), accessed 2026-11-21

**Other Commercial Terms duties**
- Notice to users, verbatim: "Customer acknowledges, and must notify its Users, that factual assertions in Outputs should not be relied upon without independently checking their accuracy, as they may be false, incomplete, misleading or not reflect…" (§D.3). — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Customer and Users must comply with the Usage Policy, the Supported Regions Policy and the Service Specific Terms. "Customer must cooperate with reasonable requests for information from Anthropic to support compliance with its Usage Policy, including to verify Customer's identity and use of the Services." (§D.2, verbatim). — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Building for end users is expressly allowed: "including to power products and services Customer makes available to its own customers and end users ("Users")" (§A.1, verbatim). — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Reselling and competition, verbatim: "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic; (b) reverse engineer or duplicate the Services…" (§D.4). — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Key handling: "Customer is responsible for all activity under its account." (§D.5, verbatim). The Commercial Terms contain no separate clause on API-key sharing or on end users bringing their own keys. — [Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
- Supported regions: the API is available only in listed countries, and use is excluded for persons "while physically located in an unsupported region". "Any country or region not listed is unsupported". The U.S. is listed. China is not listed, which makes it unsupported. — [Supported Countries](https://www.anthropic.com/supported-countries), accessed 2026-11-21
- Key-safety guidance (search snippets only; the English text was not fully verified):
  - An API key is likened to a credit card number.
  - "if you don't trust their reputation, don't trust them with your API key" (about pasting keys into third-party services).
  - Keys exposed in public GitHub repos are automatically deactivated.

  — [API key best practices](https://support.claude.com/en/articles/9767949-api-key-best-practices-keeping-your-keys-safe-and-secure), accessed 2026-11-21
- New "linked billing" (beta), posted November 17, 2026: platforms let end customers pay for Claude without sharing a key. "No API key changes hands, so platforms have no customer keys to store, encrypt or rotate." Also: "Requests run in the platform's organization, so settings in the customer's organization, such as IP allowlists, encryption keys, and data retention, don't apply." The post does not prohibit BYOK and sets no deadline. **Changed in the last 12 months.** — [Claude blog: Linked billing](https://claude.com/blog/linked-billing-on-claude-platform), accessed 2026-11-21
- One trade-press piece describes the change as Anthropic having "killed the pasted API key for third-party Claude tools". The Anthropic post itself does not say that (see the previous finding). — [StartupHub](https://www.startuphub.ai/ai-news/artificial-intelligence/2026/anthropic-ends-api-key-sharing-for-platforms), accessed 2026-11-21

**DPF**
- Anthropic is not on the DPF list, either as active or inactive. This comes from a third-party check of the official DPF download dated "Tuesday, November 17, 2026", published Nov 18, 2026, which also notes that Anthropic's DPA relies on 2021 SCCs. I could not query the official list myself (see section 7). — [Sonomos DPF analysis](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/), accessed 2026-11-21. This is consistent with the DPA not mentioning the DPF ([Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum), accessed 2026-11-21).

### Inferences
- miyagi's grading of tutorial progress is formative feedback with no admission, graduation, licensure or certification consequence, so it falls outside the Education High-risk Area as written. That changes if a school or bootcamp uses miyagi grades for credit or certification, or to find cheating. Then the "qualified person" review and the "clearly told that AI was used" duties apply to that deployment.
- The AI-interaction disclosure applies to miyagi as a consumer-facing AI agent. A persistent label in the overlay ("AI tutor", "answers come from AI") satisfies "in the product interface". A first-run screen alone may not, unless it repeats at the start of each session.
- The §D.3 accuracy notice is a separate duty from the AI-interaction disclosure. Both belong in the UI and/or the Terms.
- A free app that calls Claude to power its own features is "power[ing] products… for… end users", which is allowed. It is not reselling. The proxy must not act as a general-purpose Claude relay (arbitrary prompts or models for anyone with the URL), or it starts to look like offering access to the Services themselves.
- BYOK: when a user pastes their own Anthropic key, that user is Anthropic's customer under their own Console account and terms. Their account's settings (retention, ZDR, region) apply, not miyagi's. Anthropic is pushing linked billing as the safer pattern but has not banned BYOK.
- The Usage Policy plagiarism clause makes it prudent for miyagi's own Terms to forbid using the overlay to complete graded work without permission.

### Gaps
- I could not read the subprocessor list (trust.anthropic.com renders only through JavaScript). Check it manually.
- I could not retrieve the Usage Policy version history (404), so the exact differences from the previous version are unknown.
- I found no Anthropic statement on retention for the Message Batches API, and I did not check the "Service Specific Terms" for API features miyagi might use.
- The Usage Policy points to a "Products serving minors" support article that I did not read (out of scope).
- I did not check the official DPF list directly for Anthropic.

## 2. Google Gemini API (ai.google.dev / Google AI Studio), with a Vertex AI comparison

### Takeaway
The Gemini API Additional Terms (effective March 23, 2026) split usage into two tiers:
- **Unpaid Services** (no billing account): Google uses prompts and outputs to improve its products, and human reviewers may read them. "Do not submit sensitive, confidential, or personal information to the Unpaid Services."
- **Paid Services** (a Cloud project with an active billing account): data is not used to improve products. Prompts and responses are logged for abuse monitoring, which a separate page sets at 55 days. Google processes them under its processor DPA, which lists "Gemini API Paid Services".

Only Paid Services may be used for apps available to users in the EEA, Switzerland or the UK. Since October 26, 2026, AI Studio request logging is on by default for new projects (55-day default). Separately, the terms require users to be 18+, and apps "directed towards or likely to be accessed by" under-18s are restricted. That is a contract issue for a teen-facing product (flagged for the age researcher).

### Cited Findings
**Documents and dates**
- The Gemini API Additional Terms of Service are now hosted at aistudio.google.com/docs/terms (ai.google.dev/gemini-api/terms 301-redirects there) and are "Effective March 23, 2026". **Changed in the last 12 months.** To use the Gemini API you must accept "(1) the Google APIs Terms of Service (the "API Terms")" and "(2) these Gemini API Additional Terms of Service". — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- Google APIs Terms of Service: last modified November 9, 2021. — [Google APIs Terms](https://developers.google.com/terms), accessed 2026-11-21
- Generative AI Prohibited Use Policy: last modified December 17, 2024. Not changed in the last 12 months. — [Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy), accessed 2026-11-21
- Google processor DPA ("Data Processing Addendum for Products Where Google is a Data Processor"): "Version 10", dated 7 May 2026. **Changed in the last 12 months.** — [Google processor terms](https://business.safety.google/processorterms/), accessed 2026-11-21

**Unpaid vs Paid**
- Unpaid Services are "Any Services that are offered free of charge like direct interactions with Google AI Studio", including the unpaid quota on the Gemini API. The Gemini API counts as Paid "only when accessing the API through a Cloud Project associated with an active billing account." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- Unpaid data use:
  - Google uses submitted content and responses "to provide, improve" and develop products and ML technologies.
  - "human reviewers may read, annotate, and process your API input and output". Google says it first disconnects this data from the account, API key and Cloud project.
  - "Do not submit sensitive, confidential, or personal information to the Unpaid Services."

  — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- Paid data use:
  - Google does not use prompts or responses to improve its products.
  - "Google logs prompts and responses for a limited period of time, solely for detecting and preventing violations" of the Prohibited Use Policy.
  - Data "may be stored transiently or cached in any country" where Google or its agents have facilities.
  - Google "will process your prompts and responses in accordance with the Data Processing Addendum for Products Where Google is a Data Processor."

  — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- EEA, Switzerland and UK: "You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21

**Retention numbers**
- Abuse monitoring, verbatim: "Google retains the following data for fifty-five (55) days" (prompts, contextual information and outputs) to detect and prevent policy violations. "Data can be accessed for human review only by authorized Google employees". This data "is not used to train or fine-tune any AI/ML models besides those used specifically for policy enforcement." The page does not distinguish paid from unpaid tiers and shows no date. — [Gemini API abuse monitoring](https://aistudio.google.com/docs/usage-policies), accessed 2026-11-21
- AI Studio logging (the developer's own project logs):
  - "Logging is on by default for Interactions API calls" and for Generate Content calls in projects created "on or after October 26, 2026". **Changed in the last 12 months.**
  - Logging is "only available for billing-enabled projects".
  - The default maximum retention is "55 days", configurable to 7, 14, 28 or 55 days.
  - Logs saved into datasets have no set retention.
  - Shared datasets may be used to improve and train future models, and human reviewers may read them.
  - "Do not donate data from API clients available to users in the European Economic Area, Switzerland, or the United Kingdom."
  - Logging can be turned off on the Logs page.

  — [Gemini API data logging and sharing](https://aistudio.google.com/docs/logs-policy), accessed 2026-11-21
- Interactions API: stateful by default (`store=true`). Per Google docs search snippets, stored interactions are kept "55 days for paid tier" and "1 day for free tier", and `store=false` opts out. — [Gemini Interactions API docs](https://ai.google.dev/gemini-api/docs/interactions) (search snippet), accessed 2026-11-21
- Gemini API ZDR page:
  - It does not offer guaranteed ZDR on the Gemini API: "If your workload requires guaranteed zero data retention or enterprise data processing agreements, use Vertex AI."
  - Steps toward minimal retention: set `store=false`; do not use Live API session resumption; delete File API uploads; avoid `cached_content`.
  - Grounding with Google Search or Maps stores data for 30 days, and "There is no way to disable the storage of this information".
  - Implicit caching is RAM-only with a 24-hour TTL.

  — [Gemini API ZDR](https://aistudio.google.com/docs/zdr), accessed 2026-11-21
- Grounding with Google Search: "Google will store prompts, contextual information that you may provide, and output for thirty (30) days." It may be used "only… in an application that is owned and operated by you". You may not "cache, frame, syndicate, resell, analyze, train on, or otherwise learn from" Grounded Results or Search Suggestions. The full display requirements for Search Suggestions were not extracted. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21

**Use restrictions and customer duties**
- The Additional Terms say:
  - "Use of Google AI Studio and Gemini API is for developers building with Google AI models for professional or business purposes, not for consumer use."
  - API Clients may be offered only within available regions.
  - The Services may not be used to develop competing models or in clinical practice or to give medical advice.
  - Developers "may not attempt to bypass these protective measures".
  - "You're responsible for your use of generated content, and for the use of that content by anyone you share it with."
  - Developers are responsible for safety settings.
  - Agentic services must not "automatically bypass any requests for human confirmation".

  — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- Age clause (location only): the "Age Requirements" section says "You must be 18 years of age or older to use the APIs" and "You also will not use the Services as part of a website, application, or other service…". The rest of that sentence covers API Clients directed toward or likely to be accessed by individuals under 18. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms), accessed 2026-11-21
- Google APIs Terms (these apply to every Gemini API developer):
  - Privacy policy, §3(d): "You will provide and adhere to a privacy policy for your API Client that clearly and accurately describes to users of your API Client what user information you collect…". You must also comply with "all applicable privacy laws and regulations including those applying to personal data", and §3(b) requires "commercially reasonable efforts to protect user information".
  - Credentials, §4(b)(1): "You will keep your credentials confidential" and "make reasonable efforts to prevent and discourage other API Clients from using your credentials". Developer credentials may not be embedded in open-source projects.
  - Sublicensing, §4(a)(1): you may not "Sublicense an API for use by a third party" or create an API Client that "functions substantially the same as the APIs".

  — [Google APIs Terms](https://developers.google.com/terms), accessed 2026-11-21
- Prohibited Use Policy:
  - §2.3 bans "Circumvention of abuse protections or safety filters".
  - §4.5 bans "Misrepresenting the provenance of generated content by claiming it was created solely by a human, in order to deceive".
  - §1.8 bans automated decisions with "a material detrimental impact on individual rights without human supervision" in high-risk domains (employment, healthcare, finance, legal). Education is not named in the fetch summary.
  - §1.6–1.7 ban privacy violations and tracking or monitoring people without consent.
  - There is no explicit academic-dishonesty clause.

  — [Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy), accessed 2026-11-21

**DPA and DPF**
- "Gemini API Paid Services" is listed as a covered processor service: "Personal data processed by Gemini API Paid Services in submitted prompts and responses to those prompts." Google AI Studio is not listed. — [Google processor services list](https://business.safety.google/services/), accessed 2026-11-21
- The processor DPA is accepted by click or by incorporation in the Agreement. It provides SCC modules plus EU, UK and Swiss coverage, gives 30 days' email notice of new subprocessors (list at business.safety.google/subprocessors), and its §7.4 says Google "has certified under the Data Privacy Framework on behalf of itself and certain wholly-owned US subsidiaries." — [Google processor terms](https://business.safety.google/processorterms/), accessed 2026-11-21
- Google LLC is reported active on the DPF list for the EU-U.S. framework, the UK Extension and the Swiss-U.S. framework, covering HR and non-HR data. The record says it "applies to Google LLC and its wholly-owned U.S. subsidiaries", with a usage end date of 13 September 2027. This is a third-party check of the official file. — [Sonomos DPF analysis](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/), accessed 2026-11-21

**Vertex AI (brief comparison)**
- Vertex AI runs under the Google Cloud Platform terms and the Cloud Data Processing Addendum. Per search snippets of the docs page, now titled "Gemini Enterprise Agent Platform and zero data retention":
  - Google does not train on customer data without permission.
  - Prompt logging for abuse monitoring applies to some customers, who "can request an exception for abuse monitoring" to get ZDR.
  - Implicit caching is in-memory only, and durable caching can be disabled per project.
  - Grounding with Google Search storage cannot be disabled. "Web Grounding for Enterprise" is recommended for ZDR.

  — [Vertex AI / Agent Platform data governance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance) (search snippets, not a full fetch), accessed 2026-11-21

### Inferences
- miyagi's own Gemini key must sit on a billing-enabled Cloud project, because that makes every call Paid. Otherwise teens' screenshots and code would go to training and human review, in direct conflict with "Do not submit … personal information to the Unpaid Services". Any EEA, UK or Swiss users would also put miyagi in breach.
- If miyagi's Gemini project was created on or after Oct 26, 2026, AI Studio logging is probably on by default. That stores full prompts (including screenshots) and responses in the project for up to 55 days, visible to whoever has project access. miyagi should turn it off, or set it to 7 days and disclose that. It should never share logs or datasets with Google.
- BYOK with a Gemini key: if the user's own key belongs to an unpaid project, their screenshots are used for training and human review under Google's terms. The privacy policy and the key-entry UI must warn about this. Gemini users must also be 18+ under Google's terms, so BYOK by teens conflicts with Google's terms, whatever miyagi says.
- §4(b)(1) of the Google APIs Terms (keep credentials confidential and discourage other API Clients from using them) arguably means a user who pastes their key into miyagi is letting another API Client use their credentials. Whether Google treats this as a breach is unclear. This is a gap rather than a finding.
- miyagi must have a published privacy policy for the Gemini API Client (§3(d)). That is a contractual duty, separate from any legal one.
- The Gemini API ZDR page suggests the Gemini API has no guaranteed ZDR. If miyagi needs ZDR, or a stronger enterprise DPA for minors' data, Vertex AI is Google's recommended path.

### Gaps
- The Additional Terms say only "limited period of time" for paid-tier abuse logging. The 55-day figure comes from the separate abuse-monitoring page, which shows no date and does not say which tier it covers.
- Unpaid-tier retention (how long human-reviewed data is kept) is not stated on any page I read.
- I did not extract the exact display requirements for Grounding with Google Search (Search Suggestions rendering rules). They apply only if miyagi uses grounding.
- I did not read Google's subprocessor list (business.safety.google/subprocessors).
- The Interactions API retention figures come from search snippets of Google docs, not a full fetch.
- The Vertex comparison rests on search snippets only.

## 3. Supabase (Auth with Google sign-in)

### Takeaway
Supabase (Supabase Pte. Ltd., Singapore, for direct customers) acts as processor under a DPA that is now part of the Terms by incorporation (Version 1, dated August 1, 2026; no separate signature). Transfers rely on SCCs. I found no evidence of DPF certification. Per user, Auth stores email, phone, timestamps (created, confirmed, last sign-in), provider identities, and user_metadata copied from the first provider (Google profile data such as name and avatar). Sessions record IP. Audit-log entries carry user agent and actor id, and IP only for some events. Deleting a user removes the auth.users row and cascades to sessions. The pages I read do not say whether audit-log entries and platform logs are purged on deletion.

### Cited Findings
**Contract**
- DPA:
  - Dated "Version 1 — August 1, 2026". **Changed in the last 12 months.**
  - It "supplements and forms part of" the Terms, and "acceptance of the Agreement shall have the same effect as signing the SCCs" (cl. 12.2).
  - Roles: "Supabase acts as a processor/service provider, and Customer as controller/business."
  - Transfers: SCCs Modules 2 and 3 (Irish law), the UK Addendum B.1.0 and a Swiss Addendum. The DPF is not mentioned.
  - Subprocessors: general authorization, with 30 days' notice only to customers who subscribe to updates and a 5-day objection window.
  - Deletion: data is deleted after a 30-day post-termination retention period.
  - Breach notice "where feasible, within forty-eight (48) hours".
  - PHI requires a BAA.

  — [Supabase DPA](https://supabase.com/legal/dpa), accessed 2026-11-21
- Earlier DPA versions were published as PDFs (e.g., "Supabase+DPA+250314.pdf", "…260317.pdf", "…260601.pdf"), so the DPA was revised several times in 2026. — [search results listing Supabase DPA PDFs](https://supabase.com/downloads/docs/Supabase+DPA+260601.pdf), accessed 2026-11-21
- Terms of Service:
  - Contracting entity: "Supabase Pte. Ltd." (Singapore) for non-AWS-Marketplace customers (§1(j)).
  - "The Parties agree to comply with the Data Processing Addendum, which is incorporated into this Agreement" (§7(b)).
  - Customer has "sole responsibility" for Customer Data and credential security (§3(c)), and represents it holds "the necessary rights and consents" (§9(a)).
  - Supabase "will not use, nor allow any third-party to use, Customer Data" to train AI models without prior written consent (§8(b)).
  - Supabase may compile Aggregated Data from usage and Customer Data and share it in compliance with law (§2(f), §8(b)).
  - No last-updated date renders: the version selector loads client-side.

  — [Supabase Terms](https://supabase.com/terms), accessed 2026-11-21
- Privacy Policy:
  - End-user data stored in projects is "Customer Data", which the policy does not govern. "We use such Customer Data primarily as a processor."
  - Account contact data is kept while the account is active and "for 60 days after you close your account".
  - Transfers to the U.S. and Singapore rely on SCCs.
  - No DPF mention, and no visible last-updated date.

  — [Supabase Privacy Policy](https://supabase.com/privacy), accessed 2026-11-21
- Subprocessor list: published as PDFs. The latest entry is dated October 12, 2026 (the earlier one June 1, 2026). **Changed in the last 12 months.** There is a "Subscribe to updates" form, which I did not submit. — [Supabase Subprocessors](https://supabase.com/legal/subprocessors), accessed 2026-11-21
- Supabase Pte. Ltd. (Singapore) is the primary data processor. Supabase, Inc. (U.S.) provides technical support and operational services. Transfers rely on SCCs. — [Supabase Data Residency and Transfers FAQ](https://supabase.com/legal/privacy-resources/data-residency-and-transfers-faq) (search snippet), accessed 2026-11-21

**What Auth stores and logs**
- User object attributes: `id`, `aud`, `role`, `email`, `email_confirmed_at`, `phone`, `phone_confirmed_at`, `confirmed_at`, `last_sign_in_at`, `created_at`, `updated_at`, `app_metadata`, `user_metadata`, `identities`, `is_anonymous`. `user_metadata` "Defaults to the first provider's identity data", which for Google sign-in means the profile fields Google returns. — [Supabase Auth: Users](https://supabase.com/docs/guides/auth/users), accessed 2026-11-21
- Audit logs:
  - Entries record the action (e.g., `user_signedup`, `login`), the actor `user_id` and `user_agent`.
  - "`ip_address` is recorded only for some events" (MFA, passkeys, identity linking, recovery codes). For a session's IP, check "the `ip` column in `auth.sessions`".
  - Logs go to external log storage and can optionally also be written to `auth.audit_log_entries`. The "Write audit logs to the database" setting turns the second copy off.
  - The page gives no retention period by plan.

  — [Supabase Auth audit logs](https://supabase.com/docs/guides/auth/audit-logs), accessed 2026-11-21
- Platform log retention: Free 1 day, Pro 7 days, Team 28 days, Enterprise 90 days. The table covers API and database logs and does not say whether Auth logs follow it. — [Supabase Logs](https://supabase.com/docs/guides/telemetry/logs), accessed 2026-11-21

**Deleting a user**
- `auth.admin.deleteUser` "Requires a `service_role` key" and must run server-side. `shouldSoftDelete` defaults to false. If true, "the user will be soft-deleted from the auth schema" (identifiable by a hashed user ID), and this "is not reversible". — [deleteUser reference](https://supabase.com/docs/reference/javascript/auth-admin-deleteuser), accessed 2026-11-21
- On deletion:
  - A hard delete "removes the row from `auth.users`, which cascades to `auth.sessions`".
  - Deletion "does not automatically sign out a user", and "a user's JWT will remain "valid" until it has expired".
  - Your own tables should reference `auth.users` "on delete cascade".
  - "You cannot delete a user if they are the owner of any objects in Supabase Storage."
  - The page says nothing about audit logs.

  — [Supabase: Managing user data](https://supabase.com/docs/guides/auth/managing-user-data), accessed 2026-11-21

**Region**
- Each project is deployed to one primary region, chosen at setup, and the region "determines where your primary project data is stored". Specific regions include us-east-1/2, us-west-1/2, ca-central-1, eu-west-1/2/3, eu-central-1/2, eu-north-1, ap-south-1, ap-southeast-1/2, ap-northeast-1/2 and sa-east-1. "General" regions let Supabase pick the AWS region. Region choice is "a data-location control, not proof of regulatory compliance". The page does not say where logs and backups live. — [Supabase Regions](https://supabase.com/docs/guides/platform/regions), accessed 2026-11-21

**DPF**
- I found no evidence that Supabase is DPF-certified. Its documents rely on SCCs. — [Supabase DPA](https://supabase.com/legal/dpa); [Supabase Privacy Policy](https://supabase.com/privacy), accessed 2026-11-21

### Inferences
- With Google sign-in, miyagi holds at least the following in Supabase, and the privacy policy should list them:
  - Google account email
  - Google profile name and avatar URL (in `user_metadata` and `identities`)
  - Google subject ID (in `identities`)
  - Created, confirmed and last-sign-in timestamps
  - Per-session IP and user agent, plus audit events
- To delete an account properly, miyagi must hard-delete the auth user, cascade or delete its own rows and any Storage objects, revoke sessions or wait for the JWT to expire, and rely on log retention (1 day on Free, 7 on Pro) for log copies to age out. It should also delete matching rows in `auth.audit_log_entries` if database audit logging is on, because Supabase does not say those rows are cascaded. Both points are inferences; see Gaps.
- Because the contracting entity is in Singapore and there is no DPF, transfers of EU or UK users' data rely on SCCs already in the DPA. miyagi needs nothing extra to sign, but its policy should name the transfer mechanism.

### Gaps
- I could not confirm whether `auth.audit_log_entries` rows or external Auth logs are deleted when a user is deleted, or how long Auth logs are kept per plan.
- I could not read the subprocessor list (PDF links only).
- I could not get last-updated dates for the Supabase Terms and Privacy Policy (the version selector loads client-side).
- I could not confirm whether the 2026 DPA versions replaced an earlier "request a signed DPA in the dashboard" process.

## 4. Render (hosts miyagi's API proxy)

### Takeaway
Render Services, Inc. is a processor under a DPA that the Terms incorporate (no signature needed). It is DPF-certified (EU-U.S., UK Extension, Swiss-U.S.) since January 6, 2025, with SCCs as the fallback. Render keeps service logs 7 days (Hobby), 14 days (Pro) or 30 days (Scale/Enterprise). Logs contain whatever miyagi's proxy writes to stdout, plus HTTP request logs (method, status, URL) on Pro and above. Render reserves the right to monitor User Content. The Terms and Privacy Policy changed on July 10, 2026.

### Cited Findings
- Terms of Service:
  - "Last Modified: July 10, 2026" (verbatim). **Changed in the last 12 months.**
  - Contracting entity: "Render Services, Inc."
  - "Personal Data that you provide to the Service pursuant to this Agreement is subject to Render's Data Processing Addendum… which is incorporated into and forms part of this Agreement." (verbatim)
  - "Render's Acceptable Use Policy is hereby incorporated by reference."
  - "Render has the right (but not the obligation) in its sole discretion to monitor and/or remove any User Content on the Service." (verbatim)
  - "You are responsible for the acts of others utilizing your access to the Service".
  - Age clause (location only): "Eligibility" says "Any use or access to the Service by anyone under 16 is strictly prohibited". This covers Render account users, not necessarily end users of an app hosted there.

  — [Render Terms](https://render.com/terms), accessed 2026-11-21
- Acceptable Use Policy:
  - "Last Modified: August 22, 2025" (verbatim). Just over 12 months old.
  - Prohibits using the Service to "Infringe upon intellectual property (including copyrights) or privacy rights, or collect personal information from other users without proper consent".
  - Prohibits "Resell, rent, lease, or otherwise provide the Service to third parties".
  - Prohibits bypassing access restrictions, "including using the Service to bypass network restrictions or access non-public services".

  — [Render Acceptable Use Policy](https://render.com/acceptable-use), accessed 2026-11-21
- Privacy Policy:
  - "Last Modified: July 10, 2026". **Changed in the last 12 months.**
  - "Note that we may also process Personal Data of our customers' end users or employees in connection with our provision of certain services to customers, in which case we are the processor of Personal Data." (verbatim)
  - Device and IP data is kept "for as long as we need it" for system operations.
  - DPF statement: "Render complies with the EU-U.S. Data Privacy Framework… the UK Extension… and the Swiss-U.S. Data Privacy Framework". The FTC has jurisdiction.

  — [Render Privacy Policy](https://render.com/privacy), accessed 2026-11-21
- DPA (no date shown on the page; read from the raw HTML):
  - It "supplements the Render Terms of Service… between… Customer and Render Services, Inc."
  - Roles (§2.1): "Customer may act either as a controller or processor and… Company is a processor".
  - Transfers out of the EEA, UK and Switzerland go "(i) pursuant to the Data Privacy Framework, or (ii) if the Data Privacy Framework does not apply or ceases to be available, pursuant to the EU SCCs" (§6.2, §6.4, §6.5). The SCCs are deemed signed.
  - Subprocessors are listed at render.com/trust, with at least 10 days' notice before a new one and 10 days to object (§4.2–4.4).
  - Breach: "without undue delay" (§8.6), with no hour limit.
  - Return or delete at the end of the services (§2.4).
  - There are U.S. state-law addenda (Virginia, Colorado and others).

  — [Render DPA](https://render.com/dpa), accessed 2026-11-21
- Subprocessors and certifications:
  - Subprocessors: AWS, Google Cloud Platform and Cloudflare (Hosting / Cloud Platform); ClickHouse Inc.; Anthropic, PBC (AI / Machine Learning); Grafana Labs (Raintank, Inc.) (Monitoring); Temporal Technologies Inc. (Workflow Orchestration); TypeSafe AI, Inc. (AI / Machine Learning). All are listed as U.S. entities.
  - Certifications listed: SOC 2 Type 2, a GDPR DPA, HIPAA, and "Certified under the EU-US Data Privacy Framework including the UK extension and Swiss-US DPF".

  — [Render Trust](https://render.com/trust), accessed 2026-11-21
- DPF certification "effective as of January 6, 2025", covering the EU-U.S. DPF, the UK Extension and the Swiss-U.S. DPF. Announced February 4, 2025. — [Render changelog](https://render.com/changelog/render-achieves-certification-under-the-eu-us-data-privacy-framework), accessed 2026-11-21
- Log retention, verbatim: "Render's log retention period depends on your workspace's plan": Hobby 7 days, Pro 14 days, Scale/Enterprise 30 days. "With a Pro workspace or higher, the log explorer also shows HTTP request logs for web services", which show the HTTP method, status code and requested URL. Logs can be streamed to a third-party provider for longer retention. — [Render Logging docs](https://render.com/docs/logging), accessed 2026-11-21
- Regions: Oregon, Ohio and Virginia (USA), Frankfurt (Germany) and Singapore. The region is chosen at creation and cannot be changed for an existing service. Static sites use a global CDN. — [Render Regions docs](https://render.com/docs/regions), accessed 2026-11-21

### Inferences
- Render is a processor for whatever passes through miyagi's proxy (screenshots, code, questions, and BYOK keys if they transit the proxy). Render's own retention applies mainly to logs, so miyagi controls exposure by never logging request bodies, images, prompts or keys.
- Running miyagi's own app backend on Render is not "provid[ing] the Service to third parties". The AUP resale clause targets reselling Render's hosting itself.
- Render's subprocessor list includes Anthropic and TypeSafe AI. Those are presumably for Render's own AI features (an assumption). They do not change miyagi's Anthropic relationship, but they belong in any subprocessor-chain disclosure.

### Gaps
- No date is shown on the DPA page.
- The docs do not say whether Render staff can read service memory or ephemeral disk outside support or abuse cases. The only access language is the Terms' "right… to monitor and/or remove any User Content".
- I did not verify Render's DPF record on the official list (third-party JavaScript-only site). The evidence is Render's own privacy policy, trust page and changelog.

## 5. GitHub Pages (marketing and download site)

### Takeaway
GitHub logs every Pages visitor's IP address "for security purposes" as its own processing under the GitHub Privacy Statement (effective April 27, 2026). Pages is "not intended for or allowed to be used as a free web-hosting service to run your online business, e-commerce site, or any other website that is primarily directed at either facilitating commercial transactions or providing commercial software as a service (SaaS)". A static download page for a free app fits the stated purpose ("a showcase for personal and organizational projects"). GitHub states it is DPF-certified.

### Cited Findings
- "When a GitHub Pages site is visited, the visitor's IP address is logged and stored for security purposes, regardless of whether the visitor has signed into GitHub or not." (verbatim). — [About GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), accessed 2026-11-21
- Usage limits:
  - Verbatim: "GitHub Pages is not intended for or allowed to be used as a free web-hosting service to run your online business, e-commerce site, or any other website that is primarily directed at either facilitating commercial transactions or providing commercial software as a service (SaaS). GitHub Pages sites shouldn't be used for sensitive transactions like sending passwords or credit card numbers."
  - Published sites may be at most 1 GB, with a recommended source repository limit of 1 GB.
  - Soft bandwidth limit: "100 GB per month".
  - Soft limit of 10 builds per hour, which does not apply to custom Actions workflows.

  — [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits), accessed 2026-11-21
- Additional Products and Features terms ("Version Effective Date: August 27, 2026"; **changed in the last 12 months**), Pages section, verbatim:
  - "GitHub Pages is intended to host static web pages, but primarily as a showcase for personal and organizational projects."
  - "…not intended for or allowed to be used as a free web hosting service to run your online business, e-commerce site, or any other website that is primarily directed at either facilitating commercial transactions or providing commercial software as a service (SaaS). Some monetization efforts are permitted on Pages, such as donation buttons and crowdfunding links."
  - "GitHub Pages may not be used in violation of the Agreement, the GitHub Acceptable Use Policies, or the GitHub Pages service limitations".

  — [GitHub Terms for Additional Products and Features](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features), accessed 2026-11-21
- Acceptable Use Policies: §9 "Excessive bandwidth use" lets GitHub "suspend your Account, throttle your file hosting, or otherwise limit your activity". §5 bans using the platform "to deliver malicious executables". No visible date; an HTML comment reads "localization update 2026-03-11". — [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies), accessed 2026-11-21
- GitHub General Privacy Statement:
  - "Effective date: April 27, 2026". **Changed in the last 12 months.**
  - It covers Service Usage Information such as "IP address, device information, session details, date and time of requests".
  - "GitHub has certified to the U.S. Department of Commerce that it adheres to the EU-U.S. Data Privacy Framework Principles."
  - It has no Pages-specific section.

  — [GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement), accessed 2026-11-21
- GitHub Terms of Service: "Effective date: April 27, 2026". **Changed in the last 12 months.** They add a new "Access Reciprocity" clause (D.9) about scraping public GitHub content to train commercial AI. It does not apply below 700 million monthly active users and is not relevant to hosting a site. — [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service), accessed 2026-11-21
- Microsoft states that certain U.S. subsidiaries, including GitHub, maintain their own DPF certification. — [Microsoft DPF covered entities](https://www.microsoft.com/en-us/privacy/microsoft-data-privacy-framework-covered-entities) (search snippet), accessed 2026-11-21

### Inferences
- A static landing page with a free download, docs and a code-gated link is neither "facilitating commercial transactions" nor "commercial software as a service", so it is within the rules. It would become doubtful if the site began selling subscriptions or licenses or taking payments. Donation buttons are expressly allowed.
- Large installers belong in GitHub Releases rather than the Pages site, to stay under the 1 GB site limit and the 100 GB/month soft bandwidth limit.
- The privacy policy should say that the site host (GitHub) logs visitors' IP addresses for security under GitHub's own privacy statement. GitHub acts as an independent controller here: no DPA covers Pages visitors for a free account.

### Gaps
- GitHub does not publish a retention period for Pages visitor IP logs.
- I did not confirm GitHub's DPF record on the official list.

## 6. jsDelivr and Google Fonts (site assets)

### Takeaway
Loading a script from cdn.jsdelivr.net sends the visitor's IP, browser type and version, referrer domain, URL and time to Volentio JSD Limited (England & Wales) and its CDN providers (Cloudflare, Fastly, Gcore; Bunny for legacy endpoints). The retention period is unspecified ("a shorter period … until it is analyzed and deleted"). There are no cookies and no sale of data. Loading Google Fonts sends the visitor's IP, the requested URL and HTTP headers (user agent, referer) to Google. Google says it sets no cookies and does not use this data for profiles or targeted ads. Self-hosting both removes these third parties entirely.

### Cited Findings
- jsDelivr Privacy Policy:
  - "*Effective date: November 23, 2023*". Not changed in the last 12 months; the last commits to the source file date from 2023-11-23.
  - Operator: "Volentio JSD Limited… a company registered in England and Wales, operates the cdn.jsdelivr.net service".
  - Usage Data "may include information such as your computer's Internet Protocol address (e.g., IP address), browser type, browser version, referrer data (limited to domain), the URLs of our Service that you visit (limited to the cdn.jsdelivr.net domain), the time and date of your visit, unique device identifiers and other diagnostic data."
  - "Non-aggregated Usage Data is retained for a shorter period of time until it is analyzed and deleted, except when this data is used to strengthen the security or to improve the functionality of our Service, or we are legally obligated…"
  - "Our Services do not use cookies or other similar technologies."
  - "We use third-party Service Providers to serve all of our traffic under the domain cdn.jsdelivr.net. This means all of these providers have access to your IP address and other information sent by your web browser."
  - "We do not sell your personal data."

  The policy page at jsdelivr.com renders only through JavaScript. The text above was read from jsDelivr's own source file on GitHub. — [jsDelivr Privacy Policy](https://www.jsdelivr.com/terms/privacy-policy-jsdelivr-net); [source file](https://raw.githubusercontent.com/jsdelivr/jsdelivr/master/Privacy%20Policy.md), accessed 2026-11-21
- jsDelivr Sub-Processors: Cloudflare, Fastly, Gcore, and Bunny ("Limited to legacy bootstrapcdn.com CDN endpoints"). "Neither we nor our providers track any individual user." — [jsDelivr Sub-Processors](https://raw.githubusercontent.com/jsdelivr/jsdelivr/master/Sub-Processors.md), accessed 2026-11-21
- jsDelivr DPA: "Volentio JSD Data Processing Agreement" between a Subscriber and "Volentio JSD Limited". It lists processed data (IP addresses, browser type and version, referrer domain, URLs, time, device identifiers), SCC Clause 9 Option 2 with 5 days' notice, and CCPA service-provider restrictions. A separate search snippet says the privacy policy does not apply to data processed for enterprise or business users. — [jsDelivr DPA (PDF)](https://www.jsdelivr.com/documents/data-processing-agreement.pdf), accessed 2026-11-21
- Google Fonts privacy FAQ (developers.google.com/fonts/faq/privacy now 301-redirects to fonts.google.com/faq#privacy, which renders only through JavaScript, so the content comes from search snippets of the FAQ):
  - Requests to the Google Fonts Web API are unauthenticated, no cookies are set or logged, and requests go to resource-specific domains (fonts.googleapis.com, fonts.gstatic.com).
  - Each request sends "(1) the IP address used by the respective user to access the Internet, (2) the requested URL on the Google server, and (3) HTTP headers including the user agent, and the referer".
  - "Google does not use any information collected by Google Fonts to create profiles of end users or for targeted advertising."

  — [Google Fonts privacy FAQ](https://developers.google.com/fonts/faq/privacy) (search snippets), accessed 2026-11-21
- Google Fonts does not appear on Google's processor-services list, so Google acts as an independent controller for font requests. — [Google processor services list](https://business.safety.google/services/), accessed 2026-11-21
- Search results also report European enforcement against embedding Google Fonts from Google's servers without consent: a Munich court ruling against a website, and an Austrian DPA finding against Google. The summaries conflict on the Austrian outcome, and I did not read either primary source. — [iubenda on the Austrian DPA decision](https://www.iubenda.com/en/blog/gdpr-violation-lack-of-transparency-in-data-processing-via-google-fonts/); [CookieFirst on Google Fonts and the GDPR](https://cookiefirst.com/google-fonts-and-the-gdpr-how-does-it-work/) (search snippets only), accessed 2026-11-21

### Inferences
- jsDelivr and Google Fonts are not processors for miyagi on the free public CDN. They receive visitor IPs as independent parties. The simplest fix is to self-host the scripts and fonts in the Pages repo. The privacy policy can then drop both vendors, leaving only GitHub Pages' IP logging.
- If either stays, the privacy policy must name it, say that the visitor's IP, user agent and referrer go to it when the page loads, and link to its policy. For EU visitors, a consent or legitimate-interest analysis would be needed.

### Gaps
- jsDelivr publishes no retention period in days for raw logs.
- The Google Fonts FAQ text comes from search snippets. I could not read it live, and its last-updated date is unknown.
- Google publishes no retention period for Fonts request logs.
- jsDelivr is a UK company, so the DPF does not apply. Whether its CDN providers are DPF-certified was not checked.

## 7. Data Privacy Framework status (dataprivacyframework.gov)

### Takeaway
The official list (dataprivacyframework.gov/list) renders only through JavaScript, so I could not query it directly. Based on vendors' own statements and a Nov 17, 2026 third-party check of the official file:
- **Google LLC:** active.
- **Render:** certified since Jan 6, 2025, per its own documents.
- **GitHub:** certified, per its own statement.
- **Anthropic:** not listed.
- **Supabase:** no evidence of certification.
- **jsDelivr:** UK company, so not applicable.

### Cited Findings
- dataprivacyframework.gov/list returned only the page title, with no participant data. — [DPF List](https://www.dataprivacyframework.gov/list), accessed 2026-11-21
- **Google LLC:** active (EU-U.S., UK Extension, Swiss-U.S.; HR and non-HR). The record "applies to Google LLC and its wholly-owned U.S. subsidiaries", and the usage end date is 13 September 2027. **Anthropic** and OpenAI were not found as active or inactive participants. Method: a search of the official file "as of Tuesday, November 17, 2026 6:01 AM EST". The source is a vendor blog, not the Department of Commerce. — [Sonomos DPF analysis](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/), accessed 2026-11-21
- Google's own DPA says Google "has certified under the Data Privacy Framework on behalf of itself and certain wholly-owned US subsidiaries" (§7.4). — [Google processor terms](https://business.safety.google/processorterms/), accessed 2026-11-21
- **Render** (DPA importer "Render Services, Inc."): certified to the EU-U.S. DPF, UK Extension and Swiss-U.S. DPF, effective January 6, 2025. — [Render changelog](https://render.com/changelog/render-achieves-certification-under-the-eu-us-data-privacy-framework); [Render Privacy Policy](https://render.com/privacy), accessed 2026-11-21
- **GitHub:** "GitHub has certified to the U.S. Department of Commerce that it adheres to the EU-U.S. Data Privacy Framework Principles." — [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement), accessed 2026-11-21
- **Supabase:** no DPF mention in its DPA or privacy policy, which rely on SCCs. — [Supabase DPA](https://supabase.com/legal/dpa), accessed 2026-11-21
- **Anthropic:** its DPA relies on SCCs plus the UK and Swiss addenda, with no DPF mention. — [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum), accessed 2026-11-21
- Context: the DPF remains in force. The EU General Court dismissed the Latombe challenge on 3 September 2025, and the appeal (C-703/25 P) was pending as of 18 November 2026. — [Sonomos DPF analysis](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/), accessed 2026-11-21

### Inferences
- Where there is no DPF (Anthropic, Supabase), EU, UK and Swiss transfers rely on the SCCs already built into each vendor's DPA. miyagi's privacy policy should say "Standard Contractual Clauses" for those vendors and "Data Privacy Framework (with SCCs as fallback)" for Render and Google.

### Gaps
- I did not verify any participant record directly on dataprivacyframework.gov. A person should search each name in a browser and record the exact legal entity names, active status and renewal dates.

## 8. Summary table

### Takeaway
One-line view per vendor. Details and quotes are in sections 1–7.

### Cited Findings
| Vendor | Data we send | Their role | Retention | Training use | Contract (DPA / SCC / DPF) | Customer duties we must meet | Sources (accessed 2026-11-21) |
|---|---|---|---|---|---|---|---|
| **Anthropic** (Claude API via our Render proxy) | Screenshots, user code, lesson context, questions; model outputs | Processor ("Customer is the controller and Anthropic is Customer's processor") | Deleted within 30 days by default. Flagged: inputs/outputs up to 2 yrs, classifier scores up to 7 yrs. Feedback 5 yrs. ZDR only by agreement. Covered models: 30 days mandatory | "may not train models on Customer Content" | DPA incorporated by reference (eff. Feb 24, 2025). EU SCCs M2/M3 + UK and Swiss addenda. **Not on DPF list** (third-party check) | AI disclosure at start of each session or in the UI. Tell users outputs may be inaccurate (§D.3). Users must follow the Usage Policy (no plagiarism, no guardrail bypass). High-risk Education rules if grades are used for credentials or misconduct. Supported Regions Policy. No reselling or competing use. Responsible for all account activity and key security | [Commercial Terms](https://www.anthropic.com/legal/commercial-terms); [Usage Policy](https://www.anthropic.com/legal/aup); [Retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data); [Covered models](https://support.claude.com/en/articles/15425996-data-retention-practices-for-covered-models); [DPA](https://www.anthropic.com/legal/data-processing-addendum); [Regions](https://www.anthropic.com/supported-countries); [Sonomos](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/) |
| **Google Gemini API** (paid project, via proxy) | Same as Anthropic | Processor on Paid Services (processor DPA lists "Gemini API Paid Services"). On Unpaid, Google uses data for its own purposes | Paid: abuse logs 55 days. AI Studio logs default on for projects created on or after Oct 26, 2026 (55 days default, 7–55 configurable). Interactions `store` 55 days paid / 1 day free. Grounding 30 days. No guaranteed ZDR (Google points to Vertex) | Paid: not used to improve products. Unpaid: used for improvement, human reviewers | Google processor DPA v10 (May 7, 2026), applies to Paid. SCC modules. **Google LLC DPF active** | Must use Paid for EEA, UK and CH users. Must not send personal data to Unpaid. Publish a privacy policy (APIs ToS §3(d)). Keep credentials confidential (§4(b)(1)). Prohibited Use Policy. No sublicensing of the API. 18+ and under-18 app restriction (age researcher) | [Additional Terms](https://aistudio.google.com/docs/terms); [Abuse monitoring](https://aistudio.google.com/docs/usage-policies); [Logs](https://aistudio.google.com/docs/logs-policy); [ZDR](https://aistudio.google.com/docs/zdr); [APIs ToS](https://developers.google.com/terms); [Processor terms](https://business.safety.google/processorterms/); [Services](https://business.safety.google/services/); [PUP](https://policies.google.com/terms/generative-ai/use-policy) |
| **Supabase Auth** | Google sign-in result: email, name/avatar (user_metadata), Google identity, timestamps, session IP and user agent, audit events | Processor (Supabase Pte. Ltd., Singapore) | Until we delete the user (hard delete cascades to sessions). Platform logs 1 / 7 / 28 / 90 days by plan (Auth-log coverage unclear). Post-termination 30 days. Account-holder data 60 days after closure | Will not train AI on Customer Data without written consent | DPA v1 Aug 1, 2026, incorporated in Terms. SCCs M2/M3 + UK and Swiss. **No DPF found** | Responsible for Customer Data and consents (§9(a)). Credential security (service_role key server-side only). Choose region | [DPA](https://supabase.com/legal/dpa); [Terms](https://supabase.com/terms); [Privacy](https://supabase.com/privacy); [Users](https://supabase.com/docs/guides/auth/users); [Audit logs](https://supabase.com/docs/guides/auth/audit-logs); [Logs](https://supabase.com/docs/guides/telemetry/logs); [Delete user](https://supabase.com/docs/guides/auth/managing-user-data); [Regions](https://supabase.com/docs/guides/platform/regions) |
| **Render** (proxy host) | All proxied traffic (screenshots, code, questions, any BYOK key in transit), plus whatever we log | Processor (Render Services, Inc.) | Logs 7 days (Hobby) / 14 days (Pro) / 30 days (Scale/Enterprise). HTTP request logs (method, status, URL) on Pro and above | None stated | DPA incorporated in Terms. **DPF certified** (EU, UK, CH) since Jan 6, 2025, SCCs as fallback. 10-day subprocessor notice | AUP: no privacy infringement or collecting personal info without consent, no reselling Render. Responsible for others' use of our access | [Terms](https://render.com/terms); [AUP](https://render.com/acceptable-use); [Privacy](https://render.com/privacy); [DPA](https://render.com/dpa); [Trust](https://render.com/trust); [Logging](https://render.com/docs/logging) |
| **GitHub Pages** (site) | Site visitors' IP and request data | Independent controller (GitHub) | Not published ("logged and stored for security purposes") | n/a | GitHub Privacy Statement (Apr 27, 2026). **GitHub DPF certified** (self-stated). No DPA for free Pages | Not for commerce or SaaS. Not for sensitive transactions. 1 GB site, 100 GB/month soft bandwidth | [About Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages); [Limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits); [Additional terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features); [Privacy](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| **jsDelivr** (if scripts load from CDN) | Visitor IP, browser type and version, referrer domain, URL, time | Independent controller (Volentio JSD Ltd, UK). DPA available for subscribers | Unspecified "shorter period" for non-aggregated logs | n/a | UK entity (DPF n/a). DPA with SCCs for subscribers | None beyond disclosure | [Privacy source](https://raw.githubusercontent.com/jsdelivr/jsdelivr/master/Privacy%20Policy.md); [Sub-processors](https://raw.githubusercontent.com/jsdelivr/jsdelivr/master/Sub-Processors.md); [DPA](https://www.jsdelivr.com/documents/data-processing-agreement.pdf) |
| **Google Fonts** (if loaded from Google) | Visitor IP, requested URL, user agent, referer | Independent controller (Google), not on the processor list | Not published | "does not use … to create profiles … or for targeted advertising" | Google LLC DPF active | None beyond disclosure (and EU consent risk) | [Fonts FAQ](https://developers.google.com/fonts/faq/privacy) (snippets); [Services list](https://business.safety.google/services/) |

### Inferences
- The table's "role" for jsDelivr, Google Fonts and GitHub Pages is my reading of the documents, since no processor agreement covers free public use. The same applies to "Unpaid Gemini = Google uses data for its own purposes".

### Gaps
- See the per-vendor Gaps above. The unknowns that matter most for a privacy policy: Supabase Auth-log deletion and retention, retention for GitHub Pages IP logs and Google Fonts logs, and direct confirmation of DPF entries.

## 9. Implications for miyagi

### Takeaway
miyagi can describe all of these vendors truthfully in a privacy policy today. But it is likely breaching or straining at least three customer duties unless it acts:
- **Gemini tier and age rules.** miyagi must run Gemini on a paid, billing-enabled project with AI Studio logging off or minimized. Google's 18+ rule for apps likely to be used by minors conflicts with teen users.
- **Anthropic's AI-interaction disclosure and accuracy notice.** These must be shown in the product.
- **Its own logging and BYOK key handling.** These must match what the policy says.

A lawyer is warranted, mainly because of minors, screenshots that capture third parties' data, Gemini's age clause, and EU transfers.

### Cited Findings
- Anthropic requires an AI disclosure "at the beginning of each chat session or in the product interface" ([Usage Policy](https://www.anthropic.com/legal/aup)) and a user notice that factual assertions "should not be relied upon without independently checking their accuracy" ([Commercial Terms §D.3](https://www.anthropic.com/legal/commercial-terms)), accessed 2026-11-21.
- Gemini allows "only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom". It warns "Do not submit sensitive, confidential, or personal information to the Unpaid Services" and requires users to be 18+ ([Gemini API Additional Terms](https://aistudio.google.com/docs/terms)). Logging is on by default for projects created on or after Oct 26, 2026 ([Logs policy](https://aistudio.google.com/docs/logs-policy)), accessed 2026-11-21.
- The Google APIs Terms require "a privacy policy for your API Client that clearly and accurately describes to users of your API Client what user information you collect" and confidential credentials ([Google APIs Terms](https://developers.google.com/terms)), accessed 2026-11-21.
- Render keeps logs 7, 14 or 30 days by plan ([Render Logging](https://render.com/docs/logging)). Supabase keeps logs 1, 7, 28 or 90 days by plan ([Supabase Logs](https://supabase.com/docs/guides/telemetry/logs)). Both accessed 2026-11-21.

### Inferences
**What the privacy policy must say, per vendor**
1. **Anthropic:**
   - What is sent: screenshots of the user's screen, which may include anything visible; code; lesson context; questions.
   - Anthropic acts as miyagi's processor and does not train on the data.
   - It deletes data within 30 days by default, but keeps flagged content up to 2 years and safety scores up to 7 years.
   - Transfers to the U.S. are under SCCs.
2. **Google Gemini:**
   - The same categories are sent.
   - Paid tier: not used to train or improve Google's models, but logged up to 55 days for abuse monitoring, possibly with human review of flagged content. Also disclose any AI Studio log retention miyagi keeps.
   - If Grounding with Google Search is used: 30-day storage.
   - Google LLC is DPF-certified.
3. **Supabase:**
   - Google sign-in data stored: email, name, profile picture URL, Google account ID, sign-in times, session IP addresses and user agents, and auth audit events.
   - The storage region.
   - Retention until the user deletes their account, plus log retention.
   - SCCs (Singapore and U.S. entities).
4. **Render:**
   - It hosts the proxy that relays requests.
   - What miyagi logs (ideally only metadata) and how long logs last (7, 14 or 30 days by plan).
   - DPF.
5. **GitHub Pages:** GitHub logs site visitors' IP addresses for security, under GitHub's own privacy statement.
6. **jsDelivr and Google Fonts:** self-host both and drop them, or disclose that loading the site sends IP, user agent and referrer to each.
7. **Telemetry:** opt-in, sent to miyagi's own endpoint. Describe the fields, the retention, and where the endpoint is hosted (probably Render, so Render's log retention applies).
8. **BYOK:**
   - When a user brings their own key, requests are made under the user's own agreement with Anthropic or Google. That provider's terms and the user's account settings govern retention and training.
   - With an unpaid (free-tier) Gemini key, Google may use the content for training and have humans review it.
   - Say exactly where the key is stored (local OS keychain or app storage) and whether it transits miyagi's proxy. If it does, say it is never logged or stored server-side.

**Settings and tiers miyagi must use**
- **Gemini:**
  - Use a billing-enabled Cloud project for all miyagi-key traffic, so all calls are Paid Services.
  - Turn AI Studio logging off, or set it to 7 days.
  - Never share datasets with Google.
  - Use `store=false` if the Interactions API is used.
  - Avoid Files API, context-cache and Grounding unless needed and disclosed.
  - Vertex AI is the route if ZDR or a stronger enterprise DPA becomes necessary (e.g., for schools).
- **Anthropic:**
  - The defaults are acceptable for a policy (30 days, no training).
  - Avoid the Files API, or delete files.
  - Consider asking for ZDR later. It needs an agreement, and covered models force 30-day retention anyway.
- **Supabase:**
  - Pick a specific region (e.g., us-east-1) rather than a "general" one.
  - Keep the `service_role` key server-side.
  - Decide whether to write audit logs to the database. If yes, delete a user's audit rows on account deletion.
  - Implement full deletion: hard `deleteUser`, cascades, Storage objects.
- **Render:**
  - Never log request bodies, screenshots, prompts, outputs or API keys.
  - Pick a region.
  - Know that log retention follows the plan.
  - Subscribe to subprocessor notices at render.com/trust. The DPA says the customer "agrees to subscribe". Doing so means submitting a form, which a person must do; it was not done in this research.
- **Site:** self-host scripts and fonts, keep the site free of commerce, and host binaries in Releases.

**Customer duties miyagi may currently be breaching (to verify against the app)**
- *Anthropic Usage Policy AI disclosure:* breached if the overlay does not visibly say it is AI at session start or in the interface.
- *Anthropic §D.3 accuracy notice:* breached if no notice is shown anywhere (UI or Terms).
- *Anthropic Supported Regions Policy:* breached if nothing restricts use from unsupported regions. At minimum, miyagi's Terms should prohibit that use. Geo-blocking at the proxy is safer.
- *Gemini:*
  - Using an unpaid key for user traffic breaches the personal-data warning, and the EEA, UK and Swiss rule if any such users exist.
  - Teen users conflict with the 18+ and "likely to be accessed by individuals under 18" restriction. This needs the age researcher's analysis and probably a product decision: route minors to Anthropic only, move to Vertex AI, or get Google's approval.
  - "professional or business purposes, not for consumer use" is ambiguous for a free consumer app. A lawyer should read it.
- *Google APIs ToS §3(d):* miyagi must already have a privacy policy covering what it collects and shares with Google.
- *Google APIs ToS §4(b)(1) and Anthropic §D.5:* miyagi's own keys must never ship in the desktop app binary. Everything goes through the proxy. And the proxy must authenticate miyagi clients so it is not an open relay, which would also strain the "no reselling or sublicensing" clauses.
- *Usage Policy plagiarism clause:* miyagi's Terms should forbid using it to submit AI-assisted graded work without permission. The overlay design should not facilitate covert exam help.
- *Usage Policy High-risk Education:* not triggered by formative grading. It is triggered if miyagi is marketed to or used by institutions for credit, certification or misconduct decisions. Then a qualified human must review, and students must be told AI was used.
- *Render AUP and Anthropic surveillance clause:* screenshots can capture other people's messages and data. miyagi should minimize capture (active window or region only, with redaction where possible) and tell users not to capture other people's private information.

**Is a lawyer needed? Yes, for these reasons**
1. Minors: COPPA (if under-13s can sign up) and state teen-privacy laws. Gemini's contractual 18+ restriction is a direct conflict that a lawyer should resolve before launch.
2. Screenshots are an unusually broad data category. They may include third parties' personal data and sensitive categories, which brings in GDPR Art. 9 and CCPA "sensitive personal information" questions, plus purpose limitation.
3. International transfers to two processors without the DPF (Anthropic, Supabase), under SCCs. If EU or UK users are served, miyagi as exporter may need a transfer impact assessment and an Art. 27 representative analysis.
4. BYOK structure: who is the controller when a user's own key is used, and whether collecting users' keys fits Google's credential clause.
5. Whether "grading tutorials" could fall within Anthropic's Education high-risk area for some customers, and how to word AI disclosures and accuracy notices.
6. Drafting the Terms and the Privacy Policy, so that the vendor duties above (AI disclosure, accuracy notice, regions, prohibited uses) flow down to users.

### Gaps
- I have not verified miyagi's actual configuration:
  - which Gemini project tier and creation date miyagi uses
  - whether AI Studio logging is on
  - whether BYOK keys transit the proxy
  - what the proxy logs
  - which Supabase plan and region are used
  - whether audit logs are written to the database
  - whether the site actually loads jsDelivr or Google Fonts

  Each of these changes what the policy must say and whether a duty is being breached.
- Supabase Auth-log retention and deletion behavior is unconfirmed.
- No DPF status was verified on the official site.
