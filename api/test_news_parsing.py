from api.main import deduplicate_articles, sanitize_article


def article(**kwargs):
    value = {
        "id": "1", "group_id": "g1", "title": "Story", "url": "https://example.com",
        "publisher": "Example", "published_date": "2026-10-15T07:30:00",
        "original_language": "EN", "sentiment": "Positive", "newsworthiness_score": 0.6,
        "ai_summary": "Summary", "tags": [{"code": "CM01", "name": "Corporate", "is_primary": True}],
        "is_press_release": True, "is_breaking": True, "article_type": {"code": "NEWS", "label": "News"},
        "sentiment_score": 0.8, "entities": {"person": ["A Person"]},
    }
    value.update(kwargs)
    return value


def test_normalizes_fields_and_keeps_live_cache_fields():
    normalized = sanitize_article(article())
    assert normalized["sentiment"] == "positive"
    assert normalized["published_date"] == "2026-10-15T07:30:00"
    assert normalized["newsworthiness_score"] == 0.6
    assert normalized["tags"][0]["code"] == "CM01"
    assert normalized["types"] if "types" in normalized else True
    assert normalized["entities"]["person"] == ["A Person"]
    assert normalized["is_press_release"] and normalized["is_breaking"]


def test_uses_types_only_when_tags_key_is_missing():
    normalized = sanitize_article(article(tags=None, types=[{"code": "WT02", "name": "Risk"}]))
    assert normalized["tags"] == []
    legacy = article()
    legacy.pop("tags")
    legacy["types"] = [{"code": "WT02", "name": "Risk"}]
    assert sanitize_article(legacy)["tags"][0]["code"] == "WT02"


def test_deduplicates_group_prefer_english_then_score_and_same_day_tag_translations():
    translated = article(id="fr", original_language="FR", newsworthiness_score=0.99, published_date="2026-10-15T06:00:00")
    english = article(id="en", original_language="EN", newsworthiness_score=0.2)
    other_translation = article(id="de", group_id="different", original_language="DE", published_date="2026-10-15T08:00:00", newsworthiness_score=0.9)
    result = deduplicate_articles([translated, english, other_translation])
    assert [item["id"] for item in result] == ["en"]
