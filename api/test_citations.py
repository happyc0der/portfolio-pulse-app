import pytest

from api.citations import citation_checked_text, split_sentences


def numbered(*numbers):
    return [{"number": number} for number in numbers]


# Failure 1: abbreviations and initials split sentences mid-date (QA r2, The Browser Company).

def test_arc_shutdown_dates_are_not_split():
    raw = ("- **What happened:** Arc will stop receiving updates on Oct. 22, 2026, and is asking users to switch to its newer browser, Dia [1]. "
           "New accounts closed on Oct. 22, all Arc accounts will be deactivated on Dec. 22, and data will be deleted by Jan. 21, 2027 [1].\n"
           "- **Why it matters for our position:** The company is now betting entirely on Dia, an AI-first, Chromium-based browser with a $20/month Pro tier [2]. "
           "Headcount was 99 as of Oct. 1, 2026, compared with a peak of 135 in March 2025 [3].\n"
           "- **What to ask the founder:** What share of Arc users have moved to Dia ahead of the Dec. 22 deactivation date [1]?")
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2, 3), "partner_note")
    assert text == raw
    assert dropped == 0
    assert cited == [1, 2, 3]


@pytest.mark.parametrize("sentence", [
    "Arc stops updating on Jan. 5, Feb. 6, Mar. 7, Apr. 8, Jun. 9, Jul. 10 and Aug. 11 [1].",
    "Dia ships on Sep. 1, Sept. 2, Oct. 3, Nov. 4 or Dec. 5, 2026 [1].",
    "Acme Inc. sold the unit to Foo Corp. and Bar Co. Ltd. through Baz Holdings LLC. in a cash deal [1].",
    "Mr. Patel, Ms. Chen, Mrs. Ortiz and Dr. Okafor met on Main St. last week [1].",
    "The bid values Eliyan at approx. $3 billion, est. 3x the last round, vs. $1 billion in May [1].",
    "It ranked No. 3 in the U.S. and No. 5 in the U.K. by revenue [1].",
    "Chiplet buyers, e.g. hyperscalers, want one vendor, i.e. a single supplier [1].",
    "The round was led by J. Smith and A. B. Jones of Seligman Ventures [1].",
    "Revenue grew 3.5% to $1.25 billion, with gross margin at 61.2% [1].",
])
def test_abbreviations_initials_and_decimals_do_not_end_a_sentence(sentence):
    assert split_sentences(sentence) == [sentence]
    assert citation_checked_text(sentence, numbered(1), "partner_note") == (sentence, 0, [1])


def test_real_sentence_boundaries_still_split():
    assert split_sentences("Revenue rose 3.5% [1]. Eliyan closed a Series B. The round was led by Seligman [2]. Who led it? [2] Why now [1]?") == [
        "Revenue rose 3.5% [1].", "Eliyan closed a Series B.", "The round was led by Seligman [2].", "Who led it? [2]", "Why now [1]?"]
    text, dropped, _ = citation_checked_text("Eliyan closed a Series B. The round was led by Seligman [2].", numbered(2), "partner_note")
    assert text == "The round was led by Seligman [2]."
    assert dropped == 1


# Failure 2: sentences that state no fact were deleted (QA r5 lost its ask section, r7 lost 9 of 12 sentences).

def test_partner_note_keeps_uncited_questions_to_the_founder():
    raw = ("- **What happened:** The FTC has sent investigative demands to the health tech industry over how Epic Systems grants access to health data [2].\n"
           "- **Why it matters for our position:** Particle's headcount fell from 59 in February 2026 to 39 in October 2026, a 29% drop over six months [4].\n"
           "- **What to ask the founder:** How is the team resourcing the Epic litigation alongside the FTC probe? "
           "Which customers are waiting on the outcome before signing? What would a favorable ruling unlock for the pipeline?")
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2, 3, 4), "partner_note")
    assert text == raw
    assert dropped == 0
    assert cited == [2, 4]


def test_question_carrying_an_uncited_figure_is_dropped():
    raw = "- **What to ask the founder:** Is the current team enough to ship Dia on Windows? Is a team of 99, with 48 engineers, enough for both platforms?"
    text, dropped, _ = citation_checked_text(raw, numbered(1), "partner_note")
    assert text == "- **What to ask the founder:** Is the current team enough to ship Dia on Windows?"
    assert dropped == 1


