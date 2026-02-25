from app.core.quality import assess_text_quality

def test_quality_empty():
    score, signals, reasons = assess_text_quality("")
    assert score == 0.0
    assert "EMPTY" in reasons

def test_quality_readable_better():
    good = "這是一段正常的中文段落，包含一些英文 ABC 123。\n\n第二段也正常。"
    bad = "| | | \n _ _ _ \n @@##$$%%^^"
    s1, _, _ = assess_text_quality(good)
    s2, _, _ = assess_text_quality(bad)
    assert s1 > s2
