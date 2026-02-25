from app.pipelines.extract import choose_route_auto

def test_auto_route_fallback_for_garbage():
    ocr_text = "| | | \n _ _ _ \n @@##$$%%^^" * 10
    decision, score, signals, reasons = choose_route_auto(ocr_text, threshold=0.9)
    assert decision == "vlm"
    assert score < 0.9
