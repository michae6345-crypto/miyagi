# DRAFT: miyagi Terms of Service and app license

> **DRAFT. Not legal advice. Not published, not shown in the app.**
> A lawyer should review this before anyone is asked to accept it (see "Notes for the team" at the end, and
> `docs/legal/RISKS.md`). Items marked **[TBD]** need a founder decision.

Last updated: [TBD]

These terms are an agreement between you and [TBD: the company that runs miyagi; see the team notes] ("miyagi",
"we", "us"). They cover the miyagi app for Mac and Windows, the miyagi-cloud service the app talks to, and the
website at miyagi.study. Together we call these "miyagi".

By clicking "I agree" in the app, or by using miyagi, you agree to these terms and to our
[Privacy Policy](https://miyagi.study/privacy). If you don't agree, don't use miyagi.

## 1. Who can use miyagi

- You must be **13 or older**. If you are under 13, please don't use miyagi.
- If you are **under 18** (or under the age of majority where you live), a parent or legal guardian must agree to
  these terms for you, and they are responsible for your use of miyagi. Parents: see section 15.
- You can't use miyagi if you are barred from receiving software or services under the laws of the United States or
  where you live, including if you are in a country or region under US embargo (section 13).

## 2. What miyagi does

miyagi turns a coding tutorial into a hands-on lesson. While you follow a lesson, it looks at your screen and your
code, checks whether you've done each step, and coaches you. To do that, the app sends some of what it sees to AI
services (today Anthropic and Google), either through miyagi-cloud or straight to the provider if you add your own
API key. The [Privacy Policy](https://miyagi.study/privacy) says exactly what is sent, where, and how long it's kept.

miyagi is a learning aid. It is new, it changes often, and parts of it may be marked as beta.

## 3. Your account

Signing in (with Google) is optional for some features and required for others [TBD: which]. If you sign in, keep
your Google account secure; you're responsible for what happens under your sign-in. Tell us if you think someone
else is using it.

## 4. The app license

We give you a personal, non-exclusive, non-transferable, revocable license to install and use the miyagi app on
computers you own or control, for your own learning, while you follow these terms.

You may not:

- copy, sell, rent, sublicense or redistribute the app (sharing the official download link is fine);
- reverse engineer, decompile or disassemble the app, except where the law allows it even though these terms say no;
- pull out, use or share any key, token or credential built into the app or issued to it by miyagi-cloud;
- remove or change our notices, or the notices of open-source components.

The app includes open-source software. Those components are licensed under their own terms, listed in the app's
third-party notices [TBD: ship THIRD_PARTY_NOTICES], and nothing here limits your rights under those licenses.

The app may download and install updates automatically. Some updates are needed to keep using miyagi-cloud.

If you got the app from the Microsoft Store, the Store's standard application license terms also apply, and where
they conflict with section 4, the Store terms win for the app itself. [TBD: confirm when the Store listing exists.]

## 5. Using miyagi-cloud fairly

miyagi-cloud pays for AI calls so you don't have to. To keep it working for everyone, you may not:

- get around usage limits, for example by creating many accounts or installs, or sharing install tokens;
- call miyagi-cloud from anything other than the miyagi app, scrape it, or overload it;
- use miyagi to break the law, to harm others, or to make malware or anything else meant to cause damage;
- point miyagi at other people's private information (messages, documents, accounts) without their permission;
- use miyagi in a way that breaks the AI providers' rules, which apply to everything sent to them:
  [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) and
  [Google Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy);
- use miyagi to cheat: for example, to complete graded schoolwork or tests where AI help isn't allowed.

We set free usage limits and may change them. We may pause or block access if we see abuse.

## 6. Your screen, your code, and what's on them

You keep all rights to your code, your files and anything else that is yours. You give us permission to read,
copy, process and send your screen content, code and questions, as described in the Privacy Policy, only to run
miyagi for you (including sending them to our AI providers), to keep miyagi secure, and to fix problems you report.
We don't use them to train AI models, and we don't sell them.

**You control what's on your screen.** During a lesson, miyagi takes screenshots. Before a lesson, close or hide
anything you don't want sent: passwords, API keys, banking, private messages, other people's information. miyagi
blacks out some apps (such as password managers and Messages), but it can't catch everything. You can pause or end
a lesson at any time. [TBD: confirm the app has a visible pause.]

## 7. Lessons, AI output and grades

- **AI makes mistakes.** Lessons, hints, explanations, code suggestions and grades are made by AI and may be wrong,
  incomplete or out of date. Check them before you rely on them.
- **Grades are feedback, not credentials.** When miyagi says a step passed, that means its checks passed on your
  machine at that moment. It isn't a certification, a school grade, or proof that your code is correct or safe.
- **Be careful with commands and code.** Lessons may ask you to install packages or run commands. Read them first,
  run them only on a computer you're allowed to change, and keep backups. You're responsible for what you run.
- **No professional advice.** Nothing in miyagi is legal, financial, medical or security advice.
- **What you make is yours.** As between you and us, you own the code you write. To the extent we have any rights in
  the AI output miyagi generates for you, we give them to you, subject to the AI providers' terms. Others may get
  similar output.

## 8. Tutorials and other people's content

The videos miyagi builds lessons from belong to their creators and are played through YouTube. miyagi is not
affiliated with, endorsed by or sponsored by YouTube, Google or the tutorial creators. When you watch a video in
miyagi, YouTube's [Terms of Service](https://www.youtube.com/t/terms) apply to that video.

A lesson is a study guide that follows the video and points back to it. Lessons built for a video may be saved and
shown to other learners who pick the same video; they are built from the video, never from your screen or code.
[TBD: confirm against the cloud cache code.]

If you believe something in miyagi infringes your copyright, see section 12.

## 9. Your own API keys

You can add your own API key for a supported AI provider. If you do:

- the key is stored on your computer, locked by your system's secure storage (Keychain on Mac), and sent only to
  that provider;
- calls made with your key are between you and that provider, under your agreement with them; you pay their charges
  and are responsible for following their terms and rules;
- keep your key secret, and remove it in Settings when you stop using it. We are not responsible for charges or
  problems caused by a key you added, unless we caused them by breaking these terms.

## 10. Third-party services

miyagi relies on services we don't control, including YouTube, Google sign-in, Supabase, Render, Anthropic and
Google Gemini. They may change or stop, and that may change or stop parts of miyagi. Their own terms and privacy
policies apply to how they handle what they receive.

## 11. Feedback

If you send us ideas or suggestions, we may use them without owing you anything.

## 12. Copyright complaints

If you believe material in miyagi infringes your copyright, send a notice to our designated agent with the details
listed in 17 U.S.C. § 512(c)(3): [TBD: DMCA agent name, address and email, as registered with the US Copyright
Office]. We may remove material and, in appropriate cases, end the access of people who repeatedly infringe.

## 13. Export and sanctions

You may not use, download or export miyagi in breach of US export control and sanctions laws, including in a
country or region under comprehensive US embargo, or if you are on a US government restricted-party list. Our AI
providers only support certain countries; miyagi may not work everywhere.

## 14. Ending things

You can stop using miyagi at any time. To delete your data, use Settings, Privacy, Delete my data, and contact us to
delete your account (see the Privacy Policy).

We may suspend or end your access if you break these terms, if the law requires it, or if we stop offering miyagi.
If we stop offering miyagi-cloud, we'll try to tell you first. Sections 6 (the last two sentences), 7, 11, 16, 17,
18 and 19 survive.

## 15. For parents and guardians

If your teen uses miyagi, you agree to these terms on their behalf and are responsible for their use. You can ask
us to delete your teen's account and data at any time (see the Privacy Policy). If you learn that a child under 13
is using miyagi, tell us and we will delete their data.

## 16. Disclaimers

miyagi is provided "as is" and "as available". To the fullest extent the law allows, we make no promises that
miyagi will be accurate, uninterrupted, secure or error-free, or that it fits your purpose, and we disclaim implied
warranties such as merchantability, fitness for a particular purpose and non-infringement.

Some places don't allow these disclaimers, so some of them may not apply to you. Nothing in these terms limits
rights you have under consumer protection laws that can't be waived.

## 17. Limits on liability

To the fullest extent the law allows:

- we are not liable for indirect, incidental, special, consequential or punitive damages, or for lost data, lost
  profits or lost work, arising from miyagi;
- our total liability for any claim about miyagi is limited to the greater of what you paid us for miyagi in the
  12 months before the claim, or US$50.

These limits don't apply to liability that can't be limited by law, such as for fraud, gross negligence, willful
misconduct, or (where the law says so) death or personal injury caused by negligence.

## 18. Disputes

Let's try to fix problems first: email us at [TBD: contact] and give us 30 days to try to resolve it.

These terms are governed by the laws of the State of California, without regard to conflict-of-laws rules. Any
dispute will be decided in the state or federal courts in [TBD: county], California, and you and we agree to those
courts' jurisdiction, except that either of us may bring a claim in small claims court where it qualifies. If you
live in the EU, the UK or another place whose consumer laws give you the right to sue at home under your local law,
these terms don't take that right away.

## 19. General

- **Changes.** We may update these terms. For important changes, we'll tell you in the app before they apply and ask
  you to agree again; changes won't apply to disputes that started before them. The date at the top shows the
  latest version.
- **Whole agreement.** These terms and the Privacy Policy are the whole agreement between you and us about miyagi.
- **If part doesn't work.** If a court finds part of these terms unenforceable, the rest still applies.
- **No waiver.** If we don't enforce something right away, we can still enforce it later.
- **Assignment.** You can't transfer these terms. We can transfer them if miyagi is transferred to another company,
  for example when we form one, and we'll tell you if that happens.

## 20. Contact

[TBD: contact email and postal address.]

---

## Notes for the team (not for publication)

[Filled in from the contract-law research: why each clause is drafted this way, what a lawyer must check, and
sources.]
