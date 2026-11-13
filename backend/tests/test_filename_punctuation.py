import pytest

from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.domain.entities.document import Document
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.metadata_filters import MetadataFilters


@pytest.fixture
def profile():
    return Document(DocumentId("doc_profile"), "Profile.pdf", "pdf", "test")


@pytest.mark.parametrize(
    "ending", [".", "...", "?", "!", ",", ":", ";", ")", '"', "", ".\nNext sentence."]
)
def test_filename_with_sentence_punctuation_selects_the_named_document(profile, ending):
    question = (
        "Explain the event-driven ETL pipeline developed at ASAL Technologies in Profile.pdf"
        + ending
    )
    result = MetadataFilterResolver().resolve(question, [profile])
    assert result.doc_ids == [str(profile.id)]


@pytest.mark.parametrize(
    "name",
    [
        "Missing.pdf.",
        "OtherProfile.pdf.",
        "Profile.pdf.bak",
        "Profile.pdf...backup",
        "Profile.pdf-extra",
    ],
)
def test_similar_or_unknown_filename_never_selects_profile(profile, name):
    result = MetadataFilterResolver().resolve(f"Explain the pipeline in {name}", [profile])
    assert result.doc_ids == []


@pytest.mark.parametrize("selected", [[], ["doc_other"], ["doc_profile"]])
def test_punctuation_fix_does_not_widen_explicit_document_selection(profile, selected):
    result = MetadataFilterResolver().resolve(
        "Describe the ETL pipeline in Profile.pdf.", [profile], MetadataFilters(doc_ids=selected)
    )
    assert result.doc_ids == (["doc_profile"] if "doc_profile" in selected else [])
