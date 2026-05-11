



#______________________________Testing  OpenAI Client Confi_________________________________

# import asyncio
# from app.clients.openai_client import embed_text

# async def test():
#     print("Calling OpenAI embeddings API...")
#     vector = await embed_text("credit card with no foreign transaction fee")
#     print(f"OpenAI OK Ã¢â‚¬â€ vector has {len(vector)} dimensions")
#     print(f"First 3 values: {vector[:3]}")

# asyncio.run(test())


#________________________________Testing Anthropic client_____________________________________

# import asyncio
# from app.clients.anthropic_client import generate_answer

# async def test():
#     print("Calling Anthropic Claude API...")
#     answer = await generate_answer(
#         system_prompt="You are a helpful assistant. Reply in exactly 5 words.",
#         user_prompt="Is this API working?",
#         max_tokens=20
#     )
#     print(f"Anthropic OK Ã¢â‚¬â€ Claude replied: {answer}")

# asyncio.run(test())


#_____________________________________Pinecone client connects___________________________________

# from app.clients.pinecone_client import get_index

# print("Connecting to Pinecone...")
# index = get_index()
# stats = index.describe_index_stats()
# print(f"Pinecone OK Ã¢â‚¬â€ connected to index")
# print(f"Dimensions: {stats.dimension}")
# print(f"Current vector count: {stats.total_vector_count} (0 is correct Ã¢â‚¬â€ ingestion hasn't run yet)")  # noqa: E501

#_________________________________________Testing Ingestion.py__________________________________
# import json
# from pathlib import Path

# from app.models import Card
# from app.rag.ingest import card_to_chunks

# data = json.loads(Path("data/cards.json").read_text(encoding="utf-8-sig"))
# first_card = Card.model_validate(data[0])
# chunks = card_to_chunks(first_card)

# print(f"Chunking OK Ã¢â‚¬â€ {first_card.name} produced {len(chunks)} chunks:")
# for chunk in chunks:
#     print(f"  [{chunk['section']}] {chunk['text'][:80]}...")


#__________________________________________Retrieving Data from Pinecone_______________________
# from app.clients.pinecone_client import get_index

# index = get_index()
# stats = index.describe_index_stats()
# count = stats.total_vector_count
# print(f"Pinecone vector count: {count}")
# if count == 25:
#     print("PASS Ã¢â‚¬â€ all 25 chunks are stored in Pinecone")
# else:
#     print(f"FAIL Ã¢â‚¬â€ expected 25, got {count}. Re-run: python -m scripts.ingest")


#__________________________________Pinecone live retrieval__________________________________________
import asyncio

from app.rag.retrieve import retrieve_chunks


async def test():
    print("Querying Pinecone for 'Travel Insurance'...")
    chunks = await retrieve_chunks("Travel Insurance", top_k=3)
    print(f"Retrieved {len(chunks)} chunks:")
    for c in chunks:
        print(
        f"  Score: {c['score']:.3f} | "
        f"{c['metadata']['card_name']} | "
        f"section: {c['metadata']['section']}"
        )

asyncio.run(test())
