# EU and UK privacy, cookie, AI Act and accessibility obligations for miyagi (status 2026-11-21)

Scope note: research notes only, not legal advice. Every link was accessed 2026-11-21. Where a source is secondary (law-firm blog, vendor blog, news), it is labelled "secondary". Primary texts were read in full-text copies from EUR-Lex, legislation.gov.uk, EDPB, ICO and the Commission. No founder details were used in any search.

## Q1. Territorial scope: does GDPR (Art. 3(2)) or UK GDPR reach a free, worldwide-downloadable US app with no EU/UK marketing?

### Takeaway
Being free does not take miyagi out of scope. "Offering services" (Art. 3(2)(a)) needs evidence that miyagi *envisages* serving EU or UK users, and passively accepting sign-ups is weak evidence on its own. The bigger risk is Art. 3(2)(b), "monitoring of behaviour", which needs no intent to target. An app that screenshots the user's screen, reads their code and grades their progress can plausibly count as monitoring of anyone using it in the EU or UK. The UK GDPR uses the same test. The safe working assumption is that both laws apply to EU and UK users.

### Cited Findings
- GDPR Art. 3(2): it applies to a non-EU controller processing data of people "who are in the Union" where the processing relates to "(a) the offering of goods or services, irrespective of whether a payment of the data subject is required ... or (b) the monitoring of their behaviour as far as their behaviour takes place within the Union." — [GDPR, Regulation (EU) 2016/679, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- EDPB on free services: whether an activity is an offer of services "is not therefore dependent whether payment is made in exchange for the goods or services provided." — [EDPB Guidelines 3/2018 on territorial scope, v2.0 adopted 12 Nov 2019, v2.1 7 Jan 2020](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- EDPB: processing an EU person's data "alone is not sufficient". The element of "targeting", either by offering goods or services or by monitoring behaviour, "must always be present in addition." — [EDPB Guidelines 3/2018, p.15](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- Recital 23, quoted by the EDPB: "the mere accessibility of the controller's ... website in the Union, of an email address or of other contact details, or the use of a language generally used in the third country where the controller is established, is insufficient". A currency or language used in a member state, or "the mentioning of customers or users who are in the Union", may show intent. — [EDPB Guidelines 3/2018, p.17](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- EDPB targeting factors, to be weighed in combination:
  - the EU or a member state is named in relation to the service;
  - paid search referencing or ad campaigns aimed at an EU audience;
  - the international nature of the activity;
  - dedicated EU addresses or phone numbers;
  - a non-home top-level domain (e.g. ".de") or a neutral TLD such as ".eu";
  - travel instructions from member states;
  - mention of an international clientele from member states, e.g. testimonials;
  - an EU language or currency;
  - delivery of goods to member states. — [EDPB Guidelines 3/2018, pp.17-18](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- EDPB Example 10: a US news app "exclusively directed at the U.S. market", shown by its terms and USD-only pricing, is not subject to GDPR when a US tourist uses it in Europe. — [EDPB Guidelines 3/2018, p.16](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- EDPB on monitoring (Art. 3(2)(b)):
  - Unlike 3(2)(a), it has no express "intention to target" requirement. "Monitoring" implies the controller "has a specific purpose in mind for the collection and subsequent reuse of the relevant data about an individual's behaviour within the EU".
  - Not every online collection counts. The controller's purpose and "any subsequent behavioural analysis or profiling techniques" matter.
  - Tracking "through other types of network or technology", not only the web, is relevant.
  - Listed examples include "Online tracking through the use of cookies or other tracking techniques", "Personalised diet and health analytics services online" and "Market surveys and other behavioural studies based on individual profiles." — [EDPB Guidelines 3/2018, pp.19-20](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- EDPB Example 18: an app developer in Canada with no EU establishment that "monitors the behaviour of data subject in the Union" is subject to GDPR under Art. 3(2)(b). — [EDPB Guidelines 3/2018, p.20](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- UK GDPR Art. 3(2) mirrors the EU text, covering the offering of goods or services "irrespective of whether a payment of the data subject is required, to such data subjects in the United Kingdom" or "the monitoring of their behaviour as far as their behaviour takes place within the United Kingdom." — [UK GDPR Art. 3, legislation.gov.uk](https://www.legislation.gov.uk/eur/2016/679/article/3) (accessed 2026-11-21)
- UK Upper Tribunal, *ICO v Clearview AI Inc* [2025] UKUT 319 (AAC), October 2025: a US company's processing was held to be "within the territorial scope of the GDPR and UK GDPR". The case went back to the First-tier Tribunal on the merits. — [11KBW case note, 14 Oct 2025 (secondary)](https://www.11kbw.com/knowledge-events/case/upper-tribunal-hands-down-clearview-v-ico-judgment-on-territorial-and-material-scope-of-gdpr/); [ICO news, Oct 2025](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2025/10/uk-upper-tribunal-hands-down-judgment-on-clearview-ai-inc) (accessed 2026-11-21)
- The Dutch AP held that Locatefamily.com, apparently Canadian with no EU establishment, fell under Art. 3(2) because it "provides a service to EU-based individuals". — [Hunton blog, 19 May 2021 (secondary)](https://www.hunton.com/privacy-and-cybersecurity-law-blog/dutch-dpa-fines-company-525000-eur-for-failure-to-designate-eu-representative); [EDPB national news](https://www.edpb.europa.eu/node/2676_en) (accessed 2026-11-21)

### Inferences
- **Art. 3(2)(a), offering.** These facts point away from targeting: English only, US-based, no EU ads, USD or no pricing, and a generic ".study" TLD that is neither EU nor neutral-EU. Accepting EU sign-ups alone is probably not enough under the EDPB's test. That changes with any of the following:
  - listing the Microsoft Store build in EU or UK markets on purpose;
  - EU or UK testimonials, or "users in 40 countries" style claims that name EU states;
  - EUR or GBP pricing;
  - outreach to EU or UK communities.
- **Art. 3(2)(b), monitoring.** This is the more likely hook. miyagi repeatedly captures screen content and code, then analyses it to grade a specific user and steer their next step. That fits "tracking through other types of ... technology" combined with analysis of a person's behaviour. A regulator could find monitoring whatever the marketing posture. Opt-in usage telemetry adds a second, classic monitoring activity.
- **Recommended posture.** Treat EU and UK users as in scope. The alternative is to block EU/UK sign-ups (geo-gate, and exclude EU/UK markets in the Microsoft Store) and say in the terms that the service is for US users. EDPB Example 10 suggests that a documented US-only posture plus technical gating is the cleanest way to stay out.

### Gaps
- I did not read the full Clearview Upper Tribunal judgment, so I cannot quote how it read "monitoring". A search result points to a later Court of Appeal stage ([judiciary.uk listing PDF, Oct 2026](https://www.judiciary.uk/wp-content/uploads/2026/10/WC-2026.10.19-Clearview-Appellant.pdf), accessed 2026-11-21, not opened). Its outcome is unknown as of 2026-11-21.
- I found no CJEU ruling squarely interpreting Art. 3(2)(b) for desktop software.

## Q2. If in scope: representative, notice, legal bases, children's consent, special categories, DPIA, processor terms, records, breach notification

### Takeaway
If GDPR or UK GDPR applies, miyagi needs the following:
- an EU representative and a UK representative (the "occasional" exemption does not fit a core, continuous service);
- a full Art. 13 notice;
- contract necessity (Art. 6(1)(b)) as the basis for core grading and accounts, and consent for telemetry;
- a plan for teens: the age of digital consent is 13 to 16 by country, and 13 in the UK;
- controls on incidental special-category data in screenshots;
- a DPIA (several high-risk criteria are met);
- Art. 28 DPAs with every vendor;
- a written record of processing (the under-250 exemption does not apply);
- a 72-hour breach process covering every relevant authority.

### Cited Findings
**Representative (Art. 27)**
- Art. 27(1): "Where Article 3(2) applies, the controller or the processor shall designate in writing a representative in the Union."
  - The exemption (27(2)(a)) covers processing that is "occasional", involves no large-scale special-category or criminal data, and "is unlikely to result in a risk".
  - The representative must be in a member state where the data subjects are (27(3)).
  - Designating one is "without prejudice to legal actions which could be initiated against the controller" (27(5)). — [GDPR Art. 27, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- EDPB:
  - Processing is "occasional" only "if it is not carried out regularly, and occurs outside the regular course of business or activity of the controller".
  - Authorities can address "corrective measures or administrative fines" to the representative, though its direct liability is limited to Arts. 30 and 58(1)(a).
  - The representative's details must be in the information given to users. — [EDPB Guidelines 3/2018, pp.24-28](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_3_2018_territorial_scope_after_public_consultation_en_1.pdf) (accessed 2026-11-21)
- UK GDPR Art. 27 has the same structure and the same "occasional ... unlikely to result in a risk" exemption, with a representative "in the United Kingdom". — [UK GDPR Art. 27, legislation.gov.uk](https://www.legislation.gov.uk/eur/2016/679/article/27) (accessed 2026-11-21)

**Notice contents (Art. 13), all due "at the time when personal data are obtained"**
- Art. 13(1):
  - (a) identity and contact details of the controller and of its representative;
  - (b) DPO contact, where applicable;
  - (c) purposes and legal basis;
  - (d) the legitimate interests pursued, if relying on Art. 6(1)(f);
  - (e) recipients or categories of recipients;
  - (f) any intended third-country transfer, whether an adequacy decision exists, or the safeguards used and how to get a copy.
- Art. 13(2):
  - (a) retention period or the criteria for it;
  - (b) rights of access, rectification, erasure, restriction, objection and portability;
  - (c) the right to withdraw consent, where consent is the basis;
  - (d) the right to complain to a supervisory authority;
  - (e) whether providing data is a statutory or contractual requirement, and the consequences of not providing it;
  - (f) any automated decision-making or profiling under Art. 22, with "meaningful information about the logic involved".
- Art. 13(3): further notice before any new purpose. — [GDPR Art. 13, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)

**Legal bases**
- EDPB on Art. 6(1)(b): processing must be "objectively necessary" for the contract. Art. 6(1)(b) "will not cover processing which is useful but not objectively necessary". If "realistic, less intrusive alternatives" exist, the processing is not necessary. — [EDPB Guidelines 2/2019 on Art. 6(1)(b), v2.0 adopted 8 Oct 2019, para 25](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines-art_6-1-b-adopted_after_public_consultation_en.pdf) (accessed 2026-11-21)
- EDPB: user-engagement metrics "cannot be regarded as necessary for the provision of the service". Art. 6(1)(b) is not generally appropriate "for the purposes of improving a service or developing new functions"; providers may use "legitimate interest or consent" instead. — [EDPB Guidelines 2/2019, paras 48-49](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines-art_6-1-b-adopted_after_public_consultation_en.pdf) (accessed 2026-11-21)

**Children (Art. 8)**
- Art. 8(1) applies only "Where point (a) of Article 6(1) applies" (consent) to information society services offered directly to a child.
  - The default age is 16. Member states may lower it, but not below 13.
  - Art. 8(2) requires "reasonable efforts to verify" parental consent.
  - Art. 8(3) leaves national contract law on minors' contracts untouched. — [GDPR Art. 8, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- The UK GDPR sets the age at 13 ("at least 13 years old") and gives ministers power to change it within 13 to 16. — [UK GDPR Art. 8, legislation.gov.uk](https://www.legislation.gov.uk/eur/2016/679/article/8) (accessed 2026-11-21)
- Member-state ages (secondary table, last updated 15 Oct 2026):
  - **13:** Belgium, Denmark, Estonia, Finland, Latvia, Malta, Portugal, Sweden (UK also 13).
  - **14:** Austria, Bulgaria, Cyprus, Italy, Lithuania, Spain.
  - **15:** Czechia, France, Greece.
  - **16:** Croatia, Germany, Hungary, Ireland, Luxembourg, Netherlands, Poland, Romania, Slovakia, and Slovenia (the table says 16 still applies, with 15 proposed). — [gdprlocal, "Digital Age of Consent under the GDPR", updated 15 Oct 2026 (secondary)](https://gdprlocal.com/digital-age-of-consent-under-the-gdpr/) (accessed 2026-11-21)
  - The older official map is [FRA 2017 mapping (pre-dates most national laws)](https://fra.europa.eu/en/publication/2017/mapping-minimum-age-requirements-concerning-rights-child-eu/consent-use-data-children) (accessed 2026-11-21).

**Incidental special-category data in screenshots (Art. 9)**
- CJEU Grand Chamber, *Meta v Bundeskartellamt*, C-252/21, 4 July 2023:
  - Para 68: what matters is whether data "allow information falling within one of the categories ... to be revealed, irrespective of whether that information concerns a user ... or any other natural person".
  - Para 69: the prohibition applies regardless of "whether the controller is acting with the aim of obtaining" sensitive information.
  - Para 89: where data "collected en bloc without it being possible to separate the data items" include "at least one sensitive data item", processing is prohibited unless an Art. 9(2) derogation applies. — [CJEU C-252/21, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62021CJ0252) (accessed 2026-11-21)

**DPIA (Art. 35)**
- Art. 35(1): a DPIA is required where processing, "in particular using new technologies", is "likely to result in a high risk". Art. 35(7) lists its minimum contents: a systematic description, necessity and proportionality, risks, and measures. — [GDPR Art. 35, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- WP248 (endorsed by the EDPB) lists nine criteria:
  1. evaluation or scoring, including profiling and predicting "performance at work ... reliability or behavior";
  2. automated decisions with legal or similar effect;
  3. systematic monitoring;
  4. sensitive or highly personal data;
  5. large scale;
  6. matching or combining datasets;
  7. vulnerable data subjects, including children;
  8. innovative use of new technology;
  9. processing that prevents people from exercising rights.

  "In most cases ... a processing meeting two criteria would require a DPIA". — [WP29 WP248 rev.01, revised 4 Oct 2017](https://ec.europa.eu/newsroom/article29/redirection/document/47711) (accessed 2026-11-21)
- ICO's list of processing that requires a DPIA includes:
  - "Innovative technology" "(including AI)", when combined with another WP248 criterion;
  - "Tracking" of behaviour, including online;
  - "Targeting of children or other vulnerable individuals", including "intending to offer online services directly to children".

  The page says it is under review following the DUAA. — [ICO, Examples of processing likely to result in high risk](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/examples-of-processing-likely-to-result-in-high-risk/) (undated; accessed 2026-11-21)

**Processor terms (Art. 28) and vendor terms**
- Art. 28(3): processing by a processor "shall be governed by a contract" setting out the subject matter, duration, nature, purpose, data types and data subjects, plus the mandatory processor duties. — [GDPR Art. 28, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- Anthropic's DPA (effective 24 Feb 2025):
  - It is incorporated into "the Anthropic Commercial Terms of Service or other agreement" that references it.
  - EU SCCs Module 2/3 are "deemed to have been executed", with UK and Swiss addenda.
  - It does not mention the DPF. — [Anthropic Data Processing Addendum](https://www.anthropic.com/legal/data-processing-addendum) (accessed 2026-11-21)
- Supabase's DPA (Version 1, 1 Aug 2026) forms part of the ToS, and "acceptance of the Agreement shall have the same effect as signing the SCCs". It uses SCCs Modules 2/3 and the UK Addendum B.1.0, and does not mention the DPF. — [Supabase DPA](https://supabase.com/legal/dpa) (accessed 2026-11-21)
- Render publishes a DPA. Its text did not render for my fetch tool; search snippets say it uses EU and UK SCCs. — [Render DPA page](https://render.com/dpa) (accessed 2026-11-21)
- Google Gemini API terms (effective 23 Mar 2026):
  - Developers may use "only Paid Services when making API Clients available to users" in the EEA, Switzerland or the UK.
  - For Unpaid Services, "human reviewers may read, annotate, and process your API input and output".
  - "You must be 18 years of age or older to use the APIs". Use in any service "directed towards or is likely to be accessed by individuals under the age of 18" is not allowed.
  - Paid Services run under Google's processor DPA. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (accessed 2026-11-21)

**Records (Art. 30)**
- Art. 30(5): the duty to keep records "shall not apply to an enterprise ... employing fewer than 250 persons unless the processing ... is likely to result in a risk ..., the processing is not occasional, or the processing includes special categories". — [GDPR Art. 30, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)

**Breach notification (Arts. 33/34)**
- Art. 33(1): notify the supervisory authority "without undue delay and, where feasible, not later than 72 hours" after becoming aware, unless "unlikely to result in a risk".
- Art. 34(1): tell data subjects when a breach is "likely to result in a high risk". — [GDPR Arts. 33-34, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)
- EDPB: for non-EU controllers, "the mere presence of a representative in a Member State does not trigger the one-stop-shop system", so the breach must be notified "to every supervisory authority for which affected data subjects reside in their Member State". — [EDPB Guidelines 9/2022 on breach notification, v2.0 28 Mar 2023, para 73](https://www.edpb.europa.eu/system/files/2023-04/edpb_guidelines_202209_personal_data_breach_notification_v2.0_en.pdf) (accessed 2026-11-21)

**Private enforcement venue**
- Art. 79(2): users can sue "before the courts of the Member State where the data subject has his or her habitual residence". — [GDPR Art. 79, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) (accessed 2026-11-21)

### Inferences
- **Art. 27 exemption.** Screen and code processing is miyagi's regular, core activity, and it involves children plus possible special-category data. So the "occasional" exemption is very unlikely to apply. Both an EU representative and a UK representative would be needed once miyagi is in scope.
- **Legal bases, by processing activity:**
  - Core screenshot and code analysis for grading, and account data from Google sign-in via Supabase: Art. 6(1)(b), necessary to provide the requested lab. Contract capacity of 13 to 17-year-olds under national law remains a question (Art. 8(3)).
  - Opt-in crash and usage telemetry: consent, which is also needed under ePrivacy (Q5). Legitimate interest is a fallback for crash logs only.
  - Shared per-video lesson cache: legitimate interest if any personal data is in it. Better to design it so that no user data enters the cache.
  - Training or improving models on user content: neither 6(1)(b) nor implied consent fits. Avoid it, and make sure vendors do not train either (Gemini Unpaid tier does).
  - Bring-your-own API keys: 6(1)(b).
- **Art. 8 and teens.** If miyagi relies on contract rather than consent for teens, Art. 8's parental-consent rule is not triggered on its face. Regulators, the ICO in particular, still expect age-appropriate design, and the ICO's TikTok, MediaLab and Reddit cases all turned on under-13s without parental consent (Q8). A 13+ minimum, with a hard block below 13, matches the UK age and the lowest EU age. Users aged 13 to 15 in 16-age countries are the residual risk if any processing relies on consent, including telemetry.
- **Art. 9 exposure.** Full-screen screenshots can capture health portals, messages, religious or political content, or other people's data. Under C-252/21 paras 68, 69 and 89, a single sensitive item captured en bloc can make the whole batch Art. 9 processing, with no derogation available. The practical fix is technical:
  - capture only the editor and tutorial windows, not the full screen;
  - redact on the device before upload;
  - discard images after grading;
  - give users pause and exclude controls.
- **DPIA.** miyagi meets at least four WP248 criteria: evaluation or scoring of performance, systematic monitoring, vulnerable data subjects (teens) and innovative technology (AI). A DPIA is effectively mandatory under both the EU and ICO lists.
- **Records.** The Art. 30(5) exemption fails because processing is not occasional and is likely to result in risk. A short written record of processing is required.

### Gaps
- Whether a representative must be appointed in each member state where users are, or in one only: Art. 27(3) says "one of the Member States". The market cost of representative services was not researched.
- I did not verify whether Render's DPA is accepted automatically or must be signed; the page did not render.
- Anthropic's own rules on minors using API-built apps, and any age term in its Commercial Terms, were not checked. The vendor-terms notes may cover this.

## Q3. International transfers: DPF status (Latombe, appeal), UK data bridge, vendor certifications

### Takeaway
- **Which flows count as transfers.** When EU users send data straight to miyagi in the US, that is not a "transfer" under Chapter V. When miyagi passes the data on to its US processors (Anthropic, Google, Supabase, Render), that is a transfer.
- **DPF status.** The EU-US Data Privacy Framework stands after the General Court upheld it on 3 Sept 2025. The appeal (C-703/25 P) is pending with no hearing or Advocate General opinion as of mid-November 2026, and *Trump v Slaughter* (29 June 2026) adds political risk.
- **Vendor coverage.** Google LLC and Render are DPF-certified, Render including the UK Extension. Anthropic is not and relies on SCCs; Supabase relies on SCCs, and its DPF status is unverified. The UK Extension ("data bridge") rides on the DPF.

### Cited Findings
- EDPB:
  - A transfer requires three things: (1) an exporter subject to GDPR for the processing; (2) disclosure to an importer; (3) an importer "in a third country, irrespective of whether or not this importer is subject to the GDPR".
  - Example 1: a non-EU controller collecting directly from an EU data subject under Art. 3(2) "does not constitute a transfer".
  - Example 2: when that controller engages a non-EEA processor, the disclosure "would amount to a transfer", and it must apply "Article 28 and Chapter V". — [EDPB Guidelines 05/2021 on the interplay of Art. 3 and Chapter V, v2.0 adopted 14 Feb 2023](https://www.edpb.europa.eu/system/files/2023-02/edpb_guidelines_05-2021_interplay_between_the_application_of_art3-chapter_v_of_the_gdpr_v2_en_0.pdf) (accessed 2026-11-21)
- General Court, *Latombe v Commission*, T-553/23, 3 Sept 2025: it dismissed the challenge and upheld the 2023 DPF adequacy decision. It found the Data Protection Review Court sufficiently independent and US bulk-collection limits adequate. — [WilmerHale blog, 1 Dec 2025 (secondary)](https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20251201-european-court-of-justice-to-review-challenge-to-eu-us-data-privacy-framework) (accessed 2026-11-21)
- Appeal C-703/25 P:
  - Filed 31 Oct 2025 on four grounds: DPRC independence, whether the DPRC is "established by law", bulk-collection safeguards, and presidential power over bulk-collection purposes.
  - "As of mid-November 2026, no hearing date or Advocate General opinion had been made public."
  - The Commission's next periodic DPF review is due in 2027. — [Captain Compliance, 20 Nov 2026 (secondary)](https://captaincompliance.com/education/eu-us-data-privacy-framework-litigation-status-2026/) (accessed 2026-11-21)
- *Trump v Slaughter* (US Supreme Court, 29 June 2026) held that the President can remove FTC commissioners at will. On 31 July 2026 the EDPB Chair asked the Commission to assess the effect on the DPF. No amendment or suspension has been announced. — [Captain Compliance, 20 Nov 2026 (secondary)](https://captaincompliance.com/education/eu-us-data-privacy-framework-litigation-status-2026/); [Faegre Drinker, 17 Sep 2026 (secondary)](https://www.faegredrinker.com/en/insights/publications/2026/9/trump-v-slaughter-implications-of-the-us-supreme-court-ruling-for-eu-us-data-transfers-and-the-data-privacy-framework) (accessed 2026-11-21)
- UK data bridge: commentary says it "relies on the DPF". It is a separate UK instrument, and the Secretary of State can revoke the 2023 regulations at any time. I found no DSIT announcement of a review. — [Faegre Drinker, 17 Sep 2026 (secondary)](https://www.faegredrinker.com/en/insights/publications/2026/9/trump-v-slaughter-implications-of-the-us-supreme-court-ruling-for-eu-us-data-transfers-and-the-data-privacy-framework); [DSIT analysis of the UK Extension, 2023](https://assets.publishing.service.gov.uk/media/650801f6fc63f60014957399/analysis_of_the_uk_extension_to_the_eu-us_data_privacy_framework.pdf) (accessed 2026-11-21)
- Vendor DPF status, from a copy of the official DPF List current to 17 Nov 2026 (secondary):
  - Google LLC holds active EU-US, UK Extension and Swiss certifications.
  - Anthropic is not on the list at all, neither as an active nor as an inactive participant, and its DPA relies on 2021 SCCs. — [Sonomos, 18 Nov 2026 (secondary)](https://sonomos.ai/blog/anthropic-openai-google-dpf-sccs-2026/) (accessed 2026-11-21)
  - Anthropic's DPA itself confirms SCCs and no DPF mention. — [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum) (accessed 2026-11-21)
- Render: "As of January 6, 2025, Render is officially certified" under the EU-US DPF, the UK Extension and the Swiss-US DPF. — [Render changelog, 4 Feb 2025](https://render.com/changelog/render-achieves-certification-under-the-eu-us-data-privacy-framework) (accessed 2026-11-21)
- EU to UK: the Commission renewed the UK adequacy decisions on 19 Dec 2025, to 27 Dec 2031. This matters only if miyagi ever uses EU-based vendors sending data to the UK. — [Hunton (secondary)](https://hunton.com/privacy-and-information-security-law/european-commission-renews-uk-data-adequacy-decisions) (accessed 2026-11-21)

### Inferences
- **DPF-certified processors (Google LLC, Render).** miyagi can rely on the DPF, with the vendors' SCCs as fallback, since Google's terms keep SCCs as a fallback.
- **Anthropic and Supabase.** miyagi relies on their SCCs, which are incorporated automatically on acceptance of their terms. That requires a short transfer impact assessment, a one-page memo.
- **If the CJEU strikes down the DPF.** Only the Google and Render flows lose a mechanism. Their DPAs reference SCCs, so the practical impact on miyagi is low.
- **UK users.** The same analysis runs under UK GDPR: the UK Extension for certified vendors, and the IDTA or UK Addendum for the others.

### Gaps
- I could not query dataprivacyframework.gov directly; the participant list is a JavaScript app my fetch tool could not render. Status for Supabase, GitHub (Pages hosting) and Render's current active status should be checked by hand on the list.
- No official curia.europa.eu docket page was read for C-703/25 P; status comes from secondary sources dated 20 Nov 2026.
- There is a known legal wrinkle: the 2021 SCCs are drafted for importers not subject to GDPR, while a processor serving an Art. 3(2) controller may itself be in scope. I did not research the Commission's planned "Art. 3(2) importer" SCCs or whether they have been adopted.

## Q4. UK: Children's Code reach and standards, data protection fee, Data (Use and Access) Act 2025 changes

### Takeaway
The ICO's Children's Code covers any online service "likely to be accessed by" under-18s in the UK. The ICO says it "may also apply" to non-UK services that offer to or monitor UK users. A tutorial overlay used by self-taught teens is likely in scope if UK teens are a "substantive and identifiable user group".

The DUAA 2025 is now largely in force, with three changes that matter here:
- a statutory duty to weigh "children's higher protection matters" (from 5 Feb 2026);
- new PECR cookie exemptions (from 5 Feb 2026);
- a mandatory complaints process for controllers (from 19 June 2026).

Whether a non-UK controller must pay the ICO fee is unclear. The lowest tier is £52.

### Cited Findings
- ICO on who the code covers:
  - It applies to "information society services likely to be accessed by children" and "is not restricted to services specifically directed at children"; a child is "a person under 18".
  - For services without a UK establishment, the DPA 2018 "may also apply" where the service is offered to, or monitors the behaviour of, UK users.
  - "Likely to be accessed" means "more probable than not", judged on the nature and appeal of the service, access controls and evidence.
  - The definition applies if "children form a substantive and identifiable user group". — [ICO, Children's Code: services covered by this code](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/services-covered-by-this-code/) (undated; accessed 2026-11-21)
- The 15 standards, as summarised by the ICO:
  1. best interests of the child as "a primary consideration";
  2. DPIA;
  3. age-appropriate application: a risk-based approach to recognising age, "or apply the standards ... to all users";
  4. transparency: concise, prominent, age-appropriate, with short explanations when data use starts;
  5. no detrimental use of data;
  6. follow your own policies and community standards;
  7. default settings "high privacy" by default;
  8. data minimisation, with separate choices for each element;
  9. no data sharing without a compelling reason;
  10. geolocation off by default, with an obvious sign when on;
  11. parental controls, with an obvious sign when the child is monitored;
  12. profiling "off by default";
  13. no nudge techniques;
  14. connected toys and devices;
  15. online tools for exercising rights. — [ICO, Children's Code standards](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/code-standards/) (accessed 2026-11-21)
- The code is issued under s.123 DPA 2018. — [DPA 2018 s.123, legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2018/12/section/123) (accessed 2026-11-21)
- DUAA s.81 adds UK GDPR Art. 25(1A):
  - For information society services "likely to be accessed by children", the controller "must take into account the children's higher protection matters".
  - Those matters are how to best protect and support children using the service, and that children "merit specific protection", "may be less aware of the risks" and "have different needs at different ages".
  - In force 5 Feb 2026 (SI 2026/82, reg. 2(k)). — [Data (Use and Access) Act 2025 s.81](https://www.legislation.gov.uk/ukpga/2025/18/section/81) (accessed 2026-11-21)
- DUAA s.103 adds DPA 2018 s.164A on complaints to controllers:
  - controllers must facilitate complaints, e.g. "providing a complaint form which can be completed electronically";
  - acknowledge within 30 days;
  - take appropriate steps "without undue delay";
  - and report the outcome.
  - In force 19 June 2026 (SI 2026/82, reg. 3(a)). — [DUAA 2025 s.103](https://www.legislation.gov.uk/ukpga/2025/18/section/103) (accessed 2026-11-21)
- ICO fee:
  - The 2018 Regulations require "a data controller" to pay, unless all of its processing is exempt.
  - Address rules refer to a principal place of business "in the UK".
  - There is no provision specific to controllers established outside the UK. — [Data Protection (Charges and Information) Regulations 2018 reg. 2](https://www.legislation.gov.uk/uksi/2018/480/regulation/2) (accessed 2026-11-21)
  - The ICO's fee FAQ says only "If you are a controller and the exemptions don't apply to you, you will have to pay the fee." — [ICO data protection fee FAQs](https://ico.org.uk/for-organisations/data-protection-fee/data-protection-fee/data-protection-fee-faqs/) (accessed 2026-11-21)
- Fee amounts since 17 Feb 2025: Tier 1 £52, for turnover up to £632,000 or no more than 10 staff; Tier 2 £78; Tier 3 £3,763. — [Lewis Silkin, 6 Feb 2025 (secondary)](https://www.lewissilkin.com/insights/2025/02/06/fee-payable-to-the-ico-to-increase-in-february-102jzb9); [SI 2025/63](https://www.legislation.gov.uk/uksi/2025/63/made) (accessed 2026-11-21)
- UK age of digital consent is 13 (see Q2). — [UK GDPR Art. 8](https://www.legislation.gov.uk/eur/2016/679/article/8) (accessed 2026-11-21)

### Inferences
- If miyagi serves UK users, the Children's Code should be treated as applicable to the whole product, because teens are an expected user group. The cheapest route is standard 3's option to apply the standards to all users:
  - high-privacy defaults;
  - telemetry off (it is already opt-in);
  - no profiling for anything beyond the requested grading;
  - no geolocation;
  - child-readable notices;
  - no nudges toward sharing more data.
- The DUAA complaints duty means a UK-facing privacy notice should give an electronic complaint route, such as a form or an email address, and the team should acknowledge complaints within 30 days.

### Gaps
- I found no ICO statement on whether an overseas controller in scope only through UK GDPR Art. 3(2) must pay the fee. An older ICO disclosure reportedly said non-payment by overseas controllers would be considered "case by case" (search snippet only, not verified).
- I did not research whether the ICO has published an updated Children's Code or age-assurance guidance since the DUAA.

## Q5. Cookies and device access: ePrivacy Art. 5(3), UK PECR reg. 6, local storage, the static website, third-party CDNs and fonts

### Takeaway
- **Scope of Art. 5(3) and PECR reg. 6.** Both cover any storing of, or access to, information on the user's device, not just cookies. The EDPB says software on the device that sends locally held information to a server is "gaining access". So miyagi's screenshot and code upload, and its telemetry, are in scope.
- **Core lab.** It fits the "strictly necessary for a service explicitly requested" exemption.
- **Telemetry.** It needs consent in the EU. In the UK, the new statistics exemption applies if users get clear information and a free opt-out, and the data is used only to improve the service.
- **Website.** A static site with dynamic Google Fonts or jsDelivr scripts sends visitors' IP addresses to third parties. LG München I (2022) treated this as unlawful without consent for Google Fonts. Self-hosting removes the issue.

### Cited Findings
- ePrivacy Art. 5(3):
  - Storing information, or "the gaining of access to information already stored, in the terminal equipment of a subscriber or user", is allowed only with consent after clear and comprehensive information.
  - Exempt: storage or access "strictly necessary in order for the provider of an information society service explicitly requested by the subscriber or user to provide the service". — [Directive 2002/58/EC (consolidated 19 Dec 2009), EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02002L0058-20091219) (accessed 2026-11-21)
- EDPB Guidelines 2/2023 (v2.0 adopted 7 Oct 2024):
  - Art. 5(3) applies when an entity "distributes software on the terminal equipment of the user that is stored and will then proactively call an Application Programming Interface ('API') endpoint", and to JavaScript sending asynchronous requests (para 33).
  - Local applications using information "strictly inside the terminal" (local file access, cookies, local storage) do not trigger it "as long as the information does not leave the device, but when this information or any derivation of this information is accessed, Article 5(3) ePD would apply" (para 44).
  - Tracking pixels and tracking links are covered (paras 47-51).
  - IP-based tracking is covered where the IP originates from the user's equipment (paras 54-55).
  - The guidelines do not analyse exemptions, and applicability "does not systematically mean that consent needs to be collected" (para 56). — [EDPB Guidelines 2/2023 on the technical scope of Art. 5(3) ePD, v2.0](https://www.edpb.europa.eu/system/files/documents/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf) (accessed 2026-11-21)
- UK PECR reg. 6, substituted by DUAA s.112: storage or access is prohibited "Subject to Schedule A1". Access "includes ... collecting or monitoring information automatically emitted by the terminal equipment". In force 5 Feb 2026. — [DUAA 2025 s.112](https://www.legislation.gov.uk/ukpga/2025/18/section/112) (accessed 2026-11-21)
- New PECR Schedule A1 exceptions (DUAA Sch. 12, in force 5 Feb 2026):
  - **Strictly necessary**, "for the provision of an information society service requested by the subscriber or user". Includes security, preventing or detecting fraud, and "automatically authenticating the identity" of the user.
  - **Statistical purposes**, where the "sole purpose" is collecting statistics to improve the service or website. Conditions:
    - "clear and comprehensive information";
    - no sharing except to make the improvements;
    - "a simple means of objecting, free of charge".
  - **Appearance and functionality**, adapting a website to user preferences, with information and an objection right.
  - **Emergency assistance.** — [DUAA 2025 Schedule 12](https://www.legislation.gov.uk/ukpga/2025/18/schedule/12) (accessed 2026-11-21)
- The ICO finalised its storage and access technologies guidance on 29 April 2026. Commentary stresses that the exceptions apply only where technologies are used solely for the excepted purposes. — [ICO news, 29 Apr 2026](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2026/04/final-storage-and-access-technologies-guidance-published/); [Osborne Clarke (secondary)](https://marketinglaw.osborneclarke.com/advertising-regulation/new-exceptions-explained-in-ico-final-guidance-on-storage-and-access-technologies-could-online-advertising-be-next/) (accessed 2026-11-21)
- PECR maximum fines rose from £500,000 to UK GDPR levels: £17.5m or 4% of turnover. — [Bratby Law, DUAA commencement note (secondary)](https://bratby.law/data-use-and-access-act-2025-commencement/); [PolicyPros (secondary)](https://www.policypros.co.uk/cookie-consent-changes-duaa-guide/) (accessed 2026-11-21)
- LG München I, 20 Jan 2022, 3 O 17493/20:
  - Dynamically embedding Google Fonts passed the visitor's IP address to Google without consent.
  - The court granted an injunction and €100 damages under Art. 82 GDPR, noting the operator could have used the fonts without contacting Google's servers (self-hosting).
  - This is a first-instance ruling. It triggered a wave of mass demand letters seeking €100 each. — [Bavarian court database entry](https://www.gesetze-bayern.de/Content/Document/Y-300-Z-BECKRS-B-2022-N-612); [ra-plutte commentary (secondary)](https://www.ra-plutte.de/lg-muenchen-dynamische-einbindung-google-web-fonts-ist-dsgvo/) (accessed 2026-11-21)
- jsDelivr's privacy policy (effective 23 Nov 2023) says it collects usage data "that can include IP addresses", and that its CDN service providers "have access to your IP address". — [jsDelivr privacy policy](https://jsdelivr.com/privacy-policy-jsdelivr-net) (accessed 2026-11-21)

### Inferences
- **Desktop app:**
  - Uploading screen and code captures and lesson context to miyagi's proxy is "access" under Art. 5(3), per EDPB para 44. It falls within the strictly-necessary exemption because the user explicitly starts a lab. Even so, the first-run flow should name exactly what is captured.
  - Auth tokens and stored API keys in local storage or the OS keychain are strictly necessary.
  - Opt-in telemetry needs prior consent in the EU, which it already has as opt-in. In the UK it could run on the statistics exception with notice and a free opt-out, but keeping it opt-in is simpler and works for both.
  - Any third-party crash SDK that also uses the data for its own purposes breaks the UK "sole purpose" condition.
- **Website (GitHub Pages):**
  - Self-host fonts and scripts so visitors' browsers never contact Google Fonts or jsDelivr.
  - Avoid analytics, or use a cookieless, first-party, aggregate-only tool.
  - With no cookies or trackers, no banner is needed. GitHub itself still receives visitor IPs as host.
- **German demand-letter risk.** It is low but real for a site that visibly loads Google Fonts dynamically. Each claim is small (about €100), and the fix takes minutes.

### Gaps
- How far each EU member state's national ePrivacy law reaches a non-EU provider was not researched. ePrivacy is a directive, transposed nationally.
- GitHub Pages' own logging and DPF status, and whether jsDelivr's operator is EU-based, were not verified. A vendor site claims jsDelivr is EU-based; I did not confirm it.

## Q6. EU AI Act: Art. 50 transparency, Annex III education, provider vs deployer, AI literacy, Digital Omnibus status

### Takeaway
- **Role.** miyagi is a *provider*, specifically a "downstream provider", of an AI system built on Claude and Gemini. It is reached through Art. 2(1)(c) whenever its output is used in the EU, free or not.
- **Art. 50.** It has applied since 2 August 2026. miyagi must tell users they are interacting with AI unless that is obvious. It must also mark AI-generated text in a machine-readable way. Systems placed on the market before 2 Aug 2026 had until 2 Dec 2026 for the marking.
- **High-risk.** Self-study grading is very likely outside Annex III point 3(b). The Commission's May 2026 draft guidelines say voluntary informal-learning tools with no recognised credential "should not be classified as high-risk". In any case, the Digital Omnibus (Regulation (EU) 2026/1744, in force 27 July 2026) moved Annex III high-risk duties to 2 Dec 2027.
- **AI literacy.** Art. 4 is now softened to "take measures to support" staff AI literacy.

### Cited Findings
**Scope and roles**
- Art. 2(1)(c): the Act applies to "providers and deployers of AI systems that have their place of establishment or are located in a third country, where the output produced by the AI system is used in the Union". — [AI Act, Regulation (EU) 2024/1689, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- Definitions in Art. 3:
  - "Provider" means one that "develops an AI system ... or that has an AI system ... developed and places it on the market or puts the AI system into service under its own name or trademark, whether for payment or free of charge".
  - "Downstream provider" means a provider of an AI system "which integrates an AI model, regardless of whether the AI model is provided by themselves ... or provided by another entity based on contractual relations".
  - "Deployer" excludes use "in the course of a personal non-professional activity". — [AI Act Art. 3, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- Art. 2(12): the open-source exemption does not cover systems falling under Art. 5 or Art. 50. — [AI Act Art. 2, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)

**Art. 50 transparency**
- Art. 50(1): providers must design AI systems "intended to interact directly with natural persons" so people "are informed that they are interacting with an AI system, unless this is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect".
- Art. 50(2): providers of systems "generating synthetic audio, image, video or text content" must ensure outputs are "marked in a machine-readable format and detectable as artificially generated". This does not apply where the system performs "an assistive function for standard editing or do[es] not substantially alter the input data".
- Art. 50(4): deployer duties for deepfakes and for text published to inform the public on matters of public interest.
- Art. 50(5): information must be given "at the latest at the time of the first interaction or exposure" and "shall conform to the applicable accessibility requirements". — [AI Act Art. 50, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- Timing:
  - The Act "shall apply from 2 August 2026". Chapters I-II (including Art. 4) apply from 2 Feb 2025. — [AI Act Art. 113, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
  - Commission FAQ (10 June 2026): from 2 Aug 2026, providers and deployers in scope of Art. 50(2) and (4) must comply. Systems placed on the market before that date "benefit from a transitional period for compliance until 2 December 2026". — [Commission FAQ, Code of Practice on transparency of AI-generated content](https://digital-strategy.ec.europa.eu/en/faqs/code-practice-transparency-ai-generated-content) (accessed 2026-11-21)
- Code of Practice on marking and labelling AI-generated content: final version published 10 June 2026, assessed by the Commission as adequate for Art. 50(2), (4) and (5) on 8 July 2026. It is voluntary; Art. 50 itself is binding. — [Commission news](https://digital-strategy.ec.europa.eu/en/news/commission-publishes-code-practice-marking-and-labelling-ai-generated-content); [Commission opinion on adequacy](https://digital-strategy.ec.europa.eu/en/library/commission-opinion-assessment-code-practice-transparency-ai-generated-content) (accessed 2026-11-21)
- Final Commission guidelines on Art. 50 published 20 July 2026. They are non-binding and include worked examples for interactive AI. — [Commission library page](https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems); [Stephenson Harwood (secondary)](https://www.stephensonharwood.com/post/102nfqh/eu-ai-act-update-european-commission-adopts-guidelines-on-article-50-transparenc/) (accessed 2026-11-21)

**Annex III education and the high-risk filter**
- Annex III point 3(b) covers AI systems "intended to be used to evaluate learning outcomes, including when those outcomes are used to steer the learning process of natural persons in educational and vocational training institutions at all levels". — [AI Act Annex III, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- Art. 6(3) filter: an Annex III system is not high-risk where it "does not pose a significant risk of harm ... including by not materially influencing the outcome of decision making" and meets one of the listed conditions, such as a narrow procedural task. — [AI Act Art. 6, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- Draft Commission guidelines on high-risk classification (published for consultation 19 May 2026; still a draft):
  - "Institutions" covers formal and non-formal education, public and private, online or offline. Such institutions are "normally accredited or sanctioned" and may issue certificates (paras 210-212).
  - Only systems that make "an evaluation towards a final decision affecting educational and professional pathways based on a summative assessment" fall under 3(b) (para 223).
  - "intelligent tutoring systems that provide personalised feedback" "should not be classified as high-risk" (para 224).
  - AI systems "used by students on their own volition to support non-formal and informal learning", not required by their institution, "should not be classified as high-risk" unless they lead to "a credential, certification, or ... validation recognised by the relevant public authorities" (para 225).
  - Out-of-scope example: language-learning apps giving instant feedback with no credential.
  - Para 215 warns that systems inside point 3 "should always be classified as high-risk, even if" they meet the Art. 6(3) filter. — [Commission draft guidelines page](https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-classification-high-risk-ai-systems); [Annex III draft PDF, copy hosted by dirittobancario.it](https://www.dirittobancario.it/wp-content/uploads/2026/05/Draft-Guidelines-on-the-classification-of-high-risk-AI-Annex-III.pdf) (accessed 2026-11-21)
- Art. 5(1)(f) prohibits inferring emotions "in the area of education institutions" except for medical or safety reasons. — [Draft guidelines para 216, summarising Art. 5(1)(f)](https://www.dirittobancario.it/wp-content/uploads/2026/05/Draft-Guidelines-on-the-classification-of-high-risk-AI-Annex-III.pdf) (accessed 2026-11-21)

**AI literacy (Art. 4)**
- Original Art. 4: providers and deployers "shall take measures to ensure, to their best extent, a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf". — [AI Act Art. 4, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)
- As amended by the Omnibus: "Providers and deployers of AI systems shall take measures to support the development of AI literacy of their staff". This "does not require providers or deployers to guarantee any specific level of AI literacy of any individual". — [Regulation (EU) 2026/1744, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2026/1744/oj?locale=en) (accessed 2026-11-21)

**Digital Omnibus on AI: status as of 2026-11-21**
- Regulation (EU) 2026/1744 of 8 July 2026, published in the OJ on 24 July 2026. Recital 46 says it enters into force "on the third day following" publication, so 27 July 2026.
  - Recital 40: Annex III high-risk obligations move to "2 December 2027" and Annex I-embedded ones to "2 August 2028".
  - Recital 38: providers of generative systems already on the market before 2 Aug 2026 get "a four-month transitional period" for marking. — [Regulation (EU) 2026/1744, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2026/1744/oj?locale=en) (accessed 2026-11-21)
- Legislative history:
  - provisional agreement 7 May 2026;
  - Parliament vote 16 June 2026;
  - Council approval 29 June 2026;
  - the removal of Art. 6(3) registration was dropped, so registration still applies, through a simplified procedure;
  - a new ban on AI generating CSAM or non-consensual intimate content applies from 2 Dec 2026. — [Sidley Data Matters, 22 June 2026 (secondary)](https://datamatters.sidley.com/2026/06/22/eu-lawmakers-reach-provisional-agreement-to-delay-key-eu-ai-act-obligations/); [Cuatrecasas (secondary)](https://www.cuatrecasas.com/en/portugal/intellectual-property/art/digital-omnibus-ai-has-been-published) (accessed 2026-11-21)

**Penalties**
- Art. 99(4)(g): breaches of Art. 50 carry fines "up to EUR 15 000 000 or ... up to 3 % of its total worldwide annual turnover", whichever is higher. For SMEs and start-ups, "whichever thereof is lower" (Art. 99(6)). — [AI Act Art. 99, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)

### Inferences
- **Roles.** miyagi is the provider because it puts its own AI system on the market under its own name, free of charge. Anthropic and Google are GPAI model providers. End users studying for themselves are not deployers, because personal non-professional use is excluded. Schools or bootcamps that adopt miyagi would become deployers.
- **Art. 50(1).** A tutor-style overlay that chats and gives feedback is "intended to interact directly". The AI nature may be "obvious", but a one-line first-run disclosure ("Feedback and lessons are generated by AI (Claude, Gemini)") plus a persistent label removes the argument.
- **Art. 50(2).** miyagi generates synthetic text: lessons, hints and feedback. Unless the "assistive function for standard editing" exception applies, outputs need machine-readable marking. The practical route is to follow the Code of Practice measures for text, such as metadata or provenance tags in exported or shared lesson content, and to check whether the Art. 50 guidelines accept reliance on upstream model watermarking. That last point is not verified.
- **Annex III.** Self-directed, no certificate, formative feedback: on the draft guidelines, miyagi is outside 3(b). The risk returns in three cases:
  - miyagi issues certificates or badges recognised by public authorities;
  - schools require students to use it and use its grades in final marks;
  - it adds emotion or attention inference from webcam or behaviour (the Art. 5(1)(f) prohibition in education settings).

  None of these dates bites before 2 Dec 2027.
- **Art. 4.** Two founders keeping a short written note of the AI-literacy measures they take (vendor limits, hallucination risks, review process) is proportionate.

### Gaps
- I did not read the final Art. 50 guidelines' text on downstream providers relying on upstream watermarking, or on text-marking exceptions for code. The Commission FAQ is silent on both.
- The final (non-draft) high-risk classification guidelines had not been located as of 2026-11-21. Paras 223-225 may change.
- Which authority enforces Art. 50 against a non-EU provider with no EU representative (national market surveillance authorities) was not researched in depth. Art. 22 authorised representatives are tied to high-risk providers (the Art. 22 heading is "Authorised representatives of providers of high-risk AI systems").

## Q7. European Accessibility Act (Directive 2019/882): does it cover miyagi?

### Takeaway
Probably not. The EAA lists specific services: e-communications, audiovisual-media access, transport elements, consumer banking, e-books with dedicated reading software, and e-commerce. A free coding-tutorial overlay is none of these, and general-purpose software is not listed. Even if a future paid checkout made miyagi an "e-commerce service", microenterprises providing services are exempt.

### Cited Findings
- Services covered by Art. 2(2):
  - (a) electronic communications services;
  - (b) services providing access to audiovisual media services;
  - (c) elements of air, bus, rail and waterborne passenger transport services;
  - (d) consumer banking services;
  - (e) "e-books and dedicated software";
  - (f) "e-commerce services". — [Directive (EU) 2019/882, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0882) (accessed 2026-11-21)
- Definitions in Art. 3:
  - "E-commerce services": "services provided at a distance, through websites and mobile device-based services by electronic means and at the individual request of a consumer with a view to concluding a consumer contract".
  - "E-book and dedicated software": digital files conveying "an electronic version of a book" and the software dedicated to reading them.
  - "Microenterprise": "fewer than 10 persons and ... annual turnover not exceeding EUR 2 million or an annual balance sheet total not exceeding EUR 2 million". — [Directive (EU) 2019/882 Art. 3, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0882) (accessed 2026-11-21)
- Art. 4(5): "Microenterprises providing services shall be exempt from complying with the accessibility requirements ... and any obligations relating to the compliance with those requirements." — [Directive (EU) 2019/882 Art. 4, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0882) (accessed 2026-11-21)
- Member states must apply the measures "from 28 June 2025". — [Directive (EU) 2019/882 Art. 31, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0882) (accessed 2026-11-21)
- Separately, AI Act Art. 50(5) requires AI-interaction disclosures to "conform to the applicable accessibility requirements". — [AI Act Art. 50(5), EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689) (accessed 2026-11-21)

### Inferences
- miyagi is outside the EAA's service list today. A future paid subscription sold through miyagi.study would arguably be an "e-commerce service". A two-person company with no revenue is a microenterprise, so the service-side duties would not apply until it reaches 10 staff or €2m.
- Basic accessibility is still worth doing for the AI-disclosure text and the site: keyboard access, contrast and screen-reader labels.

### Gaps
- National transposition details, and whether any member state widened the scope, were not researched. Commission or AccessibleEU interpretive guidance on "e-commerce services" for free apps was not found.

## Q8. Enforcement realism: regulators acting against non-EU small apps and edtech

### Takeaway
EU and UK regulators do act against non-EU companies with no local establishment, most often over children, AI chatbots and missing representatives. Typical triggers are complaints, media attention or sector sweeps. I found one fine against a small non-EU site (Locatefamily, €525k for having no EU representative) but no case against a two-person, pre-revenue startup. The realistic risks for miyagi are:
- a complaint-driven inquiry, usually after a child-safety story or a data incident;
- app-store or vendor (Google) terms enforcement;
- small German-style damages claims.

A proactive fine is far less likely.

### Cited Findings
- **Dutch AP v Locatefamily.com.** €525,000 fine for not designating an EU representative under Art. 27, with an order to appoint one plus €20,000 per two weeks up to €120,000. The AP rejected the "occasional" exemption. Announced May 2021. — [Hunton, 19 May 2021 (secondary)](https://www.hunton.com/privacy-and-cybersecurity-law-blog/dutch-dpa-fines-company-525000-eur-for-failure-to-designate-eu-representative); [EDPB national news](https://www.edpb.europa.eu/node/2676_en) (accessed 2026-11-21)
- **Italian Garante v Luka Inc. (Replika, US).** €5m fine, decision 10 April 2025.
  - Breaches included Arts. 5(1)(a), 6, 12, 13, 5(1)(c), 24 and 25(1).
  - The company "had not implemented any age verification mechanisms" despite declaring minors excluded.
  - The Garante ordered compliance changes. — [EDPB news on Garante decision, 2025](https://www.edpb.europa.eu/news/national-news/2025/ai-italian-supervisory-authority-fines-company-behind-chatbot-replika_sv) (accessed 2026-11-21)
- **Italian Garante v OpenAI.** €15m fine (decision n. 755 of 2 Nov 2024), annulled in full by the Tribunal of Rome on 18 March 2026. The reported grounds are procedural, centred on the Irish DPC's lead-authority status. Sources differ on the judgment number. — [WSGR (secondary)](https://www.wsgr.com/en/insights/openai-prevails-in-landmark-italian-ai-and-gdpr-enforcement-case.html); [Advant NCTM (secondary)](https://www.advant-nctm.com/en/news/why-did-the-court-of-rome-annul-the-data-protection-authoritys-order-on-openai) (accessed 2026-11-21)
- **ICO v TikTok.** £12.7m (4 April 2023) for processing data of up to 1.4m UK under-13s without parental consent (May 2018 to July 2020). — [ICO news, 4 Apr 2023](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/04/ico-fines-tiktok-127-million-for-misusing-children-s-data/) (via search; accessed 2026-11-21). One secondary search summary gave £14.5m, which conflicts with the ICO figure of £12.7m.
- **ICO v MediaLab (Imgur's owner, "MediaLab.AI, Inc.").** £247,590, announced 5 Feb 2026.
  - No age assurance, no parental consent for under-13s, and no DPIA on children's risks.
  - The case was tied to the Children's Code strategy. Imgur withdrew from the UK.
  - The Commissioner said companies that ignore child users "can expect to face similar enforcement action". — [ICO news, Feb 2026](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2026/02/imgur-owner-medialab-fined-over-children-s-privacy-failures) (accessed 2026-11-21)
- **ICO v Reddit.** £14.47m (24 Feb 2026), with an estimated ~226,000 under-13 users processed without a valid lawful basis. — [ICO news, Feb 2026](https://cy.ico.org.uk/about-the-ico/media-centre/news-and-blogs/2026/02/reddit-issued-with-1447m-fine-for-children-s-privacy-failures/) (via search; accessed 2026-11-21)
- **ICO v Clearview AI (US).** The Upper Tribunal confirmed ICO jurisdiction over a US company in Oct 2025 and remitted the £7.5m penalty appeal to the First-tier Tribunal. A further appeal stage appeared in Oct 2026 listings (unverified). — [ICO news, Oct 2025](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2025/10/uk-upper-tribunal-hands-down-judgment-on-clearview-ai-inc) (accessed 2026-11-21)
- **Private claims.** The LG München I Google Fonts ruling (€100) prompted mass €100 demand letters in Germany (see Q5). — [ra-plutte (secondary)](https://www.ra-plutte.de/lg-muenchen-dynamische-einbindung-google-web-fonts-ist-dsgvo/) (accessed 2026-11-21)

### Inferences
- **Enforcement focus.** Children's data is the clearest priority, especially at the ICO, which has fined three platforms since 2023 and named age assurance as a focus. Missing age checks, missing DPIAs and missing parental consent for under-13s recur in every children's case. miyagi's expected teen users put it in the ICO's line of sight, but only at scale or after a complaint.
- **No one-stop shop.** A non-EU controller cannot use the one-stop-shop (EDPB 9/2022 para 73). Any of 27 EU authorities, plus the ICO, can act separately.
- **Collectability.** Fining a US entity with no EU or UK assets is practically hard to collect. That is my inference; I found no source quantifying collection. But an order can be served on the EU/UK representative, and app stores, Google sign-in or the Gemini API can be cut off if terms are breached. Vendor enforcement, such as Google's under-18 term, is the more immediate risk than regulator fines.
- **Likelihood ranking for a micro startup.** From least to most likely:
  - proactive regulator fine: very low;
  - regulator inquiry after a complaint: low;
  - vendor or app-store action: low to medium;
  - small private claims (website fonts): low.

### Gaps
- I found no case of an EU or UK regulator fining a two-person, pre-revenue, non-EU edtech app.
- No statistics on cross-border collection of GDPR fines from US companies.
- The size and ownership of Locatefamily, and whether the fine was ever paid, are not known.

## Q9. Implications for miyagi

### Takeaway
Plan as if GDPR, UK GDPR and the UK Children's Code apply to EU and UK users, and AI Act Art. 50 to all EU use. Most duties are paperwork and small product changes. Three items need real decisions:
1. how to handle teen users, given Google's 18+ Gemini term and Art. 8 and Children's Code duties;
2. how to limit screen capture so it stops scooping up sensitive and third-party data;
3. whether to appoint EU and UK representatives, or geo-gate EU and UK users until miyagi is ready.

### Inferences
Each item below lists the risk, who could act, likelihood, severity, the mitigation and whether a lawyer is needed. Likelihood and severity are my judgements based on the findings above.

| # | Risk | Who could act | Likelihood | Severity | Concrete mitigation | Lawyer? |
|---|---|---|---|---|---|---|
| 1 | **Teen users vs Gemini API terms.** Google bars use in services "likely to be accessed by individuals under the age of 18", and EEA/UK/CH users must be served on Paid Services only (Q2). | Google (API suspension); indirectly the ICO and EU authorities | Medium (contractual; Google can act without a complaint) | High: loss of a core model provider | App: route all under-18 traffic to Claude only, or raise the minimum age to 18. Use the paid Gemini tier for any EU/UK traffic and never the free tier. Doc: record the age policy and model routing. | Yes. Interpreting Google's term and Anthropic's minors rules, and getting written confirmation, is contract work. |
| 2 | **Children's data: Art. 8 ages 13-16, UK Children's Code, DUAA higher-protection duty** (Q2, Q4, Q8) | ICO (most active); EU authorities (Garante); complainants | Low now, medium at scale or after a press story | High (ICO fined MediaLab £247,590 and Reddit £14.47m) | App: age gate at sign-up with a hard block under 13; telemetry and any profiling off by default; no geolocation; high-privacy defaults for everyone (standard 3, "apply to all users"); a child-readable "what miyagi sees" screen. Doc: Children's Code checklist and DPIA. Process: delete accounts found to be under 13. | Recommended once and early, to settle the teen strategy (contract vs consent basis, minimum age per country). |
| 3 | **Screenshots capture special-category and third-party data** (C-252/21 paras 68, 69, 89) | Any EU authority or the ICO; private claims under Art. 82 / Art. 79(2) | Low | High if it happens: a breach of captured screens would be serious | App: capture only the editor and tutorial windows; on-device redaction or blur of other apps; a visible capture indicator and pause hotkey; no screenshot retention after grading; send the minimum, e.g. code text and cropped regions; never put user captures in the shared lesson cache. Vendors: use zero or short retention API settings; never the Gemini Unpaid tier, where human reviewers may read inputs. | No, it is an engineering fix. Note it in the DPIA. |
| 4 | **No EU/UK representative** (Art. 27; Locatefamily €525k) | Dutch AP or any EU authority; the ICO | Low | Medium | Process: appoint a commercial EU representative and UK representative before actively growing EU/UK use, and name them in the privacy notice. Alternative: geo-block EU/UK sign-ups, exclude EU/UK markets in the Microsoft Store, and state "US only" in the terms. | Light-touch. A representative contract is standard, but counsel should check who can sign for the company, since founders' contract capacity is a US-law question outside this note. |
| 5 | **Privacy notice missing Art. 13 items** | Any EU authority, the ICO, complainants | Medium (this is what complaints cite first; Replika was found in breach of Art. 13) | Medium | Doc: one notice for app and site listing every Art. 13(1)-(2) item (Q2), including legal basis for each purpose; vendors (Anthropic, Google, Supabase, Render); transfers and SCCs/DPF; retention; rights; complaint to an authority; the representatives; and a UK complaint form with 30-day acknowledgement (DUAA s.164A). | Optional review. A template is fine for a first version. |
| 6 | **ePrivacy / PECR for the app** (screen/code upload, telemetry, local storage) | EU authorities; the ICO (PECR fines now up to £17.5m/4%) | Low | Low to medium | App: keep telemetry opt-in with a clear prompt; avoid third-party analytics SDKs that reuse data; describe on first run what is captured and sent (the strictly-necessary exemption covers the lab itself). | No. |
| 7 | **Website: Google Fonts / jsDelivr send visitor IPs** (LG München I) | German claimants, consumer associations | Low | Low (about €100 per claim, plus nuisance) | Site: self-host fonts and JS, no third-party requests on load, no analytics (or cookieless first-party only); no banner needed. Add a short site privacy notice. | No. |
| 8 | **Transfers to US processors** (Anthropic SCCs; Supabase SCCs; Render and Google DPF) | EU authorities, the ICO | Low | Low to medium; rises if the CJEU annuls the DPF in C-703/25 P | Doc: accept or execute every vendor DPA (Anthropic DPA via Commercial Terms, Supabase DPA, Render DPA, Google paid-services DPA); a one-page transfer assessment; list mechanisms in the notice. Process: watch C-703/25 P and the Commission's 2027 DPF review. | No, unless a vendor asks for negotiated terms. |
| 9 | **No DPIA or records of processing** (Art. 35, WP248, ICO list; Art. 30(5) exemption fails) | Any authority, as an aggravating factor (MediaLab lacked a DPIA) | Low as a standalone issue; high as an add-on in any investigation | Medium | Doc: a DPIA using the ICO template, covering screen capture, teens, AI vendors, the shared cache and BYO keys; a one-page record of processing. Update both when features change. | Optional review of the DPIA. |
| 10 | **Breach handling** (72 hours; notify every EU authority where affected users live, plus the ICO) | All authorities | Low | High (screens and code may hold secrets) | Process: incident runbook listing authorities and contact routes; Render/Supabase logging; secret-scanning before upload, so tokens and keys in user code are masked. | No for the runbook; yes if a real breach happens. |
| 11 | **AI Act Art. 50 transparency and marking** (applies since 2 Aug 2026; marking transitional to 2 Dec 2026) | National market surveillance authorities | Very low | Low to medium (fines up to €15m/3%, the lower figure for SMEs) | App: a first-run "AI-generated" disclosure and a persistent label on AI feedback, accessible text (Art. 50(5)); machine-readable provenance on exported or shared AI text, following the Code of Practice for text. Doc: a short Art. 4 AI-literacy note. | No, unless miyagi signs the Code of Practice formally. |
| 12 | **Drifting into high-risk (Annex III 3(b)) or the Art. 5(1)(f) prohibition** | Market surveillance authorities (from 2 Dec 2027 for Annex III) | Very low today | High if triggered: conformity duties | Product rule: no officially recognised certificates, no selling to schools as a grading tool for final marks, no emotion or attention inference, without re-assessment. Track the final high-risk guidelines (draft paras 223-225). | Yes, before any school or credential deal. |
| 13 | **Shared per-video lesson cache leaking user data across users** | Authorities (Art. 5(1)(f), Art. 32); affected users | Low | Medium | App: build the cache only from public video context and model output, never user code or screens; review cached items for personal data. | No. |
| 14 | **ICO data protection fee** (unclear for non-UK controllers; Tier 1 £52) | ICO (fixed penalties for non-payment) | Very low | Very low | Process: if UK users become material, pay Tier 1 voluntarily, or keep a note on why it was not paid. | A quick question to counsel or the ICO helpline (not contacted here). |
| 15 | **EAA** | National market surveillance authorities | Very low (not a listed service; microenterprise exemption) | Low | None required now. Keep basic accessibility; re-check if staff reaches 10 or turnover reaches €2m, or if a paid checkout launches. | No. |

### Gaps
- Anthropic's minors policy for API-built consumer apps, and its zero-retention options, were not checked here. They matter for items 1 and 3; see the vendor-terms notes.
- Representative-service pricing, and whether one provider can cover both EU and UK, was not researched.
- Whether miyagi.study's planned Microsoft Store listing defaults to all markets, including the EU and UK, which bears on "targeting", was not checked.
- Non-EU, non-UK regimes (Switzerland nFADP, Brazil LGPD and others) are out of scope.
