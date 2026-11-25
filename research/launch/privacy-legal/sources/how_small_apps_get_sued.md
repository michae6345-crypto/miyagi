# How small, free apps and very early startups get sued or threatened in the US (2023-2026), and how to handle each cheaply

Status as of 2026-11-21. Every link below was accessed 2026-11-21; the source's own date is given beside each link. Law-firm alerts, vendor blogs and trackers are secondary sources and labeled as such. Items marked "search summary" came from a search-result digest and were not fetched in full, so verify them before quoting. This is research, not legal advice.

## 1. Patent assertion entities (patent trolls) and small app developers

### Takeaway
NPE litigation is rising again: up about 20% in 2025, and roughly 90% of high-tech patent suits are NPE suits. Historically most NPE defendants are small companies, but "small" in this data still means companies with revenue or venture funding. A free, pre-revenue app is much more likely to get a templated demand letter than a lawsuit. Defenses exist (Alice §101 motions, IPR, Octane fee shifting), but they cost five to six figures, and 2025 USPTO changes made IPR harder to get.

### Cited Findings
**Volume and who files (2024-2026)**
- District court patent cases were 4,531 in 2025, up 12% from 4,053 in 2024. NPEs filed 55.4% of them (51.8% in 2024), and NPE filings rose 21.6% — [Unified Patents, "Patent Dispute Report: 2025 in Review", 2026-01-13](https://www.unifiedpatents.com/insights/2026/1/13/patent-dispute-report-2025-in-review), accessed 2026-11-21.
- High tech was 58.9% of district court filings, and NPEs brought 90.3% of high-tech district court litigation. E.D. Tex. got 44.2% of NPE filings. Torus Ventures LLC was the top plaintiff, Patent Armory was third, and 9 of the top 10 plaintiffs were NPEs — [Unified Patents, 2026-01-13](https://www.unifiedpatents.com/insights/2026/1/13/patent-dispute-report-2025-in-review), accessed 2026-11-21.
- RPX counted NPE filings up "almost 19%" in 2025 over 2024 (search summary) — [RPX Q4 in Review, Jan 2026](https://www.rpxcorp.com/wp-content/uploads/sites/6/2026/04/RPX-Q4-in-Review-January-2026.pdf), accessed 2026-11-21. RPX also says NPEs added 1,189 defendants in H1 2025, up 30% year over year (search summary) — [RPX Q2 in Review, July 2025](https://www.rpxcorp.com/wp-content/uploads/sites/6/2025/07/RPX-Q2-in-Review-July-2025.pdf), accessed 2026-11-21.
- Unified defines "NPE (Small Company)" as a former operating company that now mainly monetizes its patents. The 2025 report gives no breakdown by defendant size — [Unified Patents, 2026-01-13](https://www.unifiedpatents.com/insights/2026/1/13/patent-dispute-report-2025-in-review), accessed 2026-11-21.

**Do they target startups and pre-revenue apps?**
- Chien's RPX-based study found that at least 55% of PAE defendants make under $10M a year, while operating-company plaintiffs sued sub-$10M defendants only about 16% of the time (search summary; PDF text could not be extracted) — [Chien, "Patent Assertion and Startup Innovation", New America, 2013-09](https://static.newamerica.org/attachments/3894-patent-assertion-and-startup-innovation/Patent%20Assertion%20and%20Startup%20Innovation_Executive%20Summary_Updated.3b3e5574a0644474a13127a89a7b1078.pdf), accessed 2026-11-21.
- In Chien's 2012 non-random survey, 79 of 223 tech startups had received a patent demand. About 13 of those 79 had under $100,000 in revenue. Companies under $100M revenue made up at least 66% of unique troll defendants (search summary) — [Chien, "Startups and Patent Trolls", SSRN, 2012](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2146251), accessed 2026-11-21. Responses to demands included 22% "do nothing" and 18% settle (search summary) — [TechCrunch, 2013-09-06](https://techcrunch.com/2013/09/06/what-to-do-if-you-get-a-troll-demand/), accessed 2026-11-21.
- A LOT Network/HTS study of 6,000+ NPE defendants (2017-2022, Unified data) found targets averaged "nearly four" funding rounds and $65M raised before their first NPE suit, a "sweet spot" around Series C-D. 39% of NPE litigation against IPO companies came within two years of the IPO. Visible products in the market draw suits — [TechCrunch, "The anatomy of a patent litigation target", 2023-07-28](https://techcrunch.com/2023/07/28/the-anatomy-of-a-patent-litigation-target/), accessed 2026-11-21.
- LOT Network says 52% of companies sued make under $25M revenue (the network's own marketing figure) — [LOT Network startup page, undated](https://lotnet.com/startup-overview/), accessed 2026-11-21.

**Demand amounts and settlements**
- The FTC's PAE study (2009-2014 data, 22 PAEs, 2,100+ holding entities) found litigation-PAE royalties were typically below the lower bound of early litigation costs, which it called "consistent with nuisance litigation" — [FTC, "Patent Assertion Entity Activity", 2016-10](https://www.ftc.gov/node/45029), accessed 2026-11-21. A critic reports the FTC found 77% of litigation-PAE settlements were under $300,000, a benchmark drawn from an AIPLA cost study (secondary; not confirmed in FTC text) — [Heritage Foundation, 2016](https://www.heritage.org/government-regulation/commentary/the-ftcs-pae-study-recommendations-case-not-proven), accessed 2026-11-21.
- Litigation-PAE cases generally settled "within the first six months to a year" (FTC commissioner remarks, search summary) — [FTC, McSweeny remarks, 2016-10-13](https://www.ftc.gov/es/system/files/documents/public_statements/991353/mcsweeny_-_opening_remarks_at_public_policy_forum_on_pae_report_10-13-16.pdf), accessed 2026-11-21.
- Cloudflare's alternative to fighting an NPE was a "low six-figure" settlement — [TechCrunch, 2023-07-28](https://techcrunch.com/2023/07/28/the-anatomy-of-a-patent-litigation-target/), accessed 2026-11-21.
- Historical app example: in 2011 Lodsys sent small iOS developers letters with a 21-day deadline over in-app purchase/upgrade links, asking about 0.575% of US revenue. Apple said its license covered developers — [EFF FAQ, 2011](https://www.eff.org/issues/faqs-lodsys-targets), accessed 2026-11-21; [MacRumors, 2011-05-13](https://www.macrumors.com/2011/05/13/lodsys-threatens-to-sue-app-store-developers-over-purchase-links/), accessed 2026-11-21.

**Patent areas hitting apps and edtech (2024-2025 examples, secondary tracker)**
- Cascade Systems (digital media management patent) sued Learnfly Edtech (E.D. Tex., May 2025) and Skillshare (S.D.N.Y., Sept 2025). Both were dismissed without prejudice — [PatSnap, Learnfly, 2025](https://www.patsnap.com/resources/blog/litigation/cascade-systems-v-learnfly-edtech-digital-media-management-patent-patsnap/), accessed 2026-11-21; [PatSnap, Skillshare, 2025](https://www.patsnap.com/resources/blog/litigation/cascade-systems-v-skillshare-patent-dispute-over-digital-media-management-patsnap/), accessed 2026-11-21.
- Authentixx (content authentication) sued Maven Learning (W.D. Tex., June 2025) and dismissed 16 days later. Musicqubed asserted four patents against upGrad/KnowledgeHut (E.D. Tex., 2024-2025). Nimitz Technologies (streaming) v. Imagine Learning (D. Del.) ended with claims dismissed with prejudice in Nov 2025 — [PatSnap, Authentixx v. Maven](https://www.patsnap.com/resources/blog/litigation/authentixx-v-maven-learning-electronic-content-authentication-patent-patsnap/), accessed 2026-11-21; [PatSnap, Musicqubed v. upGrad](https://www.patsnap.com/resources/blog/litigation/musicqubed-v-upgrad-knowledgehut-patent-dismissal-patsnap/), accessed 2026-11-21; [PatSnap, Nimitz v. Imagine Learning](https://www.patsnap.com/resources/blog/litigation/nimitz-technologies-v-imagine-learning-streaming-content-patent-dispute-patsnap/), accessed 2026-11-21.

**Defenses and their cost**
- AIPLA 2025 survey (via IPWatchdog): with $1M-$10M at risk, the median cost was $600,000 through discovery, motions and claim construction, and $1M through trial and appeal. With $10M-$25M at risk it was $1.5M and $3M. NPE litigation costs about 35% more than competitor litigation. The sub-$1M tier was not reported in the article, and the full survey is members-only — [IPWatchdog, 2026-10-01](https://ipwatchdog.com/2026/10/01/the-true-cost-of-patent-infringement-litigation-enforcement-and-defense-in-a-complex-market/), accessed 2026-11-21; [AIPLA survey page](https://www.aipla.org/home/news-publications/economic-survey), accessed 2026-11-21.
- IPR government fees alone are $23,750 (request, up to 20 claims) plus $28,125 (post-institution). There is no small or micro entity discount. Schedule effective 2025-01-19 — [USPTO fee schedule, rev. 2026-11-01](https://www.uspto.gov/learning-and-resources/fees-and-payment/uspto-fee-schedule), accessed 2026-11-21. Older AIPLA-based attorney-cost estimates for IPR through hearing are about $250,000-$275,000, and the two sources conflict — [CRA/Landslide, 2018-05](https://media.crai.com/sites/default/files/publications/The_Cost_of_Doubling_Up_An_Economic_Assessement_of_Duplication_in_PTAB_proceedings_Landslide_May_2018_Layne_Farrar.pdf), accessed 2026-11-21.
- 2025 USPTO changes: from March 26, 2025 the Director decides discretionary denials in a separate first phase. A new "settled expectations" factor (June 2025) tends to deny review of patents in force about 6+ years — [Jones Day, 2025-06](https://www.jonesday.com/en/insights/2025/06/uspto-director-denies-ipr-institution-based-on-settled-expectations), accessed 2026-11-21; [Taft, 2025](https://www.taftlaw.com/news-events/law-bulletins/the-rise-of-settled-expectations-in-uspto-review-and-the-fallout-for-patent-owners-and-challengers/), accessed 2026-11-21. PTAB institution rates for petitions against NPE patents fell from 64.6% (Q1 2025) to 33.6% (Q4 2025). There were 607 discretionary denials, a record — [Unified Patents, 2026-01-13](https://www.unifiedpatents.com/insights/2026/1/13/patent-dispute-report-2025-in-review), accessed 2026-11-21.
- Alice §101 motions to dismiss succeed much more often in N.D. Cal. and S.D.N.Y. than in E.D./W.D. Tex. — [Sterne Kessler/Law360, 2024-07](https://www.sternekessler.com/news-insights/insights/alice-step-2-trends-show-courts-extrinsic-evidence-reliance/), accessed 2026-11-21. The pleadings-stage invalidation rate fell from over 60% (2015) to about 38% (2019) — [Akin Gump/Law360, 2020](https://www.akingump.com/a/web/mhJ3FnBYSHiXfunVMTFwig/law360-overlooked-patent-cases-lessons-on-section-101-motions.pdf), accessed 2026-11-21.
- Fee shifting: under *Octane Fitness v. ICON* (2014), an "exceptional" case under 35 U.S.C. §285 is one that stands out for the weakness of a party's position or unreasonable litigation conduct, proven by preponderance — [Octane Fitness, 572 U.S. 545 (2014), Justia](https://supreme.justia.com/cases/federal/us/572/545/), accessed 2026-11-21.
- Ignoring letters: EFF told Lodsys targets that a letter "is not a lawsuit" and creates no legal obligation to respond — [EFF FAQ, 2011](https://www.eff.org/issues/faqs-lodsys-targets), accessed 2026-11-21. Under *Halo v. Pulse* (2016), courts may enhance damages up to treble for egregious willful infringement, and knowledge of the patent bears on that — [Halo Electronics, 579 U.S. 93 (2016), Justia](https://supreme.justia.com/cases/federal/us/579/93/), accessed 2026-11-21.
- State anti-troll laws: Vermont's 2013 statute bars "bad faith assertion of patent infringement" — [9 V.S.A. §4197](https://legislature.vermont.gov/statutes/section/09/120/04197), accessed 2026-11-21. Others include Oregon, Virginia, Utah, Missouri, Texas (AG penalty up to $50,000 per violation), Colorado, Montana, North Dakota, Washington, New Hampshire, Louisiana and Florida. By 2014, 28 states had enacted or introduced such laws — [Foley & Lardner survey, 2014-08](https://www.foley.com/insights/publications/2014/08/survey-of-state-laws-against-badfaith-patent-asser), accessed 2026-11-21; [Florida Stat. 501.993](https://flsenate.gov/Laws/Statutes/2017/0501.993), accessed 2026-11-21. California's SB 681 (2015, "Patent Demands") was introduced — [SB 681 as introduced, 2015-02-27](https://www.leginfo.ca.gov/pub/15-16/bill/sen/sb_0651-0700/sb_681_bill_20150227_introduced.htm), accessed 2026-11-21.
- Free and cheap shields: LOT Network membership is free for companies under $25M revenue. If a member's patent is sold to a PAE, every other member gets a license — [Legal Dive](https://www.legaldive.com/news/patenttrolls-LOTnetwork-patentassertionentities-Google-Dropbox-Microsoft-intellectualproperty-IP/626065/), accessed 2026-11-21; [TechCrunch, 2016-09-01](https://techcrunch.com/2016/09/01/lot-network-waives-patent-troll-protection-membership-fees-for-startups/), accessed 2026-11-21. Unified Patents does not charge small companies, and small members act as an "early warning system" by reporting demand letters (undated secondary) — [eWeek](https://www.eweek.com/mobile/google-backed-unified-patents-working-to-deter-patent-trolls/), accessed 2026-11-21.

### Inferences
- Patent damages are built on a royalty base, and NPEs pick targets with revenue or funding. A free, unfunded app offers little to collect, so a lawsuit is unlikely. A cheap demand letter sent in bulk is still possible.
- Ignoring a letter does not trigger default the way ignoring a served complaint does. But a letter is notice that can later feed a willfulness argument. The safe cheap move is to log it, preserve it, not admit anything, and get a free read from a clinic, Unified or EFF.
- With IPR harder to get in 2025-2026, the cheapest real defenses for a tiny defendant are an early §101 motion in a favorable court, or pointing out there is no revenue to win and making the cost of suing obvious.

### Gaps
- No 2024-2026 data isolates pre-revenue or free-app defendants. Unified's and RPX's defendant-size breakdowns are behind paywalls.
- AIPLA 2025 figures for disputes under $1M at risk, and current IPR attorney costs, are members-only. No reliable recent number was found.
- No enacted California bad-faith-demand statute was found. SB 681 (2015) was introduced, but enactment was not confirmed. California targets would rely on federal law (Octane) and general unfair-competition law.
- No 2024-2026 survey of typical NPE demand amounts was found.

## 2. Privacy demand-letter mills (CIPA, VPPA, BIPA) and ADA website suits

### Takeaway
Privacy and accessibility mills go after websites that have pixels, analytics, chat widgets, search bars, video players or e-commerce. They aim at small and mid-sized businesses that will pay to make the letter go away. SB 690 removes private §638.51 (pen-register) suits over websites and apps starting 2027-01-01, but §631 wiretap claims remain. A static site with no trackers is a poor target. The app's own data flow (screens and code sent to third-party AI) is the theory to design against.

### Cited Findings
**CIPA volume, asks, targets**
- "Nearly 4,000 privacy claims" over digital tracking have been filed since 2022, and an estimated 50,000-100,000+ claims including those settled privately. "Demand amounts are typically between $15,000 and $40,000." Small and mid-sized businesses are "prime targets" — [Constangy, 2026-02-18](https://www.constangy.com/newsroom/newsletters/cipa-suits-why-a-60-year-old-law-makes-your-website-a-target), accessed 2026-11-21.
- CIPA statutory damages are "commonly cited at $5,000 per violation." Triggers include search bars, chat widgets, contact forms, Google Analytics, Meta/LinkedIn/TikTok pixels and session replay. Letters reach businesses "with no connection to California," often with a 20-day deadline — [Ward and Smith via National Law Review, 2026-07-16](https://natlawreview.com/article/cipa-demand-letter-wave-how-one-serial-litigant-turning-basic-websites-tsunami), accessed 2026-11-21.
- One self-represented serial litigant sent "thousands" of letters in about 18 months, each with a one-paragraph demand and a draft complaint, and followed up with suits or arbitrations. One firm alone had 100+ clients hit. Pushback has worked: an arbitrator dismissed CIPA and ECPA claims (May 2026), a C.D. Cal. judge dismissed for lack of Article III standing, and targets have filed declaratory-judgment suits — [Fisher Phillips, 2026-07-16](https://www.fisherphillips.com/en/insights/insights/businesses-fight-back-against-vivek-shahs-privacy-demand-letter-spree), accessed 2026-11-21.
- One tracker counted 1,500+ CIPA suits in the 18 months before August 2025, 1,000+ of them in 2025 (search summary, source attribution unconfirmed) — [IBTimes](https://www.ibtimes.com/cipa-lawsuits-are-surging-why-your-website-could-next-3805384), accessed 2026-11-21.
- A demurrer or motion to dismiss generally costs more than a typical individual CIPA settlement, so nuisance settlements are often the rational choice. At least seven federal judges have recently denied class certification in website wiretap cases — [Holland & Knight, 2026-10-14](https://www.hklaw.com/en/insights/publications/2026/10/sb-690-is-law-will-the-cipa-shakedown-continue), accessed 2026-11-21.

**SB 690**
- Signed 2026-09-30 and effective 2027-01-01. It amends §637.2 so that only the Attorney General can bring §638.51 pen-register/trap-and-trace claims over website or app conduct. It has a two-year retroactivity provision. §631(a) private claims remain, and an earlier version that covered §631 stalled — [Holland & Knight, 2026-10-14](https://www.hklaw.com/en/insights/publications/2026/10/sb-690-is-law-will-the-cipa-shakedown-continue), accessed 2026-11-21; [Morgan Lewis, 2026-10](https://www.morganlewis.com/pubs/2026/10/california-eliminates-private-right-of-action-under-cipas-pen-register-and-trap-and-trace-provision), accessed 2026-11-21; [Crowell](https://www.crowell.com/en/insights/client-alerts/california-governor-signs-sb-690-limiting-private-right-of-action-under-cipas-pen-register-and-trap-and-trace-provisions), accessed 2026-11-21. Commentators expect plaintiffs to shift to §631 and §632, and say the website-tracking wave "isn't over" — [Goodwin, 2026-09](https://www.goodwinlaw.com/en/insights/publications/2026/09/alerts-technology-cldr-california-curbs-cipa-pen-register-suits), accessed 2026-11-21.

**Mass arbitration**
- Under AAA's 2024 mass-arbitration rules (25+ similar cases), the flat initiation fee is $8,125 for the business and $3,125 for claimants, about $11,250 in total no matter how many cases are filed. Later per-case or arbitrator fees were not verified — [Mayer Brown, 2024-02-05](https://www.mayerbrown.com/en/insights/publications/2024/02/american-arbitration-association-adopts-new-mass-arbitration-rules-and-fee-schedules), accessed 2026-11-21; [AAA mass arbitration page](https://adr.org/rules-forms-and-fees/mass-arbitration/), accessed 2026-11-21.
- AAA received 82 consumer mass arbitrations covering 247,000+ individual filings in the period ending 2025 (secondary) — [Privacy World, 2026-11](https://www.privacyworld.blog/2026/11/mass-arbitration-is-not-slowing-down-what-the-aaas-data-means-for-2026-and-2027/), accessed 2026-11-21. Only 1% of consumer mass-arbitration cases that closed in 2024 ended in an award, so the pressure is mostly settlement leverage — [Skadden, 2025-04](https://www.skadden.com/insights/publications/2025/04/the-american-arbitration-association-infographic), accessed 2026-11-21.

**VPPA**
- *Solomon v. Flipps Media* (2d Cir., May 2025) limited PII to information an "ordinary person" could use to identify someone's viewing, which defeated Meta Pixel VPPA claims — [Morgan Lewis, 2025-07](https://www.morganlewis.com/pubs/2025/07/second-circuit-shuts-the-door-on-meta-pixel-vppa-claims), accessed 2026-11-21. The Supreme Court granted cert in *Salazar v. Paramount Global* (No. 25-459) on 2026-01-26 to decide who counts as a VPPA "consumer". It is set for the October 2026 term, and no decision was found — [Ropes & Gray, 2026-02](https://www.ropesgray.com/en/insights/alerts/2026/02/supreme-court-to-consider-the-video-privacy-protection-act), accessed 2026-11-21; [Cornell LII cert page](https://www.law.cornell.edu/supct/cert/25-459), accessed 2026-11-21.

**BIPA**
- SB 2979 (effective 2024-08-02) limits recovery to one per person for repeated collection of the same biometric. In April 2026 the Seventh Circuit held the amendment applies retroactively — [King & Spalding](https://www.kslaw.com/insights/articles/illinois-bipa-reform-takes-effect), accessed 2026-11-21; [ABA Business Law Today, 2026-05](https://www.americanbar.org/groups/business_law/resources/business-law-today/2026-may/7th-circuit-holds-bipa-damages-remedy-applies-retroactively), accessed 2026-11-21.

**ADA website and app suits**
- 5,114 ADA digital accessibility suits were filed in 2025 (1/1-12/15): 3,195 federal and 1,919 in NY/CA state courts. 64% targeted companies under $25M revenue. 1,427 hit companies sued before, and many targets already used accessibility overlay widgets. Top industries were e-commerce, food service and healthcare, with no software category — [UsableNet 2025 year-end report, 2025-12/2026-01](https://info.usablenet.com/2025-year-end-digital-accessibility-lawsuit-report-plain-text), accessed 2026-11-21.- Vendor estimates (interested sources) put small-business website settlements at $5,000-$20,000, with demand-letter-stage deals often lower — [Accessible.org](https://accessible.org/ada-website-compliance-lawsuit-settlement-amounts/), accessed 2026-11-21.

### Inferences
- The mills scan for trackers and money. A static GitHub Pages site with no analytics, no chat and no pixels gives CIPA scanners nothing to grab and gives ADA plaintiffs no transaction to complain about.
- The live exposure is a §631-style "third-party eavesdropping" theory about the app itself, since it sends screen content to Anthropic and Google. Clear, prior, recorded consent in onboarding (not buried in terms), plus accurate disclosures, is the cheap prevention. Constangy notes that retroactive consent does not work.
- Mass arbitration needs many claimants and a business that can pay. Whether miyagi's terms should use an arbitration clause at all, given the $8,125 initiation fee per campaign, is a question for the terms note.
- VPPA probably does not fit miyagi, because it does not rent, sell or deliver video. Still, it does learn which videos a user watches, so that data should not go to ad or analytics parties.

### Gaps
- No source gave demand amounts or settlement outcomes for free apps or sites with no revenue.
- Exact CIPA filing counts for 2023-2026 vary by tracker and were not verified from primary dockets.
- Whether ADA Title III reaches a web-only free app depends on the circuit. This was not researched.
- A search summary attributed a count of 3,117 federal website accessibility suits in 2025 (up 27% from 2,452) to Seyfarth Shaw, but the underlying page was not identified or fetched.
- A search summary put the total cost of a filed ADA website case for a small business at about $15,000-$90,000 (vendor blog), but the specific page was not confirmed.

## 3. Trademark disputes between startups sharing a name

### Takeaway
Most name fights end with letters, not lawsuits: a rebrand, a phase-out or a coexistence deal. TTAB oppositions are cheap to file ($600 per class), but taking one to trial can cost $75,000 or more and take more than two years. Rebranding early is the cheapest outcome.

### Cited Findings
- TTAB notice of opposition fee is $600 per class electronically ($700 on paper) — [USPTO fee schedule, rev. 2026-11-01](https://www.uspto.gov/learning-and-resources/fees-and-payment/uspto-fee-schedule), accessed 2026-11-21.
- Median total TTAB trial pendency was 142.1 weeks in FY2025, and the FY2026 page lists 136 weeks (search summary) — [USPTO TTAB filings and performance](https://www.uspto.gov/trademarks/ttab/ttab-incoming-filings-and-performance), accessed 2026-11-21.
- A fully litigated TTAB trial can be "$75,000 or more" — [LexBlog, 2021-07-26](https://www.lexblog.com/2021/07/26/u-s-trademark-opposition-facts-for-international-companies/), accessed 2026-11-21. Cheap oppositions run about $3,000-$15,000 when they settle early — [Patent Trademark Blog](https://www.patenttrademarkblog.com/trademark-opposition-cost/), accessed 2026-11-21. A vendor estimates about 95% of oppositions and cancellations settle before trial — [Trademarkraft (vendor)](https://trademarkraft.com/blogs/news/ttab-caseloads-vs-uspto-filings-trademark-opposition-cancellation-trends-2021-2025-why-95-settle-before-trial), accessed 2026-11-21.
- Coexistence agreements set permitted uses, channel limits and dispute procedures, and let both brands operate "without the cost, delay, or uncertainty of litigation." They often grow out of an exchange of cease-and-desist letters — [Troutman, 2026-09-28](https://www.troutman.com/insights/when-similar-marks-collide-the-role-of-coexistence-agreements/), accessed 2026-11-21.
- Many C&D letters overreach. Check the sender's registrations first. Common responses are a phase-out period, coexistence or asserting prior use. A name is easier to change early — [Traverse Legal](https://www.traverselegal.com/blog/demand-to-rebrand-a-guide-for-businesses/), accessed 2026-11-21.
- AIPLA 2023 reported rising median trademark litigation costs for cases with over $1M at risk. The figures are members-only — [AIPLA 2023 survey page](https://www.aipla.org/detail/journal-issue/2023-report-of-the-economic-survey), accessed 2026-11-21.

### Inferences
- For a free app with no registered mark, the realistic outcomes of a C&D from an established "Miyagi"-named business are a rebrand or a coexistence letter. A federal suit is unlikely unless the app ignores the letter and keeps growing.
- A free clearance search on USPTO's trademark search and a check of app stores and domains now costs nothing and avoids a forced rebrand later.

### Gaps
- No empirical rate was found for how often trademark C&Ds escalate to suits.
- Current AIPLA federal trademark suit costs (under $1M at risk) are not public.

## 4. Copyright: DMCA notices, creator claims, statutory damages, AI and video suits

### Takeaway
The fast, cheap threat is a DMCA takedown to GitHub, which can disable a repo within about one business day. The expensive threat is statutory damages, which need a timely registration under §412. Creator lawsuits so far target big AI firms that downloaded and trained on YouTube video, not small tools that look at a screen the user is already watching.

### Cited Findings
- Statutory damages run $750-$30,000 per work, up to $150,000 if willful, and as low as $200 if innocent — [17 U.S.C. §504, Cornell LII](https://www.law.cornell.edu/uscode/text/17/504), accessed 2026-11-21.
- §412 bars statutory damages and attorney's fees for infringement of an unpublished work that began before registration, and for infringement after publication but before registration, "unless such registration is made within three months after the first publication" — [17 U.S.C. §412, Cornell LII](https://www.law.cornell.edu/uscode/text/17/412), accessed 2026-11-21.
- GitHub gives the user about one business day to change content named in a takedown, or disables the whole repo at once if the notice claims the entire repo. After a counter-notice, content returns unless the claimant shows a filed lawsuit within 10-14 days. Repeat infringers may lose their accounts — [GitHub DMCA Takedown Policy](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy), accessed 2026-11-21.
- In 2024 a YouTuber filed a class action against OpenAI over transcribing YouTube videos, on unjust-enrichment and California unfair-competition theories — [TechCrunch, 2024-08-05](https://techcrunch.com/2024/08/05/youtuber-files-class-action-suit-over-openais-scrape-of-creators-transcripts/), accessed 2026-11-21.
- In 2026, creators filed proposed DMCA §1201 anti-circumvention class actions against Meta, ByteDance and Runway, and against Amazon, OpenAI and Apple, for downloading YouTube videos to train video models — [Law360, 2026-04-03](https://www.law360.com/ip/articles/2461742), accessed 2026-11-21; [Runway complaint, CourtListener, 2026-02-18](https://storage.courtlistener.com/recap/gov.uscourts.cand.461722/gov.uscourts.cand.461722.1.0.pdf), accessed 2026-11-21.

### Inferences
- miyagi's risk drops sharply if it never downloads videos or transcripts, never stores or redistributes frames, and only analyzes what is on the user's own screen. That keeps it out of the §1201 "circumventing YouTube's download protections" pattern. Earlier research in `Miyagi legal and privacy risks/youtube_copyright_trademark.md` covers YouTube's terms.
- Registering miyagi's own code or site copy within three months of publication keeps statutory damages available if someone copies it. That matters less than defense.

### Gaps
- No suits or letters against small edtech or AI video-summary tools were found for 2023-2026.
- No data was found on how often YouTube creators send letters to tool makers.

## 5. Data breach class actions against small companies

### Takeaway
Breach class actions are now filed even over small breaches, sometimes under 1,000 people, and are monetized early before class certification. TransUnion's standing rule gets many risk-of-harm-only claims dismissed. The best defense is having little sensitive data to lose.

### Cited Findings
- About 1,822 data privacy class actions were filed in 2025, up 18%. Courts granted dismissal motions more often, and only three class certification rulings were made in breach cases (plaintiffs won one) — [Duane Morris Class Action Review 2026 blog, 2026-01-21](https://blogs.duanemorris.com/classactiondefense/2026/01/21/video-dmcar-trend-6-data-privacy-filings-continued-to-grow-as-the-playbook-became-more-refined/), accessed 2026-11-21. The top 10 breach settlements in 2024 totaled $593.2M — [Duane Morris, 2025-02](https://www.duanemorris.com/pressreleases/duane_morris_llp_publishes_its_data_breach_class_action_review_2025_0225.html), accessed 2026-11-21.
- Bloomberg Law counted 1,446 breach class actions in H2 2025 and 1,421 in H1 2026, a plateau (search summary) — [Bloomberg Law analysis](https://news.bloomberglaw.com/bloomberg-law-analysis/analysis-plateau-in-data-breach-class-actions-continued-in-h1-correct), accessed 2026-11-21.
- Plaintiffs' firm websites have been found soliciting class members over breaches that affected fewer than 1,000 people (search summary) — [Constangy Cyber Advisor](https://www.constangy.com/constangy-cyber-advisor/minor-breaches-major-trouble-why-minor-cyber-incidents-can-lead-to-major-legal-fallout), accessed 2026-11-21.
- After *TransUnion v. Ramirez* (2021), every class member needs concrete injury to recover damages, and a bare risk of future harm generally does not create standing for damages — [Jenner & Block, 2021](https://www.jenner.com/en/news-insights/publications/supreme-court-limits-article-iii-standing-for-class-action-plaintiffs-implications-for-data-breach-class-actions), accessed 2026-11-21.

### Inferences
- A miyagi breach that exposes minors' screenshots, which could show anything on screen, would be an attractive suit even at small scale. Not storing screenshots, short retention, and not collecting identifiers like real names or emails reduce both the odds and the damages.

### Gaps
- No settlement ranges for small-company breaches (under 10,000 people) were found.
- Cyber insurance options for an unincorporated or teen-run project were not researched.

## 6. Small claims court (California)

### Takeaway
A user can sue in California small claims for up to $12,500 without lawyers on either side, for $30-$100 in fees. A defendant who loses can appeal, but a plaintiff who loses cannot. For a free app, a user would struggle to show money damages, but showing up is mandatory.

### Cited Findings
- Individuals can sue for up to $12,500 and businesses for up to $6,250. Lawyers can advise but cannot appear. Filing fees are $30-$100. A plaintiff who loses cannot appeal, and a defendant who loses can — [California Courts Self-Help, "Small claims in California", © 2026](https://selfhelp.courts.ca.gov/small-claims-basics), accessed 2026-11-21; [Santa Clara Superior Court, small claims](https://santaclara.courts.ca.gov/divisions/small-claims-division), accessed 2026-11-21.
- Larger claims go to limited civil court, where lawyers can appear, or the plaintiff waives the excess — [California Courts Self-Help](https://selfhelp.courts.ca.gov/small-claims-or-limited-civil), accessed 2026-11-21.

### Inferences
- The cheapest response to a small-claims suit is to attend with documents (terms, consent screens, logs), since a no-show can mean losing by default. A clinic or lawyer can prepare you beforehand.

### Gaps
- No data on how often users sue app makers in small claims was found.
- Rules for minors as parties (a guardian ad litem may be needed) and the cap on repeat small-claims filings were not verified.

## 7. What defense costs and where to get free or cheap help

### Takeaway
Real defense costs start in the tens of thousands for a TTAB trial or a CIPA motion and reach $600K+ for patent discovery. California has several free startup law clinics, USPTO-certified IP clinics, LOT Network, Unified Patents and California Lawyers for the Arts' low-cost referrals.

### Cited Findings
- Costs: patent $600,000 median through discovery with $1-10M at risk — [IPWatchdog/AIPLA 2025, 2026-10-01](https://ipwatchdog.com/2026/10/01/the-true-cost-of-patent-infringement-litigation-enforcement-and-defense-in-a-complex-market/), accessed 2026-11-21. TTAB trial $75,000+ — [LexBlog, 2021](https://www.lexblog.com/2021/07/26/u-s-trademark-opposition-facts-for-international-companies/), accessed 2026-11-21. A CIPA motion to dismiss usually costs more than an individual settlement — [Holland & Knight, 2026-10-14](https://www.hklaw.com/en/insights/publications/2026/10/sb-690-is-law-will-the-cipa-shakedown-continue), accessed 2026-11-21. Small-business ADA website settlements run about $5,000-$20,000 (vendor estimate) — [Accessible.org (vendor)](https://accessible.org/ada-website-compliance-lawsuit-settlement-amounts/), accessed 2026-11-21.
- Stanford Law's Entrepreneurship Clinic gives free transactional help to early-stage startups — [Stanford News, 2025-07](https://news.stanford.edu/stories/2025/07/law-school-entrepreneurship-clinic-legal-support-startups), accessed 2026-11-21. UC Irvine's Startup and Small Business Clinic serves Orange County and nearby, and holds office hours with the UCI ANTrepreneur Center — [UCI Law](https://www.law.uci.edu/academics/real-life-learning/clinics/startup-small-business.html), accessed 2026-11-21. Berkeley's New Business Community Law Clinic serves low-income entrepreneurs (East Bay and Central Valley) — [Berkeley Law](https://www.law.berkeley.edu/experiential/clinics/new-business-community-law-clinic/our-work/), accessed 2026-11-21. Others are Santa Clara's Entrepreneurs' Law Clinic — [SCU](https://law.scu.edu/centers/elc/services/), accessed 2026-11-21 — Pepperdine's Startup Law Clinic, focused on tech startups — [Pepperdine](https://law.pepperdine.edu/palmer-center/startuplawclinic.htm), accessed 2026-11-21 — and USC's Small Business Clinic (2017 article; confirm it still runs) — [USC News](https://today.usc.edu/professors-brainchild-evolves-into-highly-respected-legal-clinic/), accessed 2026-11-21.
- The USPTO Law School Clinic Certification Program has 70+ clinics doing pro bono patent and trademark work. California participants on the Nov 2025 map include UCI, UCLA, USD, USF and Thomas Jefferson — [USPTO map, 2025-11-19](https://www.uspto.gov/sites/default/files/documents/Law-School-Clinic-Map-19Nov2025.pdf), accessed 2026-11-21; [USPTO program page](https://www.uspto.gov/lawschoolclinic), accessed 2026-11-21. UCLA's clinic charges no fees — [UCLA Law](https://law.ucla.edu/academics/clinical-and-experiential-programs/uspto-patents-trademarks), accessed 2026-11-21.
- California Lawyers for the Arts runs a State Bar-certified referral service with regular, pro bono and modest-means tiers. A volunteer staff attorney consult is $35 ($20 for members). It says it is temporarily narrowing the matters it refers — [CLA LRIS](https://calawyersforthearts.org/lris-cla/), accessed 2026-11-21.
- LOT Network is free under $25M revenue — [Legal Dive](https://www.legaldive.com/news/patenttrolls-LOTnetwork-patentassertionentities-Google-Dropbox-Microsoft-intellectualproperty-IP/626065/), accessed 2026-11-21.

### Inferences
- UCI's clinic and the UCI/UCLA USPTO clinics are the closest free options for Southern California founders, and Stanford, Berkeley and Santa Clara cover the Bay Area. Most transactional clinics do not litigate, so they help with letters, terms and trademarks, not with defending a lawsuit.

### Gaps
- No reliable figure was found for what a lawyer charges to answer a demand letter.
- Whether clinics take clients under 18 or require an entity or a parent was not researched.
- Google for Startups or accelerator legal credits, and pro bono litigation defense programs, were not researched.
- Insurance notice duties and which policies, if any, cover a teen-run app were not researched.

## 8. Playbook for a demand letter, subpoena or lawsuit

### Takeaway
A letter is not a lawsuit, but a served complaint has hard deadlines: 30 days in California state court and 21 days in federal court. Preserve everything, don't admit anything, don't reply on your own, and get a clinic or lawyer in the first week.

### Cited Findings
- California: file a written response within 30 calendar days of service (CCP §412.20). Substitute service adds time; Sacramento court guidance gives 40 days (search summary — [Sacramento Superior Court guide](https://ftp.saccourt.ca.gov/civil/docs/cv-responding-to-a-complaint.pdf), accessed 2026-11-21). The parties can agree to a 15-day extension (CRC 3.110(d)). A missed deadline allows a request for default, and setting a default aside is hard — [California Courts Self-Help, "Decide what to do if you're sued"](https://selfhelp.courts.ca.gov/node/1582), accessed 2026-11-21; [Self-Help, default](https://selfhelp.courts.ca.gov/civil-lawsuit/defendant/default), accessed 2026-11-21; [Sacramento County Public Law Library](https://saclaw.org/respond-to-lawsuit), accessed 2026-11-21.
- Federal: answer within 21 days after service, or 60 days if service is waived — [FRCP 12(a), Cornell LII](https://www.law.cornell.edu/rules/frcp/rule_12), accessed 2026-11-21.
- For privacy demand letters: route to counsel, don't let non-lawyers reply, don't ignore even a templated letter, preserve the site configuration (screenshots, tag-manager exports, consent settings), and don't pay before investigating — [Ward and Smith via NLR, 2026-07-16](https://natlawreview.com/article/cipa-demand-letter-wave-how-one-serial-litigant-turning-basic-websites-tsunami), accessed 2026-11-21. Document what your tools collect, and consider dismissal or a declaratory suit instead of paying — [Fisher Phillips, 2026-07-16](https://www.fisherphillips.com/en/insights/insights/businesses-fight-back-against-vivek-shahs-privacy-demand-letter-spree), accessed 2026-11-21.
- For patent letters: no legal duty to respond to a letter — [EFF, 2011](https://www.eff.org/issues/faqs-lodsys-targets), accessed 2026-11-21 — but willfulness exposure exists — [Halo, Justia](https://supreme.justia.com/cases/federal/us/579/93/), accessed 2026-11-21.
- For DMCA takedowns: respond within GitHub's roughly one-business-day window, or file a counter-notice — [GitHub DMCA policy](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy), accessed 2026-11-21.

### Inferences
- A one-page runbook should cover: date-stamp and save the letter or envelope; check whether it is a letter, a served summons or a subpoena; calendar the deadline; freeze deletion of relevant logs and configs; reply to no one; contact a clinic, CLA or a lawyer; and notify any insurer if a policy exists.

### Gaps
- No source was researched on subpoena response duties for third-party data (for example a subpoena for a user's data). This should be covered when writing the privacy policy.

## Implications for miyagi (ranked by likelihood at launch scale)

### Takeaway
At launch, miyagi's most likely legal friction is cheap and fixable: platform takedowns, name disputes and user complaints. The expensive kinds (patent suits, class actions) need revenue, funding or a breach to become likely. Prevention is mostly design choices made now.

### Cited Findings
- See sections 1-8. Key anchors: NPE targets average $65M raised — [TechCrunch, 2023-07-28](https://techcrunch.com/2023/07/28/the-anatomy-of-a-patent-litigation-target/), accessed 2026-11-21. CIPA mills key off trackers — [NLR, 2026-07-16](https://natlawreview.com/article/cipa-demand-letter-wave-how-one-serial-litigant-turning-basic-websites-tsunami), accessed 2026-11-21. Breach suits hit small breaches — [Constangy](https://www.constangy.com/constangy-cyber-advisor/minor-breaches-major-trouble-why-minor-cyber-incidents-can-lead-to-major-legal-fallout), accessed 2026-11-21. GitHub takedowns move in about one business day — [GitHub](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy), accessed 2026-11-21.

### Inferences
Ranking (most to least likely for a free, teen-built app at launch scale; judgment, not data):

1. **DMCA or platform complaint (GitHub, YouTube, app stores).** Prevention: never download, store or redistribute video, frames or transcripts; keep third-party assets licensed; keep the repo free of others' content. Cheapest response: fix and confirm within GitHub's window, or file a counter-notice if the claim is wrong. Lawyer needed: a claimant files a lawsuit after a counter-notice, or claims statutory damages on a registered work.
2. **Trademark C&D over the name.** Prevention: run a free USPTO and app-store search now and keep a fallback name. Cheapest response: check the sender's registrations and classes, then offer a phase-out or coexistence, or rebrand while it is cheap. Lawyer needed: a TTAB opposition is filed against a miyagi application, or a federal complaint is served (use a USPTO clinic such as UCI or UCLA).
3. **Privacy complaint or demand letter about the app's data flow (CIPA §631 theory, minors' data).** Prevention: clear, prior, logged in-app consent before any capture (a parent path for teens per the earlier privacy research), no analytics or pixels on the site or in the app, accurate privacy policy, and minimal retention. Cheapest response: don't reply yourself or pay; preserve configs; take it to a clinic. Many letters fold when there is no tracker and documented consent. Lawyer needed: a served complaint, an arbitration demand, or a regulator letter.
4. **Small-claims suit by a user or parent.** Prevention: free app, no promises of results, clear terms and disclaimers. Cheapest response: show up with documents, since no lawyers are allowed in court; the defendant can appeal. Lawyer needed: only for advice beforehand, or if the case moves to limited civil.
5. **Data breach suit (only if the server leaks data).** Prevention: don't keep screenshots after grading, encrypt, keep few identifiers, and have a breach-notice plan. Cheapest response: notify as the law requires, then raise TransUnion standing in any suit. Lawyer needed: any breach involving minors' data, right away.
6. **Patent troll letter.** Prevention: stay pre-revenue and quiet about funding; join LOT Network (free under $25M) once there is an entity; report letters to Unified Patents. Cheapest response: don't ignore or admit; log it; get a free read from a clinic or EFF; note there is no revenue. Lawyer needed: a complaint is served (21-day federal clock), or the letter names a specific product and patent with a lawsuit draft.
7. **ADA website or app accessibility suit.** Prevention: accessible static site (alt text, contrast, keyboard navigation) and no overlay widgets (overlay users still get sued). Cheapest response: fix and document. Lawyer needed: a served complaint.
8. **VPPA or BIPA.** Near zero, since miyagi does not deliver video or collect biometrics. Keep it that way: no face or voice templates, and no viewing history sent to ad or analytics parties.

### Gaps
- The ranking is judgment, not data. No dataset covers lawsuits against free, teen-built apps.
- Whether the founders, as minors and possibly without an entity, would be personally named, and how guardian-ad-litem and parental-liability rules apply, needs checking against the business-setup note (`Miyagi legal and privacy risks/platforms_business_setup.md`).
