from app.services.embeddings import DeterministicEmbeddings


def test_deterministic_and_similar_texts_score_higher():
    e = DeterministicEmbeddings()
    a = e.embed_query("feature gating via flags")
    b = e.embed_query("feature gating via flags")
    assert a == b  # deterministic

    def dot(x, y):
        return sum(i * j for i, j in zip(x, y))

    near = dot(a, e.embed_query("gating flags feature"))
    far = dot(a, e.embed_query("database migration tooling"))
    assert near > far
