import asyncio
from llm import LlmClient


async def main() -> None:
    client = LlmClient.from_config()
    try:
        result = await client.chat(
            messages=[{"role": "user", "content": "只回答两个字：可用"}],
            max_tokens=16,
        )
        print(result["content"].strip(), result["usage"])
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())