



#______________________________Testing  OpenAI Client Confi_________________________________

# import asyncio
# from app.clients.openai_client import embed_text

# async def test():
#     print("Calling OpenAI embeddings API...")
#     vector = await embed_text("credit card with no foreign transaction fee")
#     print(f"OpenAI OK — vector has {len(vector)} dimensions")
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
#     print(f"Anthropic OK — Claude replied: {answer}")

# asyncio.run(test())


#_____________________________________Pinecone client connects_______________________________________

from app.clients.pinecone_client import get_index

print("Connecting to Pinecone...")
index = get_index()
stats = index.describe_index_stats()
print(f"Pinecone OK — connected to index")
print(f"Dimensions: {stats.dimension}")
print(f"Current vector count: {stats.total_vector_count} (0 is correct — ingestion hasn't run yet)")
