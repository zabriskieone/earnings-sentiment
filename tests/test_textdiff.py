from earnings_sentiment.textdiff import diff_sentences, normalize, word_diff


def test_normalize_masks_numbers_dates_and_years():
    a = normalize("Net sales increased 12% to $114.5 billion during fiscal 2026, as of September 26, 2026.")
    b = normalize("Net sales increased 8% to $102.5 billion during fiscal 2025, as of September 27, 2025.")
    assert a == b


def test_diff_classifies_sentences():
    old = [
        "iPhone net sales increased 6% due to higher sales of Pro models.",
        "The Company faces intense competition in all markets.",
        "Gross margin was negatively affected by the weaker yen.",
        "The Company repurchased shares under its program.",
    ]
    new = [
        "iPhone net sales increased 11% due to higher sales of Pro models.",          # figure update -> unchanged
        "The Company faces intense competition in all of its markets and channels.",  # reworded
        "The Company is experiencing supply constraints for memory and storage.",     # added
        "The Company repurchased shares under its program.",                           # unchanged
    ]
    r = diff_sentences(new, old)
    assert r.unchanged == 2
    assert [c.text for c in r.added] == ["The Company is experiencing supply constraints for memory and storage."]
    assert [c.text for c in r.removed] == ["Gross margin was negatively affected by the weaker yen."]
    assert len(r.reworded) == 1 and "channels" in r.reworded[0].text and "competition" in r.reworded[0].before
    assert 0 < r.share_changed < 1


def test_word_diff_marks_insertions_and_deletions():
    ops = word_diff("faces intense competition in all markets", "faces intense competition in all of its markets")
    assert ("+", "of its") in ops and all(op in "=+-" for op, _ in ops)


def test_identical_documents_have_no_changes():
    s = ["Revenue grew strongly in the quarter across every region.", "Services reached a new all-time record."]
    r = diff_sentences(s, list(s))
    assert r.unchanged == 2 and not (r.added or r.removed or r.reworded)


def test_word_diff_ignores_rolled_forward_years_and_figures():
    ops = word_diff("Mac net sales increased during 2025 compared to 2024 due to laptops and desktops.",
                    "Mac net sales increased during 2026 compared to 2025 due to laptops.")
    changed = [t for op, t in ops if op != "="]
    assert changed == ["and desktops.", "laptops."] or all("202" not in t for t in changed)
