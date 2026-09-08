from devops_assistant.rag.ingest import load_local
from devops_assistant.rag.chunking import chunk_documents


def test_load_local_returns_all_source_types(tmp_path=None):
    docs = load_local("sample_repo_data")
    source_types = {d.source_type for d in docs}
    assert source_types == {"yaml", "pr", "commit", "doc"}


def test_load_local_includes_expected_pr():
    docs = load_local("sample_repo_data")
    pr_47 = [d for d in docs if d.id == "pr:47"]
    assert len(pr_47) == 1
    assert "node:20" in pr_47[0].text


def test_chunking_never_produces_empty_chunks():
    docs = load_local("sample_repo_data")
    chunks = chunk_documents(docs)
    assert len(chunks) >= len(docs)
    assert all(c.text.strip() for c in chunks)


def test_yaml_document_is_not_split_when_small():
    docs = load_local("sample_repo_data")
    yaml_doc = [d for d in docs if d.source_type == "yaml"][0]
    chunks = chunk_documents([yaml_doc])
    # Small fixture YAML should stay intact as a single chunk.
    assert len(chunks) == 1
    assert chunks[0].text == yaml_doc.text
