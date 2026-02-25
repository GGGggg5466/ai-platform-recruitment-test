from __future__ import annotations
from typing import Dict, Any
import os
from neo4j import GraphDatabase

class Neo4jStore:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")

    def write_doc_graph(self, doc_id: str, chunks: list[dict]) -> Dict[str, Any]:
        """
        Writes:
          (:Document {id: <doc_id>})
          (:Chunk {id: <chunk_node_id>, doc_id: <doc_id>, chunk_id: <chunk_id>, text: <text>})
          (Document)-[:HAS_CHUNK]->(Chunk)

        Returns references that can be queried by cypher-shell using {id: "..."}.
        """
        chunk_node_ids: list[str] = []

        driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        try:
            with driver.session() as session:
                # Create doc node
                session.run(
                    """
                    MERGE (d:Document {id: $doc_id})
                    SET d.updated_at = timestamp()
                    """,
                    doc_id=doc_id,
                )

                # Create chunk nodes + relationships
                for i, ch in enumerate(chunks):
                    chunk_id = ch.get("chunk_id", f"c{i}")
                    text = ch.get("text", "")
                    chunk_node_id = f"{doc_id}::{chunk_id}"
                    chunk_node_ids.append(chunk_node_id)

                    session.run(
                        """
                        MATCH (d:Document {id: $doc_id})
                        MERGE (c:Chunk {id: $chunk_node_id})
                        SET c.doc_id = $doc_id,
                            c.chunk_id = $chunk_id,
                            c.text = $text,
                            c.updated_at = timestamp()
                        MERGE (d)-[:HAS_CHUNK]->(c)
                        """,
                        doc_id=doc_id,
                        chunk_node_id=chunk_node_id,
                        chunk_id=chunk_id,
                        text=text,
                    )

        finally:
            driver.close()

        return {"doc_node_id": doc_id, "chunk_node_ids": chunk_node_ids}