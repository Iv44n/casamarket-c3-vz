from dataclasses import dataclass

from openai import OpenAI


@dataclass
class OpenAIProvider:
    client: OpenAI
    model: str
    use_json_response_format: bool = True

    def complete(self, prompt: str) -> str:
        kwargs = {}
        if self.use_json_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.choices[0].message.content or ""


def build_openai_provider(
    api_key: str,
    model: str,
    *,
    base_url: str | None = None,
    use_json_response_format: bool = True,
) -> OpenAIProvider:
    return OpenAIProvider(
        client=OpenAI(api_key=api_key, base_url=base_url),
        model=model,
        use_json_response_format=use_json_response_format,
    )
