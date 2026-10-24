from datetime import date, timedelta

from api.main import calculate_pulse, classify_article


def signal(code, sentiment="neutral", name="Tag Name", published_date="2026-10-24T12:00:00"):
    return {"tags": [{"code": code, "name": name, "is_primary": True}], "sentiment": sentiment, "published_date": published_date, "severity": 1}


def test_funding_classification():
    result = classify_article(signal("CM01"))
    assert (result["category"], result["severity"], result["suggested_action"]) == ("Funding", 2, "Congratulate; offer intros to later-stage investors")


def test_people_negative_classification():
    result = classify_article(signal("WT02"))
    assert result["category"] == "People" and result["severity"] == 3
    assert result["suggested_action"] == "Check-in call with the founder this week"


def test_people_positive_classification():
    result = classify_article(signal("WT01"))
    assert result["category"] == "People" and result["severity"] == 1
    assert result["suggested_action"] == "Congratulate the new leader"


def test_product_classification():
    result = classify_article({**signal("SD01"), "sentiment": "positive"})
    assert result["category"] == "Product" and result["severity"] == 1
    assert result["suggested_action"] == "Amplify it; offer customer intros"
    assert classify_article({**signal("SD01"), "sentiment": "neutral"})["suggested_action"] == "Note it for the next portfolio update"


def test_corporate_classification():
    result = classify_article(signal("CM03"))
    assert result["category"] == "Corporate" and result["severity"] == 3
    assert result["suggested_action"] == "Exit tracking; prepare the LP disclosure"


def test_risk_classification():
    result = classify_article(signal("RC03"))
    assert result["category"] == "Risk" and result["severity"] == 3
    assert result["suggested_action"] == "Risk flag: call the founder, prepare an LP note"


def test_negative_funding_escalates_to_risk():
    result = classify_article(signal("CM02", sentiment="negative"))
    assert result["category"] == "Risk" and result["severity"] == 3


def test_lg01_negative_people_classification():
    result = classify_article(signal("LG01", sentiment="negative"))
    assert result["category"] == "People" and result["severity"] == 3


def test_lg01_neutral_people_positive_classification():
    result = classify_article(signal("LG01", sentiment="neutral"))
    assert result["category"] == "People" and result["severity"] == 1


def test_unmapped_tag_is_dropped_as_noise():
    assert classify_article(signal("MD01")) is None


def test_pulse_decay_uses_half_life_of_90_days():
    today = date(2026, 10, 24)
    one_event = {"severity": 2, "published_date": (today - timedelta(days=90)).isoformat() + "T12:00:00"}
    assert calculate_pulse([one_event], today=today) == 1.0
    assert calculate_pulse([{**one_event, "published_date": today.isoformat()}], today=today) == 2.0


def test_negative_explainer_does_not_escalate_to_risk():
    article = signal("SD01", sentiment="negative")
    article["article_type"] = {"code": "explainer", "label": "Explainer"}
    result = classify_article(article)
    assert result["category"] == "Product" and result["severity"] == 1


def test_negative_reported_news_still_escalates_to_risk():
    article = signal("SD01", sentiment="negative")
    article["article_type"] = {"code": "news_analysis", "label": "News analysis"}
    assert classify_article(article)["category"] == "Risk"


def test_action_fits_the_story():
    from api.main import classify_article
    company = {"name": "Resy", "website": "resy.com"}
    base = {"tags": [{"code": "SD01", "name": "Product Launches"}], "article_type": {"code": "news_analysis"}, "published_date": "2026-10-20"}
    passing = classify_article({**base, "title": "Top 10 restaurant apps of 2026", "sentiment": "positive"}, company)
    assert passing["severity"] == 1 and passing["suggested_action"].startswith("Mentions the company in passing")
    bad = classify_article({**base, "title": "My AI agent got me banned from Resy", "sentiment": "negative", "article_type": {"code": "opinion"}}, company)
    assert "Amplify" not in bad["suggested_action"] and bad["suggested_action"].startswith("Read it")
    good = classify_article({**base, "title": "Resy launches a new booking feature", "sentiment": "positive"}, company)
    assert good["suggested_action"].startswith("Amplify it")


def test_ticker_headlines_are_market_noise():
    from api.main import is_market_noise
    assert is_market_noise({"title": "SoundHound AI (SOUN), Why Is It Getting Attention Today?", "publisher": "Yahoo"})
    assert not is_market_noise({"title": "Firefly Aerospace stock rises on Starcloud AI computing deal", "publisher": "Reuters"})
