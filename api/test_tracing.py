from api.tracing import CONTEXT_LIMIT, STEP_LIMIT, retrieval_query, sources_context, sources_steps


def source(n: int, summary: str = "A summary sentence. " * 30) -> dict:
    return {"number": n, "title": f"Headline {n}", "publisher": "Reuters", "date": "2026-10-20T07:30:00", "ai_summary": summary}


def test_context_lists_every_source_number_within_prisms_limit():
    for count in (1, 4, 12, 60):
        text = sources_context([source(n) for n in range(1, count + 1)])
        assert len(text) <= CONTEXT_LIMIT
        assert all(f"[{n}] Headline {n} (Reuters, 2026-10-20)" in text for n in range(1, count + 1))


def test_context_keeps_short_summaries_whole():
    text = sources_context([source(1, "Eliyan is in talks to be acquired.")])
    assert "[1] Headline 1 (Reuters, 2026-10-20): Eliyan is in talks to be acquired." in text


def test_retrieval_query_names_the_company():
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": '{"company": {"name": "Eliyan"}}'}]
    assert retrieval_query(messages) == "akta.pro news and company data for Eliyan"
    assert retrieval_query([{"role": "user", "content": "not json"}]) == "akta.pro portfolio sources"


def test_first_step_names_the_full_range_and_every_number_within_the_judges_window():
    for count in (1, 6, 17, 44, 60):
        steps = sources_steps([source(n) for n in range(1, count + 1)])
        assert all(len(step) <= STEP_LIMIT for step in steps)
        assert f"{count} numbered akta.pro sources, [1] to [{count}]" in steps[0]
        assert all(f"[{n}] Headline" in steps[0] for n in range(1, count + 1))
        details = "\n".join(steps[1:])
        assert all(f"[{n}] Headline {n} (Reuters, 2026-10-20)" in details for n in range(1, count + 1))