def test_founder_email_keeps_pleasantries_offer_question_and_signoff():
    raw = ("Hi,\n"
           "Congrats on a big month for Eliyan. Eliyan introduced its Nexus and Oscar chiplets at OCP Summit 2026, and both are sampling now [3]. "
           "That follows the oversubscribed $145 million Series C at a $1 billion valuation [8]. Your engineering team grew 40% this year.\n"
           "I'd be glad to introduce you to the infrastructure leads at two hyperscalers in our network who are evaluating chiplet interconnects. "
           "Would a short call next week work? Let me know what would be most useful.\n"
           "Talk soon,\n"
           "Priya Raman\n"
           "Partner, Plug and Play Ventures")
    text, dropped, cited = citation_checked_text(raw, numbered(*range(1, 18)), "founder_email")
    assert text == ("Hi,\n"
                    "Congrats on a big month for Eliyan.\n"
                    "Eliyan introduced its Nexus and Oscar chiplets at OCP Summit 2026, and both are sampling now [3].\n"
                    "That follows the oversubscribed $145 million Series C at a $1 billion valuation [8].\n"
                    "I'd be glad to introduce you to the infrastructure leads at two hyperscalers in our network who are evaluating chiplet interconnects.\n"
                    "Would a short call next week work?\n"
                    "Let me know what would be most useful.\n"
                    "Talk soon,\n"
                    "Priya Raman\n"
                    "Partner, Plug and Play Ventures")
    assert dropped == 1
    assert cited == [3, 8]


@pytest.mark.parametrize("sentence, kept", [
    ("This could be a meaningful outcome for the fund.", True),
    ("It is worth watching closely before the next board meeting.", True),
    ("Eliyan is now the frontrunner in chiplet interconnects.", False),  # name as first word, used mid-sentence below
    ("The bidder is reportedly Marvell.", False),
    ("Revenue tripled last year.", False),
    ("Headcount fell 29% over six months.", False),
    ("The round was priced at $1 billion.", False),
])
def test_uncited_statement_is_kept_only_without_names_or_quantities(sentence, kept):
    raw = f"- **Why it matters for our position:** The bid came two months after Eliyan raised its Series C [1]. {sentence}"
    text, dropped, _ = citation_checked_text(raw, numbered(1), "partner_note")
    assert (sentence in text, dropped) == (kept, 0 if kept else 1)


def test_unknown_citation_is_dropped_even_in_a_question_or_offer():
    raw = "Who is the bidder [9]? I'd be happy to introduce you to the Arm team [7]. Why did Arm walk away [1]?"
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2), "partner_note")
    assert text == "Why did Arm walk away [1]?"
    assert dropped == 2
    assert cited == [1]


# Failure 3: a label whose content is all dropped must not dangle; headings stay.

def test_label_on_its_own_line_is_dropped_when_everything_under_it_is_dropped():
    raw = ("**What happened:**\n"
           "- Arc will stop receiving updates on Oct. 22, 2026, and is asking users to switch to Dia [1].\n"
           "**Why it matters for our position:**\n"
           "- Headcount is down 19% over 24 months, and engineering has 48 people [3].\n"
           "**What to ask the founder:**\n"
           "- The team shrank from a peak of 135 people in March 2025.")
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2, 3), "partner_note")
    assert text == ("**What happened:**\n"
                    "- Arc will stop receiving updates on Oct. 22, 2026, and is asking users to switch to Dia [1].\n"
                    "**Why it matters for our position:**\n"
                    "- Headcount is down 19% over 24 months, and engineering has 48 people [3].")
    assert dropped == 1
    assert cited == [1, 3]


def test_nested_bullet_label_is_dropped_when_its_sub_bullets_are_dropped():
    raw = ("- **What happened:**\n"
           "  - Arc will stop receiving updates on Oct. 22, 2026 [1].\n"
           "- **What to ask the founder:**\n"
           "  - Is a team of 99 enough to ship Dia on Windows?")
    text, dropped, _ = citation_checked_text(raw, numbered(1), "partner_note")
    assert text == "- **What happened:**\n- Arc will stop receiving updates on Oct. 22, 2026 [1]."
    assert dropped == 1


def test_lp_update_drops_an_empty_company_label_but_keeps_headings_and_actions():
    raw = ("## Portfolio highlights\n"
           "- **Reco (2026-10-15):** Reco raised an additional $55 million, bringing total funding to $140 million [22].\n"
           "## Companies to watch\n"
           "**Starcloud**\n"
           "- **Concern:** Starcloud raised nearly $500 million for a plan to mine Bitcoin in orbit [12].\n"
           "- **Action:** Ask for the updated launch timeline and how cooling will be solved.\n"
           "**Trulioo**\n"
           "- **Concern:** 93% of firms saw more bot traffic over the prior 12 months.\n"
           "## Outlook\n"
           "**Next quarter:**\n"
           "- Three more companies plan to raise.")
    text, dropped, cited = citation_checked_text(raw, numbered(12, 22), "partner_note")
    assert text == ("## Portfolio highlights\n"
                    "- **Reco (2026-10-15):** Reco raised an additional $55 million, bringing total funding to $140 million [22].\n"
                    "## Companies to watch\n"
                    "**Starcloud**\n"
                    "- **Concern:** Starcloud raised nearly $500 million for a plan to mine Bitcoin in orbit [12].\n"
                    "- **Action:** Ask for the updated launch timeline and how cooling will be solved.\n"
                    "## Outlook")
    assert dropped == 2
    assert cited == [12, 22]


