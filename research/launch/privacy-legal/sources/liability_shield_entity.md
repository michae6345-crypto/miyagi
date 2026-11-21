# Liability shields for miyagi: who can be sued today, what an entity does and does not protect, veil piercing, minors' and parents' personal exposure (status 2026-11-21)

Scope note. This builds on the earlier pass in `../Miyagi legal and privacy risks/` (especially `platforms_business_setup.md` §4 on minors' contracts, formation fees, CUTMA and EIN, and `terms_eula_enforceability.md` on vendor flow-down clauses). Those points are not repeated except where needed to connect them to liability. All California statute text comes from California.Public.Law, which mirrors leginfo and shows "Verified: Nov. 16, 2026" on each page fetched. Leginfo itself returns HTTP 403 to automated fetches. Justia case pages also returned 403, so case text came from Stanford SCOCAL, a firm-hosted PDF of the opinion, or (where marked "via search result") secondary summaries. This is research, not legal advice.

---

## 1. With no entity, who can be sued for the app's harms, and can minors be sued and have judgments enforced against them?

### Takeaway
Two people who run a business together "for profit" are a general partnership by default, whether or not they meant to form one. Each partner is then jointly and severally liable for all partnership obligations, though partnership assets must usually be exhausted first. Separately, each founder is personally liable for his own torts: a minor "is civilly liable for a wrong done by the minor", and disaffirming a contract does not undo tort liability. A minor is sued through a guardian ad litem. A money judgment lasts 10 years and can be renewed for another 10, so a judgment entered against a 16-year-old could follow him well into his thirties.

### Cited Findings
**Default partnership**
- **Partnership formation (Cal. Corp. Code §16202(a)).** "the association of two or more persons to carry on as coowners a business for profit forms a partnership", "whether or not the persons intend to form a partnership." Under (c)(3), a person who receives a share of a business's profits "is presumed to be a partner". Section text last updated Jan. 1, 1997. — [Cal. Corp. Code §16202 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_16202), accessed 2026-11-21
- **Joint and several liability (§16306).** Under (a), partners are liable "jointly and severally for all obligations of the partnership" unless the claimant agreed otherwise or a law provides otherwise. Under (b), a newly admitted partner is not personally liable for obligations incurred before admission. Under (c), partners in a *registered limited liability partnership* are not liable merely because they are partners. (A registered LLP is not something a software startup can normally use in California. That point is inference, not checked this pass.) — [Cal. Corp. Code §16306 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_16306), accessed 2026-11-21
- **Suing partners, and the exhaustion rule (§16307).**
  - A partnership "may sue and be sued in the name of the partnership" (a).
  - A plaintiff may sue the partnership and any or all partners, in the same action or separately (b).
  - "A judgment against a partnership is not by itself a judgment against a partner" (c).
  - Under (d), a creditor generally cannot levy on a partner's personal assets for a partnership claim unless one of these applies: a partnership writ came back unsatisfied; the partnership is in bankruptcy; the partner agreed to waive exhaustion; a court allows it because partnership assets are clearly insufficient; or liability is imposed on the partner "by law or contract independent of the partnership", which covers the partner's own torts.
  - — [Cal. Corp. Code §16307 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_16307), accessed 2026-11-21

**Minors as defendants**
- **Minors' tort liability (Fam. Code §6600).** "A minor is civilly liable for a wrong done by the minor, but is not liable in exemplary damages unless at the time of the act the minor was capable of knowing that the act was wrongful." — [Cal. Fam. Code §6600 (verified Nov. 16, 2026)](https://california.public.law/codes/family_code_section_6600), accessed 2026-11-21
- **How a minor appears in court (Code Civ. Proc. §372(a)(1)).** A minor "shall appear either by a guardian or conservator of the estate" or by "a guardian ad litem appointed by the court in which the action or proceeding is pending." Under (d), a proposed guardian ad litem must disclose conflicts and any familial or affiliate relationship with a party. Last updated Jan. 1, 2023. — [Cal. Code Civ. Proc. §372 (verified Nov. 16, 2026)](https://california.public.law/codes/code_of_civil_procedure_section_372), accessed 2026-11-21

**How long a judgment lasts**
- **Ten-year life (CCP §683.020).** "upon the expiration of 10 years after the date of entry of a money judgment", "The judgment may not be enforced", enforcement "shall cease", and liens are "extinguished". — [Cal. Code Civ. Proc. §683.020 (verified Nov. 16, 2026)](https://california.public.law/codes/code_of_civil_procedure_section_683.020), accessed 2026-11-21
- **Renewal (CCP §683.120).** Filing a renewal application "extends the period of enforceability of the judgment as renewed for a period of 10 years" from filing (b). For the category of judgments defined in §683.110(c), renewal is allowed only once and for "a period of five years" (c). Last updated Jan. 1, 2023. — [Cal. Code Civ. Proc. §683.120 (verified Nov. 16, 2026)](https://california.public.law/codes/code_of_civil_procedure_section_683.120), accessed 2026-11-21

**Contracts (from the earlier pass)**
- **Minors' contracts.** A minor's contract can be disaffirmed before 18 or within a reasonable time after (§§6700, 6710). This is a contract defense only; §6600 above governs torts. — [Cal. Fam. Code §6710](https://california.public.law/codes/family_code_section_6710), accessed 2026-11-21; details in `platforms_business_setup.md` §4

### Inferences
- **Partnership status today.** With no entity, miyagi is most likely a California general partnership between the two founders: they co-own and co-run it, and they plan to commercialize. A free app with no revenue yet may still be a "business for profit" if the plan is to make money later. That is a fact question this pass did not resolve. If it is *not* a partnership, each founder is simply an individual operator, and that is no better: each is still personally liable for his own torts under §6600.
- **Who is exposed for a privacy or data harm.**
  - The founder who wrote or deployed the code can be sued personally for negligence or a statutory violation. That is liability "independent of the partnership" under §16307(d), so the plaintiff need not exhaust partnership assets.
  - The other founder can be reached jointly and severally for partnership obligations under §16306, after exhaustion.
  - Disaffirmance (Fam. Code §6710) helps against *contract* claims, such as vendor bills or EULA-based claims. It does not help against tort or statutory claims.
- **How long a judgment can follow a founder.** A judgment entered in 2027 against a 16-year-old stays enforceable to 2037. If renewed, it lasts to 2047 (§§683.020, 683.120), unless it falls in the §683.110(c) once-only category.
- **Exemplary damages.** Punitive damages against a minor need proof he could know the act was wrongful (§6600). Teen founders who knowingly ignore a known privacy defect would likely meet that test.

### Gaps
- §683.110(c) was not opened, so it is unverified which judgments get only one 5-year renewal. From memory it targets certain consumer-debt and medical-debt judgments; verify before relying on it.
- No source was found on whether a minor partner can disaffirm personal liability for partnership debts while losing his capital contribution (the common-law rule in some states).
- Not researched: California's unincorporated association statutes (Corp. Code §18000 et seq.) as an alternative to partnership characterization for a no-profit project.
- Bankruptcy dischargeability of a judgment against a founder (for example, the willful-and-malicious-injury exception) was not researched.

---

## 2. What is the parents' personal exposure: parental liability statutes, negligent supervision, and above all signing vendor contracts in a parent's name?

### Takeaway
Statutory parental liability (Civ. Code §1714.1) is narrow. It requires the minor's *willful misconduct*, and it is capped at about $56,400 per tort (2025 adjustment), with personal-injury liability limited to medical, dental and hospital costs. Negligent-supervision liability requires a parent to know of the child's *specific* dangerous propensity and to have a chance to control it. The much larger parental risk is contractual. If a parent opens the Anthropic, Google Cloud, Supabase, Render, Apple or Microsoft accounts in their own name, the parent is "you" or "Customer". The parent then personally owes fees and broad indemnities, some of them uncapped. These include Anthropic K.2, which has no cap, and Apple §10, which expressly covers end-user claims about "age-inappropriate, bullying, addictive" or harmful content. The fix is to have an entity be the contracting party, with the parent clicking "on behalf of" the entity as its manager or officer.

### Cited Findings
**Statutory parental liability**
- **Civ. Code §1714.1(a).**
  - Trigger: "Any act of willful misconduct of a minor that results in injury or death to another person" or injury to property.
  - The misconduct is "imputed to the parent or guardian having custody and control of the minor for all purposes of civil damages", and the parent is "jointly and severally liable with the minor".
  - The statutory figure is "twenty-five thousand dollars ($25,000) for each tort". For injury to a person, imputed liability is "further limited to medical, dental and hospital expenses".
  - Subdivision (c) requires an adjustment "every two years by the Judicial Council" using the California CPI.
  - Section last updated Jan. 1, 2008.
  - — [Cal. Civ. Code §1714.1 (verified Nov. 16, 2026)](https://california.public.law/codes/civil_code_section_1714.1), accessed 2026-11-21
- **Current adjusted cap.** The Judicial Council set the §1714.1(a)/(b) limit at **$56,400 per tort effective July 1, 2025**, up from $52,700. The next adjustment is due by July 1, 2027. — [Judicial Council, California Rules of Court amendments effective July 1, 2025 (Appendix B) (adopted Mar. 26, 2025)](https://courts.ca.gov/system/files/rules-court/2025-03-26-rules-effective-07-01-2025.pdf), via search result, accessed 2026-11-21
  - Ambiguity: it is unclear whether the separate medical-expense sub-limit in (a) is also indexed or stays at $25,000. Sources summarized in search results differ.
- **Civ. Code §1714.3** covers parental liability for a minor's discharge of a firearm and is not relevant here. — [Shouse Law Group summary (undated)](https://www.shouselaw.com/ca/personal-injury/vicarious-liability/parental-liability), via search result, accessed 2026-11-21

**Negligent supervision (common law)**
- **CACI No. 428 (Parental Liability, nonstatutory).** A parent who did not witness the conduct may be liable if the parent knew of the child's dangerous propensity or habit and negligently failed to control it. — [CACI No. 428 (Justia mirror, undated)](https://justia.com/trials-litigation/docs/caci/400/428), via search result, accessed 2026-11-21
- **Specific-propensity requirement.** General knowledge that a child misbehaves is not enough; the parent must know of the specific type of behavior that caused the injury. California follows Restatement (Second) of Torts §316. — [Plaintiff Magazine, "Bad parenting does not always equal tort liability" (July 2013)](https://plaintiffmagazine.com/recent-issues/item/bad-parenting-does-not-always-equal-tort-liability), via search result, accessed 2026-11-21. That article discusses *Robertson v. Wentz* (1986) 187 Cal.App.3d 1281 ([Justia](https://law.justia.com/cases/california/court-of-appeal/3d/187/1281.html)) and *Poncher v. Brackett* (1966) 246 Cal.App.2d 769 ([Justia](https://law.justia.com/cases/california/court-of-appeal/2d/246/769.html)). Opinions not opened.
- **Timing of knowledge.** The knowledge need not have existed for any set time, as long as it came early enough to allow reasonable restraining measures. — [*Costello v. Hart* (1972) 23 Cal.App.3d 898](https://law.justia.com/cases/california/court-of-appeal/3d/23/898.html), via search result, accessed 2026-11-21
- **Online analog (Georgia, persuasive only).** In *Boston v. Athearn* (Ga. Ct. App. Oct. 10, 2014), 329 Ga. App. 890, a seventh-grader built a fake, defamatory Facebook profile of a classmate.
  - The court let a jury decide whether his parents were negligent in failing to make him remove it *after they were notified*.
  - It did not hold them liable for his creating it.
  - — [Eric Goldman, Technology & Marketing Law Blog (Nov. 2014)](https://blog.ericgoldman.org/archives/2014/11/are-parents-liable-for-their-childrens-online-pranks-boston-v-athearn.htm); [ABA Journal (Oct. 2014)](https://www.abajournal.com/news/article/parents_could_be_liable_for_seventh_graders_fake_facebook_page_about_classm), via search result, accessed 2026-11-21

**When an agent becomes personally liable**
- **Civ. Code §2343.** "One who assumes to act as an agent is responsible to third persons as a principal" only in these cases (the statute's words are "in no others"):
  1. "When, with his consent, credit is given to him personally in a transaction";
  2. when he signs a written contract in the principal's name "without believing, in good faith, that he has authority to do so";
  3. "When his acts are wrongful in their nature."
  - — [Cal. Civ. Code §2343 (verified Nov. 16, 2026)](https://california.public.law/codes/civil_code_section_2343), accessed 2026-11-21

**Vendor contracts: who is "you" and what "you" indemnify**
- **Anthropic Commercial Terms (effective Jun. 17, 2025).** — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), accessed 2026-11-21
  - The Customer is "the organization, company, or other entity that you represent". You may not bind an entity unless "you have the legal authority to bind that entity."
  - K.2: "Customer will defend Anthropic and its personnel, successors, and assigns from and against any Anthropic Claim". This covers third-party claims related to Customer's or Users' "Inputs or other data provided by Customer" and "(b) use of the Services in violation of the Usage Policy". Customer also pays resulting judgments and approved settlements.
  - L.3: the liability caps "do not apply to either party's obligations under Section K (Indemnification)". **The customer indemnity is uncapped.**
  - Law: California for non-EEA, Swiss or UK customers; venue in California courts, with arbitration in San Francisco.
- **Google APIs Terms of Service (last modified Nov. 9, 2021).** — [Google APIs Terms of Service](https://developers.google.com/terms), accessed 2026-11-21
  - §1(b): accepting for an entity means "you have authority to bind that entity", and "you" then means the entity.
  - Indemnity: "if you are a business, you will defend and indemnify Google, and its affiliates, directors, officers, employees, and users" against third-party claims arising from misuse of the APIs by you or end users, violations of the Terms by you or end users, and content or data sent through the APIs.
  - Google's own liability is capped at six months of fees. The text does not expressly say whether the developer's indemnity is capped.
  - Law and venue: California law; "LITIGATED EXCLUSIVELY IN THE FEDERAL OR STATE COURTS OF SANTA CLARA COUNTY".
- **Supabase Terms (version date not shown on page).** — [Supabase Terms](https://supabase.com/terms), accessed 2026-11-21
  - The person accepting warrants authority to bind an organization, and also agrees "YOU ... ACCEPT THIS AGREEMENT AND AGREE THAT YOU ARE LEGALLY BOUND BY ITS TERMS."
  - §10(b): Customer indemnifies Supabase against third-party claims that Customer Data or AI Input infringes "US intellectual property or other rights", and claims "based on Customer's or any Authorized User's" negligence, willful misconduct or unauthorized use.
  - Customer is responsible for all uses resulting from access it provides and is liable for Authorized Users' acts.
  - §11 caps liability at 12 months of fees, but the cap excludes indemnity obligations. For excluded claims Supabase's own cap is three times that amount.
- **Render.** The full text did not render for automated fetch, so this is from search snippets only:
  - The account holder agrees "to indemnify Render in accordance with Section 10" for claims arising from third-party tools using the account — [Render Terms of Service](https://render.com/terms), via search result, accessed 2026-11-21.
  - The DPA requires the customer to indemnify Render Services, Inc. for providing personal data improperly — [Render DPA](https://render.com/dpa), via search result, accessed 2026-11-21.
  - Revised terms took effect July 10, 2026 — [Render terms update](https://render.com/terms-update), via search result, accessed 2026-11-21.
- **Apple Developer Program License Agreement (web version, no date shown; latest dated PDF found in the earlier pass is 20251008).** — [Apple DPLA](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/), accessed 2026-11-21
  - "You" means "the person(s) or legal entity ... that has accepted this Agreement under its own developer account".
  - §10 indemnity runs from the developer to Apple against "any and all claims, losses, liabilities, damages, taxes, expenses and costs" arising from:
    - (i) breach of any representation or warranty;
    - (ii) infringement claims;
    - (iii) EULA breaches;
    - (iv) Apple's permitted delivery of the app;
    - (v) end-user or third-party claims about "age-inappropriate, bullying, addictive, violent, or otherwise harmful content";
    - (vi) "Your use ... of the Apple Software or Services";
    - (vii) MDM claims.
  - The indemnity excludes "any Application for macOS that is distributed outside of the App Store and does not use any Apple Services or Certificates."
  - §13 caps Apple's liability to the developer at "fifty dollars ($50.00)".
- **Microsoft Services Agreement (published Jul. 30, 2026; effective Sept. 30, 2026).** A parent of a minor accountholder agrees to be bound and is "responsible for all use of the Microsoft account or Services" (quoted in the earlier pass). — [Microsoft Services Agreement](https://www.microsoft.com/en-us/servicesagreement), accessed 2026-11-21

**Contracts made before the company exists (promoter liability)**
- A person who contracts for a not-yet-formed corporation stays personally liable even after the corporation adopts the contract, unless there is a novation (a three-way agreement releasing the promoter). This is from a 1931 California Court of Appeal decision summarized in search results (case name not shown) and a bar-prep guide. Both are low-quality, secondary sources. — [Hall Approved summary of 1931 Cal. Ct. App. case](https://hallapproved.com/ca/cases/appeals/1931/3296136/); [Open Exam Prep, CA Bar business associations guide (undated)](https://open-exam-prep.com/study-guides/ca-bar/business-associations/corp-formation), via search result, accessed 2026-11-21

### Inferences
- **Statutory parental liability.** §1714.1 is unlikely to be the main risk. A data leak or bad AI coaching would usually be negligence, not "willful misconduct". Even when it applies, it is capped at $56,400 per tort.
- **Negligent supervision.** The risk is low unless a parent learns of a specific harmful practice and does nothing. *Athearn* shows that notice, followed by failure to act, is the danger point. Practical rule: if a parent learns of a data leak, a minor-safety failure or a takedown demand, it should be fixed promptly and documented.
- **Vendor contracts are the real parental risk.** If a parent signs up individually, the parent is the "Customer" or "you":
  - §2343(1) applies (credit "given to him personally"), and there is no disclosed entity principal to shift liability to.
  - Every indemnity above then runs against the parent's personal assets. Anthropic's is uncapped (L.3). Supabase's sits outside its cap. Apple's §10(v) covers end-user content-harm claims, which matters for a teen-facing app. Apple's (vi) reaches any use of Apple Software or Services.
  - Apple's carve-out probably does **not** help miyagi. A Developer ID-signed, notarized Mac app uses Apple "Certificates" (inference from the clause wording).
- **A parent who opens accounts now is a promoter.** The parent stays liable on those accounts until each vendor agrees to transfer them to the entity, or the parent closes them and the entity opens fresh ones. Simply "adopting" the accounts after formation does not release the parent (secondary sources above).
- **The limit.** Once the entity holds the accounts and the parent clicks "on behalf of [Entity]" with authority, the parent is an agent of a disclosed principal. Under §2343 the parent is then not personally liable, except for the parent's own wrongful acts.

### Gaps
- The Microsoft App Developer Agreement (Partner Center) indemnity clause was not retrieved this pass.
- Render's §10 indemnity text was not retrieved; only snippets were.
- GitHub's Terms for organization accounts were not researched.
- Whether Google's developer indemnity is capped is not stated in the Terms text retrieved.
- No modern California appellate case on promoter liability was located. The 1931 case name was not visible.
- Whether vendors allow transferring an individual account to an entity was not checked. Apple's and Microsoft's Individual-to-Company paths are covered in the earlier pass (Microsoft: Individual accounts cannot be converted).

---

## 3. LLC vs C-corp: scope of the shield, what it does not cover, California veil piercing, the habits that prevent it, and whether single-member or parent-managed LLCs are pierced more

### Takeaway
California LLCs and corporations both make the entity's debts its own. Neither protects anyone from their own torts, their own guarantees or contracts, trust-fund payroll taxes, or alter-ego piercing. California pierces only when two things are both shown: (1) a unity of interest so the separate personalities "do not in reality exist", and (2) an inequitable result. Being hard to collect from is not enough. For a teen-run startup, the California LLC has one concrete advantage: failure to hold meetings or observe formalities "shall not be considered a factor" in LLC alter-ego analysis, unless the LLC's own documents require meetings. *Greenspan v. LADT* shows a non-owner *manager* can be added as an alter-ego judgment debtor. That is directly relevant if a parent manages an LLC whose units are held for the kids.

### Cited Findings
**What the statutes shield**
- **California LLC shield (Corp. Code §17703.04).** — [Cal. Corp. Code §17703.04 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_17703.04), accessed 2026-11-21
  - (a): the LLC's liabilities "are solely the debts, obligations, or other liabilities of the limited liability company". They do not become a member's or manager's "solely by reason of the member acting as a member or manager acting as a manager".
  - (b): a member "shall be subject to liability under the common law governing alter ego liability", the same as a corporate shareholder. But "the failure to hold meetings of members or managers or the failure to observe formalities ... shall not be considered a factor tending to establish" alter ego, "where the articles of organization or operating agreement do not expressly require the holding of meetings".
  - (c): the shield does not affect a member's liability "to third parties for the member's participation in tortious conduct or pursuant to the terms of a written guarantee or other contractual obligation entered into by the member, other than an operating agreement."
  - (e): a member may agree to be personally obligated, but only in the articles or a written operating agreement "that specifically references this subdivision".
- **Delaware LLC shield (6 Del. C. §18-303).** (a): obligations are "solely the debts, obligations and liabilities of the limited liability company". A member or manager is not liable solely because of that role. (b): a member or manager "may agree to be obligated personally". — [6 Del. C. ch. 18, subch. III](https://delcode.delaware.gov/title6/c018/sc03/index.html), accessed 2026-11-21

**Directors' and officers' own torts**
- ***Frances T. v. Village Green Owners Assn.* (1986) 42 Cal.3d 490.** — [Stanford SCOCAL](https://scocal.stanford.edu/opinion/frances-t-v-village-green-owners-assn-28425), accessed 2026-11-21
  - "Directors are liable to third persons injured by their own tortious conduct" (p. 504).
  - A director is immune "unless he authorizes, directs, or in some meaningful sense actively participates" in the wrong (p. 504).
  - Directors "do not incur personal liability for torts of the corporation merely by reason of their official position" (p. 507).
  - Liability can attach where "they knew that a condition or instrumentality under their control posed an unreasonable risk of injury" and failed to act (p. 510).

**The alter-ego test**
- ***Automotriz Del Golfo De California v. Resnick* (1957) 47 Cal.2d 792.** This is the source of the two-part test (p. 796). The corporation's capital was "'trifling compared with the business to be done and the risks of loss'" (p. 797), and inadequate capitalization plus active participation supported piercing. Pin cites are from later cases quoting it. — [Stanford SCOCAL](https://scocal.stanford.edu/opinion/automotriz-etc-de-california-v-resnick-26786), via search result, accessed 2026-11-21
- ***Sonora Diamond Corp. v. Superior Court* (2000) 83 Cal.App.4th 523, 538–539.** Points as quoted in secondary summaries; verify against the opinion:
  - Both unity of interest and an inequitable result are required.
  - Factors include commingling, identical equitable ownership, use of the same offices and employees, inadequate capitalization, disregard of formalities, and identical directors and officers. "Stock ownership alone is not enough."
  - "[d]ifficulty in enforcing a judgment or collecting a debt does not satisfy this standard."
  - Alter ego is an extreme remedy, used sparingly.
  - — [Studicata summary](https://www.studicata.com/summaries/court-of-appeal-of-california/sonora-diamond-corporation-v-superior-court-2000-ji8kos); [vLex](https://case-law.vlex.com/vid/sonora-diamond-corp-v-889831050), via search result, accessed 2026-11-21
- ***Greenspan v. LADT, LLC* (2010) 191 Cal.App.4th 486 (2d Dist., filed Dec. 30, 2010, certified for publication).** — [Opinion PDF hosted on gmsr.com, text extracted locally](https://www.gmsr.com/wp-content/uploads/2022/03/2010-12-30-Greenspan-Opinion.pdf), accessed 2026-11-21
  - **Facts.** A developer formed several LLCs, "transferred ownership of the companies to a trust, chose his brother as the trustee, and acted as the 'manager'". The LLCs lost an $8.45 million arbitration. The $47 million they had recently received "dwindled to less than $13,000."
  - **Holding.** The Court of Appeal reversed the denial of the creditor's CCP §187 motion to add the manager, the trustee and affiliated companies as judgment debtors. It held the alter-ego doctrine "may apply to a trustee but not a trust."
  - **Factors.** The opinion quotes *Zoran Corp. v. Chen* (2010) 185 Cal.App.4th 799 for the 14-factor list. The list includes commingling; treating company assets as one's own; holding oneself out as personally liable; failing to keep minutes or records; "sole ownership of all of the stock in a corporation by one individual or the members of a family"; inadequate capitalization; use as "a mere shell"; and concealment of ownership. "No single factor is determinative."
  - **Reverse piercing.** The opinion notes that *Postal Instant Press v. Kaswa* (2008) 162 Cal.App.4th 1510 bars "outside reverse" piercing of a *corporation*, meaning reaching the company's assets for an owner's personal debt.
- **LLC-specific secondary points.**
  - *Curci Investments v. Baldwin* (2017) 14 Cal.App.5th 214 is reported to allow reverse veil piercing against an LLC. — [Alper Law-hosted opinion](https://www.alperlaw.com/wp-content/uploads/opinions/curci-investments-v-baldwin.pdf), via search result; not opened, accessed 2026-11-21
  - *Misik v. D'Arco* (2011) 197 Cal.App.4th 1065 holds that adding an alter ego after judgment under §187 inserts the real defendant's name rather than adding a new party. — via [search-result summaries of trial-court tentative rulings](https://rulings.law/rulings/judge-joseph-lipner/bc506921-2023-09-19.html), accessed 2026-11-21
  - A practitioner source says being single-member alone does not establish alter ego; there must be abuse of the form. — via search results above, accessed 2026-11-21

**Taxes the shield does not cover**
- **Trust Fund Recovery Penalty.** A "responsible person" with the duty and power to collect and pay withheld payroll taxes who "willfully" fails to do so is personally liable for 100% of the unpaid trust-fund taxes. Owners of owner-managed businesses generally qualify. This applies to LLC members and corporate officers alike. — [IRS, Employment Taxes and the Trust Fund Recovery Penalty](https://www.irs.gov/businesses/small-businesses-self-employed/employment-taxes-and-the-trust-fund-recovery-penalty-tfrp), via search result, accessed 2026-11-21

**Regulators name individuals directly**
- FTC COPPA cases against app developers often name the individuals who run the company:
  - **HyperBeard (2020):** two individual defendants were named alongside the company. A $4 million penalty was suspended to $150,000, and the order binds the individuals in any future child-directed app. — [TechCrunch (June 2020)](https://techcrunch.com/?p=1998606); [Hunton Andrews Kurth (2020)](https://www.hunton.com/privacy-and-cybersecurity-law-blog/ftc-issues-new-coppa-case-involving-behavioral-advertising-in-kids-apps-issues-4-million-dollar-civil-penalty-amid-dissenting-vote), via search result, accessed 2026-11-21
  - **Retro Dreamer (2015):** the president and vice-president were named individually. — [Kelley Drye (Dec. 2015)](https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/app-developers-settle-coppa-violations-relating-to-third-party-ad-network-practices), via search result, accessed 2026-11-21
  - **W3 Innovations (2011):** the company's president was named. — [Kelley Drye (2011)](https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/ftc-settles-with-mobile-app-developer-over-alleged-privacy-violations.md), via search result, accessed 2026-11-21
- The search did not establish the FTC's legal test for individual liability. The cases show the practice, not the standard.

**Formation logistics and cost (earlier pass)**
- California LLC: $70 to file, $20 Statement of Information, and $800 annual tax with no first-year exemption.
- California corporation: no $800 minimum franchise tax in the first taxable year.
- Delaware C-corp: $109 minimum filing, $175 minimum franchise tax, $50 annual report, plus California qualification.
- — `platforms_business_setup.md` §4, citing [FTB LLC page (updated Mar. 5, 2026)](https://www.ftb.ca.gov/file/business/types/limited-liability-company/index.html) and [FTB Corporations page (updated Dec. 16, 2025)](https://www.ftb.ca.gov/file/business/types/corporations/index.html), accessed 2026-11-21

**Formation services**
- **Stripe Atlas.** "You and your Company represent that each of the Founders is 18 years of age or older." — [Stripe Atlas Terms (fr-ca locale, last updated Jul. 22, 2025)](https://stripe.com/fr-ca-ca/atlas/legal), via search result, accessed 2026-11-21
- **Clerky (Delaware C-corp).** Reported prices: $427 to incorporate, $299 post-incorporation setup, or an $819 "Company Lifetime Package". These figures come from third-party reviews around October 2026; verify on clerky.com. — [Rho, Clerky review (2026)](https://www.rho.co/blog/clerky-review); [Clerky](https://clerky.com/), via search result, accessed 2026-11-21

### Inferences
- **What an entity blocks and what it does not.** The entity blocks claims against the founders and parents *merely because they own or manage it*: contract claims against the company, vendor indemnities owed by the company, and vicarious claims for others' acts. It does **not** block a claim that a founder personally wrote, approved or deployed the harmful code or data practice. *Frances T.* and §17703.04(c) say so. In a two-person company where the founders do everything, that "personal participation" exception is wide. The shield is strongest for contract and indemnity exposure and weakest for privacy torts and regulatory actions.
- **LLC vs C-corp on liability alone.** The two shields are essentially the same. The LLC formality rule (§17703.04(b)) is a real advantage for founders who will not hold board meetings or keep minutes. A corporation's missed formalities do count as an alter-ego factor (the *Greenspan* and *Zoran* factor list includes "failure to maintain minutes or adequate corporate records").
- **C-corp's other advantages.** These are cost and financing, not liability: no first-year $800 (California corporation), and the usual investor preference for Delaware C-corps. The investor preference is not cited here; it is the general practice view. An LLC can convert later; conversion cost was not researched.
- **Single-member or family-owned.** Sole or family ownership is a listed factor (*Greenspan*/*Zoran* factor [5]) but not enough by itself ("Stock ownership alone is not enough", per *Sonora Diamond*).
- **Parent-managed LLC.** The danger is not the structure itself. It is the parent treating LLC money as household money, or the LLC holding no assets while the parent pays its bills personally. *Greenspan* shows a non-owner manager who dominates the entity can be added as a judgment debtor.
- **Capitalization.** For an app with real minor-privacy risk and no revenue, "capitalization" in practice means having insurance plus enough cash for vendor bills. A shell with $0 that runs a teen-data product is the *Automotriz* fact pattern ("trifling compared with the business to be done and the risks of loss"). This is an inference; no case was found applying it to a free software startup.

### Gaps
- Primary texts of *Automotriz* and *Sonora Diamond* could not be fetched (Justia 403). Pin cites and quotes come from secondary summaries.
- No California case was found holding that single-member or family LLCs are pierced *more often*; only the factor lists exist.
- California's treatment of unpaid LLC taxes (FTB suspension and its effect on the LLC's capacity to defend suits) was not researched.
- No source was retrieved on the FTC's standard for individual liability.

---

## 4. Can minors be LLC members or managers or corporate shareholders or directors; is parent-as-manager plus CUTMA custody the usual answer; and what must a founders' agreement and IP assignment say?

### Takeaway
No California or Delaware statute found bars minors from being members, managers, shareholders or directors (earlier pass). But a minor's signature on the operating agreement, stock purchase or IP assignment can be disaffirmed. Atlas-style services require every founder to be 18 or older. The usual workable structure is:

- a parent as organizer and sole manager (or incorporator, director and officer);
- each founder's units or shares held by a parent "as custodian" under CUTMA;
- a written founders' agreement plus IP assignment signed by the founders, joined by the parents, and ratified by each founder at 18.

CUTMA itself adds a liability shield. The custodian is not personally liable on contracts signed in the disclosed custodial capacity, or for torts, unless personally at fault. The minor is not personally liable for obligations that arise from merely owning the custodial property. California's court-approval route for minors' contracts (Fam. Code §6750) covers only the entertainment field, so it likely cannot make a software IP assignment disaffirmance-proof.

### Cited Findings
**Who can form and hold an entity (earlier pass)**
- No age qualifier appears in the formation statutes: LLC organizers are "persons" ([Cal. Corp. Code §17702.01](https://california.public.law/codes/corporations_code_section_17702.01); [§17701.02](https://california.public.law/codes/corporations_code_section_17701.02)); a corporation is formed by "natural persons" ([§200](https://california.public.law/codes/corporations_code_section_200)); Delaware directors must be "natural person[s]" ([8 Del. C. §141(b)](https://delcode.delaware.gov/title8/c001/sc04/index.html)). All accessed 2026-11-21; details in `platforms_business_setup.md` §4.
- **CUTMA basics.** An adult is 18 or older. Custodial property is delivered at 18 unless delayed; for transfers by will, trust or nomination it can be delayed up to age 25. — [Prob. Code §3901](https://california.public.law/codes/probate_code_section_3901); [§3920](https://california.public.law/codes/probate_code_section_3920); [§3920.5](https://california.public.law/codes/probate_code_section_3920.5), accessed 2026-11-21
- **EIN for a minor.** The IRS will collect the parent's TIN for a minor's EIN application from December 2026. — [IRS IRM procedural update (Oct. 28, 2026)](https://www.irs.gov/pub/foia/ig/spder/ts-21-1026-0875.pdf), accessed 2026-11-21

**CUTMA liability rules (Prob. Code §3917)**
- (a): claims based on "a contract entered into by a custodian acting in a custodial capacity", on obligations from owning custodial property, or on torts during the custodianship may be asserted "against the custodial property by proceeding against the custodian in the custodial capacity".
- (b): "A custodian is not personally liable" in two situations:
  - "On a contract properly entered into in the custodial capacity unless the custodian fails to reveal that capacity and to identify the custodianship in the contract";
  - "For an obligation arising from control of custodial property or for a tort committed during the custodianship unless the custodian is personally at fault."
- (c): "A minor is not personally liable for an obligation arising from ownership of custodial property or for a tort committed during the custodianship unless the minor is personally at fault."
- — [Cal. Prob. Code §3917 (verified Nov. 16, 2026)](https://california.public.law/codes/probate_code_section_3917), accessed 2026-11-21

**Court approval of minors' contracts (Fam. Code §6750)**
- It covers contracts for "artistic or creative services", sports, and a minor's agreement to "purchase, or otherwise secure, sell, lease, license, or otherwise dispose of" "literary, musical, or dramatic properties".
- Those rights must be for use in "motion pictures, television, the production of sound recordings", the stage, or otherwise "in the entertainment field".
- — [Cal. Fam. Code §6750 (verified Nov. 16, 2026)](https://california.public.law/codes/family_code_section_6750), accessed 2026-11-21

**Formation-service age limit**
- Stripe Atlas requires every founder to be 18 or older (Atlas Terms, Jul. 22, 2025; cited in section 3).

**Founder IP practice (secondary)**
- Each founder normally assigns pre-formation IP to the company at formation, typically as part of the founder stock purchase.
- Investors expect signed IP assignments from every founder, employee, contractor and advisor who contributed.
- Minors' disaffirmance must be total: a minor cannot keep the benefits (such as the equity) while voiding the burdens (such as the assignment).
- After 18, a former minor can ratify, and silence beyond a reasonable time may count as ratification.
- These search results did **not** address a minor founder's IP assignment specifically.
- — [Polsinelli, "What's a little IP among friends" (undated)](https://www.polsinelli.com/david-cykiert/publications/shelf-space-whats-a-little-ip-among-friends-why-founders-shouldnt-wait-on-ip-assignments); [JD Supra, "Who Really Owns Your Startup's IP?" (undated)](https://www.jdsupra.com/legalnews/who-really-owns-your-startup-s-ip-5341962/); [UpCounsel on minors' contracts (undated, low authority)](https://upcounsel.com/contracts-made-by-minors-are-void), via search result, accessed 2026-11-21

**Why written founder terms matter**
- **Snapchat.** Reggie Brown's co-founder claims against Evan Spiegel and Bobby Murphy (filed 2013) were settled in September 2014 for $157.5 million. The settlement was disclosed in Snap's 2017 S-1; Brown had reportedly sought a one-third stake. — [TechCrunch (Feb. 2, 2017)](https://techcrunch.com/2017/02/02/snapchat-reggie-brown/); [Fortune (Feb. 3, 2017)](https://fortune.com/2017/02/03/snapchat-snap-ipo-spiegel-murphy-brown), via search result, accessed 2026-11-21

### Inferences
- **Why CUTMA custody is the best fit.**
  - A parent who signs "as custodian for [founder] under the California Uniform Transfers to Minors Act" is shielded on those contracts under §3917(b)(1).
  - A founder who merely owns custodial units is shielded for obligations of ownership under §3917(c).
  - The founders still remain liable for their own fault, consistent with §6600.
- **The custody trade-off.** Under §3920 the units go to each founder at 18 automatically. The parent cannot hold them back for a lifetime transfer; delay to 25 is only for transfers by will, trust or nomination.
- **IP assignment cannot be made disaffirmance-proof by court approval.** Software is not "literary, musical, or dramatic properties ... in the entertainment field" (§6750). The protections are therefore contractual and practical:
  1. Each founder signs a present-tense assignment ("hereby assigns") of all miyagi code, designs, names and domains, including pre-formation work.
  2. Each parent signs a joinder consenting and agreeing to cause performance.
  3. Equity is issued (to the custodian) as consideration for the assignment, so disaffirming means giving up the equity.
  4. A one-page ratification is signed by each founder within days of turning 18.
  5. The repo, domains and accounts are moved into the entity's name, so practical control matches legal title.
- **What the founders' agreement must cover.**
  - Equity split and vesting, with a cliff and acceleration only if agreed.
  - What happens if a founder leaves: repurchase of unvested units.
  - Decision rights, with the parent-manager acting on the founders' instructions within limits.
  - Confidentiality.
  - The IP assignment above.
  - A statement that no partnership exists outside the entity, with all prior partnership assets contributed to it.
  - Dispute resolution.
  - This list is drawn from the secondary practice sources and the *Snapchat* lesson; a lawyer should draft it.

### Gaps
- No source specific to a minor founder's IP assignment or stock purchase was found, nor any case where a minor founder disaffirmed one.
- 17 U.S.C. §204(a) (copyright transfers must be in a signed writing) was not re-verified this pass.
- Whether a CUTMA custodian may hold LLC units subject to vesting and repurchase (a "restricted" transfer) was not researched; this needs a lawyer.
- Whether Clerky or similar services accept minor founders was not checked.

---

## 5. What else shields individuals: indemnification, insurance, and acting only in an official capacity?

### Takeaway
California and Delaware both let the entity indemnify its people and advance their defense costs. California LLCs *must* indemnify a manager who complied with statutory duties (§17704.08(a)). California corporations must indemnify an agent who wins on the merits (§317(d)). Indemnity is only as good as the company's bank balance, though. Insurance is what actually pays:

- Tech E&O covers claims that the software caused harm.
- Cyber covers breach response.
- D&O covers individuals named for management decisions.

Vendor estimates put a $1M bundle of general liability, tech E&O and cyber at about $2,000–$4,000 a year for a pre-revenue startup. Signing only in a representative capacity, with the entity's name on every contract, keeps the individual from becoming the principal (Civ. Code §2343; Prob. Code §3917(b)).

### Cited Findings
**California corporations (Corp. Code §317)**
- (b): may indemnify an agent in third-party proceedings who "acted in good faith and in a manner the person reasonably believed to be in the best interests of the corporation".
- (d): an agent "successful on the merits" "shall be indemnified" for expenses.
- (e): permissive indemnity requires a determination by disinterested directors, independent counsel, shareholders or a court.
- (f): expenses may be advanced against an undertaking to repay.
- (g): rights beyond §317 must be authorized in the articles. This ties to §204(a)(11).
- (i): the corporation may "purchase and maintain insurance on behalf of any agent" even where it could not indemnify.
- — [Cal. Corp. Code §317 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_317), accessed 2026-11-21

**California LLCs (Corp. Code §17704.08)**
- (a): the LLC *must* reimburse and indemnify a member of a member-managed LLC, or the manager of a manager-managed LLC, for liabilities incurred on the company's behalf if they "complied with the duties stated in Section 17704.09".
- (b): the LLC "may indemnify" others, such as officers and agents.
- (c): the LLC may insure a person even where the operating agreement could not limit that person's liability.
- (d): mandatory indemnification of an "agent" who succeeds on the merits or settles, if the agent acted in good faith. Expenses include attorney's fees.
- Last updated Jan. 1, 2016.
- — [Cal. Corp. Code §17704.08 (verified Nov. 16, 2026)](https://california.public.law/codes/corporations_code_section_17704.08), accessed 2026-11-21

**Delaware**
- **8 Del. C. §145.** (a): permissive indemnity if the person "acted in good faith" and in a manner not "opposed to the best interests of the corporation". (c)(1): mandatory for directors and officers who succeed. (e): advancement on an undertaking. (f): non-exclusive. (g): the corporation may buy insurance even where it could not indemnify. — [8 Del. C. ch. 1, subch. IV](https://delcode.delaware.gov/title8/c001/sc04/index.html), accessed 2026-11-21
- **6 Del. C. §18-108.** "Subject to such standards and restrictions, if any, as are set forth in its limited liability company agreement, a limited liability company may, and shall have the power to, indemnify and hold harmless any member or manager or other person". — [6 Del. C. ch. 18, subch. I](https://delcode.delaware.gov/title6/c018/sc01/index.html), accessed 2026-11-21

**Insurance (all vendor or broker sources with a sales interest)**
- **What each policy covers.**
  - D&O pays defense costs for founders and directors named personally.
  - Tech E&O responds to claims that the software or service caused a customer loss.
  - Cyber responds to breaches and attacks.
  - Brokers recommend starting with cyber, tech E&O and general liability, and adding D&O later. Founders often wait until a term sheet for D&O.
  - — [Corgi, D&O page (undated)](https://www.corgi.insure/directors-and-officers); [Corgi, founders' guide (undated)](https://www.corgi.insure/blog/startup-insurance-guide-for-founders); [Embroker, E&O for startups (undated)](https://www.embroker.com/blog/errors-and-omissions-for-startups), via search result, accessed 2026-11-21
- **Cost.**
  - About $2,000–$4,000 a year for a pre-revenue or early-revenue startup with $1M limits across GL, tech E&O and cyber.
  - D&O alone is about $5,000–$10,000 a year at later stages.
  - Early-stage companies commonly start with $1M limits.
  - — [Corgi, startup insurance (undated)](https://www.corgi.insure/startup-insurance); [Corgi, cost by stage (undated)](https://www.corgi.insure/blog/startup-insurance-cost-by-stage); [Vouch, startup insurance costs (undated)](https://www.vouch.us/blog/startup-insurance-costs), via search result, accessed 2026-11-21

**Acting only in an official capacity**
- Civ. Code §2343 (section 2): an agent is personally liable only when credit is given to him personally, when he signs without good-faith authority, or when his acts are wrongful.
- Prob. Code §3917(b) (section 4): a custodian is shielded only if the contract reveals the custodial capacity and identifies the custodianship.

### Inferences
- **Operating agreement terms that help.**
  - Mandatory indemnification and advancement for the manager, members and any officers.
  - Authority to buy insurance.
  - No requirement to hold meetings, which preserves the §17703.04(b) formality protection.
  - No clause invoking §17703.04(e), which would create personal liability.
- **A Delaware LLC agreement** can be broader still (§18-108 has almost no statutory standard). A California corporation's indemnity beyond §317 needs an articles provision.
- **Indemnity cannot cover everything.** It does not cover what the law will not let the company pay, such as bad-faith conduct. It is worthless if the company has no money. Insurance, whose availability for an entity managed for minors was not checked, is what funds defense of a privacy or product claim that names a founder personally.
- **Two standard insurance gaps.** Insurers commonly exclude regulatory fines and intentional acts. COPPA civil penalties may therefore be uninsured. This is the general pattern, not verified for any specific policy.

### Gaps
- Whether insurers will write tech E&O and cyber for an LLC whose owners are minors, and at what price for a teen-facing AI app, was not checked. Quotes would be needed.
- Coverage of COPPA and FTC civil penalties, or state privacy penalties, under cyber and E&O policies was not verified.
- Corp. Code §204(a)(11) and §17701.10(g) (the limits on eliminating LLC duties) were referenced but not opened.

---

## 6. Real examples: student or teen founders, minors, or their parents personally sued over software, apps or online acts

### Takeaway
No reported case was found of a California high-school founder, or a founder's parents, being personally sued over a startup app. Close analogs show the pattern. Minors are sued personally over software and online conduct, and parents get pulled in:

- Epic Games sued a 14-year-old over Fortnite cheats and sought default judgment against him and his mother.
- The RIAA sued a 12-year-old, and her mother paid $2,000.
- A Georgia court let negligent-supervision claims go to a jury against parents over a fake Facebook profile.

Student-founder disputes (Snapchat, Yik Yak) are mostly co-founder claims over informal, unwritten founder deals.

### Cited Findings
- **Epic Games v. C.R. (E.D.N.C., filed 2017).**
  - Epic sued a 14-year-old for distributing Fortnite cheats. His mother wrote to the court objecting that he was a minor, and the judge treated her letter as a motion to dismiss.
  - Judge Malcolm Howard ruled the letter was not enough to dismiss the suit (2018).
  - Epic sought default judgment against "14-year-old Fortnite cheater and his mom", arguing his age did not matter because he played the game (PC Gamer, Apr. 25, 2018).
  - Epic argued it did not violate Rule 5.2(a) because it did not know he was a minor when it filed.
  - The case settled around February 2021 under seal while he was still under 18.
  - — [PC Gamer (Apr. 25, 2018)](https://www.pcgamer.com/epic-seeks-default-judgment-in-lawsuit-against-14-year-old-fortnite-cheater-and-his-mom); [TechSpot (2018)](https://www.techspot.com/news/75518-federal-court-epic-can-go-ahead-lawsuit-against.html); [Techdirt (Feb. 11, 2021)](https://www.techdirt.com/articles/20210211/09060746230/epic-games-case-against-teenage-fortnite-cheater-finally-settles.shtml); [TorrentFreak](https://torrentfreak.com/?p=200222), via search result, accessed 2026-11-21
- **RIAA file-sharing suits (September 2003).** A 12-year-old in New York was among 261 people sued. Her mother settled for $2,000 less than a day after filing. — [InfoWorld (Sept. 2003)](https://www.infoworld.com/article/2222832/riaa-settles-with-12-year-old-pirate-s-mother.html); [CBS News (Sept. 2003)](https://www.cbsnews.com/news/downloading-girl-escapes-lawsuit), via search result, accessed 2026-11-21
- ***Boston v. Athearn* (Ga. Ct. App. Oct. 10, 2014).** Parents may face a jury on negligence for failing to make their son remove a defamatory fake profile after notice (see section 2).
- **Snapchat.** The 2013 suit against two Stanford-student co-founders settled for $157.5 million in 2014 (see section 4).
- **Yik Yak (2014).** A former classmate and fraternity brother sued the app's two founders, claiming he was unfairly pushed out. A Forbes profile describes a lawyer who specializes in such co-founder suits, including Snapchat and Yik Yak. — [Forbes (Nov. 18, 2014)](https://www.forbes.com/sites/ellenhuet/2014/11/18/yik-yak-lawsuit-frat-bro/); [Forbes (Apr. 14, 2015)](https://www.forbes.com/sites/ryanmac/2015/04/14/cofounder-lawsuits-luan-tran-snapchat-yik-yak/), via search result, accessed 2026-11-21
- **Teen founder later sued personally as an adult.** A class action naming a founder who had started companies as a teenager, along with his platform, was filed in S.D.N.Y. on March 23, 2026. This is a low-quality source, and it does not say whether family members were named. — [Wikipedia, Ben Pasternak](https://en.wikipedia.org/wiki/Ben_Pasternak), via search result, accessed 2026-11-21
- **FTC COPPA cases naming individuals** (HyperBeard 2020, Retro Dreamer 2015, W3 Innovations 2011): see section 3.

### Inferences
- **Being a minor does not deter suit.** Plaintiffs sue the minor and pull in the parent. *Epic* shows a court will not dismiss just because the defendant is 14. The minor's real defenses are contract disaffirmance and the merits.
- **The most common lawsuit against student founders** in reported examples is a claim by a third friend or early contributor to equity. That is exactly what a written founders' agreement and a clean IP assignment prevent.

### Gaps
- No reported California case was found where a minor startup founder, or a founder's parents, were personally sued over an app's harm to users.
- Court records for *Epic v. C.R.* were not pulled; the case name and number are from press reports only.
- No case was found applying §1714.1 to software or online conduct.

---

## Implications for miyagi

### Takeaway
Today the two founders are most likely a general partnership. Each is personally liable for his own torts and jointly for partnership debts. Any vendor account opened in a parent's name makes that parent the indemnifying "Customer", in some cases with no cap. The protective setup is a California manager-managed LLC, set up as follows:

- A parent is the sole manager, and each founder's units are held by that parent as CUTMA custodian.
- The LLC, not any person, holds every vendor account, the repo, the domain and the Developer ID.
- Money stays separate, and every signature is made in a representative capacity.
- The operating agreement indemnifies the manager and founders.
- Tech E&O and cyber insurance are bought as soon as quotes allow.

A Delaware C-corp gives the same shield and is the better choice only if fundraising is near. The entity will still not protect a founder from claims over code or data practices he personally built. For those, the product-compliance work in the earlier pass is the real shield.

### Step-by-step setup
Each row says what it blocks, its approximate cost, and whether a lawyer is needed. Costs are state fees from the earlier pass or vendor-quoted figures; lawyer fees were not researched.

| # | Step | What lawsuit or exposure it blocks | Cost | Lawyer? |
|---|---|---|---|---|
| 1 | **Freeze new personal-name signups now.** Until the entity exists, a parent opens only the accounts launch truly needs, on the lowest spend, and keeps a list of each one for transfer. | Limits the parent's personal "Customer" indemnities (Anthropic K.2 uncapped; Supabase §10(b); Google APIs indemnity; Apple §10) and promoter liability to the shortest window (§2343(1)). | $0 | No |
| 2 | **Form a California LLC, manager-managed, with a parent as organizer and sole manager.** The articles must not require meetings. (Alternative: a Delaware C-corp with a parent as sole director and officer, if raising money within about 12 months; Stripe Atlas is unavailable because founders must be 18+.) | Ends default-partnership joint-and-several liability for *future* obligations (§§16202, 16306). Debts become the LLC's alone (§17703.04(a)). Keeps missed formalities out of the alter-ego analysis (§17703.04(b)). | CA LLC: $70 filing + $20 Statement of Information + $800/yr tax (no first-year exemption). DE C-corp: $109 + $175/yr + $50 + CA qualification, or roughly $427–$819 via Clerky. | Recommended (to draft the operating agreement) |
| 3 | **Issue each founder's units to a parent "as custodian for [founder] under the California Uniform Transfers to Minors Act."** Units vest and go to each founder at 18 (§3920). | The minor is not personally liable merely for owning the units, and the custodian is not liable on properly disclosed contracts or for torts absent personal fault (Prob. Code §3917). Avoids a disaffirmable minor signature on the equity grant. | $0 | Yes (vesting and repurchase on custodial units) |
| 4 | **Sign a founders' agreement plus a present-tense IP assignment.** Each founder assigns all miyagi code, designs, name and domain, including pre-formation work, in exchange for the equity. Parents sign a joinder. No partnership outside the LLC; all prior partnership assets are contributed. Each founder signs a short ratification within days of turning 18. | Blocks a co-founder or "third friend" equity suit (*Snapchat*, *Yik Yak*). Blocks a founder later claiming he personally owns the code. Reduces disaffirmance risk; Fam. Code §6750 court approval does not apply to software. | Lawyer fee (not researched) | Yes |
| 5 | **Move every account into the LLC.** Anthropic, Google Cloud/Gemini, Supabase, Render, the GitHub organization, the domain registrar, Apple (organization enrollment with a free D-U-N-S) and a Microsoft Partner Center *Company* account. The parent accepts each "on behalf of" the LLC as manager. Close personal accounts, or get each vendor's written transfer, rather than just "adopting" them. | Moves vendor indemnities, fees and termination risk from the parent's personal assets to the LLC. The parent acting for a disclosed principal with authority is not personally liable (§2343). Ends promoter liability, which only a novation or a fresh account ends. | Mostly $0; Apple $99/yr (earlier pass) | No (but check each vendor's transfer terms) |
| 6 | **Open an LLC bank account and card under the EIN, and pay every vendor from it.** Capitalize it with a documented contribution covering at least several months of vendor bills plus the insurance premium. Never pay LLC bills personally or personal bills from the LLC. Keep a simple ledger. | Defeats alter-ego claims built on commingling, treating LLC assets as one's own, or "trifling" capital (*Automotriz*; *Greenspan* and *Zoran* factors). This matters most for a parent-manager, who can be added as a judgment debtor under CCP §187 (*Greenspan*). | Bank fees (often $0) + capital contribution | No |
| 7 | **Sign only in a representative capacity, and name the LLC as operator everywhere.** Sign as "[Parent], Manager, miyagi LLC". Name the LLC in the Terms, Privacy Policy, EULA, website footer, app About screen and code-signing certificate. The custodian signs "as custodian under CUTMA". | Prevents §2343(1) personal credit. Satisfies §3917(b)(1) disclosure. Users' and vendors' claims run to the LLC. | $0 | No |
| 8 | **Operating agreement terms:** mandatory indemnification and advancement for the manager, members and officers (§17704.08), authority to buy insurance, no meeting requirement, and no §17703.04(e) personal-obligation clause. | Shifts defense costs of suits naming the parent or founders to the LLC and its insurer. | Included in step 2 | Yes |
| 9 | **Get insurance quotes for tech E&O, cyber and general liability (about $1M limits); add D&O later.** Disclose that users include 13–17-year-olds and that AI providers process screen and code data. | Pays defense and damages for claims that the app caused harm (E&O) or a breach (cyber), including suits naming founders personally. This is what makes the indemnity in step 8 real. Fines may be excluded. | About $2,000–$4,000/yr (vendor estimate, unverified for this risk profile) | No (broker) |
| 10 | **Never sign a personal guarantee, and never put an individual's name on a vendor agreement after formation.** If a vendor demands a guarantee, choose another vendor. | Guarantees and individual contracts survive the shield (§17703.04(c)). | $0 | No |
| 11 | **Run the product as if the founders were personally on the hook, because for their own conduct they are.** Follow the earlier pass's COPPA, privacy and minors' safety work. Document fixes. When a parent learns of a specific harmful practice or leak, see that it is fixed promptly. | Personal-participation torts (*Frances T.*; §17703.04(c); Fam. Code §6600) and FTC actions naming individuals (HyperBeard, Retro Dreamer, W3). Negligent-supervision claims arise on notice plus inaction (*Athearn*). §1714.1 is capped at $56,400 per tort and only for willful misconduct. | Time | Partly (privacy counsel for COPPA questions) |
| 12 | **Keep the LLC in good standing.** File the Statement of Information every two years, pay the $800 tax by its due date, and make no payroll until a payroll provider is in place. | Avoids the Trust Fund Recovery Penalty (personal, 100% of withheld taxes) and status problems that weaken the shield. | $20 every two years + $800/yr | No (accountant once revenue starts) |

### Gaps
- Lawyer and drafting fees for steps 2–4 and 8 were not researched.
- LLC-to-C-corp conversion cost and process were not researched.
- Each vendor's account-transfer terms (Anthropic, Google, Supabase, Render, GitHub) and the Microsoft developer-agreement indemnity were not checked.
- Insurer appetite and pricing for a teen-facing AI app owned by a minor-custodial LLC is unknown; quotes are needed.
- The FTB suspension consequences of missed LLC taxes or filings were not researched.
- No case was found testing how a California court treats a parent-managed, CUTMA-held LLC in an alter-ego dispute; *Greenspan* is the closest analog.
