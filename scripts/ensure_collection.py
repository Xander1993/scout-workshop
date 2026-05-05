"""Idempotent creation of the scout_workshop Qdrant collection."""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

COLLECTION = "scout_workshop"
VECTOR_SIZE = 3072

INDEXED_FIELDS = {
    "reference_type": PayloadSchemaType.KEYWORD,
    "vertical": PayloadSchemaType.KEYWORD,
    "techniques": PayloadSchemaType.KEYWORD,
    "color_mood": PayloadSchemaType.KEYWORD,
    "typography_style": PayloadSchemaType.KEYWORD,
    "layout_pattern": PayloadSchemaType.KEYWORD,
}


def ensure_collection(client: QdrantClient) -> str:
    """Create the scout_workshop collection if absent; verify dims if present.

    Returns one of: "created", "already_exists_ok".
    Raises ValueError if an existing collection has the wrong vector dim.
    """
    if client.collection_exists(COLLECTION):
        info = client.get_collection(COLLECTION)
        existing_dim = info.config.params.vectors.size
        if existing_dim != VECTOR_SIZE:
            raise ValueError(
                f"Collection '{COLLECTION}' exists with dim={existing_dim}; "
                f"refusing to alter. Expected {VECTOR_SIZE}."
            )
        return "already_exists_ok"

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    for field, schema in INDEXED_FIELDS.items():
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    return "created"


if __name__ == "__main__":
    client = QdrantClient(host="localhost", port=6333)
    print(ensure_collection(client))
