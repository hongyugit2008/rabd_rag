import logging

from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODE


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting LLM smoke test")
    logger.info("config | base_url=%s | model=%s", LLM_BASE_URL, LLM_MODE)

    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL.rstrip("/"),
    )

    prompt = "请用一句话回复：本地应用程序与大模型连接测试成功。"
    logger.info("sending test prompt, len=%s", len(prompt))

    try:
        response = client.chat.completions.create(
            model=LLM_MODE,
            messages=[
                {"role": "system", "content": "你是一个用于连通性测试的助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        answer = response.choices[0].message.content or ""
        logger.info("LLM response received")
        print("\n===== LLM RESPONSE =====")
        print(answer)
        print("===== END RESPONSE =====\n")
    except Exception as e:
        logger.exception("LLM smoke test failed")
        print(f"测试失败：{e}")


if __name__ == "__main__":
    main()
