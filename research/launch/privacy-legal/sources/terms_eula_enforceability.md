# Enforceable Terms of Service + desktop EULA for a free AI learning app used by teens (California law, with EU/UK notes), status 2026-11-21

Not legal advice. Research notes for a drafter. Status date: 2026-11-21. A dagger (†) marks a source I did not open in this session. Those cites come from established law and standard statutory text and are given so the drafter can check them. leginfo.legislature.ca.gov and law.justia.com refused automated fetches (HTTP 403) in this session, so California statute text marked † should be checked against the official site before anyone quotes it.

---

## 1. Formation: clickwrap vs sign-in-wrap vs browsewrap, the Ninth Circuit test, desktop first-run design, and notice of changes

### Takeaway
Under California law as the Ninth Circuit applies it (Berman 2022, Oberstein 2023, Keebaugh 2024, Chabolla Feb 2025, Godun Apr 2025), anything short of a true "I agree" clickwrap is judged on two steps. Step one asks whether the notice was reasonably conspicuous, given visual design and the context of the transaction. Step two asks whether the user was explicitly told which action means assent. Courts keep striking down designs that are close but not exact. A first-run screen with an unchecked box or an "I agree" button, and a sentence saying that clicking means agreement right next to it, is the safe pattern. Material changes, especially to data use, should go through in-app re-acceptance and should not be applied retroactively.

