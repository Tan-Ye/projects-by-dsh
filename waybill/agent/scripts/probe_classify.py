import asyncio
from llm import AccountOption, LlmClient, classify_account

CANDIDATES: list[AccountOption] = [
    {"code": "6601.01", "name": "差旅费"},
    {"code": "6601.03", "name": "交通费"},
    {"code": "6601.04", "name": "业务招待费"},
    {"code": "6601.05.01", "name": "办公用品"},
]

async def main() -> None:
    client = LlmClient.from_config()
    try:
        for summary in ["客户拜访打车费", "跟客户吃饭顺便打车", "买了两箱 A4 纸"]:
            judgment = await classify_account(client, summary, CANDIDATES)
            print(f"\n{summary}")
            print("  chosen:", judgment["chosen"], f"({judgment['confidence']:.2f})")
            print("  理由  :", judgment["rationale"])
            if judgment["alternatives"]:
                print("  备选  :", judgment["alternatives"])
    finally:
        await client.aclose()
        
if __name__ == "__main__":
    asyncio.run(main())