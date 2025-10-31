# sbir-etl/tests/unit/ml/test_patent_classifier.py


from src.ml.models.dummy_pipeline import DummyPipeline
from src.ml.models.patent_classifier import PatentCETClassifier, PatentClassification


def make_dummy_pipelines():
    """
    Return two dummy pipelines:
      - 'artificial_intelligence' with keywords ['machine learning']
      - 'quantum_information_science' with keywords ['quantum', 'qubit']
    These mirror the tiny synthetic pipelines used elsewhere in tests.
    """
    pipes = {
        "artificial_intelligence": DummyPipeline(
            cet_id="artificial_intelligence", keywords=["machine learning"], keyword_boost=1.0
        ),
        "quantum_information_science": DummyPipeline(
            cet_id="quantum_information_science", keywords=["quantum", "qubit"], keyword_boost=1.0
        ),
    }
    return pipes


def test_single_classify_prefers_expected_cet():
    pipelines = make_dummy_pipelines()
    classifier = PatentCETClassifier(pipelines=pipelines)

    # Text clearly about ML should prefer the AI CET
    res_ai = classifier.classify("A study of machine learning methods for imaging sensors")
    assert isinstance(res_ai, list) and len(res_ai) >= 1
    top = res_ai[0]
    assert isinstance(top, PatentClassification)
    assert top.cet_id == "artificial_intelligence"
    assert top.score >= 0.0

    # Text clearly about quantum should prefer the quantum CET
    res_q = classifier.classify("Improved qubit coherence for quantum sensing applications")
    assert isinstance(res_q, list) and len(res_q) >= 1
    top_q = res_q[0]
    assert isinstance(top_q, PatentClassification)
    assert top_q.cet_id == "quantum_information_science"
    assert top_q.score >= 0.0


def test_classify_batch_returns_sorted_top_k():
    pipelines = make_dummy_pipelines()
    classifier = PatentCETClassifier(pipelines=pipelines)

    titles = [
        "Deep neural networks and machine learning for image analysis",
        "Quantum algorithm and qubit control",
        "An unrelated materials engineering title",
    ]
    results = classifier.classify_batch(titles, top_k=2)
    assert isinstance(results, list)
    assert len(results) == len(titles)

    # For the first title, top CET should be AI
    first_top = results[0][0]
    assert first_top.cet_id == "artificial_intelligence"

    # For the second title, top CET should be quantum
    second_top = results[1][0]
    assert second_top.cet_id == "quantum_information_science"

    # The third title has no matching keywords and should yield low/zero scores:
    third_row = results[2]
    # Even if both CETs are present, their scores should be numeric and sorted descending
    assert all(isinstance(c.score, float) for c in third_row)
    scores = [c.score for c in third_row]
    assert scores == sorted(scores, reverse=True)


def test_save_and_load_roundtrip(tmp_path):
    pipelines = make_dummy_pipelines()
    classifier = PatentCETClassifier(
        pipelines=pipelines, taxonomy_version="TEST-2025Q1", config={"model_version": "vtest"}
    )

    model_file = tmp_path / "patent_model_test.pkl"
    classifier.save(model_file)

    # Ensure file exists
    assert model_file.exists()

    # Load back
    loaded = PatentCETClassifier.load(model_file)
    assert isinstance(loaded, PatentCETClassifier)
    meta = loaded.get_metadata()
    assert meta.get("taxonomy_version") == "TEST-2025Q1" or loaded.taxonomy_version == "TEST-2025Q1"

    # Behavior should be the same on a sample text
    title = "Novel machine learning approach to image segmentation"
    orig_top = classifier.classify(title)[0].cet_id
    loaded_top = loaded.classify(title)[0].cet_id
    assert orig_top == loaded_top


def test_no_pipelines_returns_empty_lists():
    classifier = PatentCETClassifier(pipelines={})
    titles = ["Any title", "Another title"]
    results = classifier.classify_batch(titles)
    assert isinstance(results, list)
    assert len(results) == len(titles)
    # Each entry should be an empty list when no pipelines are configured
    assert all(isinstance(r, list) and len(r) == 0 for r in results)
