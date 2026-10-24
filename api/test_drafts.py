from api.main import citation_checked_text


def test_citation_check_drops_uncited_and_unknown_sources():
    text, dropped, cited = citation_checked_text("Supported detail [1]. Uncited assertion. Fake claim [9]. Another fact [2].", [{"number": 1}, {"number": 2}], "partner_note")
    assert text == "Supported detail [1].\nAnother fact [2]."
    assert dropped == 2
    assert cited == [1, 2]


def test_email_allows_greeting_and_signoff_without_citations():
    text, dropped, cited = citation_checked_text("Hi Alex,\nWe saw the launch [1].\nBest,\nJordan", [{"number": 1}], "founder_email")
    assert text == "Hi Alex,\nWe saw the launch [1].\nBest,\nJordan"
    assert dropped == 0
    assert cited == [1]


def test_email_two_line_signoff_is_kept_without_citations():
    text, dropped, cited = citation_checked_text("Hello Mei,\nThe product launch is public [1].\nWarm regards,\nDevon", [{"number": 1}], "founder_email")
    assert text == "Hello Mei,\nThe product launch is public [1].\nWarm regards,\nDevon"
    assert dropped == 0
    assert cited == [1]


def test_email_uncited_middle_claim_is_dropped_but_greeting_and_signoff_remain():
    text, dropped, cited = citation_checked_text("Hi Ofer,\nWe saw the launch [1].\nYour revenue doubled last quarter.\nBest,\nKeshav", [{"number": 1}], "founder_email")
    assert text == "Hi Ofer,\nWe saw the launch [1].\nBest,\nKeshav"
    assert dropped == 1
    assert cited == [1]


def test_partner_note_keeps_bullets_and_bold_labels():
    raw = ("- **What happened:** Eliyan received a takeover bid [1]. Arm held early talks [2].\n"
           "- **Why it matters for our position:** A sale near $3 billion triples the last round [3]. It is a great outcome.\n"
           "- **What to ask the founder:** Who is the bidder [1]?")
    text, dropped, cited = citation_checked_text(raw, [{"number": 1}, {"number": 2}, {"number": 3}], "partner_note")
    assert text == ("- **What happened:** Eliyan received a takeover bid [1]. Arm held early talks [2].\n"
                    "- **Why it matters for our position:** A sale near $3 billion triples the last round [3].\n"
                    "- **What to ask the founder:** Who is the bidder [1]?")
    assert dropped == 1
    assert cited == [1, 2, 3]


def test_headings_and_label_lines_are_kept_without_citations():
    raw = "## Portfolio highlights\n- Reco raised $55M [1].\n**Companies to watch:**\n- Eliyan may be sold [2]. Nobody knows why."
    text, dropped, cited = citation_checked_text(raw, [{"number": 1}, {"number": 2}], "partner_note")
    assert text == "## Portfolio highlights\n- Reco raised $55M [1].\n**Companies to watch:**\n- Eliyan may be sold [2]."
    assert dropped == 1


def test_citation_after_the_full_stop_stays_with_its_sentence():
    text, dropped, _ = citation_checked_text("Reco raised $55M. [1] Uncited claim.", [{"number": 1}], "partner_note")
    assert text == "Reco raised $55M. [1]"
    assert dropped == 1