# Existing behaviour that must hold.

def test_uncited_factual_sentence_is_dropped():
    sources = [{"number": 4, "title": "Networking startup Eliyan gets takeover interest, held early talks with Arm"},
               {"number": 8, "title": "Eliyan Completes $145 Million Series C"}]
    raw = "Eliyan raised $145 million at a $1 billion valuation [8]. Arm held early talks before opting out. Marvell bought Celestial AI for $2.35 billion."
    text, dropped, cited = citation_checked_text(raw, sources, "partner_note")
    assert text == "Eliyan raised $145 million at a $1 billion valuation [8]."
    assert dropped == 2
    assert cited == [8]


def test_sentence_opening_with_a_company_from_a_label_or_source_is_dropped():
    raw = ("- **Dropbox (2026-10-23):** Dropbox reported Q3 EPS of $0.75, which beat estimates [3]. Dropbox shares rose after the report.\n"
           "- **Reco (2026-10-15):** Reco raised an additional $55 million [22]. Forestay joined the round as well. That is a good sign.")
    sources = [{"number": 3, "company": "Dropbox"}, {"number": 22, "company": "Reco", "ai_summary": "Reco raised $55 million with AT&T Ventures, Forestay and Quadrille Capital."}]
    text, dropped, _ = citation_checked_text(raw, sources, "partner_note")
    assert text == ("- **Dropbox (2026-10-23):** Dropbox reported Q3 EPS of $0.75, which beat estimates [3].\n"
                    "- **Reco (2026-10-15):** Reco raised an additional $55 million [22]. That is a good sign.")
    assert dropped == 2


def test_citation_to_an_unknown_source_is_dropped():
    raw = "Tether blacklisted USDT wallets linked to CoinDCX outflows [1]. AMLBot froze about $2.2 million [4]. CoinDCX lost $44 million [1][5]."
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2, 3), "partner_note")
    assert text == "Tether blacklisted USDT wallets linked to CoinDCX outflows [1]."
    assert dropped == 2
    assert cited == [1]


@pytest.mark.parametrize("greeting, signoff", [
    ("Hi Dimitri,", "Best,\n[Name]"),
    ("Hello Mei,", "Warm regards,\nDevon"),
    ("Dear Ofer,", "Best, Jordan"),
    ("Hey Ramin,", "Cheers,\nKeshav Rajput\nPlug and Play Ventures"),
])
def test_email_greeting_and_signoff_are_kept_without_citations(greeting, signoff):
    body = "The AgentIQ launch lets customers run their program from prompts or agents like Claude and Copilot [2]."
    raw = f"{greeting}\n{body}\nYour revenue doubled last quarter.\n{signoff}"
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2), "founder_email")
    assert text == f"{greeting}\n{body}\n{signoff}"
    assert dropped == 1
    assert cited == [2]


def test_partner_note_keeps_bullets_and_bold_labels():
    raw = ("- **What happened:** Eliyan has received at least one takeover bid, and the options could value the company at up to $3 billion [1]. "
           "The company told investors about the bid but did not name the buyer, and Arm held early talks before opting out [2].\n"
           "- **Why it matters for our position:** The bid came two months after Eliyan raised $145 million at a $1 billion valuation [1]. "
           "Seligman Ventures led that Series C.\n"
           "- **What to ask the founder:** Who is the bidder, and is the $3 billion figure an actual offer price [1][2]? Is the board leaning toward a sale [1]?")
    text, dropped, cited = citation_checked_text(raw, numbered(1, 2, 3), "partner_note")
    lines = text.splitlines()
    assert [line[:40] for line in lines] == [line[:40] for line in raw.splitlines()]
    assert lines[1] == "- **Why it matters for our position:** The bid came two months after Eliyan raised $145 million at a $1 billion valuation [1]."
    assert dropped == 1
    assert cited == [1, 2]


def test_cited_numbers_are_returned_sorted_and_unique():
    raw = "Reco raised $55M [24][22]. Total funding is $140M [22]. Skan AI raised $63M [27]."
    assert citation_checked_text(raw, numbered(22, 24, 27), "partner_note")[2] == [22, 24, 27]


def test_citation_after_the_full_stop_stays_with_its_sentence():
    text, dropped, cited = citation_checked_text("Reco raised $55M. [1] Total funding hit $140M.", numbered(1), "partner_note")
    assert text == "Reco raised $55M. [1]"
    assert dropped == 1
    assert cited == [1]
