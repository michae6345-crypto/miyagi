# DRAFT: miyagi Terms of Service and app license

> **DRAFT. Not legal advice. Not published, not shown in the app.**
> Area B of the launch-risk study (`research/launch/privacy-legal.md`). A lawyer should review this before anyone is
> asked to accept it; the clauses that most need one are listed in "Notes for the team" at the end, with sources.
> **[TBD]** needs a fact we don't have yet. **[DECIDE]** is a founder decision from the register.

Effective date: [TBD]. Last updated: [TBD].

These terms are an agreement between you and [TBD: the company that runs miyagi, once formed] ("miyagi", "we",
"us"). They cover the miyagi app for Mac and Windows, the miyagi-cloud service the app uses, and the website at
miyagi.study (together, "miyagi").

**When you click "I agree" in the app, you agree to these terms and to our
[Privacy Policy](https://miyagi.study/privacy).** If you don't agree, don't use miyagi.

## 1. Who can use miyagi

- You must be **13 or older**. If you are under 13, don't use miyagi.
- If you are **under 18**, a parent or legal guardian must also agree to these terms, for themselves and for you.
  They are responsible for your use of miyagi. If you or your parent later cancel this agreement because you are a
  minor, your access ends. Parents: see section 15.
- You can't use miyagi from a country or region where our AI providers don't offer service, or where US law bars it,
  including places under comprehensive US embargo (section 13).

## 2. What miyagi does

miyagi turns a coding tutorial into a hands-on lesson. During a lesson it looks at your screen and your code, checks
whether you've done each step, and coaches you. To do that it sends some of what it sees to AI services (today
Anthropic, and Google for building lessons from videos), through miyagi-cloud or straight to the provider if you add
your own API key. The [Privacy Policy](https://miyagi.study/privacy) says exactly what is sent, where, and for how long.

**miyagi's coach is an AI.** It can be wrong (section 7).

miyagi is new and changes often. Features marked beta are provided as they are and may change or go away.

## 3. Your account

Signing in with Google is optional. If you sign in, keep your Google account secure; you're responsible for what
happens under your sign-in. Tell us if you think someone else is using it.

## 4. The app license

We give you a personal, non-exclusive, non-transferable, revocable license to install and use the miyagi app on
computers you own or control, for your own learning, as long as you follow these terms.

Except where the law lets you do it anyway, you may not:

- copy, sell, rent, sublicense or redistribute the app (sharing the official download link is fine);
- reverse engineer, decompile or disassemble the app;
- take out, use or share any credential built into the app or issued to it by miyagi-cloud;
- remove or change our notices or the notices of open-source components.

The app includes open-source software, licensed under its own terms and listed in the app's third-party notices
[TBD: ship the notices file]. Nothing here limits your rights under those licenses.

The app checks for updates and may download and install them for you. Some updates are needed to keep using
miyagi-cloud. We won't hold back security fixes to make you accept other changes.

If you got the app from the Microsoft Store, these terms are its license terms; where Microsoft's own Store terms
require something different for the app, they apply. [TBD: enter this page's address in Partner Center as the app's
additional license terms.]

## 5. Using miyagi fairly

miyagi-cloud pays for AI calls so you don't have to. To keep it working, you may not:

- get around usage limits, for example by making many accounts or installs, or by sharing install tokens;
- use miyagi-cloud from anything other than the miyagi app, scrape it, overload it, or use it as a general AI service;
- try to make the AI ignore its instructions or safety rules (jailbreaks, prompt injection), or poison saved lessons;
- use miyagi's output to train a competing AI model;
- use miyagi to break the law, to harass anyone, to make sexual content, or to make malware or anything meant to harm;
- point miyagi at other people's private information (messages, documents, accounts) without their permission;
- **use miyagi to cheat**, for example to complete graded schoolwork, tests or interviews where AI help isn't allowed,
  or to hand in AI-assisted work without saying so where that's required;
- break the AI providers' rules, which apply to everything sent to them:
  [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) and
  [Google Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy).

We set free usage limits and may change them. We may pause or block access if we see abuse.

## 6. Your screen, your code, and what's on them

You keep all rights to your code, your files and anything else that's yours. You let us read, copy, process and send
your screen content, code and questions, as described in the Privacy Policy, only to run miyagi for you (including
through our AI providers), to keep miyagi secure, and to fix problems you report. We don't use them to train AI models
and we don't sell them.

**You control what's on your screen.** During a lesson miyagi takes screenshots. Before a lesson, close or hide what
you don't want sent: passwords, API keys, banking, private messages, and anyone else's information. miyagi leaves
out some apps (such as password managers and Messages), but it can't catch everything. You can pause or end a lesson
at any time. [TBD: the app needs a visible pause.] Only show miyagi things you have the right to show.

## 7. Lessons, AI output and grades

- **AI makes mistakes.** Lessons, hints, explanations, code and grades are made by AI and can be wrong, incomplete or
  out of date. Check them before you rely on them.
- **Grades are practice feedback.** When miyagi says a step passed, its checks passed on your computer at that moment.
  That isn't a certificate, a school grade, or proof that your code is correct or safe.
- **These terms beat the chat.** If the AI says something about miyagi's prices, features or rules that differs from
  these terms or our website, these terms and the website are what count.
- **Be careful with commands and code.** Lessons may ask you to install packages or run commands, and miyagi can run a
  step for you. Read what it will run first, run it only on a computer you're allowed to change, and keep backups.
- **No professional advice.** Nothing in miyagi is legal, financial, medical, academic or career advice.
- **What you make is yours.** As between you and us, you own the code you write. To the extent we have rights in the
  output miyagi generates for you, we give them to you, subject to the AI providers' terms. Others may get similar
  output.

## 8. Tutorials and other people's content

The videos miyagi builds lessons from belong to their creators and play through YouTube. miyagi is not affiliated
with, endorsed by or sponsored by YouTube, Google, the tutorial creators, or the makers of any film. When you watch
a video in miyagi, you agree to the [YouTube Terms of Service](https://www.youtube.com/t/terms), and Google's
[Privacy Policy](https://policies.google.com/privacy) applies to YouTube's player.

A lesson is a study guide that follows the video, credits its creator and links back to it. [DECIDE, register B12:
Lessons built for a video may be saved and shown to other learners who pick the same video. They are miyagi's service
content: we license them to you to use in miyagi, and you don't own them. They are built from the video, never from
your screen or code. We remove a video's lessons when its creator asks.]

## 9. Your own API keys

You may add your own API key for a supported AI provider if you are **18 or older**. If you do:

- the key stays on your computer, locked by your system's secure storage, and calls with it go straight from your
  computer to that provider, never through miyagi-cloud;
- those calls are between you and the provider, under your agreement with them: you pay their charges, and their terms
  decide how they use what you send (on some free tiers, the provider may use it to improve its products);
- keep your key secret, and remove it in Settings when you stop using it. We aren't responsible for charges or misuse
  of a key you added, unless we caused it by breaking these terms.

## 10. Third-party services

miyagi relies on services we don't control, including YouTube, Google sign-in, Supabase, Render, GitHub, VS Code,
Anthropic and Google Gemini. They may change or stop, and that may change or stop parts of miyagi. Their own terms and
privacy policies govern what they do with what they receive.

## 11. Feedback

If you send us ideas or suggestions, we may use them without owing you anything.

## 12. Copyright complaints

If you think something in miyagi infringes your copyright, send our designated agent a notice with the details listed
in 17 U.S.C. § 512(c)(3): your contact details; the work; where it appears in miyagi (the lesson or video link); a
statement that you believe in good faith the use isn't authorized; a statement, under penalty of perjury, that your
notice is accurate and that you own the right or may act for its owner; and your signature.

Designated agent: [TBD: name, address and email, as registered with the US Copyright Office].

If your material was removed and you think that was a mistake, you can send a counter-notice with the details in
17 U.S.C. § 512(g)(3). We end the access of people who repeatedly infringe, where appropriate.

## 13. Export and sanctions

You may not use, download or export miyagi in breach of US export control or sanctions laws, including from a country
or region under comprehensive US embargo, or if you are on a US government restricted-party list. Our AI providers
serve only certain countries and regions ([Anthropic's list](https://www.anthropic.com/supported-countries)), so
miyagi may not work everywhere.

## 14. Ending things

You can stop using miyagi at any time. To delete your data, use Settings, Privacy, Delete my data, and email us to
delete your account (see the Privacy Policy).

We may suspend or end your access if you break these terms, if the law requires it, or if we stop offering miyagi. If
we stop offering miyagi-cloud, we'll try to tell you in the app first. Sections 6 (the last sentence), 7, 11, 16, 17,
18 and 19 still apply after this agreement ends.

## 15. For parents and guardians

If your teen uses miyagi, you agree to these terms for yourself and for them, and you're responsible for their use.
You can ask us to see or delete your teen's account and data at any time (see the Privacy Policy). If you learn that a
child under 13 is using miyagi, tell us and we'll delete their data.

## 16. No warranties

**miyagi is provided "as is" and "as available".** To the fullest extent the law allows, we disclaim all warranties,
express or implied, including merchantability, fitness for a particular purpose and non-infringement, and we don't
promise that miyagi will be accurate, uninterrupted, secure or error-free.

## 17. Limits on liability

To the fullest extent the law allows:

- we are not liable for indirect, incidental, special, consequential or punitive damages, or for lost data, profits
  or work, arising from miyagi;
- our total liability for all claims about miyagi is limited to the greater of US$100 or what you paid us for miyagi
  in the 12 months before the claim.

These limits don't apply to liability for fraud, willful misconduct or violations of law, or to anything else the law
doesn't let us limit. **If you live in the EU or the UK,** they also don't limit our liability for death or personal
injury caused by negligence, for gross negligence, or your rights as a consumer that can't be waived.
[TBD, lawyer: New Jersey wording.]

## 18. Disputes

Let's try to fix problems first: email us at [TBD: contact] and give us 30 days to resolve it.

These terms are governed by California law, without regard to conflict-of-laws rules. Any dispute will be decided in
the state or federal courts in [TBD: county], California, and you and we agree to those courts' jurisdiction, except
that either of us may bring a claim in small claims court where it qualifies. If you live in the EU, the UK or another
place whose consumer law lets you bring a claim at home under that law, these terms don't take that away.

## 19. General

- **Changes.** We may update these terms. For important changes we'll tell you in the app at least 30 days before they
  apply and ask you to agree again. Changes don't apply to disputes that started before them. If a change would let
  us use your data in a new way, we'll ask you first.
- **Whole agreement.** These terms and the Privacy Policy are the whole agreement between you and us about miyagi.
- **If part doesn't work.** If a court finds part of these terms unenforceable, the rest still applies.
- **No waiver.** If we don't enforce something right away, we can still enforce it later.
- **Transfer.** You can't transfer these terms. We can transfer them to a company that takes over miyagi, including
  the company we form to run it, and we'll tell you if we do.

## 20. Contact

[TBD: contact email and postal address.]

---

## Notes for the team (not for publication)

Why each clause is written this way, and where a lawyer is needed. Sources are in
`research/launch/privacy-legal/sources/terms_eula_enforceability.md` (clickwrap, minors, liability, AI terms compared,
BYOK) and `vendor_terms_data_handling.md`; all accessed 2026-11-21.

| Clause | Why | Lawyer? |
| --- | --- | --- |
| Parties (top) | Without an entity the founders are the counterparty and personally exposed, and as minors can void their own vendor contracts. Form the entity before these terms go live (register B07). | **Yes**: entity and who signs |
| Acceptance (top) | Ninth Circuit test: a reasonably conspicuous notice plus an unambiguous act of assent (Berman v. Freedom Financial, 9th Cir. 2022, as applied in [Godun v. JustAnswer, 9th Cir. 2025](https://library.nclc.org/companion-material/godun-v-justanswer-llc-9th-cir-apr-15-2025)); companies keep losing when the button text doesn't match the sentence (ClassPass said "By signing up" over a "Continue" button; Godun v. JustAnswer, 9th Cir. 2025). App screen: "By clicking 'I agree', you agree to the miyagi Terms and Privacy Policy" right above an "I agree" button, links underlined, nothing pre-checked; log terms version, time, install or account id and app version. Never rely on a footer link alone. | No (show counsel the screen) |
| 1, 15 Minors | Cal. Fam. Code 6710 lets a minor void a contract; J.R. v. Electronic Arts (Cal. Ct. App. 2024) let a minor's disaffirmance void an arbitration clause. A parent accepting as a party, and access ending on disaffirmance, is the best available pattern. Expect the cap and waivers not to bind a minor. | **Yes**: unsettled law |
| 2, 7 AI disclosure and accuracy | Anthropic's Usage Policy (eff. 2026-11-12) requires telling users they're dealing with AI "at the beginning of each chat session or in the product interface"; Commercial Terms D.3 require telling users outputs may be inaccurate. Moffatt v. Air Canada (BCCRT 2024) held a company to its chatbot's statements, hence "these terms beat the chat". No certificates: grading for credentials or misconduct is a high-risk use under Anthropic's policy. | No |
| 5 Acceptable use | Flows down Anthropic's and Google's prohibited uses (both bind end users of products built on them); Anthropic's policy bans submitting AI-assisted work without permission (register B15). | No |
| 6 License to user content | Narrow and purpose-limited; the "no training" promise is true only while Gemini runs on a paid project (register B02). Don't promise "never" anything a provider path contradicts. | No (cross-check the policy) |
| 8 YouTube | YouTube's API rules require our terms to bind users to the YouTube Terms and our policy to point to Google's Privacy Policy. Credit and link every creator (Course Hero's ~$75M verdict was mostly for stripping attribution, 17 U.S.C. 1202). The shared-lesson sentence is a placeholder for the cache decision; the underlying fair-use question needs counsel before monetizing (register B12). | **Yes** for the fair-use question, later |
| 9 BYOK | Adults only, because Gemini keys carry Google's 18+ term. The code backs "never through miyagi-cloud": the engine calls providers directly with the learner's key (`IL:server/config.py:12-17`). Anthropic's consumer terms bar sharing an API key; TypingMind-style terms put charges and provider compliance on the user. | No (yes if BYOK ever touches the proxy) |
| 12 DMCA | Safe harbor needs a designated agent registered with the Copyright Office ($6, renew every 3 years). Use a business or PO box address, not a home: the directory is public. | No |
| 13 Regions | Anthropic's Supported Regions Policy covers end users physically in unsupported regions; also geo-block at the proxy (register B11). | No |
| 16 Warranty | Conspicuous heading naming merchantability and fitness (Cal. Com. Code 2316 style). Avoid the bare "some jurisdictions don't allow..." sentence, which New Jersey's TCCWNA has been used against. | **Yes, briefly**: NJ and EU/UK wording |
| 17 Liability | $100 or 12 months' fees is the market norm (OpenAI; Anthropic and Cursor use 6 months). Cal. Civ. Code 1668 voids exemptions for fraud, willful injury and violations of law; don't purport to waive CLRA rights (1751). UK Consumer Rights Act s.65: no excluding death or injury from negligence. | **Yes**: unconscionability and 1668 |
| 18 Disputes | No arbitration for now: AAA's 2026 mass-arbitration fees fall on the business, California's fee-payment deadlines survive in softened form (Hohenshelt, 2025), McGill bars waiving public injunctive relief, the Ninth Circuit struck a custom mass-arbitration setup (Heckman, 2024), and minors can disaffirm. Revisit with counsel if paid plans come, using a 30-day opt-out and small-claims carve-out. EU/UK consumers keep their home courts and law (Rome I Art. 6, Brussels Ia Art. 18). | **Yes** before any move to arbitration |
| 19 Changes | 30 days' notice and re-acceptance for material changes; new data uses only by fresh opt-in, never retroactive ([FTC, Feb 2024](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/ai-other-companies-quietly-changing-your-terms-service-could-be-unfair-or-deceptive)). | No for the US; yes for EU/UK wording |
| Left out on purpose | No indemnity from users (weak against minors, bad look for a free tool); no non-disparagement or review-gag clause (void under Cal. Civ. Code 1670.8 and 15 U.S.C. 45b); no browsewrap. | No |
