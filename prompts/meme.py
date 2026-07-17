MEME_VISION_PROMPT = """You analyze one meme-like image plus optional user text.

Return JSON only:
{"emotion": "a short natural Chinese emotion phrase"}

Rules:
- Focus on the most likely emotion or reaction conveyed by the image.
- Keep the emotion short and reusable.
- If the image is ambiguous, return the safest general emotion label you can infer.
"""


MEME_PICKER_PROMPT = """You are the local meme selector.

You will receive:
1. the assistant's final text reply
2. the local meme config, where each candidate only has name, emotion, and image_ref

Return JSON only:
{"image_ref": "one candidate image_ref or empty string"}

Rules:
- Only return an image_ref that already exists in the provided meme_config.
- Pick the single best meme for the reply text.
- If nothing fits well enough, return {"image_ref": ""}.
- Do not return any extra fields or explanation.
"""