### Cited Findings
- **The test.** Contracts form only where "(1) the website provides reasonably conspicuous notice of the terms to which the consumer will be bound; and (2) the consumer takes some action, such as clicking a button or checking a box, that unambiguously manifests his or her assent to those terms." Godun quotes this from *Berman v. Freedom Fin. Network*, 30 F.4th 849, 856 (9th Cir. 2022), and says the same test appears in *Chabolla v. ClassPass*, 129 F.4th 1147, 1154 (9th Cir. 2025), *Sellers v. JustAnswer*, 73 Cal. App. 5th 444, 469 (2021), and *Herzog v. Superior Ct.*, 101 Cal. App. 5th 1280, 1296 (2024). — [Godun v. JustAnswer LLC, 9th Cir. No. 24-2095, opinion filed 2025-04-15, slip op. p. 14](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **True clickwrap is presumptively enforceable.** Godun says that asking users to "click[] on an 'I accept' or 'I agree' button" would have created a clickwrap agreement, which is "presumptively enforceable." It cites *B.D. v. Blizzard Ent.*, 76 Cal. App. 5th 931, 944–45 (2022). — [Godun, slip op. p. 21 n.6](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **Step one, visual design.** The question is whether the advisal is "displayed in a font size and format such that the court can fairly assume that a reasonably prudent Internet user would have seen it." The factors are location on the page, font size, color, and contrast against the background. Advisal text that was small, not "directly above or below" the action button, and gray-on-gray failed. — [Godun, slip op. pp. 15, 19](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **No checklist, and small differences matter.** "[T]here is no bright-line test for finding that a particular design element is adequate in every circumstance" (quoting Chabolla at 1156–57). Under California law, "even minor differences" in design can decide a case (quoting Sellers at 481). — [Godun, slip op. pp. 15–16](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **Step one, context of the transaction.** Courts ask whether the deal "contemplates entering into a continuing, forward-looking relationship." Factors that point toward notice include: (1) account creation with a "full registration process" (Oberstein, 60 F.4th at 517), (2) a free trial, (3) entering a credit card, and (4) downloading an app, which suggests the terms stay accessible (*Keebaugh v. Warner Bros. Ent.*, 100 F.4th 1005, 1020 (9th Cir. 2024)). — [Godun, slip op. pp. 16–17](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **Step two, explicit advisement.** The user must be "explicitly advised that the act of clicking will constitute assent to the terms," and "the notice must explicitly notify a user of the legal significance of the action she must take" (quoting Berman at 857–58). "Even strongly implicit advisement isn't enough." Approved forms: "By clicking the Continue >> button, you agree to the Terms & Conditions" (Berman) and "By tapping 'Play' I agree to the Terms of Service" (Keebaugh). — [Godun, slip op. pp. 17–18](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **The button label must match the advisal.** In Chabolla the advisal read "[b]y signing up you agree...", but the button said "Continue," so there was no unambiguous assent. A bare "I understand and agree to the Terms and Conditions" that does not "indicate to the user what action would constitute assent" fails step two. — [Godun, slip op. pp. 18, 21](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **Context does not cure a missing "By clicking..." clause.** Step two "does not look to the context of the transaction but relies on the explicit advisement." Button text matters only "insofar as it matches an advisal's explanation." — [Godun, slip op. p. 22](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **The concurrence (also by Judge R. Nelson)** criticizes Berman's dicta on hyperlink styling and argues the core test is reasonableness. It also notes that the "Platonic ideal of the hyperlink is blue and underlined" (citing Oberstein at 516). — [Godun, concurrence pp. 24–26](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **Chabolla v. ClassPass** (9th Cir. Feb. 27, 2025, 2–1, Mendoza J.; Bybee J. dissenting). A three-screen sign-up with small, gray terms links on each screen was a sign-in-wrap that failed both steps. ClassPass petitioned for rehearing en banc on 2025-04-14. I did not find the outcome. — [Hunton, "It's a Wrap" (2025)](https://www.hunton.com/privacy-and-cybersecurity-law-blog/its-a-wrap-the-latest-from-the-ninth-circuit-on-sign-in-wrap-agreements); [Eric Goldman, Technology & Marketing Law Blog (Mar. 2025)](https://blog.ericgoldman.org/archives/2025/03/the-ninth-circuit-has-a-lot-to-say-about-online-contract-formation-much-of-it-confusing-chabolla-v-classpass.htm); [Crowell, rehearing petition alert (2025)](https://www.crowell.com/en/insights/client-alerts/classpass-petition-for-rehearing-will-tell-the-future-of-sign-in-wrap-agreements-on-the-internet) (all accessed 2026-11-21)
- **A redesigned flow can succeed.** A later N.D. Cal. decision, *Blackburn v. ClassPass*, found ClassPass did form its TOS and sent the case to arbitration. — [Eric Goldman blog post on Blackburn v. ClassPass](https://blog.ericgoldman.org/?p=28782) (accessed 2026-11-21)
- **The Godun facts.** JustAnswer's payment pages used a pre-checked blue check-mark box and advisals that said "I agree" without saying which action meant assent. The panel affirmed denial of the motion to compel arbitration (135 F.4th 699). — [NCLC summary, Godun v. JustAnswer (9th Cir. Apr. 15, 2025)](https://library.nclc.org/companion-material/godun-v-justanswer-llc-9th-cir-apr-15-2025); [Bloomberg Law (2025)](https://news.bloomberglaw.com/product-liability-and-toxics-law/justanswer-fails-in-appeal-to-arbitrate-user-subscription-claims) (accessed 2026-11-21)
- **Sellers v. JustAnswer** (Cal. Ct. App. 2021). For automatic-renewal deals, "it must be clear that consumers agree not only to the one-time purchase, but also to the continuing purchases going forward." This matters for any future paid tier. — [Godun, slip op. pp. 19–20 (discussing Sellers, 73 Cal. App. 5th at 458, 480)](https://cdn.ca9.uscourts.gov/datastore/opinions/2025/04/15/24-2095.pdf) (accessed 2026-11-21)
- **The test is still current.** Unpublished Ninth Circuit memoranda dated 2026-11-04 (No. 25-7045) and 2026-11-05 (No. 25-7161) cite Chabolla and Godun as the governing framework. I saw these only in search snippets and did not read them. — [9th Cir. memo 25-7045 (2026-11-04)](https://cdn.ca9.uscourts.gov/datastore/memoranda/2026/11/04/25-7045.pdf); [9th Cir. memo 25-7161 (2026-11-05)](https://cdn.ca9.uscourts.gov/datastore/memoranda/2026/11/05/25-7161.pdf) (accessed 2026-11-21)
- **FTC on changes (blog post, 2024-02-13, "AI (and other) Companies: Quietly Changing Your Terms of Service Could Be Unfair or Deceptive").** Adopting more permissive data practices, such as sharing data with third parties or using it for AI training, and telling users only through a "surreptitious, retroactive amendment" may be unfair or deceptive under the FTC Act. The post traces this position to the 2004 *Gateway Learning* case. — [FTC Technology Blog, 2024-02-13](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/ai-other-companies-quietly-changing-your-terms-service-could-be-unfair-or-deceptive)†; summaries: [Consumer Finance Monitor (2024-02-28)](https://www.consumerfinancemonitor.com/2024/02/28/ftc-warns-quietly-changing-privacy-policies-may-be-an-unfair-or-deceptive-practice/), [IAPP](https://iapp.org/news/b/us-ftc-dont-change-your-privacy-policies-quietly-for-ai-data-harvesting) (accessed 2026-11-21)
- **How AI companies handle changes.** OpenAI: "We will give you at least 30 days advance notice of changes to these Terms that materially adversely impact you" (Terms of Use effective 2026-01-01). Anthropic's consumer terms treat continued use after posting as acceptance (Consumer Terms effective 2025-10-08, s. 12). — [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/); [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)

### Inferences
- A desktop first-run screen is a good fit for a true clickwrap, which is the presumptively enforceable category. The design rules that follow from Berman, Chabolla and Godun:
  - Use an unchecked box ("I have read and agree to the miyagi Terms of Service and End User License Agreement"), plus a primary button that stays disabled until the box is checked. Alternatively, use a single button labeled "I agree" with an advisal directly above it: "By clicking 'I agree', you agree to the Terms of Service and EULA."
  - The words in the advisal and the button label must match exactly.
  - Put the advisal directly above or below the button, in body-size text with full contrast. Never use gray-on-gray.
  - Make the links blue and underlined, and open the full text in-app. Bundle an offline copy.
  - Keep the screen uncluttered: no competing calls to action, and no skip.
  - Never pre-check the box.
- Keebaugh's "app download" and Oberstein's "account registration" factors help miyagi at step one. Neither cures a weak step-two advisal.
- **Logging (my design inference, not a holding).** Record install or account ID, terms version and hash, UTC timestamp, app version, OS, locale, which control was clicked, and an archived image or HTML of the exact screen for each version. A company has to prove what the user saw, and courts decide these cases screen by screen.
- **Changes.** Treat the FTC post as a floor: any expansion of data use, such as starting to train on user code or screen captures, needs fresh affirmative opt-in consent and must not apply retroactively. For other material changes, use an in-app modal that summarizes the change, gives advance notice (30 days matches OpenAI), and requires re-acceptance through the same clickwrap. "Continued use equals acceptance" is weaker and conflicts with EU/UK unilateral-variation limits (section 3).

### Gaps
- I did not find whether Chabolla went en banc or whether certiorari was sought. The November 2026 memoranda suggest it remains good law.
- I found no case dealing specifically with a desktop installer or first-run EULA screen in 2023–2026. The doctrine above comes from web and mobile flows. Installer clickwraps are an older and generally enforced category, but I did not verify a recent case.

---

## 2. Minors: infancy doctrine, Cal. Family Code 6700/6710, cases on minors and online terms/arbitration, drafting approaches

### Takeaway
In California a 13–17-year-old can form a contract, but can disaffirm it before turning 18 or within a reasonable time after. A clean disaffirmance can void the arbitration clause with the rest of the contract (J.R. v. Electronic Arts, 2024). Courts have limited this when the minor keeps using the product, when the disaffirmance is worded broadly enough that a delegation clause sends the question to an arbitrator, or when a parent assented. For a free app the practical answer is to have a parent or guardian agree as a party. The minor's own promises, the liability cap and the arbitration clause should all be treated as possibly unenforceable against the minor.

### Cited Findings
- **Statute.** Fam. Code § 6700: a minor may contract "in the same manner as an adult, subject to the power of disaffirmance." § 6710: a minor's contract "may be disaffirmed by the minor before majority or within a reasonable time afterwards." § 6711: no disaffirmance of obligations entered "under the express authority or direction of a statute." § 6712: limits disaffirmance for necessaries. — [Cal. Fam. Code §§ 6700–6713, leginfo](https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=FAM&division=11.&title=&part=3.&chapter=2.&article=)† (fetch blocked; the § 6710 wording is confirmed as quoted in [CPM Legal (2020-05-14)](https://www.cpmlegal.com/blogs-Advocates-For-Justice/disaffirmance-by-a-minor-as-a-defense-to-arbitration)) (accessed 2026-11-21)
- **J.R. v. Electronic Arts**, 98 Cal. App. 5th 1107 (Cal. Ct. App., 4th Dist., Div. 2, filed 2024-01-17). The minor's notice disaffirming "any" contract accepted through his EA account covered the arbitration agreement. The court affirmed denial of EA's motion to compel and rejected EA's argument that the minor had to challenge the delegation clause specifically. — [Justia opinion page](https://law.justia.com/cases/california/court-of-appeal/2024/e080414.html)† (403 to automated fetch); [courts.ca.gov PDF](https://courts.ca.gov/opinions/archive/E080414.PDF)†; summary: [WSGR](https://wsgr.com/en/insights/court-refuses-video-game-companys-arbitration-bid-in-minor-involved-case.html) (accessed 2026-11-21)
- **Williams v. Moon Active Ltd.**, No. 4:25-cv-01626 (N.D. Cal. 2025-12-09, Judge Yvonne Gonzalez Rogers). The game's terms formed a valid contract with the minor and the arbitration clause was conspicuous. The minor's letter disaffirming "all contracts" attacked the contract as a whole, so the delegation clause sent the question to the arbitrator, and arbitration was compelled. J.R. was distinguished. — [Duane Morris Class Action Defense Blog (2025-12-11)](https://blogs.duanemorris.com/classactiondefense/2025/12/11/california-federal-court-holds-that-minors-can-be-bound-to-arbitration-in-a-class-action-context/) (accessed 2026-11-21)
- **Continued use defeats disaffirmance.** In *Doe v. Epic Games*, 2020 WL 376573 (N.D. Cal. 2020-01-23), the court decided disaffirmance itself and held that a minor who keeps using the product cannot validly disaffirm, because they may not "adopt that part of an entire transaction which is beneficial, and reject its burdens." *Lopez v. Kmart* (N.D. Cal. 2015) held that disaffirmance can be "any act or declaration indicating intent to disaffirm" and "rescinds the entire contract." The same post lists *T.K. v. Adobe Sys.*, 2018 WL 1812200 (N.D. Cal. 2018-04-17) and *I.B. v. Facebook*, 905 F. Supp. 2d 989 (N.D. Cal. 2012) as cases where minors avoided arbitration. — [CPM Legal (2020-05-14)](https://www.cpmlegal.com/blogs-Advocates-For-Justice/disaffirmance-by-a-minor-as-a-defense-to-arbitration) (accessed 2026-11-21)
- **R.A. v. Epic Games** (C.D. Cal. 2019). Arbitration was denied because the minor had stopped playing Fortnite and filed a declaration disaffirming the EULA. **Heidbreder v. Epic Games** (E.D.N.C. 2020) enforced the arbitration clause even though a minor gave the final assent. These are search-result summaries; I did not read the opinions. — [Robins Kaplan, "Trends in video game company quests to arbitrate cases" (PDF)](https://robinskaplan.com/-/media/pdfs/trends-in-video-game-company-quests-to-arbitrate-cases) (accessed 2026-11-21)
- **2025–2026 trend toward enforcement.** The following are reported, but I did not read the opinions:
  - *Garcia v. Roblox* (C.D. Cal. 2026): the minor did not effectively disaffirm until she stopped using Roblox in September 2025, and arbitration of all claims was compelled. [Courthouse News, Uhl v. Roblox order (2026-05)](https://www.courthousenews.com/wp-content/uploads/2026/05/uhl-vs-roblox-order.pdf)
  - An Epic (Fortnite) ruling in December 2025 found a child under 13 equitably estopped from denying the EULA's arbitration clause. [Bloomberg Law](https://news.bloomberglaw.com/litigation/epic-games-wins-renewed-bid-to-arbitrate-kids-privacy-claims)
  - *Orellana v. Roblox* (Fla. 2025): most claims were sent to arbitration. [Goldman blog via TagTeam](https://tagteam.harvard.edu/hub_feeds/3626/feed_items/13816482)
  - (all accessed 2026-11-21)
- **Industry practice for teens.**
  - OpenAI: minimum age 13, and "If you are under 18 you must have your parent or legal guardian's permission to use the Services" (Terms of Use effective 2026-01-01). — [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/)
  - Anthropic Consumer Terms require users to be 18+ (s. 2, effective 2025-10-08). — [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms)
  - Cursor requires the age of majority, 18 in the US (s. 2, updated 2026-09-03). — [Cursor Terms](https://cursor.com/terms-of-service)
  - Khan Academy: individual Khanmigo users must be 18+, under-18 access runs only through adult-linked accounts, chat history is visible to the parent or guardian, and flagged messages are reported to the parent or teacher. — [Khan Academy Help Center](https://support.khanacademy.org/hc/en-us/articles/13860282793869) (help-center pages, not the ToS. The search summary did not map each statement to a specific article)
  - (all accessed 2026-11-21)

### Inferences
- **Drafting pattern.**
  - (a) Make the parent or guardian a party: "If you are under 18, your parent or legal guardian must read and accept these Terms, and by doing so agrees to them on their own behalf and on yours and is responsible for your use."
  - (b) Use a separate parent-acceptance step, such as a parent email confirmation with its own clickwrap. A checkbox the teen ticks saying "my parent agrees" is weak evidence.
  - (c) Add a "benefits retained" clause: if a minor disaffirms, the account and license end. This tracks Doe v. Epic and Garcia v. Roblox, where continued use defeated disaffirmance.
  - (d) Do not expect arbitration, the class waiver or the liability cap to hold against a minor in California state court after J.R.
- **Arbitration against minors** is unsettled. The outcome turns on the wording of the disaffirmance, delegation, continued use and parental assent. For a startup this is one more reason to consider courts over arbitration (section 8).
- **Why the parent's agreement matters.** It is an adult's contract and cannot be disaffirmed by the minor. It gives a counterparty for the parent's own claims, and it is evidence of assent and supervision. Whether a parent can waive or arbitrate the minor's own claims under California law is not settled by the sources above.

### Gaps
- I could not verify *C.M.D. v. Facebook* (N.D. Cal. 2014; my recollection is that it was affirmed at 621 F. App'x 488 (9th Cir. 2015), with a holding that minors who kept using Facebook could not disaffirm). Search did not return the opinion. Treat that as unverified.
- I found no California appellate decision since J.R. resolving whether a parent's click binds a minor to arbitration of the minor's own claims.
- Age verification and age-signal duties are privacy and child-safety law and are left to other researchers. Examples are COPPA for under-13s and California AB 1043, the Digital Age Assurance Act, which I believe becomes operative 2027-01-01 and was not verified here.

---

## 3. Disclaimers and limitation of liability: California, New Jersey TCCWNA, UK CRA 2015, EU directives; typical caps

### Takeaway
California enforces "as is" disclaimers and dollar caps in consumer terms, with limits:
- Civ. Code § 1668 bars exempting anyone from their own fraud, willful injury, or violation of law.
- § 1670.5 lets a court strike unconscionable terms.
- The CLRA's anti-waiver rule (§ 1751) voids waivers of CLRA rights.
- Implied-warranty disclaimers must be conspicuous and mention "merchantability" (Com. Code § 2316), if the UCC applies at all.

Industry caps are the greater of fees paid (in the prior 6 or 12 months) and $100. UK and EU consumer law makes the cap unenforceable for death or personal injury from negligence. It also subjects every term to a fairness and transparency test. UK statutory digital-content rights mostly attach only where a price is paid. EU digital-content rights can attach to free-for-data apps.

### Cited Findings
- **Cal. Civ. Code § 1668.** "All contracts which have for their object, directly or indirectly, to exempt anyone from responsibility for his own fraud, or willful injury to the person or property of another, or violation of law, whether willful or negligent, are against the policy of the law." — [Civ. Code § 1668, leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1668.&lawCode=CIV)† (accessed 2026-11-21)
- **Cal. Civ. Code § 1670.5.** A court may refuse to enforce a contract or clause it finds unconscionable when made, or may limit the clause. — [Civ. Code § 1670.5, leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1670.5.&lawCode=CIV)† (accessed 2026-11-21)
- **Cal. Civ. Code § 1751 (CLRA).** "Any waiver by a consumer of the provisions of this title is contrary to public policy and shall be unenforceable and void." — [Civ. Code § 1751, leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1751.&lawCode=CIV)† (accessed 2026-11-21)
- **Cal. Com. Code § 2316.** Excluding the implied warranty of merchantability requires mentioning merchantability and, if in writing, being conspicuous. Excluding fitness requires a conspicuous writing. "As is" language excludes implied warranties. — [Com. Code § 2316, leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=2316.&lawCode=COM)† (accessed 2026-11-21)
- **Industry caps, for comparison.**
  - Anthropic: "the greater of the amount you paid to us" in the prior six months or $100 (Consumer Terms s. 11, effective 2025-10-08). [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms)
  - OpenAI: the greater of the amount paid for the relevant service in the prior 12 months or $100 (Terms of Use effective 2026-01-01). [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/)
  - Cursor: the greater of six months' fees or "$100" (s. 15.2, updated 2026-09-03). [Cursor Terms](https://cursor.com/terms-of-service)
  - (all accessed 2026-11-21)
- **Disclaimer style.** Anthropic uses an all-caps "AS IS" and "AS AVAILABLE" disclaimer and adds "THE LAWS OF SOME JURISDICTIONS DO NOT ALLOW THE DISCLAIMER OF IMPLIED WARRANTIES" without naming those jurisdictions. — [Anthropic Consumer Terms s. 11](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)
- **New Jersey TCCWNA, N.J.S.A. 56:12-16.** A consumer contract may not say a provision "is or may be void, unenforceable or inapplicable in some jurisdictions" without specifying whether that is so in New Jersey. *Spade v. Select Comfort* (N.J. 2018-04-16) held that a plaintiff is not "aggrieved," and so cannot recover, without "some form of harm." That sharply cut no-injury TCCWNA class actions. — [Hunton, NJ Supreme Court clarifies TCCWNA (PDF, 2018)](https://hunton.com/media/legal/36846_new-jersey-supreme-court-clarifies-truth-in-consumer-contract.pdf); [Kelley Drye, "Ding Dong TCCWNA class actions are dead" (2018)](https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/ding-dong-tccwna-class-actions-are-dead.md) (accessed 2026-11-21)
- **UK Consumer Rights Act 2015.**
  - s. 31: no exclusion of statutory rights for goods.
  - s. 47: no exclusion of statutory rights for digital content (ss. 34–37, 41).
  - s. 57: no exclusion of the services rights, including s. 49 (reasonable care and skill), and no limiting liability below the price paid.
  - s. 65: a trader cannot exclude or restrict liability for death or personal injury resulting from negligence.
  - s. 62: unfair terms are not binding on the consumer.
  - s. 68: written terms must be transparent.
  - Schedule 2, Part 1: the indicative ("grey") list.
  - Under s. 33(1), the digital-content Chapter applies only where content is supplied "for a price paid by the consumer," or free with paid goods, services or content (s. 33(2)).
  - — [CRA 2015, legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2015/15/contents)†; [s. 65](https://www.legislation.gov.uk/ukpga/2015/15/section/65)†; [s. 33](https://www.legislation.gov.uk/ukpga/2015/15/section/33)† (accessed 2026-11-21)
- **UK s. 46** (damage to a device or other digital content) applies where "a trader supplies digital content to a consumer under a contract" and the damage would not have happened with "reasonable care and skill." Subsection (1) says nothing about free content. — [CRA 2015 s. 46](https://www.legislation.gov.uk/ukpga/2015/15/section/46) (accessed 2026-11-21)
- **EU Digital Content Directive (EU) 2019/770.**
  - Art. 3(1): it covers contracts where the consumer provides personal data instead of a price, except where the data is processed only to supply the content or to meet legal requirements.
  - Art. 8(2): the trader must supply updates, including security updates, needed to keep the content in conformity.
  - Art. 19: conditions for modifying digital content, including a valid reason in the contract, no cost to the consumer, clear information, and a right to terminate if the impact is more than minor.
  - Art. 22: terms that exclude or derogate from the national rules to the consumer's detriment are not binding.
  - — [Directive 2019/770, EUR-Lex](https://eur-lex.europa.eu/eli/dir/2019/770/oj)† (accessed 2026-11-21)
- **EU Unfair Contract Terms Directive 93/13/EEC.**
  - Art. 3(1): a term is unfair if, contrary to good faith, it causes a significant imbalance to the consumer's detriment.
  - Art. 5: plain and intelligible language.
  - Art. 6(1): unfair terms do not bind the consumer.
  - Annex grey-list items:
    - 1(a): excluding liability for death or personal injury.
    - 1(b): inappropriately excluding rights for non-performance.
    - 1(j): unilateral alteration without a valid reason specified in the contract.
    - 1(q): hindering legal action, for example by requiring arbitration not covered by legal provisions.
  - — [Directive 93/13, EUR-Lex](https://eur-lex.europa.eu/eli/dir/1993/13/oj)† (accessed 2026-11-21)

### Inferences
- For a free app, a cap of the greater of $100 and fees paid in the prior 12 months matches OpenAI and Anthropic and is defensible. A $50 floor is also seen in the market, but I did not source a specific example. Carve the cap out where law forbids it: fraud, willful misconduct, violation of law (§ 1668), and in the UK/EU death or personal injury from negligence and gross negligence.
- **Does the UCC apply?** Whether Article 2 reaches free downloadable software is unsettled. Draft the disclaimer as if § 2316 applies: conspicuous (all caps or bold under a heading), name merchantability, fitness and non-infringement, and say "as is."
- **CLRA.** It protects people who acquire goods or services "by purchase or lease," and courts have split on whether software counts. Free users may fall outside it, but a paid tier would bring it in. Do not include anything that reads as a waiver of CLRA rights. (This needs a lawyer.)
- **New Jersey.** Do not use the generic "some jurisdictions do not allow..." sentence alone. Either state which provisions do not apply to New Jersey residents, or use a savings clause phrased as "to the fullest extent permitted by applicable law." Spade reduces but does not remove the risk.
- **UK/EU.** Add a "Consumers in the UK, EU and EEA" section saying that nothing excludes non-excludable statutory rights or liability for death, personal injury, fraud, or gross negligence where the law forbids it. Avoid one-sided unilateral variation (section 1). If the free app processes personal data beyond what is needed to deliver it (for example, using session data to improve the shared lesson cache or for product analytics), the DCD may apply, bringing conformity duties and update obligations.

### Gaps
- I did not verify whether CRA s. 46 reaches free digital content, or whether a free online service counts as a "contract for a trader to supply a service" under s. 48 so that the s. 49 care-and-skill term applies. The answer depends on whether consideration exists. This needs a UK lawyer.
- I did not research member-state rules on caps, such as German law's bar on excluding liability for gross negligence in standard terms.
- I did not find a recent California appellate case on a "$100 cap" in free consumer software.

---

## 4. AI-output terms at reputable AI products; Moffatt v. Air Canada and an AI grader's statements

### Takeaway
Every major provider says outputs may be wrong, that the user must check them before relying on them, and (Gemini) that users should not rely on them for professional advice. OpenAI, Anthropic and Cursor assign the user whatever rights they have in outputs, and Google says it won't claim ownership. Anthropic's Commercial Terms require the API customer to tell its users that outputs may be inaccurate. Education products add academic-integrity rules and parent visibility. Moffatt shows a company can be bound by what its chatbot says. miyagi should frame grades as AI-generated practice feedback, not credentials or promises.

### Cited Findings
- **OpenAI** (Terms of Use effective 2026-01-01):
  - "You should not rely on Output from our Services as a sole source of truth or factual information."
  - Users must review output for their use case.
  - "We hereby assign to you all our right, title, and interest, if any, in and to Output."
  - Users may not "Represent that Output was human-generated when it was not."
  - — [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) (accessed 2026-11-21)
- **Anthropic consumer** (effective 2025-10-08): "You should not rely on any Outputs or Actions without independently confirming their accuracy" (s. 4). It assigns "all of our right, title, and interest—if any—in Outputs" (s. 4). Consumer Materials may be used for training unless the user opts out. — [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)
- **Anthropic commercial (API)** (effective 2025-06-17):
  - The customer "owns its Outputs" (s. B).
  - "Anthropic may not train models on Customer Content from Services" (s. B).
  - Section D.3 requires the customer to tell its users that outputs may be inaccurate. I have this as the fetch tool's paraphrase, not a verbatim quote.
  - — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (accessed 2026-11-21)
- **Google Gemini API Additional Terms** (effective 2026-03-23):
  - The Services "may sometimes provide inaccurate or offensive content."
  - "Don't rely on the Services for medical, mental health, legal, financial, or other professional advice."
  - "Google won't claim ownership over that content."
  - "You're responsible for your use of generated content, and for the use of that content by anyone you share it with."
  - — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (redirected from ai.google.dev/gemini-api/terms) (accessed 2026-11-21)
- **Cursor** (updated 2026-09-03): "Suggestions may contain errors or misleading information." "You agree that you are responsible for evaluating, and bearing all risks associated with, the use of any Suggestions" (s. 1.4). It assigns rights in Suggestions (s. 5.3). — [Cursor Terms of Service](https://cursor.com/terms-of-service) (accessed 2026-11-21)
- **Khan Academy (Khanmigo) guidance.** Responses may include mistakes or incomplete information. Using Khanmigo "to cheat, complete assignments on your behalf, or avoid doing your own work is not an appropriate use." Minors' chats are visible to the parent or guardian. — [Khan Academy Help Center](https://support.khanacademy.org/hc/en-us/articles/13860282793869) (help-center guidance, not ToS; accessed 2026-11-21)
- **Anthropic Usage Policy** (effective 2026-11-12). It prohibits users from "Plagiariz[ing] or submit[ting] AI-assisted work without proper permission or attribution." "Education and credentials" is a high-risk area covering grading that decides graduation and "making a determination of academic misconduct." For high-risk recommendations, "A qualified person must meaningfully review a High-risk AI Recommendation" and "the impacted individual knows AI was involved." — [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) (accessed 2026-11-21)
- **Moffatt v. Air Canada, 2024 BCCRT 149** (B.C. Civil Resolution Tribunal, 2024-02-14). Air Canada's website chatbot wrongly said bereavement fares could be claimed retroactively. The tribunal found negligent misrepresentation, rejected the argument that the chatbot was "a separate legal entity responsible for its own actions," and held that it was reasonable to rely on the chatbot. It found Air Canada "did not take reasonable care to ensure its chatbot was accurate," and awarded C$650.88 plus C$36.14 interest and C$125 in fees. Commentators note the reasoning on negligence is thin. — [ABA Business Law Today (2024-02)](https://www.americanbar.org/groups/business_law/resources/business-law-today/2024-february/bc-tribunal-confirms-companies-remain-liable-information-provided-ai-chatbot/); [CRT decision](https://decisions.civilresolutionbc.ca/crt/crtd/en/525448/1/document.do)†; [McCarthy Tétrault](https://www.mccarthy.ca/en/insights/blogs/techlex/moffatt-v-air-canada-misrepresentation-ai-chatbot) (accessed 2026-11-21)

### Inferences
- Moffatt is a small-claims decision from British Columbia, so it is persuasive only. Its principle, that the company owns its bot's statements, fits US negligent-misrepresentation and consumer-protection law. For miyagi, "You passed" or "Your code is correct" is a statement by miyagi. The harm is low as long as nothing of value depends on it. Risk rises if miyagi ties grades to certificates, unlocks, discounts, prizes or school credit, or if the AI coach makes promises about the product ("this is free forever") that the AI cannot authorize.
- **Grading.** Say grades are automated, AI-generated practice feedback that may be wrong, are not a certification of skill, and are not for academic, hiring or admissions decisions. Say the written Terms and product pages control over anything the AI says about pricing, features or policies, which answers Moffatt's paramountcy point. Disclose that the coach is an AI, as the Anthropic minors guidelines require.
- **High-risk use.** Keep miyagi out of Anthropic's "Education and credentials" high-risk category: no certificates, no teacher-facing grade exports used for marks, no misconduct detection. Otherwise human review and disclosure duties apply.
- **Academic integrity.** Mirror Khanmigo and the Anthropic AUP by prohibiting use of miyagi to complete graded schoolwork or exams in violation of the user's school or instructor rules, or to submit AI-assisted work without required attribution.

### Gaps
- I did not fetch the current Google Gemini Apps consumer terms, the Generative AI Additional Terms, GitHub Copilot's product-specific terms, or Duolingo's terms. The comparison above relies on OpenAI, Anthropic (consumer and commercial), the Gemini API, Cursor and Khan Academy help pages.
- EU AI Act Art. 50, the duty to disclose AI interaction, which I believe applies from 2026-08-02, and Annex III(3) (AI that evaluates learning outcomes in educational institutions is high-risk) were not verified this session. Nor was any 2025–2026 "Digital Omnibus" delay. These belong to other researchers.
- I found no US case holding a company to an AI grader's or tutor's output.

---

## 5. Acceptable use: what to prohibit, and flow-down duties from Anthropic and Google

### Takeaway
Anthropic's Usage Policy binds end users of products built on Claude directly. The Commercial Terms make the API customer responsible for, and liable to indemnify for, users' AUP violations, and Anthropic audits products that serve minors. Google's API terms require developers to make end users comply with law. The Gemini API terms incorporate the Prohibited Use Policy, require users to be 18+, and bar API clients "likely to be accessed by" under-18s. That last point is a serious conflict with a teen-heavy product. miyagi's AUP should incorporate both providers' policies by reference and add product-specific bans.

### Cited Findings
- **Anthropic AUP scope.** The policy covers "the end users of products or services integrating Claude." It bars bypassing "capabilities, restrictions, or guardrails established within our products" (jailbreaking and prompt injection), bars using "a different account" to "Circumvent a ban," and bars reselling or proxying access through unauthorized means. — [Anthropic Usage Policy, effective 2026-11-12](https://www.anthropic.com/legal/aup) (accessed 2026-11-21)
- **Anthropic and minors.** Products serving minors (under 18) must follow the separate guidelines. Those guidelines say: "Organizations must disclose to their users that they are interacting with an AI system rather than a human." They must comply with "all applicable child safety and data privacy regulations" such as COPPA, and say so publicly. The suggested safeguards are age verification, content moderation, monitoring and reporting, and a child-safety system prompt. "Anthropic will periodically audit organizations for compliance," and non-compliance can lead to "suspension or termination of your account." — [Anthropic Help Center, Guidelines for Organizations Serving Minors, updated 2026-03-16](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors) (accessed 2026-11-21)
- **Anthropic Commercial Terms (effective 2025-06-17).**
  - "Customer and its Users may only use the Services in compliance with these Terms," including the Usage Policy (D.2).
  - "Customer is responsible for all activity under its account" (D.5).
  - Anthropic may suspend if "Customer or any User" violates certain sections (I.3.a).
  - The customer indemnifies for claims arising from its Users' AUP-violating use (K.2).
  - No building "a competing product or service" and no reselling (D.4(a)).
  - "Services under these Terms are not for consumer use" (preamble).
  - The Commercial Terms do not expressly require flowing the AUP into end-user terms. That obligation is practical, through D.2 and K.2.
  - — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (accessed 2026-11-21)
- **Google APIs Terms of Service (last modified 2021-11-09).**
  - "You will require your end users to comply with (and not knowingly enable them to violate) applicable law" (s. 2(a)).
  - Developers must provide a privacy policy (s. 3(d)).
  - No sublicensing an API "for use by a third party," and no API client "that functions substantially the same as the APIs" (s. 4(a)(1)).
  - The developer indemnifies for "your end user's misuse of the APIs" (s. 9(c)).
  - — [Google APIs Terms of Service](https://developers.google.com/terms) (accessed 2026-11-21)
- **Gemini API Additional Terms (effective 2026-03-23).**
  - "You must be 18 years of age or older to use the APIs." There is a bar on API Clients "directed towards or is likely to be accessed by individuals under the age of 18."
  - "you must comply with our Prohibited Use Policy," and "You may not attempt to bypass these protective measures."
  - "You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom."
  - Prompts on unpaid tiers may be used to improve Google products, with human review.
  - — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (accessed 2026-11-21)

### Inferences
- **Flow-down.** The miyagi AUP should incorporate the Anthropic Usage Policy and Google's Generative AI Prohibited Use Policy by reference and link to both. The Commercial Terms make miyagi answerable for users' violations (D.5, K.2), so miyagi needs the contractual right to suspend or terminate users who violate them.
- **Product-specific prohibitions.**
  - Circumventing free-tier caps or rate limits, including multiple accounts or installs, VPN or ID resets, and automation.
  - Accessing, scraping, reverse engineering or reusing the miyagi proxy or API outside the app, and using miyagi as a general LLM relay. This also protects miyagi against the "proxying" and reselling bans and Google's "substantially the same" rule.
  - Jailbreaking or prompt-injecting the coach.
  - Capturing or uploading other people's personal data or confidential employer or school code on screen.
  - Using miyagi on content the user has no right to access.
  - Using miyagi to cheat on graded schoolwork, exams or interviews against the applicable rules.
  - Illegal, harassing or sexual content, and anything prohibited by the provider policies.
  - Interfering with the shared lesson cache, such as poisoning it.
  - Using outputs to train competing models, which mirrors Anthropic D.4(a).
- **Gemini and teen users. This is the most significant provider-term finding.** Using Gemini through the startup's proxy, on the Gemini API (AI Studio) terms, for a product that is "likely to be accessed by" 13–17-year-olds appears to breach the Gemini API Additional Terms on their face. EEA, UK and Swiss users also require paid-tier Gemini usage. This is a provider-compliance issue, not a ToS drafting issue. The options are to route teen traffic to Claude only, to move Gemini to a Google Cloud (Vertex AI) agreement whose terms allow it (not verified), or to get written permission. This needs a lawyer or a provider conversation.

### Gaps
- I did not fetch Google's Generative AI Prohibited Use Policy text or the Google Cloud / Vertex AI service terms. Whether Vertex AI's terms carry the same under-18 restriction is unknown.
- I did not find an explicit clause requiring the customer to impose the Anthropic AUP in its own user terms. The AUP applies to end users directly.

---

## 6. EULA content: license, restrictions, reverse engineering limits, updates, open source, export, termination, beta, feedback, third-party services, Store terms

### Takeaway
A desktop EULA should grant a limited, revocable, non-exclusive, non-transferable personal license, with standard restrictions. Two limits apply: EU law voids bans on certain reverse engineering (Software Directive Arts. 5–6, 8), and US DMCA § 1201(f) permits interoperability reverse engineering. The EULA should cover consent to automatic updates and carve out open-source components. On the Microsoft Store, the publisher's own terms can replace Microsoft's Standard Application License Terms (SALT). Apple's standard EULA covers only App Store distribution, so a direct-download Mac build needs miyagi's own EULA.

### Cited Findings
- **Microsoft Store.** SALT is an agreement "between you and the application publisher," and the publisher is the licensor. In Partner Center's "Additional license terms," a publisher leaves the field blank to use SALT, or enters a single URL or up to 10,000 characters of its own terms. SALT says it applies unless the app comes with separate terms. The US/Canada and EEA versions differ, and the copy found is marked "Updated October 2017." — [Microsoft Store SALT](https://www.microsoft.com/en-AQ/store/standard-application-license-terms); [EEA SALT](https://www.microsoft.com/en-GD/store/standard-application-license-terms-eea); [Partner Center: add additional information](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/add-additional-information) (accessed 2026-11-21; the learn.microsoft.com legal URL in the brief returned 404)
- **Apple** provides a "Licensed Application End User License Agreement" that applies to App Store apps when a developer provides none. — [Apple Standard EULA](https://www.apple.com/legal/internet-services/itunes/dev/stdeula/)† (accessed 2026-11-21)
- **EU Software Directive 2009/24/EC.**
  - Art. 5(1): a lawful acquirer may use and correct errors as needed for intended use, absent specific contract terms.
  - Art. 5(2): a backup copy cannot be prevented by contract.
  - Art. 5(3): a user may observe, study and test the program's functioning.
  - Art. 6: decompilation is allowed where indispensable for interoperability.
  - Art. 8: contract terms contrary to Art. 6 or Art. 5(2)–(3) are null and void.
  - — [Directive 2009/24/EC, EUR-Lex](https://eur-lex.europa.eu/eli/dir/2009/24/oj)† (accessed 2026-11-21)
- **US DMCA, 17 U.S.C. § 1201(f).** Exempts circumvention for reverse engineering to achieve interoperability of an independently created program. US courts have generally enforced contractual reverse-engineering bans (*Bowers v. Baystate Techs.*, 320 F.3d 1317 (Fed. Cir. 2003)†). — [17 U.S.C. § 1201, LII](https://www.law.cornell.edu/uscode/text/17/1201)† (accessed 2026-11-21)
- **Third-party services.** Cursor says it "does not make any representations or warranties with respect to Third-Party Services" (s. 6), and that it "may modify or discontinue all or any portion of the Service at any time" (s. 10). Its terms do not mention auto-updates. — [Cursor Terms](https://cursor.com/terms-of-service) (accessed 2026-11-21)
- **Feedback licenses.** Anthropic: "we may use the Feedback however we choose without any obligation or other payment to you" (s. 5). OpenAI: feedback may be used "without restriction or compensation to you." — [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms); [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) (accessed 2026-11-21)
- **Reverse engineering and automated extraction.** OpenAI bars users from trying to "reverse engineer, decompile or discover the source code" and from "Automatically or programmatically extract[ing] data or Output." — [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) (accessed 2026-11-21)
- **Updates in the EU.** If the DCD applies, the trader must supply updates needed for conformity (Art. 8(2)) and may modify content only under Art. 19 conditions. — [Directive 2019/770](https://eur-lex.europa.eu/eli/dir/2019/770/oj)† (accessed 2026-11-21)

### Inferences
- **EULA skeleton.**
  - Grant: personal, non-commercial, revocable, non-exclusive, non-transferable, to install on devices you own or control.
  - Restrictions: no copying beyond install and backup, no modifying, distributing, renting, circumventing caps or technical measures, accessing the proxy outside the client, or reverse engineering. Each restriction applies "except to the extent applicable law expressly permits despite this limitation," which preserves EU Arts. 5–6 and § 1201(f).
  - Updates: "The app may automatically download and install updates, which may change or remove features; you consent to this; you can stop updates by uninstalling." Do not withhold security fixes.
  - Open source: Electron, Chromium, Node and other OSS components are licensed under their own licenses, which control. Ship the notices with the app (About > Licenses).
  - Export and sanctions: a standard compliance clause; mass-market encryption only.
  - Termination: on breach, or by miyagi on notice. Survival clause.
  - Beta or experimental features: "as is," may change or end, may be less reliable.
  - Third-party services: YouTube, Google sign-in, and AI providers are governed by their own terms, and miyagi is not responsible for them.
- **Store.** If listed on the Microsoft Store, put miyagi's own EULA URL in Partner Center so one set of terms governs on every channel. Otherwise SALT governs Store installs and miyagi's terms govern direct downloads, which is inconsistent. Add a "Store distribution" clause: Microsoft or Apple is not a party, and store-required terms apply where they are mandatory.
- **No Mac App Store.** Apple's standard EULA is irrelevant to a notarized direct-download Mac build.

### Gaps
- I did not fetch SALT's full current text, so I cannot confirm its update, warranty or liability wording.
- I did not research export-control classification (EAR) or YouTube API Services Developer Policies. Those policies require API clients to tell users they are bound by the YouTube Terms of Service, which is relevant only if miyagi uses the YouTube API rather than screen observation.
- I did not research California's auto-renewal law or the status of the FTC Negative Option ("click-to-cancel") rule. They are relevant only when a paid tier launches.

---

## 7. Bring-your-own-key: provider terms on sharing credentials, how BYOK apps phrase responsibility, and the "keys stay on device" representation

### Takeaway
Provider terms cut against sharing keys with third parties:
- Anthropic's consumer terms bar sharing an "Anthropic API key" with anyone.
- Google requires developers to keep credentials confidential and to "prevent and discourage other API Clients" from using them.
- The Gemini API is 18+ only.

BYOK apps manage this by keeping the key on the user's device, calling the provider directly, and making the user responsible for provider charges and terms. miyagi's BYOK should therefore be adult-only (18+), on-device, sent directly to the provider and never through miyagi's proxy, and described accurately.

### Cited Findings
- **Anthropic Consumer Terms (s. 2, effective 2025-10-08).** "You may not share your Account login information, Anthropic API key, or Account credentials with anyone else." Section 3 bars access "through automated or non-human means" except via API key or where permitted. — [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)
- **Anthropic Commercial Terms (effective 2025-06-17)** have no clause expressly permitting or forbidding key sharing. D.5 makes the customer "responsible for all activity under its account" and requires prompt notice of compromise. — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (accessed 2026-11-21)
- **Google APIs ToS s. 4(b) (2021-11-09).** "You will keep your credentials confidential and make reasonable efforts to prevent and discourage other API Clients from using your credentials." Also: "Developer credentials may not be embedded in open source projects." — [Google APIs Terms of Service](https://developers.google.com/terms) (accessed 2026-11-21)
- **Gemini API (2026-03-23).** "You must be 18 years of age or older to use the APIs." EEA, UK and Swiss end users require Paid Services. Unpaid-tier prompts may be used to improve Google products and seen by human reviewers. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (accessed 2026-11-21)
- **TypingMind (terms dated 2026-04-20), s. 6.3.** Where services "require or allow you to provide your own API keys from third-party providers," the user alone is responsible for obtaining, managing and securing the keys under the provider's terms, and for the provider's usage charges. Its FAQ says keys are "stored locally... in your browser," with optional AES encryption. — [TypingMind Terms of Service](https://docs.typingmind.com/security-and-compliance/terms-of-service); [TypingMind FAQ](https://docs.typingmind.com/general-faqs) (accessed 2026-11-21)
- **OpenAI's position** on BYOK appears only in community-forum staff replies, and those conflict. One reply says local on-device storage is acceptable. Others say users may not share keys with BYOK apps. — [OpenAI Community, "OpenAI's 'bring your own key' policy"](https://community.openai.com/t/openais-bring-your-own-key-policy/14538/2) (informal, not terms; accessed 2026-11-21)
- **Cursor's terms (2026-09-03) do not address BYOK.** — [Cursor Terms](https://cursor.com/terms-of-service) (accessed 2026-11-21)

### Inferences
- **Architecture drives the legal position.**
  - If the key is stored in the OS keychain (macOS Keychain / Windows Credential Manager via Electron safeStorage) and requests go straight from the user's machine to api.anthropic.com or the Gemini endpoint, miyagi never receives the key. This is the TypingMind model and the strongest answer to "do not share your key."
  - If BYOK requests pass through miyagi's proxy, the key is shared with a third party. That conflicts with Anthropic's consumer clause and Google s. 4(b), and it makes miyagi a custodian of secrets.
- **Clause content.**
  - (a) BYOK is optional, for users 18+ only, matching Gemini's 18+ rule and Anthropic API eligibility.
  - (b) You must have your own account with the provider and comply with its terms and usage policies.
  - (c) You are solely responsible for all charges on your key and for rate limits.
  - (d) BYOK requests go directly from your device to the provider and are governed by the provider's terms and data policies. Free-tier Gemini keys may allow Google to use prompts, including screen and code content, for training, with human review.
  - (e) miyagi stores the key only on your device in [OS-protected storage] and does not transmit it to miyagi servers. State this only if it is literally true and tested, because it is a factual representation subject to FTC Act § 5 and California UCL/FAL deception claims.
  - (f) miyagi is not liable for charges, key leakage from your device, or provider outages.
  - (g) Revoke the key at the provider if compromised.
- Do not ship any miyagi-owned key in the client binary or repo. Google says developer credentials may not be embedded in open-source projects, and an embedded key is extractable.

### Gaps
- I did not find Anthropic's Console/API sign-up age rule stated in the Commercial Terms. Its "not for consumer use" preamble implies business or adult use, but this was not verified.
- I found no authoritative provider statement permitting third-party desktop clients to hold a user's key. Neither Anthropic nor Google addresses it expressly.

---

## 8. Disputes: governing law, venue, arbitration plus class waiver, McGill, mass arbitration, minors, small claims, opt-out

### Takeaway
Arbitration with a class waiver is common (OpenAI uses it, with a 30-day opt-out, mass-arbitration batching and a small-claims carve-out). It is costly and fragile for a tiny startup:
- The business pays AAA fees, and mass-arbitration fees are large.
- California's 30-day fee-payment statute (§ 1281.98) survives in softened form (Hohenshelt 2025).
- The Ninth Circuit struck a custom mass-arbitration protocol (Heckman 2024).
- McGill bars waiving public injunctive relief.
- Minors can disaffirm (J.R. 2024).

Anthropic's consumer terms and Cursor use courts instead. For an MVP, California courts plus a small-claims option and an informal-resolution step is the simpler, more defensible choice.

### Cited Findings
- **OpenAI (2026-01-01):**
  - Disputes go to "final and binding arbitration."
  - Users can opt out within 30 days of account creation or of an arbitration-terms update.
  - "Class arbitrations, class actions, and representative actions are prohibited."
  - Batching applies when "25 or more claimants represented by the same or similar counsel" file.
  - Small claims are excluded from arbitration.
  - California law governs.
  - — [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) (accessed 2026-11-21)
- **Anthropic consumer (2025-10-08)** has no arbitration clause. Disputes go exclusively to state or federal courts in San Francisco, under California law (s. 13). — [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)
- **Cursor (2026-09-03)** has no arbitration. There is a 30–45-day informal resolution period, then court; Texas law; and individual claims only, with no class or representative actions (ss. 16.1–16.3). — [Cursor Terms](https://cursor.com/terms-of-service) (accessed 2026-11-21)
- **Heckman v. Live Nation**, No. 23-55770 (9th Cir. 2024-10-28). Ticketmaster's arbitration clause, which used New Era ADR's mass-arbitration rules (batching without claimant input, bellwether "precedent," rules "so dense, convoluted and internally contradictory"), was held unconscionable under California law, delegation clause included. The court also held the FAA did not preempt applying *Discover Bank* to those novel procedures. — [9th Cir. opinion](https://cdn.ca9.uscourts.gov/datastore/opinions/2024/10/28/23-55770.pdf)†; [Sidley (2024-10)](https://www.sidley.com/en/insights/newsupdates/2024/10/ninth-circuits-live-nation-decision-evaluates-enforceability-of-mass-arbitration-protocols); [Perkins Coie](https://perkinscoie.com/insights/update/ninth-circuit-rejects-mass-arbitration-rules-backs-california-class-actions) (accessed 2026-11-21)
- **Hohenshelt v. Superior Court**, S284498 (Cal. 2025-08-11, 5–2). CCP § 1281.98, under which the drafting party's failure to pay arbitration fees within 30 days waives arbitration, is not preempted by the FAA. It is read to allow relief from forfeiture where nonpayment is not willful, fraudulent or grossly negligent. Federal decisions holding it preempted (*Belyea v. GreenSky*, 9th Cir.) remain. — [Cal. Supreme Court opinion (Justia PDF)](https://cases.justia.com/california/supreme-court/2025-s284498.pdf)†; [Gibson Dunn (2025-08)](https://www.gibsondunn.com/california-supreme-court-narrowly-construes-statute-governing-the-failure-to-timely-pay-arbitration-fees-to-avoid-federal-preemption/) (accessed 2026-11-21)
- **AAA mass arbitration.** Rules and fee schedules were revised effective 2024-01-15, and the consumer mass schedule applies at 25+ similar demands. A 2024 summary reports flat initiation fees totaling $11,250, replacing per-case filing fees; I could not confirm that figure is current. The 2026 consumer mass-arbitration fee schedule says "the business is responsible for all AAA fees and compensation" referenced. Under the older per-case model, 1,000 claims meant $375,000–$500,000 in business filing fees alone. — [AAA mass arbitration rules page](https://adr.org/rules-forms-and-fees/mass-arbitration/); [AAA 2026 consumer mass arbitration fee schedule (PDF)](https://www.adr.org/media/lvgavfty/2026_consumer-mass-arbitration-feeschedule.pdf); [Mayer Brown (2024-02-05)](https://www.mayerbrown.com/en/insights/publications/2024/02/american-arbitration-association-adopts-new-mass-arbitration-rules-and-fee-schedules); [ABA Business Law Today (2025-03)](https://www.americanbar.org/groups/business_law/resources/business-law-today/2025-march/evolution-of-mass-arbitration/) (accessed 2026-11-21)
- **McGill v. Citibank**, 2 Cal. 5th 945 (2017). A pre-dispute waiver of the right to seek public injunctive relief in any forum is unenforceable under California law. — [McGill v. Citibank, Justia](https://law.justia.com/cases/california/supreme-court/2017/s224086.html)† (accessed 2026-11-21)
- **Minors and arbitration** (section 2): J.R. v. EA (2024) refused to compel arbitration after disaffirmance, while Williams v. Moon Active (2025) and Garcia v. Roblox (2026) compelled it. — see section 2 sources.
- **EU consumers.** Brussels Ia (Reg. 1215/2012) Art. 18 lets consumers sue in their home courts, and Art. 19 limits pre-dispute forum clauses. Rome I (Reg. 593/2008) Art. 6(2): a choice of law cannot deprive a consumer of the mandatory protections of their home law. In *VKI v Amazon* (C-191/15, 2016-07-28), the CJEU held a choice-of-law term unfair where it misleads the consumer into thinking only the chosen law applies. — [Brussels Ia, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2012/1215/oj)†; [Rome I, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2008/593/oj)†; [C-191/15, EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62015CJ0191)† (accessed 2026-11-21)

### Inferences
- **MVP recommendation: no arbitration clause.**
  - California law. Exclusive venue in state or federal courts in the founders' county, or San Francisco, as Anthropic uses.
  - Small-claims court always available.
  - A mandatory 30-day informal-resolution notice before suit, as Cursor does.
  - A jury-waiver clause is generally unenforceable in California pre-dispute contracts. I did not source this; it needs a lawyer.
  - A class-action waiver outside arbitration is likely unenforceable in California for CLRA claims and is a weak protection anyway. Including one is a judgment call for a lawyer.
- **Why not arbitration now.** Mass-arbitration fees fall on the business. § 1281.98 adds fee-deadline traps. Heckman shows custom protocols get struck. Minors may disaffirm. McGill requires carving out public injunctive relief. Drafting has to be very careful to survive. If miyagi adds arbitration later with a paid tier, copy OpenAI's structure:
  - AAA or JAMS consumer rules.
  - A 30-day opt-out, renewed on changes.
  - A small-claims carve-out.
  - A McGill-compliant severance of public-injunction claims to court.
  - Bellwether or batching aligned with the institution's own mass-arbitration rules, not a bespoke protocol.
  - A fresh clickwrap for existing users.
- **EU/UK.** State that consumers keep their home-country mandatory protections and their right to sue at home. This avoids a VKI-style unfairness finding.

### Gaps
- I did not verify current AAA and JAMS consumer filing-fee amounts for single cases.
- I did not check whether the EU ODR-platform link requirement has ended. My understanding is that Regulation (EU) 2024/3228 closed the platform on 2025-07-20; this was not verified.

---

## 9. User content and the shared lesson cache: license from users, no-training statement, who owns derived lessons, DMCA

### Takeaway
Reputable AI terms let users keep their inputs and assign them whatever rights exist in outputs. API providers do not train on API customer content: Anthropic commercial says so, and Google says the same for paid Gemini only. miyagi needs a narrow, purpose-limited license to process screen and code content to run the service. It also needs a clear statement that lessons generated from public videos and shared across users are miyagi's service content, licensed to all users, and do not belong to any single user. A DMCA agent and notice procedure protects the shared cache.

### Cited Findings
- **Users keep their inputs; outputs are assigned to them.** OpenAI: users retain rights in Input and OpenAI assigns rights in Output. Anthropic consumer: users retain Inputs and Anthropic assigns rights in Outputs, but may train on consumer Materials unless the user opts out. — [OpenAI Terms of Use (2026-01-01)](https://openai.com/policies/row-terms-of-use/); [Anthropic Consumer Terms (2025-10-08)](https://www.anthropic.com/legal/consumer-terms) (accessed 2026-11-21)
- **Shared outputs.** Cursor says no rights pass to the user in suggestions given to other customers (s. 1.4). This is a model for "shared lessons are not exclusively yours." — [Cursor Terms (2026-09-03)](https://cursor.com/terms-of-service) (accessed 2026-11-21)
- **Provider training rules.** Anthropic commercial: "Anthropic may not train models on Customer Content from Services." Gemini API: unpaid-service content is used "to provide, improve, and develop Google products and services" with human review, while for paid services "Google doesn't use your prompts" to improve products. — [Anthropic Commercial Terms (2025-06-17)](https://www.anthropic.com/legal/commercial-terms); [Gemini API Additional Terms (2026-03-23)](https://aistudio.google.com/docs/terms) (accessed 2026-11-21)
- **FTC.** Later expanding data use (for example, to AI training) through a quiet retroactive terms change may be unfair or deceptive. — [FTC (2024-02-13)](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/ai-other-companies-quietly-changing-your-terms-service-could-be-unfair-or-deceptive)†; [Consumer Finance Monitor](https://www.consumerfinancemonitor.com/2024/02/28/ftc-warns-quietly-changing-privacy-policies-may-be-an-unfair-or-deceptive-practice/) (accessed 2026-11-21)
- **Copyright Office.** Purely AI-generated material is not copyrightable without sufficient human authorship. — [U.S. Copyright Office, Copyright and AI Part 2: Copyrightability (Jan. 2025)](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)† (accessed 2026-11-21)
- **DMCA safe harbor, 17 U.S.C. § 512(c).** Requires a designated agent registered with the Copyright Office, a notice-and-takedown process, and a repeat-infringer policy (§ 512(i)). — [17 U.S.C. § 512, LII](https://www.law.cornell.edu/uscode/text/17/512)†; [Copyright Office DMCA Designated Agent Directory](https://www.copyright.gov/dmca-directory/)† (accessed 2026-11-21)

### Inferences
- **User content license.** A non-exclusive, worldwide, royalty-free license, limited to operating, securing and improving the service, covering capture, transmission to AI providers as subprocessors, grading and display. It ends when content is deleted, except for backups and legal holds.
- **No-training statement.** Say only what is true across every path:
  - Neither miyagi nor its AI providers train on your screen or code from the miyagi proxy. That holds for Anthropic commercial, and for Gemini only on paid tiers.
  - BYOK traffic follows your own provider terms. Free Gemini keys may be used for training.
  - Do not say "never" if the proxy uses unpaid Gemini.
- **Shared cache.**
  - Lessons, labs, rubrics and tests generated from public videos are miyagi Service Content, licensed to every user under the EULA. Users get no ownership.
  - Cached lessons must not contain a user's own code or screen data. That is an engineering requirement as much as a legal one: keep a per-user layer separate from the shared layer.
  - To the extent any rights exist in AI-generated lessons, miyagi claims them, recognizing they may be thin under the Copyright Office's January 2025 view.
  - miyagi respects video creators' rights and removes lessons on valid notice.
- **DMCA.** Register an agent (this requires a legal name and address, so do it once an entity exists or use a registered agent). Publish a notice and counter-notice procedure and a repeat-infringer policy. Whether summarizing or deriving lessons from third-party YouTube videos is fair use is a copyright question for other researchers or a lawyer.

### Gaps
- I did not research fair use of tutorial-derived lessons, YouTube ToS limits on automated access or derivation, or whether miyagi's capture of YouTube content triggers the YouTube API policies.
- I did not verify the current DMCA agent fee or renewal period.

---

## Implications for miyagi

Clause-by-clause drafting recommendations. "Lawyer: yes" means a lawyer should review it before launch, with the reason given.

1. **Parties and entity.** Name the contracting party. Without an LLC, the founders personally are the counterparty and personally exposed, and they are themselves minors who can disaffirm their own contracts, including provider and vendor agreements. Form the LLC before the Terms go live and before signing provider commercial terms. **Lawyer: yes.** Entity formation, and whether minors can be members or managers in California, decide who is liable.
2. **Acceptance screen (first run).**
   - An unchecked box plus a "Continue" button disabled until checked. Or an "I agree" button with the advisal directly above: "By clicking 'I agree', you agree to the miyagi Terms of Service and EULA."
   - Blue, underlined links that open the full text. Body-size, high-contrast text. Nothing pre-checked, no clutter.
   - Log version, hash, timestamp, install or account ID, app version and an archived screen.
   - Follows Berman, Chabolla and Godun. **Lawyer: no.** Design pattern only; have counsel glance at the final screen.
3. **Age and parent consent.**
   - Block under-13s (COPPA is covered by other researchers).
   - For 13–17, a parent or guardian must accept the Terms as a party, on their own behalf and the minor's, through a separate parent step such as email confirmation.
   - Add a "benefits retained or account ends on disaffirmance" clause.
   - Assume arbitration, the cap and waivers may not bind the minor (J.R. v. EA).
   - **Lawyer: yes.** Unsettled law on parental binding of minors' claims, and the interaction with privacy and age-assurance laws.
4. **Changes to terms.**
   - Material changes: in-app notice at least 30 days ahead, with a summary and re-acceptance clickwrap.
   - Any expansion of data use or AI training: fresh opt-in only, never retroactive (FTC 2024).
   - EU/UK: list valid reasons for changes and the right to terminate.
   - Avoid "continued use equals acceptance" as the only mechanism.
   - **Lawyer: no** for the US mechanism. **Yes** for the EU/UK wording (UCTD Annex 1(j), DCD Art. 19).
5. **AI output and grading disclaimer.**
   - AI-generated lessons, grades and coaching may be inaccurate or incomplete. Verify before relying on them.
   - They are not professional, academic or career advice.
   - Grades are practice feedback, not a certification, credential or school grade.
   - The written Terms and product pages control over anything the AI says about price, features or policies (Moffatt).
   - Disclose that the coach is an AI. This is required by the Anthropic minors guidelines and Anthropic Commercial Terms D.3.
   - Avoid certificates and credential claims, which would trigger the Anthropic AUP "Education and credentials" high-risk duties.
   - **Lawyer: no.** Standard pattern; keep the language plain for teens.
6. **Acceptable Use Policy.**
   - Incorporate the Anthropic Usage Policy and Google Generative AI Prohibited Use Policy by link.
   - Prohibit:
     - cap and rate-limit circumvention and multi-accounting
     - using the proxy outside the app, scraping it, or treating it as an LLM relay
     - reverse engineering the proxy protocol
     - jailbreaks and prompt injection
     - capturing other people's personal or confidential data
     - cheating on graded schoolwork against school rules, or submitting AI-assisted work without required attribution
     - illegal, harassing or sexual content
     - cache poisoning
     - training competing models on outputs
   - Reserve suspension and termination rights.
   - **Lawyer: no.**
7. **Provider compliance (operational, not drafting).**
   - The Gemini API terms (2026-03-23) require users to be 18+, bar API clients "likely to be accessed by" under-18s, and require paid services for EEA, UK and Swiss users.
   - Before launch to teens, either route minors to Claude only or move Gemini to a Google Cloud/Vertex agreement that permits it.
   - Implement the Anthropic minors safeguards and post a public compliance statement.
   - **Lawyer: yes.** Breach risks losing API access, and indemnities flow to miyagi.
8. **Bring-your-own-key.**
   - Adults (18+) only.
   - The key is stored in OS-protected storage on the device. Calls go directly from the device to the provider, never through miyagi's proxy.
   - The user must have their own provider account and follow its terms. The user pays all provider charges. BYOK data follows the provider's policies, including possible training on free Gemini keys.
   - miyagi is not liable for key misuse on the user's device.
   - Make the "keys never leave your device" statement only if engineering confirms it, since it is a factual representation subject to FTC and UCL deception claims.
   - **Lawyer: no** for the drafting. **Yes** if any BYOK traffic touches the proxy.
9. **License to user content and no-training promise.**
   - A narrow, purpose-limited license to capture and process screen and code content to run the service, via named AI providers as subprocessors.
   - No-training statement scoped to what is true: Anthropic commercial does not train, and Gemini does not train only on paid tiers.
   - Users keep their code. miyagi assigns any rights it has in their personal outputs.
   - **Lawyer: no** for the drafting, but cross-check with the privacy policy owners.
10. **Shared lesson cache.** Generated lessons, labs, rubrics and tests are miyagi Service Content licensed to all users. Users get no ownership. User code and screen data never enter the shared cache. miyagi removes lessons on rights-holder notice. **Lawyer: yes** for the underlying copyright and fair-use question of deriving lessons from creators' videos; the contract clause itself is simple.
11. **DMCA section.** Notice, counter-notice and repeat-infringer policy. Register a Copyright Office agent once an entity and address exist. **Lawyer: no**, except for choosing who serves as agent.
12. **EULA.**
    - A limited, revocable, non-exclusive, non-transferable license.
    - Restrictions, each with "except as applicable law permits" to preserve EU Software Directive Arts. 5–6 and DMCA § 1201(f).
    - Automatic-update consent, without withholding security fixes.
    - An open-source carve-out, with notices shipped in the app.
    - Export and sanctions, termination and survival, beta features "as is," and a feedback license (as Anthropic and OpenAI have).
    - A third-party services disclaimer (YouTube, Google sign-in, AI providers).
    - A Store clause.
    - On the Microsoft Store, enter miyagi's EULA URL in Partner Center "Additional license terms" so SALT does not govern instead. Apple's standard EULA does not apply to a direct-download Mac app.
    - **Lawyer: no.** Standard pattern.
13. **Warranty disclaimer.**
    - Conspicuous (bold or caps heading): "as is," "as available," naming merchantability, fitness for a particular purpose and non-infringement (Com. Code § 2316 style).
    - Avoid the bare "some jurisdictions do not allow..." sentence (NJ TCCWNA § 56:12-16). Use "to the fullest extent permitted by law" and a short New Jersey/UK/EU statement.
    - **Lawyer: yes, briefly.** TCCWNA wording and the UK/EU mandatory-rights statement.
14. **Limitation of liability.**
    - Cap at the greater of $100 and fees paid in the prior 12 months, the market norm (OpenAI, Anthropic, Cursor).
    - Exclude indirect and consequential damages.
    - Carve-outs: fraud, willful misconduct, violation of law (Civ. Code § 1668). In the UK/EU, death or personal injury from negligence, gross negligence, and non-excludable statutory rights.
    - Do not purport to waive CLRA rights (§ 1751).
    - **Lawyer: yes.** Unconscionability and § 1668 limits, plus a paid tier would bring in the CLRA.
15. **Disputes.**
    - MVP: no arbitration. California law. Exclusive venue in California state or federal courts (founders' county or San Francisco), with small claims always allowed. A 30-day informal-resolution notice first.
    - EU/UK consumers keep home-country mandatory protections and courts (Rome I Art. 6, Brussels Ia Art. 18, VKI v Amazon).
    - Revisit arbitration only with a paid tier and counsel, using the OpenAI structure: 30-day opt-out, small-claims carve-out, a McGill public-injunction carve-out, institutional mass-arbitration rules, and re-acceptance.
    - **Lawyer: yes.** Class-waiver enforceability outside arbitration, jury-waiver limits, and any later move to arbitration.
16. **Avoid entirely.**
    - Browsewrap (terms only in a menu or footer).
    - Pre-checked boxes.
    - Advisals that don't name the action.
    - Non-disparagement or review-gag clauses, which are void under Cal. Civ. Code § 1670.8† and 15 U.S.C. § 45b† (not fetched this session).
    - Bespoke mass-arbitration protocols (Heckman).
    - Promising "never" on training or data uses that any provider path contradicts.
    - Letting the AI coach make commitments on price or features.
    - **Lawyer: no.**
